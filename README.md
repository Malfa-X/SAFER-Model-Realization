# SAFER — Software Analysis Framework for Evaluating Risk

A Python implementation of the **SAFER** risk-scoring model from
[arXiv:2408.02876v2](https://arxiv.org/abs/2408.02876)
("Elevating Software Trust: A Holistic Approach to Open-Source Risk Assessment").

SAFER quantifies the trustworthiness of a software package by combining
developer reputation, publisher reliability, user sentiment, vulnerability
exposure, and deployment context into a single score **R_FP ∈ [0, 1]**
mapped to a **Low / Moderate / High / Critical** risk band.

---

## Table of Contents

1. [How this implements the paper](#how-this-implements-the-paper)
2. [Installation](#installation)
3. [Quick start](#quick-start)
4. [Analysing a GitHub package — step by step](#analysing-a-github-package--step-by-step)
   - [Step 1: Collect data from GitHub and package registries](#step-1-collect-data-from-github-and-package-registries)
   - [Step 2: Build a SoftwareRecord](#step-2-build-a-softwarerecord)
   - [Step 3: Score and interpret](#step-3-score-and-interpret)
5. [CLI workflow](#cli-workflow)
   - [Automated analysis (safer analyze)](#automated-analysis-safer-analyze)
   - [Score a single package](#score-a-single-package)
   - [Batch-score a CSV file](#batch-score-a-csv-file)
   - [Generate a synthetic dataset](#generate-a-synthetic-dataset)
6. [REST API](#rest-api)
7. [Batch analysis — comparing multiple packages](#batch-analysis--comparing-multiple-packages)
8. [Result fields reference](#result-fields-reference)
9. [Interpreting results](#interpreting-results)
10. [Configuration and tuning](#configuration-and-tuning)
11. [Field mapping reference](#field-mapping-reference)
12. [Project structure](#project-structure)

---

## How this implements the paper

The paper (arXiv:2408.02876v2, Section V) defines 19 equations grouped into
three actor-based risk segments, a penalty factor, and a final score.
Each equation is implemented as a pure Python function in its own module
under `safer_model/formulas/`:

| Paper content | Equations | Source file |
|---|---|---|
| Developer-based risk (R_CD, R_CS, R_PL, weights) | Eq. 1–9 | `safer_model/formulas/developer.py` |
| Publisher-based risk (R_PB) | Eq. 10 | `safer_model/formulas/publisher.py` |
| User-indicated risk (R_UR) | Eq. 11 | `safer_model/formulas/user.py` |
| Penalty factor (P, context C_TXT) | Eq. 12–14 | `safer_model/formulas/penalty.py` |
| Actor weights + final score (R_F, R_FP) | Eq. 15–19 | `safer_model/formulas/final_score.py` |
| Risk band thresholds | Section V-G | `safer_model/bands.py` |
| Tunable parameters | Section VI | `safer_model/config.py` |

The paper's Table IX (Appendix) is reproduced verbatim as an integration test in
`tests/integration/test_worked_example.py`, which asserts every intermediate
value against the paper's published numbers (tolerance ±0.1 %).

### Computation pipeline

```
SoftwareRecord
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  SAFERScorer  (scorer.py)                                       │
│                                                                 │
│  Step 1  Resolve actor histories (registry or inline)           │
│  Step 2  Aggregate cross-dataset Σ sums                         │
│  Step 3  Eq. 1–4   R_CD, R_CS, R_PL                           │
│  Step 4  Eq. 6–9   w_CD, w_CS, w_PL                           │
│  Step 5  Eq. 5     R_DEV (weighted sum)                         │
│  Step 6  Eq. 10    R_PB                                         │
│  Step 7  Eq. 11    R_UR                                         │
│  Step 8  Eq. 12–14 Penalty P                                    │
│  Step 9  Eq. 15–19 w_DEV, w_PB, w_UR → R_F → R_FP             │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
SAFERResult  →  band classification (bands.py)
```

### Two operating modes

**Dataset mode** — pass all records at construction time. Registries are built
automatically; cross-package Σ statistics (`w_lc`, `e_db`, `r_pl`, `r_pb`) are
derived from the whole dataset, exactly as described in the paper's evaluation.

```python
scorer = SAFERScorer(records=records)   # builds DeveloperRegistry + PublisherRegistry
results = scorer.score_all()
```

**Standalone mode** — each `SoftwareRecord` carries pre-populated
`DeveloperHistory` / `PublisherHistory` objects. No registry is built; suitable
for single-package scoring, API calls, and the `safer analyze` command.

```python
scorer = SAFERScorer()                  # no registry
result = scorer.score(record)
```

---

## Installation

```bash
# Clone and install in editable mode (recommended for development)
git clone https://github.com/your-org/safer-model-realization.git
cd "safer-model-realization"
pip install -e .

# Verify
safer --version
```

**Requirements:** Python ≥ 3.11, pip ≥ 21.

Optional dependencies for the REST API:
```bash
pip install -e ".[dev]"   # adds pytest, httpx (for API testing)
```

---

## Quick start

```python
from safer_model.schemas.input import SoftwareRecord, DeveloperHistory, PublisherHistory
from safer_model.scorer import SAFERScorer

record = SoftwareRecord(
    software_id="psf/requests",
    code_length=4200,          # lines of code (cloc / tokei)
    language="Python",
    dependencies=5,            # entries in requirements.txt / setup.py
    code_coverage=0.85,        # Codecov badge value (0–1)
    known_vulnerabilities=8,   # GitHub Security Advisories
    unresolved_vulnerabilities=1,
    update_frequency=0.9,      # normalised release cadence (see below)
    forks=9400,
    downloads=30_000_000,      # PyPI monthly downloads
    rating=51_000,             # GitHub stars
    context=0.5,               # 0.2=security, 0.3=automation, 0.5=general
    developer_histories=[
        DeveloperHistory(
            developer_id="psf",
            total_vulnerabilities=8,
            total_software_count=12,
            software_same_lang_count=10,
            years_same_lang=14.0,
            years_total=14.0,
        )
    ],
    publisher_histories=[
        PublisherHistory(
            publisher_id="psf",
            software_published_count=12,
            years_publishing=14.0,
        )
    ],
)

scorer = SAFERScorer()
result = scorer.score(record)

print(f"R_FP = {result.r_fp:.4f}  →  {result.band.value}")
# R_FP = 0.1234  →  Low
```

---

## Analysing a GitHub package — step by step

The sections below walk through a concrete example: scoring the
**`psf/requests`** Python library.  
Every data point maps directly to a field in `SoftwareRecord`.

---

### Step 1: Collect data from GitHub and package registries

#### 1a. Repository metadata (GitHub REST API v3)

```bash
# Install the GitHub CLI or use curl with a personal access token
gh api repos/psf/requests
```

Key fields returned:

| JSON key | SAFER field | Notes |
|---|---|---|
| `stargazers_count` | `rating` | GitHub stars act as a user satisfaction signal |
| `forks_count` | `forks` | Community forks proxy developer trust weight |
| `language` | `language` | Primary language |
| `pushed_at` vs `created_at` | used to derive `update_frequency` | see 1c |

```python
import requests as http_lib   # rename to avoid conflict with package under test

resp = http_lib.get(
    "https://api.github.com/repos/psf/requests",
    headers={"Authorization": "token YOUR_PAT"},
)
repo = resp.json()

stars = repo["stargazers_count"]    # → rating
forks = repo["forks_count"]         # → forks
language = repo["language"]         # → language
```

#### 1b. Download count (PyPI / npm)

**PyPI (Python packages):**
```python
resp = http_lib.get("https://pypistats.org/api/packages/requests/recent")
downloads = resp.json()["data"]["last_month"]   # → downloads
```

**npm (JavaScript packages):**
```python
pkg = "lodash"
resp = http_lib.get(f"https://api.npmjs.org/downloads/point/last-month/{pkg}")
downloads = resp.json()["downloads"]            # → downloads
```

**No download API:** use GitHub clone count from the Traffic API
(`GET /repos/{owner}/{repo}/traffic/clones`, requires push access) or
substitute `stargazers_count` as a lower-bound proxy.

#### 1c. Update frequency

`update_frequency` ∈ (0, 1] represents how actively the package is maintained.
Compute it as the ratio of *actual release cycles* to *elapsed calendar cycles*,
capped at 1:

```python
from datetime import datetime, timezone

# Option A — using PyPI release history
resp = http_lib.get("https://pypi.org/pypi/requests/json")
releases = resp.json()["releases"]
release_count = len([v for v, files in releases.items() if files])

created_year = 2011   # requests first release
years_active = datetime.now(timezone.utc).year - created_year
releases_per_year = release_count / max(years_active, 1)

# Normalise: assume ~4 releases/year = "fully active" (adjust to your baseline)
update_frequency = min(releases_per_year / 4.0, 1.0)
```

#### 1d. Lines of code

Run **cloc** or **tokei** locally after cloning:
```bash
git clone --depth 1 https://github.com/psf/requests.git /tmp/requests
cloc /tmp/requests/requests --json | python -c \
  "import json,sys; d=json.load(sys.stdin); print(d['SUM']['code'])"
```

Or read from a badge / CI report if the repository publishes one.

#### 1e. Dependencies

```python
# PyPI: count install_requires entries
resp = http_lib.get("https://pypi.org/pypi/requests/json")
requires = resp.json()["info"].get("requires_dist") or []
dependencies = len([r for r in requires if "extra ==" not in r])
```

For npm:
```python
resp = http_lib.get("https://registry.npmjs.org/lodash/latest")
pkg_json = resp.json()
dependencies = len(pkg_json.get("dependencies", {}))
```

#### 1f. Vulnerability data (GitHub Security Advisories)

```bash
# GraphQL query for security advisories on the package
gh api graphql -f query='
  query {
    securityVulnerabilities(ecosystem: PIP, package: "requests", first: 100) {
      totalCount
      nodes { severity advisory { withdrawnAt } }
    }
  }
'
```

```python
resp = http_lib.post(
    "https://api.github.com/graphql",
    json={"query": """
        query($pkg: String!) {
          securityVulnerabilities(ecosystem: PIP, package: $pkg, first: 100) {
            totalCount
            nodes { severity advisory { withdrawnAt } }
          }
        }
    """, "variables": {"pkg": "requests"}},
    headers={"Authorization": "bearer YOUR_PAT"},
)
vulns = resp.json()["data"]["securityVulnerabilities"]

known_vulnerabilities = vulns["totalCount"]
# Unresolved = advisories not withdrawn (no fix released yet)
unresolved_vulnerabilities = sum(
    1 for v in vulns["nodes"] if v["advisory"]["withdrawnAt"] is None
)
```

Alternatively, Dependabot alerts for your own fork:
```bash
gh api repos/YOUR_ORG/YOUR_FORK/dependabot/alerts --paginate \
  | python -c "
import json, sys
alerts = json.load(sys.stdin)
known = len(alerts)
unresolved = sum(1 for a in alerts if a['state'] == 'open')
print(known, unresolved)
"
```

#### 1g. Code coverage

Check the repository's README badge or CI config for a Codecov / Coveralls value.
Most Python projects publish it at `https://codecov.io/gh/{owner}/{repo}`:

```python
resp = http_lib.get("https://codecov.io/api/gh/psf/requests")
coverage = resp.json()["repo"]["stats"]["coverage"] / 100.0   # → code_coverage
```

If no coverage data is available, use `0.0` (conservative assumption).

#### 1h. Developer history

`DeveloperHistory` captures the maintainer's track record **across all their
packages**, not just this one.  The cross-package aggregation is what gives
the SAFER model its cross-dataset signal.

```python
# List all repos by the publisher org
resp = http_lib.get(
    "https://api.github.com/orgs/psf/repos?per_page=100&type=public",
    headers={"Authorization": "token YOUR_PAT"},
)
repos = resp.json()

total_software_count = len(repos)
# Count repos in the same language
software_same_lang_count = sum(1 for r in repos if r.get("language") == "Python")

# Sum up advisory counts across all repos (simplified: use known_vulns from above × ratio)
# For a production pipeline, repeat step 1f for each repo.
total_vulnerabilities = known_vulnerabilities   # lower-bound: at least the target package

# Years of experience: date of earliest repo
from datetime import datetime, timezone
dates = [datetime.fromisoformat(r["created_at"].rstrip("Z")) for r in repos]
earliest = min(dates)
years_total = (datetime.now(timezone.utc).replace(tzinfo=None) - earliest).days / 365.25
years_same_lang = years_total   # conservative: assume all experience is in primary language
```

#### 1i. Publisher history

```python
publisher_history = PublisherHistory(
    publisher_id="psf",
    software_published_count=total_software_count,
    years_publishing=years_total,
)
```

#### 1j. Choose context

| Deployment scenario | `context` value |
|---|---|
| Security tooling, auth libraries, cryptography | `0.2` (most stringent) |
| CI/CD automation, build tools | `0.3` |
| General utilities, data processing | `0.5` |

Use `0.2` when in doubt — the framework defaults to the strictest assessment.

---

### Step 2: Build a SoftwareRecord

```python
from safer_model.schemas.input import SoftwareRecord, DeveloperHistory, PublisherHistory

record = SoftwareRecord(
    software_id="psf/requests",
    # Code
    code_length=4200,
    language="Python",
    dependencies=5,
    code_coverage=0.85,
    # Vulnerabilities
    known_vulnerabilities=8,
    unresolved_vulnerabilities=1,
    # Publisher / release
    update_frequency=0.75,
    forks=9400,
    downloads=30_000_000,
    rating=51_000,
    # Context
    context=0.5,
    # Actor histories (populated from steps 1h–1i)
    developer_histories=[
        DeveloperHistory(
            developer_id="psf",
            total_vulnerabilities=8,
            total_software_count=42,
            software_same_lang_count=38,
            years_same_lang=14.0,
            years_total=14.0,
        )
    ],
    publisher_histories=[
        PublisherHistory(
            publisher_id="psf",
            software_published_count=42,
            years_publishing=14.0,
        )
    ],
)
```

---

### Step 3: Score and interpret

```python
from safer_model.scorer import SAFERScorer

scorer = SAFERScorer()            # standalone mode — uses inline histories
result = scorer.score(record)

print(f"Risk band : {result.band.value}")
print(f"R_FP      : {result.r_fp:.4f}")
print()
print("── Intermediate scores ──────────────────")
print(f"  R_CD  (dependency risk)   : {result.r_cd:.2f}")
print(f"  R_CS  (code spec risk)    : {result.r_cs:.2f}")
print(f"  R_PL  (lang risk)         : {result.r_pl:.4f}")
print(f"  R_DEV (developer risk)    : {result.r_dev:.2f}")
print(f"  R_PB  (publisher risk)    : {result.r_pb:.4f}")
print(f"  R_UR  (user risk)         : {result.r_ur:.4f}")
print(f"  Penalty                   : {result.penalty:.4f}")
print(f"  R_F   (pre-penalty score) : {result.r_f:.4f}")
```

Sample output for `psf/requests`:
```
Risk band : Low
R_FP      : 0.0731

── Intermediate scores ──────────────────
  R_CD  (dependency risk)   : 5.00
  R_CS  (code spec risk)    : 1.52
  R_PL  (lang risk)         : 0.0000
  R_DEV (developer risk)    : 1.43
  R_PB  (publisher risk)    : 0.0356
  R_UR  (user risk)         : 0.9983
  Penalty                   : 0.0119
  R_F   (pre-penalty score) : 0.0731
```

---

## CLI workflow

### Automated analysis (`safer analyze`)

The flagship command — fetches all required data fields from GitHub, PyPI, and
npm APIs automatically, scores the package, and writes the report.
No manual data collection needed.

```bash
safer analyze REPO [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `REPO` | *(required)* | Repository in `owner/repo` format, e.g. `psf/requests` |
| `-t / --token` | `$GITHUB_TOKEN` | GitHub PAT for vulnerability and developer-history queries |
| `-c / --context` | `0.5` | Deployment context: `0.2` = security · `0.3` = automation · `0.5` = general |
| `-p / --pkg-name` | *(auto)* | Registry package name when it differs from the repo name (e.g. `next` for `vercel/next.js`) |
| `-o / --output` | `.` | Directory to write output files |
| `-f / --format` | `json` | Output format: `json` `md` `csv` — repeat the flag for multiple formats |
| `-r / --ref` | *(HEAD)* | Git tag, branch, or commit SHA to analyse a historical version |
| `--pretty / --no-pretty` | pretty | Pretty-print JSON output |

**Examples:**

```bash
# Minimal: score current HEAD, write JSON to current directory
safer analyze psf/requests --token $GITHUB_TOKEN

# Security library — strictest context, JSON + Markdown report
safer analyze hashicorp/vault --token $GITHUB_TOKEN \
  --context 0.2 --format json --format md

# Score a specific historical version tag
safer analyze pallets/flask --ref 3.0.0 \
  --format json --format md --output ./reports

# npm package whose registry name differs from the GitHub repo name
safer analyze vercel/next.js --pkg-name next --token $GITHUB_TOKEN

# Write all three output formats to a custom directory
safer analyze ultralytics/ultralytics --token $GITHUB_TOKEN \
  --format json --format md --format csv --output ./reports

# Without a token — skips GitHub Advisory and org-history queries
safer analyze chalk/chalk --format json
```

Output file naming:
- Current HEAD: `{owner}_{repo}_safer_result.json` / `_safer_report.md` / `_safer_result.csv`
- With `--ref v1.2.3`: `{owner}_{repo}_v1.2.3_safer_result.json` (etc.)

---

### Score a single package

Build a JSON payload from the collected data and pipe it to `safer score-one`:

```bash
# --pretty / --no-pretty controls JSON indentation (default: pretty)
safer score-one --json '{
  "software_id": "psf/requests",
  "code_length": 4200,
  "language": "Python",
  "dependencies": 5,
  "code_coverage": 0.85,
  "known_vulnerabilities": 8,
  "unresolved_vulnerabilities": 1,
  "update_frequency": 0.75,
  "forks": 9400,
  "downloads": 30000000,
  "rating": 51000,
  "context": 0.5,
  "developer_histories": [{
    "developer_id": "psf",
    "total_vulnerabilities": 8,
    "total_software_count": 42,
    "software_same_lang_count": 38,
    "years_same_lang": 14.0,
    "years_total": 14.0
  }],
  "publisher_histories": [{
    "publisher_id": "psf",
    "software_published_count": 42,
    "years_publishing": 14.0
  }]
}'
```

Output (pretty-printed JSON):
```json
{
  "software_id": "psf/requests",
  "r_fp": 0.0731,
  "band": "Low",
  "r_cd": 5.0,
  "r_cs": 1.52,
  ...
}
```

### Batch-score a CSV file

Prepare a CSV file where each row is one package (Table III format from the paper),
then:

```bash
safer score --input packages.csv --output results.csv

# All options:
#   -i / --input TEXT          Input CSV file (required)
#   -o / --output TEXT         Output file path (default: <input>_results.csv)
#   -f / --format [csv|json]   Output format (default: csv)
#   --dep-sensitivity FLOAT    Dependency risk multiplier, Section VI-A (default: 1.0)

# Print a quick band summary from results
safer report --input results.csv
```

CSV column names must match exactly:

```
software_id,code_length,language,dependencies,code_coverage,
known_vulnerabilities,unresolved_vulnerabilities,update_frequency,
forks,downloads,rating,context,developer,publisher,year
```

`developer` and `publisher` are string IDs; the scorer builds registries
automatically to compute cross-package aggregates.

### Generate a synthetic dataset

```bash
# 500 records, custom seed
safer generate --samples 500 --seed 7 --output data/test.csv

# Score it immediately
safer score --input data/test.csv
```

---

## REST API

Start the server:

```bash
uvicorn safer_api.app:create_app --factory --reload --port 8000
```

Interactive docs: `http://localhost:8000/docs`

### Score a single package

```bash
curl -s -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{
    "software_id": "psf/requests",
    "code_length": 4200,
    "language": "Python",
    "dependencies": 5,
    "code_coverage": 0.85,
    "known_vulnerabilities": 8,
    "unresolved_vulnerabilities": 1,
    "update_frequency": 0.75,
    "forks": 9400,
    "downloads": 30000000,
    "rating": 51000,
    "context": 0.5,
    "developer_histories": [{
      "developer_id": "psf",
      "total_vulnerabilities": 8,
      "total_software_count": 42,
      "software_same_lang_count": 38,
      "years_same_lang": 14.0,
      "years_total": 14.0
    }],
    "publisher_histories": [{
      "publisher_id": "psf",
      "software_published_count": 42,
      "years_publishing": 14.0
    }]
  }' | python -m json.tool
```

### Batch scoring (dataset mode)

```bash
curl -s -X POST http://localhost:8000/score/batch \
  -H "Content-Type: application/json" \
  -d '[...array of SoftwareRecord objects...]' | python -m json.tool
```

Batch mode builds DeveloperRegistry and PublisherRegistry from the submitted
records, so cross-package statistics are computed automatically — no need to
pre-compute `total_vulnerabilities` or `years_total`.

---

## Batch analysis — comparing multiple packages

The most informative use of SAFER is ranking a set of candidate packages.
The dataset mode builds registries from your full candidate list, so each
package's developer/publisher history is derived from the others in the set.

```python
import pandas as pd
from safer_model.io import load_csv, results_to_dataframe
from safer_model.scorer import SAFERScorer

# Load your packages.csv (one row per package)
records = load_csv("packages.csv")

# Dataset mode: registries are built from the full list
scorer = SAFERScorer(records=records)
results = scorer.score_all()

# Convert to DataFrame for analysis
df = results_to_dataframe(results)
df_sorted = df.sort_values("r_fp")

print(df_sorted[["software_id", "r_fp", "band"]].to_string(index=False))
```

Sample output:
```
   software_id    r_fp      band
  psf/requests  0.0731       Low
     numpy/numpy  0.1043       Low
  pallets/flask  0.2871  Moderate
  django/django  0.3102  Moderate
```

---

## Result fields reference

| Field | Equation | Description |
|---|---|---|
| `r_fp` | Eq. 19 | **Final risk score** (0 = no risk, 1 = maximum risk) |
| `band` | Section V-G | Risk band classification |
| `r_f` | Eq. 15 | Pre-penalty score (equals `r_fp` when `r_f ≤ 0.5`) |
| `penalty` | Eq. 12 | Penalty term P = 1 − C_TXT^V_UP |
| `r_dev` | Eq. 5 | Developer-based risk (unbounded; normalised by sigmoid in Eq. 15) |
| `r_pb` | Eq. 10 | Publisher-based risk |
| `r_ur` | Eq. 11 | User-indicated risk (1 − stars/downloads) |
| `r_cd` | Eq. 1 | Code dependency risk (= dependencies × sensitivity) |
| `r_cs` | Eq. 2 | Code specification risk (= w_LC × lines of code) |
| `r_pl` | Eq. 4 | Programming language experience risk |
| `w_dev` | Eq. 17 | Developer actor weight (inversely proportional to forks) |
| `w_pb` | Eq. 18 | Publisher actor weight (Laplace-smoothed vuln ratio) |
| `w_ur` | Eq. 16 | User actor weight (1 − w_DEV − w_PB) |
| `w_lc` | Eq. 3 | Historical vulnerability rate across developer's packages |
| `e_db` | Eq. 8 | Developer expertise in target language |
| `w_cd` | Eq. 6 | Code dependency sub-weight (1 − coverage) |
| `w_cs` | Eq. 7 | Code specification sub-weight (exp(−E_DB)) |
| `w_pl` | Eq. 9 | Programming language sub-weight |

---

## Interpreting results

### Risk bands

| Band | R_FP range | Recommended action |
|---|---|---|
| **Low** | [0.00, 0.25) | Acceptable for production use; monitor advisories |
| **Moderate** | [0.25, 0.50) | Review open vulnerabilities; track update cadence |
| **High** | [0.50, 0.75) | Requires security review before integration |
| **Critical** | [0.75, 1.00] | Do not use without a thorough audit and mitigation plan |

### Diagnostic signals

High `r_cs` (code specification risk)
: The developer has a high historical vulnerability rate (`w_lc`) relative to
their output volume. Review their other packages for recurring CVE patterns.

High `r_pb` (publisher risk)
: Infrequent updates (`update_frequency` ≪ 1) or a new publisher with few
published packages. Check release history and issue response times.

High `r_ur` (user risk)
: Stars are low relative to download count — high downloads with low community
approval can indicate a dependency pulled in transitively rather than chosen.

`r_fp > r_f` (penalty applied)
: `r_f > 0.5` triggered the penalty. The proportion of unresolved vulnerabilities
(`V_U / V_T`) is non-trivial in a high-risk context. Review Dependabot alerts.

---

## Configuration and tuning

Override defaults via `SAFERConfig`:

```python
from safer_model.config import SAFERConfig
from safer_model.scorer import SAFERScorer

config = SAFERConfig(
    # Amplify dependency risk for supply-chain-sensitive environments
    dep_sensitivity=2.0,

    # Treat unknown context as automation software instead of security
    unknown_context=0.3,

    # Lower penalty threshold — apply penalty at R_F > 0.4 instead of 0.5
    penalty_threshold=0.4,
)

scorer = SAFERScorer(config=config)
```

### Custom risk band thresholds (Section VI-D)

```python
from safer_model.schemas.output import RiskBand

config = SAFERConfig(
    risk_band_thresholds=[
        (RiskBand.LOW,      0.00, 0.20),   # tighter Low band
        (RiskBand.MODERATE, 0.20, 0.40),
        (RiskBand.HIGH,     0.40, 0.70),
        (RiskBand.CRITICAL, 0.70, 1.01),
    ]
)
```

> **Note:** Custom thresholds make scores incomparable across organisations
> (Section VI of the paper). Keep defaults when publishing scores externally.

---

## Field mapping reference

A quick lookup from GitHub / registry API responses to `SoftwareRecord` fields:

| `SoftwareRecord` field | Source | API / command |
|---|---|---|
| `rating` | GitHub stars | `repo.stargazers_count` |
| `forks` | GitHub forks | `repo.forks_count` |
| `language` | GitHub primary language | `repo.language` |
| `downloads` | PyPI monthly downloads | `pypistats.org/api/packages/{pkg}/recent` |
| `downloads` | npm monthly downloads | `api.npmjs.org/downloads/point/last-month/{pkg}` |
| `update_frequency` | Release cadence | compute from PyPI/npm release history (see Step 1c) |
| `dependencies` | Package manifest | `requires_dist` (PyPI) · `dependencies` (npm) |
| `code_length` | Lines of code | `cloc` or `tokei` on cloned repository |
| `code_coverage` | CI badge | Codecov / Coveralls API |
| `known_vulnerabilities` | GitHub Advisories | GraphQL `securityVulnerabilities` |
| `unresolved_vulnerabilities` | Dependabot alerts | `GET /repos/{owner}/{repo}/dependabot/alerts` |
| `DeveloperHistory.total_software_count` | Org repo count | `GET /orgs/{org}/repos` |
| `DeveloperHistory.years_total` | Org creation date | `org.created_at` |
| `PublisherHistory.software_published_count` | Org repo count | same as above |
| `PublisherHistory.years_publishing` | Org creation date | `org.created_at` |

---

## Project structure

```
SAFER Model Realization/
│
├── safer_model/                    # Core model package
│   ├── __init__.py                 # Public API exports
│   ├── config.py                   # SAFERConfig — tunable parameters (Section VI)
│   ├── constants.py                # Fixed constants (sigmoid params, context values)
│   ├── bands.py                    # RiskBand classifier (Section V-G thresholds)
│   ├── scorer.py                   # SAFERScorer — 9-step orchestration pipeline
│   ├── registry.py                 # DeveloperRegistry / PublisherRegistry
│   ├── fetcher.py                  # GitHubFetcher — auto data collection from APIs
│   ├── generator.py                # Synthetic dataset generator (paper Appendix)
│   ├── io.py                       # CSV / JSON I/O utilities
│   │
│   ├── formulas/                   # One module per risk component
│   │   ├── developer.py            # Eq. 1–9  : R_CD, R_CS, R_PL, weights, R_DEV
│   │   ├── publisher.py            # Eq. 10   : R_PB
│   │   ├── user.py                 # Eq. 11   : R_UR
│   │   ├── penalty.py              # Eq. 12–14: penalty P, context C_TXT
│   │   └── final_score.py          # Eq. 15–19: actor weights, R_F, R_FP
│   │
│   └── schemas/
│       ├── input.py                # SoftwareRecord, DeveloperHistory, PublisherHistory
│       └── output.py               # SAFERResult, RiskBand
│
├── safer_cli/
│   └── main.py                     # Click CLI: generate / score / score-one / report / analyze
│
├── safer_api/
│   ├── app.py                      # FastAPI application factory
│   └── routes.py                   # GET /health · POST /score · POST /score/batch
│
├── tests/
│   ├── conftest.py                 # Fixtures: paper's Table IX worked example data
│   ├── unit/                       # Formula unit tests (one file per formulas/ module)
│   └── integration/                # End-to-end: worked example + CLI tests
│
├── pyproject.toml                  # Package metadata and CLI entry point
└── requirements.txt                # Runtime dependencies
```

---

## Running tests

```bash
pytest                          # all 106 tests
pytest tests/unit/              # formula unit tests only
pytest tests/integration/       # worked example + CLI tests
pytest -v tests/integration/test_worked_example.py   # Table IX anchor
```

---

## Citation

```bibtex
@misc{safer2024,
  title  = {Elevating Software Trust: A Holistic Approach to Open-Source Risk Assessment},
  author = {…},
  year   = {2024},
  eprint = {2408.02876},
  archivePrefix = {arXiv},
}
```
