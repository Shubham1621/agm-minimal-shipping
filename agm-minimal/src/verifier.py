# src/verifier.py
"""Execution-grounded BigQuery verifier with HMAC-signed receipts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import difflib
import hashlib
import hmac
import json
import os
import re
import secrets
from typing import Any, Optional, Sequence

try:
    from google.api_core.exceptions import BadRequest
except ImportError:  # lets offline unit tests import the receipt helpers
    class BadRequest(Exception):
        """Fallback type used only when the Google Cloud SDK is not installed."""

try:
    from google.cloud import bigquery
except ImportError:  # BigQuery execution still requires requirements.txt dependencies
    bigquery = None  # type: ignore[assignment]


@dataclass(frozen=True)
class VerificationReceipt:
    """Immutable result of executing and checking a pipeline artifact."""
    receipt_id: str
    run_id: str
    task_id: str
    artifact_sha256: str
    suite_version: str
    passed: bool
    failure_codes: tuple[str, ...]
    failure_messages: tuple[str, ...]
    source_table: str
    target_table: str
    expected_partition_column: str
    expected_row_count: int
    observed_row_count: Optional[int]
    target_columns: tuple[str, ...]
    partitioning_field: Optional[str]
    filtered_dry_run_bytes: Optional[int]
    baseline_dry_run_bytes: Optional[int]
    created_at: str
    nonce: str
    key_id: str
    signature_hmac: str


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _unsigned_payload(receipt: VerificationReceipt) -> dict[str, Any]:
    payload = asdict(receipt)
    payload.pop("signature_hmac", None)
    # asdict preserves tuples; JSON canonicalization encodes them as arrays.
    return payload


def _sign(payload: dict[str, Any], signing_key: bytes) -> str:
    return hmac.new(signing_key, _canonical_json(payload), hashlib.sha256).hexdigest()


def verify_receipt_signature(receipt: VerificationReceipt, signing_key: bytes) -> bool:
    """Return True only when the HMAC-SHA256 signature is valid."""
    if not signing_key:
        return False
    expected = _sign(_unsigned_payload(receipt), signing_key)
    return hmac.compare_digest(expected, receipt.signature_hmac)


def _safe_identifier(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise ValueError(f"Unsafe BigQuery {label}: {value!r}")
    return value


def _table_fqn(project_id: str, dataset_id: str, table_id: str) -> str:
    # Project IDs may contain hyphens; dataset/table identifiers are validated.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:-]{4,1023}", project_id):
        raise ValueError(f"Unsafe BigQuery project ID: {project_id!r}")
    _safe_identifier(dataset_id, "dataset")
    _safe_identifier(table_id, "table")
    return f"`{project_id}.{dataset_id}.{table_id}`"


def _partition_expression_column(sql: str) -> Optional[str]:
    match = re.search(
        r"\bPARTITION\s+BY\s+(?:DATE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)|([A-Za-z_][A-Za-z0-9_]*))",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(1) or match.group(2)


def _select_list(sql: str) -> Optional[str]:
    # Handles the task template's CREATE TABLE ... AS SELECT ... FROM form.
    match = re.search(r"\bAS\s+SELECT\s+(.*?)\s+FROM\b", sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        match = re.search(r"\bSELECT\s+(.*?)\s+FROM\b", sql, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def _classify_bad_request(sql: str, expected_column: str, raw_message: str) -> str:
    """Classify only known benchmark failures; unknown 400s stay generic."""
    partition_column = _partition_expression_column(sql)
    select_list = _select_list(sql)
    msg = raw_message.lower()

    # A misspelled partition expression is supported only when both the SQL
    # shape and the BigQuery message point at an unresolved, similar identifier.
    if partition_column and partition_column.lower() != expected_column.lower():
        similar = difflib.SequenceMatcher(
            None, partition_column.lower(), expected_column.lower()
        ).ratio() >= 0.65
        message_mentions_candidate = partition_column.lower() in msg
        unresolved_message = any(
            token in msg for token in ("unrecognized name", "not found inside", "does not exist")
        )
        if similar and message_mentions_candidate and unresolved_message:
            return "PARTITION_COLUMN_MISSPELLED"

    # Missing from SELECT: expected partition expression remains intact, but
    # the output column is absent, and the server reports that identifier.
    if (
        partition_column
        and partition_column.lower() == expected_column.lower()
        and select_list is not None
        and not re.search(rf"\b{re.escape(expected_column)}\b", select_list, re.IGNORECASE)
        and expected_column.lower() in msg
        and any(token in msg for token in ("unrecognized name", "not found", "does not exist"))
    ):
        return "PARTITION_COLUMN_OMITTED"

    return "BIGQUERY_BAD_REQUEST"


def _finalize_receipt(
    *,
    run_id: str,
    task_id: str,
    artifact_sha256: str,
    suite_version: str,
    failure_codes: list[str],
    failure_messages: list[str],
    source_table: str,
    target_table: str,
    expected_partition_column: str,
    expected_row_count: int,
    observed_row_count: Optional[int],
    target_columns: Sequence[str],
    partitioning_field: Optional[str],
    filtered_dry_run_bytes: Optional[int],
    baseline_dry_run_bytes: Optional[int],
    signing_key: bytes,
    key_id: str,
) -> VerificationReceipt:
    if not signing_key:
        raise ValueError("signing_key must not be empty")
    unsigned = {
        "receipt_id": f"receipt-{secrets.token_hex(12)}",
        "run_id": run_id,
        "task_id": task_id,
        "artifact_sha256": artifact_sha256,
        "suite_version": suite_version,
        "passed": len(failure_codes) == 0,
        "failure_codes": tuple(dict.fromkeys(failure_codes)),
        "failure_messages": tuple(failure_messages),
        "source_table": source_table,
        "target_table": target_table,
        "expected_partition_column": expected_partition_column,
        "expected_row_count": int(expected_row_count),
        "observed_row_count": observed_row_count,
        "target_columns": tuple(target_columns),
        "partitioning_field": partitioning_field,
        "filtered_dry_run_bytes": filtered_dry_run_bytes,
        "baseline_dry_run_bytes": baseline_dry_run_bytes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),
        "key_id": key_id,
    }
    signature = _sign(unsigned, signing_key)
    return VerificationReceipt(**unsigned, signature_hmac=signature)


def verify_bigquery_pipeline(
    client: bigquery.Client,
    *,
    project_id: str,
    dataset_id: str,
    run_id: str,
    task_id: str,
    sql: str,
    source_table: str,
    target_table: str,
    expected_partition_column: str,
    expected_row_count: int,
    signing_key: bytes,
    expected_columns: Sequence[str],
    row_key: str,
    suite_version: str,
    location: Optional[str] = None,
    partition_filter_date: str = "2025-01-04",
    key_id: Optional[str] = None,
) -> VerificationReceipt:
    """Execute SQL, assert contract invariants, and return a signed receipt.

    BigQuery BadRequest errors are captured in a failed, signed receipt. Other
    infrastructure/API exceptions propagate so that availability failures are
    not mislabeled as data-pipeline defects.
    """
    if expected_row_count < 0:
        raise ValueError("expected_row_count cannot be negative")
    if not expected_columns:
        raise ValueError("expected_columns cannot be empty")
    if expected_partition_column not in expected_columns:
        raise ValueError("expected partition column must be part of expected_columns")
    _safe_identifier(dataset_id, "dataset")
    _safe_identifier(source_table, "source table")
    _safe_identifier(target_table, "target table")
    _safe_identifier(expected_partition_column, "partition column")
    _safe_identifier(row_key, "row key")
    for col in expected_columns:
        _safe_identifier(col, "expected column")

    if bigquery is None:
        raise RuntimeError("google-cloud-bigquery is required to execute pipeline verification")

    location = location or getattr(client, "location", None)
    use_key_id = key_id or os.getenv("AGM_HMAC_KEY_ID", "agm-hmac-key-v1")
    artifact_sha256 = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    failures: list[str] = []
    messages: list[str] = []
    observed_row_count: Optional[int] = None
    target_columns: tuple[str, ...] = ()
    partitioning_field: Optional[str] = None
    filtered_bytes: Optional[int] = None
    baseline_bytes: Optional[int] = None

    try:
        query_kwargs: dict[str, Any] = {}
        if location:
            query_kwargs["location"] = location
        client.query(sql, **query_kwargs).result()
    except BadRequest as exc:
        raw_message = str(exc)
        code = _classify_bad_request(sql, expected_partition_column, raw_message)
        failures.append(code)
        messages.append(raw_message)
        return _finalize_receipt(
            run_id=run_id, task_id=task_id, artifact_sha256=artifact_sha256,
            suite_version=suite_version, failure_codes=failures,
            failure_messages=messages, source_table=source_table,
            target_table=target_table,
            expected_partition_column=expected_partition_column,
            expected_row_count=expected_row_count,
            observed_row_count=None, target_columns=(), partitioning_field=None,
            filtered_dry_run_bytes=None, baseline_dry_run_bytes=None,
            signing_key=signing_key, key_id=use_key_id,
        )

    source_fqn = _table_fqn(project_id, dataset_id, source_table)
    target_fqn = _table_fqn(project_id, dataset_id, target_table)

    table = client.get_table(f"{project_id}.{dataset_id}.{target_table}")
    target_columns = tuple(field.name for field in table.schema)
    missing = sorted(set(expected_columns) - set(target_columns))
    if missing:
        failures.append("OUTPUT_SCHEMA_MISMATCH")
        messages.append(f"Target table is missing required columns: {', '.join(missing)}")

    partitioning_field = (
        table.time_partitioning.field if table.time_partitioning is not None else None
    )
    if partitioning_field != expected_partition_column:
        if partitioning_field is None:
            code = "PARTITION_EXPRESSION_MISSING"
            msg = f"Target table has no time partitioning; expected {expected_partition_column}."
        else:
            code = "PARTITION_COLUMN_MISSPELLED"
            msg = (
                f"Target time partitioning field is {partitioning_field!r}; "
                f"expected {expected_partition_column!r}."
            )
        failures.append(code)
        messages.append(msg)

    count_sql = f"SELECT COUNT(*) AS n FROM {target_fqn}"
    row = next(iter(client.query(count_sql, **({"location": location} if location else {})).result()))
    observed_row_count = int(row.n)
    if observed_row_count != expected_row_count:
        failures.append("ROW_COUNT_MISMATCH")
        messages.append(
            f"Target row count {observed_row_count} != expected {expected_row_count}."
        )

    unique_sql = (
        f"SELECT COUNT(*) AS n, COUNT(DISTINCT `{row_key}`) AS n_unique "
        f"FROM {target_fqn}"
    )
    unique_row = next(iter(client.query(unique_sql, **({"location": location} if location else {})).result()))
    if int(unique_row.n_unique) != int(unique_row.n):
        failures.append("ROW_KEY_NOT_UNIQUE")
        messages.append(
            f"Row key {row_key!r} is not unique: total={int(unique_row.n)}, "
            f"distinct={int(unique_row.n_unique)}."
        )

    # Only a partitioned table can satisfy the pruning comparison. Keep the
    # raw bytes on the receipt for reproducibility and review.
    if partitioning_field == expected_partition_column and not missing:
        column_sql = ", ".join(f"`{col}`" for col in expected_columns)
        filtered_sql = (
            f"SELECT {column_sql} FROM {target_fqn} "
            f"WHERE DATE(`{expected_partition_column}`) = DATE '{partition_filter_date}'"
        )
        baseline_sql = f"SELECT {column_sql} FROM {target_fqn}"
        dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        filtered_job = client.query(filtered_sql, job_config=dry_cfg, **({"location": location} if location else {}))
        baseline_job = client.query(baseline_sql, job_config=dry_cfg, **({"location": location} if location else {}))
        filtered_bytes = int(filtered_job.total_bytes_processed or 0)
        baseline_bytes = int(baseline_job.total_bytes_processed or 0)
        if not (filtered_bytes < baseline_bytes):
            failures.append("PARTITION_PRUNING_NOT_OBSERVED")
            messages.append(
                f"Partition pruning not observed: filtered bytes={filtered_bytes}, "
                f"baseline bytes={baseline_bytes}."
            )

    return _finalize_receipt(
        run_id=run_id, task_id=task_id, artifact_sha256=artifact_sha256,
        suite_version=suite_version, failure_codes=failures,
        failure_messages=messages, source_table=source_table,
        target_table=target_table,
        expected_partition_column=expected_partition_column,
        expected_row_count=expected_row_count,
        observed_row_count=observed_row_count, target_columns=target_columns,
        partitioning_field=partitioning_field,
        filtered_dry_run_bytes=filtered_bytes,
        baseline_dry_run_bytes=baseline_bytes,
        signing_key=signing_key, key_id=use_key_id,
    )
