"""
Synthetic dataset generator for the SAFER framework.

Implements the Appendix criteria from arXiv:2408.02876v2:
  - 26 developers (A–Z), 26 publishers (A–Z, independent)
  - Years: 2016–2023
  - Languages: C, Python, Java
  - All numeric ranges drawn from paper's appendix description

The generator produces a pandas DataFrame matching the Table III structure,
which can be saved to CSV and loaded back via safer_model.io.
"""
from __future__ import annotations

import random
import string
from typing import Any

import pandas as pd

# ── Dataset parameters (Appendix) ────────────────────────────────────────────
DEVELOPER_IDS: list[str] = list(string.ascii_uppercase)   # A–Z
PUBLISHER_IDS: list[str] = list(string.ascii_uppercase)   # A–Z, independent of devs
LANGUAGES: list[str] = ["C", "Python", "Java"]
CONTEXT_VALUES: list[float] = [0.2, 0.3, 0.5]
YEARS: list[int] = list(range(2016, 2024))   # 2016–2023

# Numeric ranges (Appendix + representative repo values)
CODE_LENGTH_RANGE = (40, 700)          # lines of code
UPDATE_FREQ_RANGE = (0.001, 1.0)       # F_UP ∈ (0, 1]
FORKS_RANGE = (0, 5000)
DOWNLOADS_RANGE = (100, 100_000)
KNOWN_VULNS_RANGE = (0, 500)
DEPENDENCIES_RANGE = (0, 30)
# rating is in [0, downloads], generated proportionally
CODE_COVERAGE_RANGE = (0.0, 1.0)


def generate_dataset(n: int = 9000, seed: int | None = 42) -> pd.DataFrame:
    """
    Generate n synthetic software records matching the paper's Appendix criteria.

    Parameters
    ----------
    n:
        Number of records to generate. Paper uses 9000. Default 9000.
    seed:
        Random seed for reproducibility. None for non-deterministic output.

    Returns
    -------
    pd.DataFrame
        Columns match Table III:
            sample, code_length, developer, publisher, year, language,
            update_frequency, forks, downloads, unresolved_vulnerabilities,
            known_vulnerabilities, dependencies, rating, code_coverage, context
    """
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []

    for i in range(1, n + 1):
        v_t = rng.randint(*KNOWN_VULNS_RANGE)
        v_u = rng.randint(0, v_t)
        downloads = rng.randint(*DOWNLOADS_RANGE)
        rating = rng.randint(0, downloads)   # stars ≤ downloads

        rows.append({
            "sample": i,
            "code_length": rng.randint(*CODE_LENGTH_RANGE),
            "developer": rng.choice(DEVELOPER_IDS),
            "publisher": rng.choice(PUBLISHER_IDS),
            "year": rng.choice(YEARS),
            "language": rng.choice(LANGUAGES),
            "update_frequency": round(rng.uniform(*UPDATE_FREQ_RANGE), 5),
            "forks": rng.randint(*FORKS_RANGE),
            "downloads": downloads,
            "unresolved_vulnerabilities": v_u,
            "known_vulnerabilities": v_t,
            "dependencies": rng.randint(*DEPENDENCIES_RANGE),
            "rating": rating,
            "code_coverage": round(rng.uniform(*CODE_COVERAGE_RANGE), 4),
            "context": rng.choice(CONTEXT_VALUES),
        })

    df = pd.DataFrame(rows)
    return df


def generate_and_save(
    path: str,
    n: int = 9000,
    seed: int | None = 42,
) -> pd.DataFrame:
    """
    Generate the dataset and save it to CSV.

    Parameters
    ----------
    path:
        Output CSV file path.
    n:
        Number of records.
    seed:
        Random seed.

    Returns
    -------
    pd.DataFrame
        The generated dataset (also written to path).
    """
    df = generate_dataset(n=n, seed=seed)
    df.to_csv(path, index=False)
    return df
