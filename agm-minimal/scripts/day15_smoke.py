#!/usr/bin/env python3
# scripts/day15_smoke.py
"""End-to-end BigQuery fixture + correct query + signed verifier receipt smoke test."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets

from google.cloud import bigquery
from src.verifier import verify_bigquery_pipeline, verify_receipt_signature

ROOT = Path(__file__).resolve().parents[1]


def run_day15_smoke() -> dict:
    project_id = os.getenv("AGM_GCP_PROJECT")
    if not project_id:
        raise RuntimeError("Set AGM_GCP_PROJECT to a personal GCP project with BigQuery enabled.")
    dataset_id = os.getenv("AGM_BQ_DATASET", "agm_sandbox")
    location = os.getenv("AGM_BQ_LOCATION", "US")
    client = bigquery.Client(project=project_id, location=location)

    fixture = (ROOT / "sql" / "create_fixture.sql").read_text(encoding="utf-8")
    fixture = fixture.replace("{{PROJECT_ID}}", project_id).replace("{{DATASET_ID}}", dataset_id)
    client.query(fixture, location=location).result()

    source_fqn = f"`{project_id}.{dataset_id}.pipeline_source`"
    target_fqn = f"`{project_id}.{dataset_id}.pipeline_target`"
    sql = (
        f"CREATE OR REPLACE TABLE {target_fqn} PARTITION BY DATE(event_date) AS "
        f"SELECT event_id, event_date, customer_id, amount, payload "
        f"FROM {source_fqn} WHERE event_id <= 100"
    )
    key_text = os.getenv("AGM_HMAC_KEY")
    key = key_text.encode("utf-8") if key_text else secrets.token_bytes(32)
    receipt = verify_bigquery_pipeline(
        client,
        project_id=project_id,
        dataset_id=dataset_id,
        run_id="day15-smoke-run",
        task_id="day15-handcrafted-correct-pipeline",
        sql=sql,
        source_table="pipeline_source",
        target_table="pipeline_target",
        expected_partition_column="event_date",
        expected_row_count=100,
        signing_key=key,
        expected_columns=("event_id", "event_date", "customer_id", "amount", "payload"),
        row_key="event_id",
        suite_version="partition-contract-v1",
    )
    signature_ok = verify_receipt_signature(receipt, key)
    target_meta = client.get_table(f"{project_id}.{dataset_id}.pipeline_target")
    source_rows = int(next(iter(client.query(
        f"SELECT COUNT(*) AS row_count FROM `{project_id}.{dataset_id}.pipeline_source`"
    ).result())).row_count)
    target_rows = int(next(iter(client.query(
        f"SELECT COUNT(*) AS row_count FROM `{project_id}.{dataset_id}.pipeline_target`"
    ).result())).row_count)
    filtered_query = (
        f"SELECT event_id, event_date, customer_id, amount, payload "
        f"FROM `{project_id}.{dataset_id}.pipeline_target` "
        "WHERE DATE(event_date) = DATE '2025-01-04'"
    )
    baseline_query = (
        f"SELECT event_id, event_date, customer_id, amount, payload "
        f"FROM `{project_id}.{dataset_id}.pipeline_target`"
    )
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    filtered_bytes = int(client.query(filtered_query, job_config=dry_cfg, location=location).total_bytes_processed or 0)
    baseline_bytes = int(client.query(baseline_query, job_config=dry_cfg, location=location).total_bytes_processed or 0)
    filtered_rows = int(next(iter(client.query(
        f"SELECT COUNT(*) AS row_count FROM `{project_id}.{dataset_id}.pipeline_target` "
        "WHERE DATE(event_date) = DATE '2025-01-04'", location=location
    ).result())).row_count)
    output = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "receipt_id": receipt.receipt_id,
        "artifact_sha256": receipt.artifact_sha256,
        "passed": receipt.passed,
        "failure_codes": list(receipt.failure_codes),
        "signature_valid": signature_ok,
        "expected_source_rows": 100,
        "source_rows": source_rows,
        "target_rows": target_rows,
        "partitioning_field": (target_meta.time_partitioning.field if target_meta.time_partitioning else None),
        "target_columns": [field.name for field in target_meta.schema],
        "filtered_dry_run_bytes": filtered_bytes,
        "baseline_dry_run_bytes": baseline_bytes,
        "partition_filtered_rows": filtered_rows,
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "day15_smoke.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    if not receipt.passed:
        raise AssertionError(f"Verifier did not pass: {receipt.failure_codes} :: {receipt.failure_messages}")
    if not signature_ok:
        raise AssertionError("Receipt HMAC verification failed")
    if source_rows != 100 or target_rows != 100:
        raise AssertionError(f"Row-count contract failed: source={source_rows}, target={target_rows}")
    if output["partitioning_field"] != "event_date":
        raise AssertionError(f"Wrong partition metadata: {output['partitioning_field']}")
    if not (0 < filtered_rows < target_rows and filtered_bytes < baseline_bytes):
        raise AssertionError(
            f"Partition pruning was not observed: filtered_rows={filtered_rows}, "
            f"target_rows={target_rows}, filtered_bytes={filtered_bytes}, baseline_bytes={baseline_bytes}"
        )
    print(f"PASS: BigQuery fixture, schema, partition metadata, row counts, pruning, and signed receipt ({receipt.receipt_id})")
    return output


if __name__ == "__main__":
    run_day15_smoke()
