"""Unit tests for safer_model/bands.py."""
import pytest

from safer_model.bands import classify_risk_band
from safer_model.schemas.output import RiskBand


class TestClassifyRiskBand:
    def test_low(self):
        assert classify_risk_band(0.0) == RiskBand.LOW
        assert classify_risk_band(0.1) == RiskBand.LOW
        assert classify_risk_band(0.249) == RiskBand.LOW

    def test_moderate(self):
        assert classify_risk_band(0.25) == RiskBand.MODERATE
        assert classify_risk_band(0.37) == RiskBand.MODERATE
        assert classify_risk_band(0.499) == RiskBand.MODERATE

    def test_high(self):
        assert classify_risk_band(0.5) == RiskBand.HIGH
        assert classify_risk_band(0.6) == RiskBand.HIGH
        assert classify_risk_band(0.749) == RiskBand.HIGH

    def test_critical(self):
        assert classify_risk_band(0.75) == RiskBand.CRITICAL
        assert classify_risk_band(0.9) == RiskBand.CRITICAL
        assert classify_risk_band(1.0) == RiskBand.CRITICAL

    def test_paper_examples(self):
        # Table IV
        assert classify_risk_band(0.37) == RiskBand.MODERATE   # Sample 1
        assert classify_risk_band(0.65) == RiskBand.HIGH        # Sample 2 (0.65)
        assert classify_risk_band(0.98) == RiskBand.CRITICAL    # Sample 4500
        assert classify_risk_band(0.21) == RiskBand.LOW         # Sample 4501
        assert classify_risk_band(0.82) == RiskBand.CRITICAL    # Sample 8999
        assert classify_risk_band(0.40) == RiskBand.MODERATE    # Sample 9000
