"""Unit tests for safer_model/generator.py."""
import pytest

from safer_model.generator import CONTEXT_VALUES, generate_dataset


class TestGenerateDataset:
    def test_row_count(self):
        df = generate_dataset(n=100, seed=1)
        assert len(df) == 100

    def test_columns_present(self):
        df = generate_dataset(n=10, seed=1)
        expected = {
            "sample", "code_length", "developer", "publisher", "year",
            "language", "update_frequency", "forks", "downloads",
            "unresolved_vulnerabilities", "known_vulnerabilities",
            "dependencies", "rating", "code_coverage", "context",
        }
        assert expected.issubset(set(df.columns))

    def test_vuln_constraint(self):
        # unresolved ≤ known for every row
        df = generate_dataset(n=200, seed=2)
        assert (df["unresolved_vulnerabilities"] <= df["known_vulnerabilities"]).all()

    def test_rating_constraint(self):
        # rating ≤ downloads
        df = generate_dataset(n=200, seed=3)
        assert (df["rating"] <= df["downloads"]).all()

    def test_context_values(self):
        df = generate_dataset(n=200, seed=4)
        assert set(df["context"].unique()).issubset({0.2, 0.3, 0.5})

    def test_update_frequency_positive(self):
        df = generate_dataset(n=200, seed=5)
        assert (df["update_frequency"] > 0).all()
        assert (df["update_frequency"] <= 1.0).all()

    def test_reproducibility(self):
        df1 = generate_dataset(n=50, seed=99)
        df2 = generate_dataset(n=50, seed=99)
        assert df1.equals(df2)

    def test_different_seeds_differ(self):
        df1 = generate_dataset(n=50, seed=1)
        df2 = generate_dataset(n=50, seed=2)
        assert not df1.equals(df2)

    def test_developer_ids_uppercase(self):
        df = generate_dataset(n=200, seed=6)
        for dev in df["developer"].unique():
            assert len(dev) == 1 and dev.isupper()

    def test_languages(self):
        df = generate_dataset(n=200, seed=7)
        assert set(df["language"].unique()).issubset({"C", "Python", "Java"})
