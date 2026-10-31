# tests/test_day15_smoke.py
"""Integration lock test. Requires personal GCP ADC and BigQuery permissions."""
import os
import pytest

from scripts.day15_smoke import run_day15_smoke


def test_day15_smoke():
    """The handcrafted task must create a real partitioned table and signed PASS receipt."""
    if not os.getenv("AGM_GCP_PROJECT"):
        pytest.skip("Set AGM_GCP_PROJECT to run the real BigQuery day-15 lock test.")
    result = run_day15_smoke()
    assert result["passed"] is True
    assert result["failure_codes"] == []
    assert result["signature_valid"] is True
    assert len(result["artifact_sha256"]) == 64
    assert result["receipt_id"].startswith("receipt-")
    assert result["expected_source_rows"] == 100
    assert result["source_rows"] == 100
    assert result["target_rows"] == 100
    assert result["partitioning_field"] == "event_date"
    assert set(result["target_columns"]) == {"event_id", "event_date", "customer_id", "amount", "payload"}
    assert 0 < result["partition_filtered_rows"] < result["target_rows"]
    assert result["filtered_dry_run_bytes"] < result["baseline_dry_run_bytes"]
