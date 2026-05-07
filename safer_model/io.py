"""
CSV and JSON I/O utilities for the SAFER framework.

Loading:
    load_csv()   — Table III-format CSV → list[SoftwareRecord]
    load_json()  — JSON string or dict  → SoftwareRecord

Saving:
    results_to_csv()        — list[SAFERResult] → CSV
    results_to_dataframe()  — list[SAFERResult] → pd.DataFrame
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from safer_model.schemas.input import (
    DeveloperHistory,
    PublisherHistory,
    SoftwareRecord,
)
from safer_model.schemas.output import SAFERResult

# ── Column name mappings from Table III CSV to SoftwareRecord fields ──────────
CSV_COLUMN_MAP: dict[str, str] = {
    "sample": "software_id",
    "code_length": "code_length",
    "developer": "_developer_id",    # used to build DeveloperHistory
    "publisher": "_publisher_id",    # used to build PublisherHistory
    "year": "_year",                 # stored for registry use, not in model
    "language": "language",
    "update_frequency": "update_frequency",
    "forks": "forks",
    "downloads": "downloads",
    "unresolved_vulnerabilities": "unresolved_vulnerabilities",
    "known_vulnerabilities": "known_vulnerabilities",
    "dependencies": "dependencies",
    "rating": "rating",
    "code_coverage": "code_coverage",
    "context": "context",
}


def load_csv(path: str | Path) -> list[SoftwareRecord]:
    """
    Load a Table III-format CSV file and return a list of SoftwareRecord objects.

    Each row is converted to a SoftwareRecord. The 'developer' and 'publisher'
    columns are captured as single-entry developer_histories and
    publisher_histories respectively (with only IDs set; aggregates are
    computed by DeveloperRegistry / PublisherRegistry at score time).

    The 'year' column is stored as a private attribute _year on each record
    for use by the registry's experience derivation.

    Parameters
    ----------
    path:
        Path to the CSV file. Must contain at minimum the columns from Table III.

    Returns
    -------
    list[SoftwareRecord]
        One record per CSV row.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Handle 'sample' as string software_id
    if "sample" in df.columns:
        df["sample"] = df["sample"].astype(str)

    records: list[SoftwareRecord] = []
    for _, row in df.iterrows():
        record = _row_to_record(row)
        records.append(record)

    return records


def _row_to_record(row: "pd.Series") -> SoftwareRecord:
    """Convert a single DataFrame row to a SoftwareRecord."""
    # Coerce update_frequency: guard against zero (replace with minimum)
    uf = float(row.get("update_frequency", 0.001))
    if uf <= 0.0:
        warnings.warn(
            f"update_frequency={uf} for software '{row.get('sample', '?')}' "
            "is invalid (must be > 0). Setting to 0.001.",
            UserWarning,
            stacklevel=3,
        )
        uf = 0.001

    # Coerce context: snap to nearest valid value
    ctx_raw = float(row.get("context", 0.2))
    ctx = _snap_context(ctx_raw)

    dev_id = str(row.get("developer", "UNKNOWN"))
    pub_id = str(row.get("publisher", "UNKNOWN"))
    year = int(row.get("year", 0)) if "year" in row.index else 0

    record = SoftwareRecord(
        software_id=str(row.get("sample", row.name)),
        code_length=int(row.get("code_length", 0)),
        dependencies=int(row.get("dependencies", 0)),
        code_coverage=float(row.get("code_coverage", 0.0)),
        language=str(row.get("language", "Unknown")),
        known_vulnerabilities=int(row.get("known_vulnerabilities", 0)),
        unresolved_vulnerabilities=int(row.get("unresolved_vulnerabilities", 0)),
        update_frequency=uf,
        forks=int(row.get("forks", 0)),
        downloads=int(row.get("downloads", 0)),
        rating=float(row.get("rating", 0.0)),
        context=ctx,
        developer_histories=[DeveloperHistory(developer_id=dev_id)],
        publisher_histories=[PublisherHistory(publisher_id=pub_id)],
    )
    # Attach year as private attribute for registry experience derivation
    object.__setattr__(record, "_year", year)
    object.__setattr__(record, "_developer_id", dev_id)
    object.__setattr__(record, "_publisher_id", pub_id)
    return record


def _snap_context(value: float) -> float:
    """Snap a float to the nearest valid context value {0.2, 0.3, 0.5}."""
    valid = [0.2, 0.3, 0.5]
    return min(valid, key=lambda v: abs(v - value))


def load_json(data: str | dict[str, Any]) -> SoftwareRecord:
    """
    Parse a single JSON string or dict into a SoftwareRecord.

    For standalone scoring, developer_histories and publisher_histories
    should be included in the JSON with pre-populated aggregates.

    Parameters
    ----------
    data:
        JSON string or Python dict conforming to the SoftwareRecord schema.

    Returns
    -------
    SoftwareRecord
    """
    if isinstance(data, str):
        data = json.loads(data)
    return SoftwareRecord.model_validate(data)


def results_to_csv(results: list[SAFERResult], path: str | Path) -> None:
    """
    Write a list of SAFERResult objects to a CSV file.

    Parameters
    ----------
    results:
        List of scored results.
    path:
        Output file path.
    """
    df = results_to_dataframe(results)
    df.to_csv(path, index=False)


def results_to_dataframe(results: list[SAFERResult]) -> pd.DataFrame:
    """
    Convert a list of SAFERResult objects to a pandas DataFrame.

    Column order mirrors the paper's Table IV, with intermediate values appended.
    """
    rows = [r.model_dump() for r in results]
    df = pd.DataFrame(rows)
    # Reorder to match Table IV: software_id, r_dev, r_pb, r_ur, r_f, r_fp, band
    priority_cols = ["software_id", "r_dev", "r_pb", "r_ur", "r_f", "r_fp", "band"]
    remaining = [c for c in df.columns if c not in priority_cols]
    df = df[priority_cols + remaining]
    return df
