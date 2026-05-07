"""
Integration tests for the safer CLI.

Uses Click's CliRunner to invoke commands in-process without subprocess overhead.
"""
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from safer_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestGenerateCommand:
    def test_basic_generate(self, runner, tmp_dir):
        out = str(tmp_dir / "dataset.csv")
        result = runner.invoke(cli, ["generate", "--samples", "50", "--output", out])
        assert result.exit_code == 0, result.output
        assert Path(out).exists()
        df = pd.read_csv(out)
        assert len(df) == 50

    def test_default_seed_reproducible(self, runner, tmp_dir):
        out1 = str(tmp_dir / "a.csv")
        out2 = str(tmp_dir / "b.csv")
        runner.invoke(cli, ["generate", "--samples", "20", "--seed", "42", "--output", out1])
        runner.invoke(cli, ["generate", "--samples", "20", "--seed", "42", "--output", out2])
        df1 = pd.read_csv(out1)
        df2 = pd.read_csv(out2)
        assert df1.equals(df2)


class TestScoreCommand:
    def test_score_generated_dataset(self, runner, tmp_dir):
        # First generate a small dataset
        dataset = str(tmp_dir / "data.csv")
        runner.invoke(cli, ["generate", "--samples", "20", "--output", dataset])

        # Then score it
        results_path = str(tmp_dir / "results.csv")
        result = runner.invoke(
            cli, ["score", "--input", dataset, "--output", results_path]
        )
        assert result.exit_code == 0, result.output
        assert Path(results_path).exists()

        df = pd.read_csv(results_path)
        assert len(df) == 20
        assert "r_fp" in df.columns
        assert "band" in df.columns
        # All R_FP values in [0, 1]
        assert (df["r_fp"] >= 0.0).all()
        assert (df["r_fp"] <= 1.0).all()
        # All bands are valid
        valid_bands = {"Low", "Moderate", "High", "Critical"}
        assert set(df["band"].unique()).issubset(valid_bands)

    def test_score_missing_input(self, runner):
        result = runner.invoke(cli, ["score", "--input", "/nonexistent.csv"])
        assert result.exit_code != 0


class TestScoreOneCommand:
    def test_score_one_json(self, runner):
        record = {
            "software_id": "test_sw",
            "code_length": 304,
            "language": "Java",
            "update_frequency": 0.08424,
            "forks": 2003,
            "downloads": 20455,
            "unresolved_vulnerabilities": 135,
            "known_vulnerabilities": 7556,
            "dependencies": 28,
            "rating": 7153,
            "code_coverage": 0.99,
            "context": 0.2,
            "developer_histories": [
                {
                    "developer_id": "W",
                    "total_vulnerabilities": 96912,
                    "total_software_count": 129,
                    "software_same_lang_count": 33,
                    "years_same_lang": 2.0,
                    "years_total": 2.0,
                }
            ],
            "publisher_histories": [
                {
                    "publisher_id": "Z",
                    "software_published_count": 123,
                    "years_publishing": 2.0,
                }
            ],
        }
        result = runner.invoke(cli, ["score-one", "--json", json.dumps(record)])
        assert result.exit_code == 0, result.output

        data = json.loads(result.output)
        assert data["software_id"] == "test_sw"
        assert 0.0 <= data["r_fp"] <= 1.0
        assert data["band"] == "Moderate"
