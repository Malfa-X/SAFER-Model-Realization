"""
Cross-dataset registries for developer and publisher aggregation.

The SAFER model requires cross-software statistics for several key computations:
  - DeveloperRegistry: aggregates V_D, |S_D|, |S_L|, E_DA, E_DS per developer
  - PublisherRegistry: aggregates E_PX, E_PY per publisher

Registries are built once from the full dataset and then queried per-record.
They are used in Dataset mode (SAFERScorer with a list of records).

For standalone single-record scoring, provide developer_histories and
publisher_histories directly in SoftwareRecord.
"""
from __future__ import annotations

from collections import defaultdict

from safer_model.schemas.input import DeveloperHistory, PublisherHistory, SoftwareRecord


class DeveloperRegistry:
    """
    Builds and serves cross-dataset developer aggregates from a full dataset.

    For each developer ID found in the dataset, the registry computes:
        total_vulnerabilities    (V_D)   — sum of known_vulns for all their software
        total_software_count     (|S_D|) — how many software they've developed
        software_same_lang_count (|S_L|) — how many of those are in the target language
        years_same_lang          (E_DS)  — years in the target language
        years_total              (E_DA)  — total years developing

    Dataset column assumptions (from Table III / generator.py):
      - Each SoftwareRecord has a single developer_id stored in
        developer_histories[0].developer_id (populated before registry call), OR
      - Records are loaded from CSV with a 'developer' column that becomes
        a single DeveloperHistory with only developer_id set (other fields from registry).

    The registry computes the cross-dataset aggregates and returns fully-populated
    DeveloperHistory objects for any queried record.

    Implementation note on years / experience:
    The paper's dataset (Table III) has a 'year' column representing the software's
    release/creation year, and the developer/publisher are identified by single letters.
    Since the dataset does not contain per-developer years-of-experience directly,
    the registry derives experience as follows:
        E_DA = current_year - min(year of all software by developer)
                                 (i.e., how long they've been developing)
        E_DS = current_year - min(year of software by developer in same language)

    This is consistent with the paper's dataset structure and worked example,
    where E_DA and E_DS values suggest years since first software in the dataset.
    """

    def __init__(self, records: list[SoftwareRecord]) -> None:
        # Maps developer_id → accumulated stats dict
        self._stats: dict[str, dict] = defaultdict(lambda: {
            "total_vulnerabilities": 0,
            "software_ids": [],
            "language_software": defaultdict(list),  # lang → [software_ids]
            "years": [],           # all years when this dev published software
            "lang_years": defaultdict(list),  # lang → [years]
        })

        for rec in records:
            dev_id = self._get_dev_id(rec)
            if dev_id is None:
                continue
            stats = self._stats[dev_id]
            stats["total_vulnerabilities"] += rec.known_vulnerabilities
            stats["software_ids"].append(rec.software_id)
            stats["language_software"][rec.language].append(rec.software_id)
            # year stored as int in the dataset; use it for experience derivation
            year = getattr(rec, "_year", None)
            if year is not None:
                stats["years"].append(year)
                stats["lang_years"][rec.language].append(year)

        self._records_by_id: dict[str, SoftwareRecord] = {r.software_id: r for r in records}

    @staticmethod
    def _get_dev_id(record: SoftwareRecord) -> str | None:
        """Extract the developer ID from a record's developer_histories."""
        if record.developer_histories:
            return record.developer_histories[0].developer_id
        return None

    def get_histories_for_software(
        self,
        record: SoftwareRecord,
    ) -> list[DeveloperHistory]:
        """
        Return fully-populated DeveloperHistory objects for all developers
        associated with this software.

        The returned histories contain cross-dataset aggregates scoped to the
        target software's language, so callers can directly sum them.
        """
        histories: list[DeveloperHistory] = []
        for raw_hist in record.developer_histories:
            dev_id = raw_hist.developer_id
            stats = self._stats.get(dev_id)
            if stats is None:
                # Developer not seen in dataset — use raw history or zeros
                histories.append(raw_hist)
                continue

            lang = record.language
            total_sw = len(stats["software_ids"])
            sw_same_lang = len(stats["language_software"].get(lang, []))
            total_vulns = stats["total_vulnerabilities"]

            # Derive experience from year spread
            all_years = stats["years"]
            lang_years = stats["lang_years"].get(lang, [])

            # If pre-populated in raw_hist (standalone mode values), prefer those
            if raw_hist.years_total > 0:
                e_da = raw_hist.years_total
                e_ds = raw_hist.years_same_lang
            elif all_years:
                import datetime
                current_year = datetime.datetime.now().year
                e_da = float(current_year - min(all_years))
                e_ds = float(current_year - min(lang_years)) if lang_years else 0.0
            else:
                e_da = 0.0
                e_ds = 0.0

            histories.append(
                DeveloperHistory(
                    developer_id=dev_id,
                    total_vulnerabilities=total_vulns,
                    total_software_count=total_sw,
                    software_same_lang_count=sw_same_lang,
                    years_same_lang=e_ds,
                    years_total=e_da,
                )
            )
        return histories


class PublisherRegistry:
    """
    Builds and serves cross-dataset publisher aggregates from a full dataset.

    For each publisher ID, the registry computes:
        software_published_count (E_PX) — total software published
        years_publishing         (E_PY) — years active as publisher
    """

    def __init__(self, records: list[SoftwareRecord]) -> None:
        self._stats: dict[str, dict] = defaultdict(lambda: {
            "software_ids": [],
            "years": [],
        })

        for rec in records:
            pub_id = self._get_pub_id(rec)
            if pub_id is None:
                continue
            stats = self._stats[pub_id]
            stats["software_ids"].append(rec.software_id)
            year = getattr(rec, "_year", None)
            if year is not None:
                stats["years"].append(year)

    @staticmethod
    def _get_pub_id(record: SoftwareRecord) -> str | None:
        if record.publisher_histories:
            return record.publisher_histories[0].publisher_id
        return None

    def get_histories_for_software(
        self,
        record: SoftwareRecord,
    ) -> list[PublisherHistory]:
        """Return fully-populated PublisherHistory objects for all publishers."""
        histories: list[PublisherHistory] = []
        for raw_hist in record.publisher_histories:
            pub_id = raw_hist.publisher_id
            stats = self._stats.get(pub_id)
            if stats is None:
                histories.append(raw_hist)
                continue

            sw_count = len(stats["software_ids"])
            all_years = stats["years"]

            if raw_hist.years_publishing > 0:
                e_py = raw_hist.years_publishing
            elif all_years:
                import datetime
                current_year = datetime.datetime.now().year
                e_py = float(current_year - min(all_years))
            else:
                e_py = 0.0

            # Prefer pre-populated software count if provided
            e_px = (
                raw_hist.software_published_count
                if raw_hist.software_published_count > 0
                else sw_count
            )

            histories.append(
                PublisherHistory(
                    publisher_id=pub_id,
                    software_published_count=e_px,
                    years_publishing=e_py,
                )
            )
        return histories
