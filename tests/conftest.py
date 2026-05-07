"""
Shared pytest fixtures.

The most important fixture is `worked_example_record`, which encodes
the exact Table IX data from the paper's Appendix. All integration tests
use this as the ground truth.
"""
import pytest

from safer_model.schemas.input import (
    DeveloperHistory,
    PublisherHistory,
    SoftwareRecord,
)


@pytest.fixture
def worked_example_record() -> SoftwareRecord:
    """
    The software record from Table IX (Appendix) of arXiv:2408.02876v2.

    Cross-dataset aggregates for developer W and publisher Z are sourced from
    the paper's continuation table (Table IX Continuation).

    Paper expected intermediate values:
        R_CD  = 28
        w_LC  = 751.2558  (= 96912 / 129)
        R_CS  = 228381.8
        R_PL  = 0         (E_DS / E_DA = 2/2 = 1 → 1 - 1 = 0)
        w_CD  = 0.01      (= 1 - 0.99)
        E_DB  = 0.255814  (= 33/129)
        w_CS  = 0.77428   (= exp(-0.255814))
        w_PL  = 0.2157    (= |1 - (0.01 + 0.77428)|)
        R_DEV = 176831.46
        R_PB  = 0.1930
        R_UR  = 0.6503
        P     = 0.0283
        w_DEV = 4.99e-4   (= 1/2003)
        w_PB  = 0.0179    (= 136/7558)
        w_UR  = 0.9815
        R_F   = 0.3755    (paper; full-precision ~0.391, same Moderate band)
        R_FP  = 0.3755
        Band  = Moderate
    """
    return SoftwareRecord(
        software_id="table_ix",
        code_length=304,
        language="Java",
        update_frequency=0.08424,
        forks=2003,
        downloads=20455,
        unresolved_vulnerabilities=135,
        known_vulnerabilities=7556,
        dependencies=28,
        rating=7153,
        code_coverage=0.99,
        context=0.2,
        developer_histories=[
            DeveloperHistory(
                developer_id="W",
                total_vulnerabilities=96912,   # V_D
                total_software_count=129,      # |S_D|
                software_same_lang_count=33,   # |S_L| (Java)
                years_same_lang=2.0,           # E_DS
                years_total=2.0,               # E_DA
            )
        ],
        publisher_histories=[
            PublisherHistory(
                publisher_id="Z",
                software_published_count=123,  # E_PX
                years_publishing=2.0,          # E_PY
            )
        ],
    )
