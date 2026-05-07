"""
GitHubFetcher — automatic data collection for SAFER analysis.

Fetches all SoftwareRecord fields from public APIs:
  - GitHub REST API v3  (repo metadata, languages, releases, org/user repos)
  - GitHub GraphQL API  (security vulnerabilities — requires token)
  - PyPI JSON API       (downloads, release history, dependencies)
  - pypistats.org       (monthly download counts)
  - npm registry API    (downloads, dependencies, versions — JavaScript/TypeScript)
  - Codecov API         (test coverage)

Usage::

    fetcher = GitHubFetcher(token="ghp_...")
    # Python package
    record, raw = fetcher.fetch("ultralytics/ultralytics")
    # npm package (auto-detected or explicit name)
    record, raw = fetcher.fetch("expressjs/express", pkg_name="express")
"""
from __future__ import annotations

import base64
import calendar
import json as _json
import warnings
from datetime import datetime, timezone
from typing import Any

import requests

from safer_model.schemas.input import DeveloperHistory, PublisherHistory, SoftwareRecord

# ── Constants ─────────────────────────────────────────────────────────────────

_GH_API = "https://api.github.com"
_PYPI_API = "https://pypi.org/pypi"
_PYPISTATS_API = "https://pypistats.org/api/packages"
_NPM_REGISTRY = "https://registry.npmjs.org"
_NPM_DOWNLOADS_API = "https://api.npmjs.org/downloads/point/last-month"
_CODECOV_API = "https://codecov.io/api/gh"
_GH_GRAPHQL = "https://api.github.com/graphql"

_TIMEOUT = 15  # seconds per request
_RELEASES_PER_YEAR_BASELINE = 4.0  # "fully active" = 4 releases/year

_NPM_LANGUAGES = {"javascript", "typescript"}


# ── Main class ────────────────────────────────────────────────────────────────


class GitHubFetcher:
    """
    Collects all data needed by SoftwareRecord from public APIs.

    Parameters
    ----------
    token:
        GitHub Personal Access Token.  Required for the GraphQL vulnerability
        query and greatly increases the REST API rate limit (5 000 vs 60 req/h).
    """

    def __init__(self, token: str | None = None) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/vnd.github+json"})
        if token:
            self._session.headers["Authorization"] = f"token {token}"
        self._token = token

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(
        self,
        repo: str,
        context: float = 0.5,
        pkg_name: str | None = None,
        ref: str | None = None,
    ) -> tuple[SoftwareRecord, dict[str, Any]]:
        """
        Fetch all fields and return a (SoftwareRecord, raw_data) pair.

        Parameters
        ----------
        repo:
            GitHub repository in ``owner/repo`` form.
        context:
            SAFER context value (0.2 = security, 0.3 = automation, 0.5 = other).
        pkg_name:
            Override the package registry name when it differs from the GitHub
            repo name (e.g. repo ``vercel/next.js`` → npm package ``next``).
        ref:
            Git ref (tag name, branch, or commit SHA) to analyse a specific
            historical version.  When omitted the current HEAD is used.

        Returns
        -------
        record:
            Fully-populated SoftwareRecord ready for SAFERScorer.score().
        raw:
            Dictionary of raw API payloads for audit / report generation.
        """
        if repo.count("/") != 1:
            raise ValueError(
                f"repo must be in 'owner/repo' format, got: {repo!r}"
            )
        owner, name = repo.split("/", 1)
        raw: dict[str, Any] = {"repo": repo}

        # ── 0. Resolve historical ref (if requested) ──────────────────────────
        commit_sha: str | None = None
        tree_sha: str | None = None
        ref_date: datetime | None = None
        if ref:
            commit_sha, tree_sha, ref_date = self._resolve_ref(owner, name, ref)
            raw["ref"] = ref
            raw["commit_sha"] = commit_sha
            raw["ref_date"] = ref_date.isoformat()

        # "now" is either the ref commit date (historical) or wall-clock time
        now = ref_date if ref_date else datetime.now(timezone.utc)

        # ── 1. GitHub repo metadata ───────────────────────────────────────────
        gh_repo = self._gh_get(f"/repos/{owner}/{name}")
        raw["github_repo"] = gh_repo

        stars: int = gh_repo.get("stargazers_count", 0)
        forks: int = gh_repo.get("forks_count", 0)
        language: str = gh_repo.get("language") or "Unknown"
        created_at_str: str = gh_repo.get("created_at", "2010-01-01T00:00:00Z")
        created_at = datetime.fromisoformat(created_at_str.rstrip("Z")).replace(
            tzinfo=timezone.utc
        )
        years_total = max((now - created_at).days / 365.25, 0.1)

        # ── 2. Code size (bytes → estimated LOC) ─────────────────────────────
        if tree_sha:
            # Historical: read the git tree at the specific commit
            code_length = self._fetch_tree_size(owner, name, tree_sha)
            raw["code_length_source"] = f"git-tree@{ref}"
        else:
            lang_data = self._gh_get(f"/repos/{owner}/{name}/languages")
            raw["languages"] = lang_data
            total_bytes = sum(lang_data.values()) if lang_data else 0
            code_length = max(int(total_bytes / 50), 1)
            raw["code_length_source"] = "languages-api"

        # ── 3. Update frequency via GitHub releases ───────────────────────────
        releases_raw = self._gh_get(f"/repos/{owner}/{name}/releases?per_page=100")
        all_releases = releases_raw if isinstance(releases_raw, list) else []

        # When analysing a historical ref, only count releases up to ref_date
        if ref_date:
            all_releases = [
                r for r in all_releases
                if self._parse_gh_date(r.get("published_at", "")) <= ref_date
            ]

        release_count = len(all_releases)
        raw["releases_count"] = release_count
        releases_per_year = release_count / max(years_total, 1)
        update_frequency = min(
            max(releases_per_year / _RELEASES_PER_YEAR_BASELINE, 0.001), 1.0
        )

        # Fall back to push-date heuristic when no releases exist
        if update_frequency <= 0.001:
            pushed_at_str = gh_repo.get("pushed_at", created_at_str)
            pushed_at = datetime.fromisoformat(pushed_at_str.rstrip("Z")).replace(
                tzinfo=timezone.utc
            )
            ref_point = ref_date if ref_date else datetime.now(timezone.utc)
            days_since_push = (ref_point - pushed_at).days
            update_frequency = 0.5 if days_since_push <= 90 else 0.1

        # ── 4. Registry data (downloads, dependencies, update_frequency) ────────
        is_npm = language.lower() in _NPM_LANGUAGES
        resolved_pkg_name = pkg_name or (
            name if is_npm else name.replace("-", "_").lower()
        )

        if is_npm:
            npm_result = self._fetch_npm(
                resolved_pkg_name, stars, years_total, ref_date=ref_date
            )
            downloads = npm_result["downloads"]
            dependencies = npm_result["dependencies"]
            # npm version history is more accurate than GitHub releases for JS packages
            if npm_result["versions"] > 0:
                releases_per_year = npm_result["versions"] / max(years_total, 1)
                update_frequency = min(
                    max(releases_per_year / _RELEASES_PER_YEAR_BASELINE, 0.001), 1.0
                )
            raw["npm_pkg_name"] = resolved_pkg_name
            raw["npm_data"] = npm_result

            # For historical refs, prefer package.json at that exact commit
            if ref:
                hist_deps = self._fetch_deps_at_ref(owner, name, ref, language)
                if hist_deps is not None:
                    dependencies = hist_deps
                    raw["dependencies_source"] = f"package.json@{ref}"
        else:
            pypi_pkg_name = resolved_pkg_name
            downloads, dependencies = self._fetch_pypi(pypi_pkg_name, language, stars)
            raw["pypi_pkg_name"] = pypi_pkg_name

            if ref:
                hist_deps = self._fetch_deps_at_ref(owner, name, ref, language)
                if hist_deps is not None:
                    dependencies = hist_deps
                    raw["dependencies_source"] = f"requirements.txt@{ref}"

        raw["pkg_name"] = resolved_pkg_name
        raw["registry"] = (
            "npm" if is_npm else ("pypi" if language.lower() == "python" else "github")
        )

        # ── 5. Code coverage via Codecov ──────────────────────────────────────
        code_coverage = self._fetch_codecov(owner, name)
        raw["code_coverage_source"] = "codecov" if code_coverage > 0.0 else "default"

        # ── 6. Vulnerability data (GraphQL) ───────────────────────────────────
        vuln_pkg = resolved_pkg_name
        known_vulns, unresolved_vulns = self._fetch_vulns(language, vuln_pkg)
        raw["known_vulnerabilities"] = known_vulns
        raw["unresolved_vulnerabilities"] = unresolved_vulns

        # ── 7. Developer / publisher history (org or user repos) ─────────────
        dev_hist, pub_hist = self._fetch_actor_history(
            owner, language, known_vulns, years_total
        )
        raw["actor_owner"] = owner

        # ── 8. Assemble SoftwareRecord ────────────────────────────────────────
        record = SoftwareRecord(
            software_id=f"{repo}@{ref}" if ref else repo,
            code_length=code_length,
            language=language,
            dependencies=dependencies,
            code_coverage=code_coverage,
            known_vulnerabilities=known_vulns,
            unresolved_vulnerabilities=unresolved_vulns,
            update_frequency=update_frequency,
            forks=forks,
            downloads=downloads,
            rating=float(stars),
            context=context,
            developer_histories=[dev_hist],
            publisher_histories=[pub_hist],
        )

        # Enrich raw with computed values for report generation
        raw.update(
            {
                "stars": stars,
                "forks": forks,
                "language": language,
                "code_length_est": code_length,
                "code_coverage": code_coverage,
                "update_frequency": update_frequency,
                "downloads": downloads,
                "dependencies": dependencies,
                "years_active": round(years_total, 1),
                "release_count": release_count,
            }
        )

        return record, raw

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _gh_get(self, path: str) -> Any:
        """GET from GitHub REST API; returns parsed JSON or empty fallback."""
        url = f"{_GH_API}{path}"
        try:
            resp = self._session.get(url, timeout=_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                warnings.warn(f"GitHub 404: {url}", stacklevel=3)
                return {}
            warnings.warn(
                f"GitHub API returned {resp.status_code} for {url}", stacklevel=3
            )
        except requests.RequestException as exc:
            warnings.warn(f"GitHub API request failed ({url}): {exc}", stacklevel=3)
        return {}

    def _fetch_pypi(
        self, pkg_name: str, language: str, stars: int
    ) -> tuple[int, int]:
        """
        Return (monthly_downloads, dependency_count).

        Falls back to (stars * 1000, 5) for non-Python packages or on error.
        """
        if language.lower() != "python":
            return stars * 1000, 5

        downloads = stars * 1000  # fallback
        dependencies = 5  # fallback

        # Monthly downloads from pypistats
        try:
            resp = requests.get(
                f"{_PYPISTATS_API}/{pkg_name}/recent",
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                downloads = resp.json().get("data", {}).get("last_month", downloads)
        except requests.RequestException as exc:
            warnings.warn(f"pypistats request failed: {exc}", stacklevel=3)

        # Dependency count from PyPI JSON
        try:
            resp = requests.get(f"{_PYPI_API}/{pkg_name}/json", timeout=_TIMEOUT)
            if resp.status_code == 200:
                info = resp.json().get("info", {})
                requires = info.get("requires_dist") or []
                dependencies = len(
                    [r for r in requires if "extra ==" not in r]
                )
        except requests.RequestException as exc:
            warnings.warn(f"PyPI request failed: {exc}", stacklevel=3)

        return int(downloads), int(dependencies)

    def _fetch_npm(
        self,
        pkg_name: str,
        stars: int,
        years_total: float,
        ref_date: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Fetch npm registry data for a package.

        Returns a dict with keys: downloads, dependencies, versions.
        When ref_date is provided, downloads reflect the calendar month of that
        date and only versions published before that date are counted.
        Falls back gracefully on any error.
        """
        result: dict[str, Any] = {
            "downloads": stars * 1000,
            "dependencies": 5,
            "versions": 0,
        }

        # Monthly downloads
        if ref_date:
            result["downloads"] = self._fetch_npm_downloads_for_month(
                pkg_name, ref_date, fallback=stars * 1000
            )
        else:
            try:
                resp = requests.get(
                    f"{_NPM_DOWNLOADS_API}/{pkg_name}",
                    timeout=_TIMEOUT,
                )
                if resp.status_code == 200:
                    result["downloads"] = int(
                        resp.json().get("downloads", result["downloads"])
                    )
            except requests.RequestException as exc:
                warnings.warn(
                    f"npm downloads request failed for {pkg_name}: {exc}", stacklevel=3
                )

        # Package metadata: dependencies and version count
        try:
            resp = requests.get(
                f"{_NPM_REGISTRY}/{pkg_name}",
                timeout=_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                time_data = data.get("time", {})

                # Count versions published up to ref_date (or all if no ref)
                if ref_date:
                    ref_iso = ref_date.isoformat()
                    versions = sum(
                        1
                        for k, v in time_data.items()
                        if k not in ("created", "modified") and v <= ref_iso
                    )
                else:
                    versions = len(
                        [k for k in time_data if k not in ("created", "modified")]
                    )
                result["versions"] = versions

                # Dependencies: from the latest version tag (overridden later by
                # _fetch_deps_at_ref when a git ref is available)
                dist_tags = data.get("dist-tags", {})
                latest_ver = dist_tags.get("latest", "")
                latest_meta = data.get("versions", {}).get(latest_ver, {})
                deps = latest_meta.get("dependencies", {})
                peer_deps = latest_meta.get("peerDependencies", {})
                result["dependencies"] = len(deps) + len(peer_deps)

                result["latest_version"] = latest_ver
                result["description"] = data.get("description", "")
            elif resp.status_code == 404:
                warnings.warn(
                    f"npm package '{pkg_name}' not found. "
                    "Use --pkg-name to specify the correct npm package name.",
                    stacklevel=3,
                )
        except requests.RequestException as exc:
            warnings.warn(
                f"npm registry request failed for {pkg_name}: {exc}", stacklevel=3
            )

        return result

    def _fetch_codecov(self, owner: str, name: str) -> float:
        """Return code coverage ∈ [0, 1] from Codecov, or 0.0 on failure."""
        try:
            resp = requests.get(
                f"{_CODECOV_API}/{owner}/{name}",
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                cov = (
                    data.get("repo", {}).get("stats", {}).get("coverage")
                    or data.get("commit", {}).get("totals", {}).get("c")
                )
                if cov is not None:
                    return min(float(cov) / 100.0, 1.0)
        except requests.RequestException:
            pass
        return 0.0

    def _fetch_vulns(self, language: str, pkg_name: str) -> tuple[int, int]:
        """
        Return (known_vulnerabilities, unresolved_vulnerabilities) via GitHub
        GraphQL.  Requires a token; returns (0, 0) if no token is set or on
        any error.
        """
        if not self._token:
            warnings.warn(
                "No GitHub token provided — vulnerability data will be 0. "
                "Pass --token to enable.",
                stacklevel=3,
            )
            return 0, 0

        ecosystem_map = {
            "python": "PIP",
            "javascript": "NPM",
            "typescript": "NPM",
            "ruby": "RUBYGEMS",
            "java": "MAVEN",
            "go": "GO",
            "rust": "CRATES_IO",
            "php": "COMPOSER",
            "c#": "NUGET",
        }
        ecosystem = ecosystem_map.get(language.lower(), "PIP")

        query = """
        query($pkg: String!, $eco: SecurityAdvisoryEcosystem!) {
          securityVulnerabilities(ecosystem: $eco, package: $pkg, first: 100) {
            totalCount
            nodes { severity advisory { withdrawnAt } }
          }
        }
        """
        try:
            resp = self._session.post(
                _GH_GRAPHQL,
                json={"query": query, "variables": {"pkg": pkg_name, "eco": ecosystem}},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                vulns = data.get("securityVulnerabilities", {})
                total = vulns.get("totalCount", 0)
                nodes = vulns.get("nodes", [])
                unresolved = sum(
                    1 for v in nodes if v.get("advisory", {}).get("withdrawnAt") is None
                )
                return total, min(unresolved, total)
        except requests.RequestException as exc:
            warnings.warn(f"GraphQL vulnerability query failed: {exc}", stacklevel=3)

        return 0, 0

    def _fetch_actor_history(
        self,
        owner: str,
        language: str,
        known_vulns: int,
        years_total: float,
    ) -> tuple[DeveloperHistory, PublisherHistory]:
        """
        Build DeveloperHistory and PublisherHistory from owner's public repos.
        Tries /orgs/{owner}/repos first, falls back to /users/{owner}/repos.
        """
        repos: list[dict] = []
        for endpoint in (f"/orgs/{owner}/repos", f"/users/{owner}/repos"):
            data = self._gh_get(f"{endpoint}?per_page=100&type=public")
            if isinstance(data, list) and data:
                repos = data
                break

        total_sw = max(len(repos), 1)
        same_lang = sum(
            1 for r in repos if (r.get("language") or "").lower() == language.lower()
        )
        same_lang = max(same_lang, 1)

        # Infer years from earliest repo
        dates = []
        for r in repos:
            raw_date = r.get("created_at")
            if raw_date:
                try:
                    dates.append(
                        datetime.fromisoformat(raw_date.rstrip("Z")).replace(
                            tzinfo=timezone.utc
                        )
                    )
                except ValueError:
                    pass
        if dates:
            earliest = min(dates)
            years_total = max(
                (datetime.now(timezone.utc) - earliest).days / 365.25, 0.1
            )

        dev_hist = DeveloperHistory(
            developer_id=owner,
            total_vulnerabilities=known_vulns,
            total_software_count=total_sw,
            software_same_lang_count=same_lang,
            years_same_lang=round(years_total, 2),
            years_total=round(years_total, 2),
        )
        pub_hist = PublisherHistory(
            publisher_id=owner,
            software_published_count=total_sw,
            years_publishing=round(years_total, 2),
        )
        return dev_hist, pub_hist

    # ── Historical-ref helpers ────────────────────────────────────────────────

    def _resolve_ref(
        self, owner: str, name: str, ref: str
    ) -> tuple[str, str, datetime]:
        """
        Resolve a git ref (tag, branch, or SHA) to (commit_sha, tree_sha, commit_date).

        Uses ``GET /repos/{owner}/{name}/commits/{ref}`` which accepts tags,
        branches, and full/abbreviated SHAs.
        """
        data = self._gh_get(f"/repos/{owner}/{name}/commits/{ref}")
        if not isinstance(data, dict) or "sha" not in data:
            raise ValueError(
                f"Cannot resolve ref '{ref}' for {owner}/{name}. "
                "Check that the tag / branch / SHA exists."
            )
        commit_sha: str = data["sha"]
        tree_sha: str = data.get("commit", {}).get("tree", {}).get("sha", "")
        commit_info = data.get("commit", {})
        date_str: str = (
            commit_info.get("committer", {}).get("date")
            or commit_info.get("author", {}).get("date", "")
        )
        if not date_str:
            raise ValueError(f"Cannot get commit date for ref '{ref}'")
        commit_date = datetime.fromisoformat(date_str.rstrip("Z")).replace(
            tzinfo=timezone.utc
        )
        return commit_sha, tree_sha, commit_date

    def _fetch_tree_size(self, owner: str, name: str, tree_sha: str) -> int:
        """
        Return estimated LOC from the git tree at tree_sha.

        Fetches the recursive tree, sums all blob sizes in bytes, then divides
        by 50 (same heuristic as the Languages API path).
        If the tree is truncated (> 100 000 entries), the estimate is partial.
        """
        data = self._gh_get(
            f"/repos/{owner}/{name}/git/trees/{tree_sha}?recursive=1"
        )
        if not isinstance(data, dict) or "tree" not in data:
            return 1
        if data.get("truncated"):
            warnings.warn(
                f"Git tree for {owner}/{name}@{tree_sha} is truncated; "
                "code-length estimate is partial.",
                stacklevel=3,
            )
        total_bytes = sum(
            item.get("size", 0)
            for item in data["tree"]
            if item.get("type") == "blob"
        )
        return max(int(total_bytes / 50), 1)

    def _fetch_deps_at_ref(
        self, owner: str, name: str, ref: str, language: str
    ) -> int | None:
        """
        Read the dependency count from the manifest file at a specific git ref.

        Tries ``package.json`` for JS/TS packages and ``requirements.txt`` for
        Python packages.  Returns ``None`` if the manifest cannot be found or
        parsed (caller should fall back to the registry-derived count).
        """
        if language.lower() in _NPM_LANGUAGES:
            data = self._gh_get(
                f"/repos/{owner}/{name}/contents/package.json?ref={ref}"
            )
            if isinstance(data, dict) and "content" in data:
                try:
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    pkg = _json.loads(content)
                    return len(pkg.get("dependencies", {})) + len(
                        pkg.get("peerDependencies", {})
                    )
                except Exception as exc:
                    warnings.warn(
                        f"Could not parse package.json@{ref}: {exc}", stacklevel=3
                    )

        elif language.lower() == "python":
            data = self._gh_get(
                f"/repos/{owner}/{name}/contents/requirements.txt?ref={ref}"
            )
            if isinstance(data, dict) and "content" in data:
                try:
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    lines = [
                        ln.strip()
                        for ln in content.splitlines()
                        if ln.strip() and not ln.startswith("#")
                    ]
                    return len(lines)
                except Exception as exc:
                    warnings.warn(
                        f"Could not parse requirements.txt@{ref}: {exc}", stacklevel=3
                    )

        return None

    def _fetch_npm_downloads_for_month(
        self, pkg_name: str, ref_date: datetime, fallback: int
    ) -> int:
        """
        Return npm download count for the calendar month containing ref_date.

        Uses the npm downloads API date-range endpoint:
        ``https://api.npmjs.org/downloads/point/{YYYY-MM-DD}:{YYYY-MM-DD}/{pkg}``
        """
        y, m = ref_date.year, ref_date.month
        last_day = calendar.monthrange(y, m)[1]
        start = f"{y}-{m:02d}-01"
        end = f"{y}-{m:02d}-{last_day:02d}"
        try:
            resp = requests.get(
                f"https://api.npmjs.org/downloads/point/{start}:{end}/{pkg_name}",
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return int(resp.json().get("downloads", fallback))
        except requests.RequestException as exc:
            warnings.warn(
                f"npm historical downloads failed for {pkg_name}: {exc}", stacklevel=3
            )
        return fallback

    @staticmethod
    def _parse_gh_date(date_str: str) -> datetime:
        """Parse a GitHub ISO-8601 date string into a timezone-aware datetime."""
        if not date_str:
            return datetime.min.replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(date_str.rstrip("Z")).replace(
            tzinfo=timezone.utc
        )
