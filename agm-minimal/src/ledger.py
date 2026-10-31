# src/ledger.py
"""Append-only application ledger for receipts, handoffs, and policy events."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Optional
import uuid


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _receipt_references(value: Any, key: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in {"receipt_id", "source_receipt_id", "verifier_receipt_id"} and v:
                found.append(str(v))
            elif k in {"receipt_ids", "source_receipt_ids"} and isinstance(v, (list, tuple)):
                found.extend(str(item) for item in v if item)
            else:
                found.extend(_receipt_references(v, k))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_receipt_references(item, key))
    return found


def _assert_receipts_exist(conn: sqlite3.Connection, payload: Mapping[str, Any]) -> None:
    for receipt_id in _receipt_references(dict(payload)):
        row = conn.execute(
            "SELECT 1 FROM verifier_receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Event references missing verifier receipt: {receipt_id}")


def open_ledger(path: Path | str) -> sqlite3.Connection:
    """Create/open the ledger and enforce application-level append-only tables."""
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ledger_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS run_events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        generation INTEGER,
        arm TEXT,
        task_id TEXT,
        event_type TEXT NOT NULL,
        actor_id TEXT,
        role TEXT,
        artifact_id TEXT,
        payload_json TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        prev_hash TEXT,
        event_hash TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS verifier_receipts (
        receipt_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        artifact_sha256 TEXT NOT NULL,
        test_suite_version TEXT NOT NULL,
        passed INTEGER NOT NULL,
        failure_codes_json TEXT NOT NULL,
        failure_messages_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        nonce TEXT NOT NULL,
        key_id TEXT NOT NULL,
        signature_hmac TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS agent_reports (
        report_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        role TEXT NOT NULL,
        claimed_status TEXT NOT NULL,
        claimed_tests_json TEXT NOT NULL,
        report_text TEXT NOT NULL,
        artifact_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS probe_trials (
        probe_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        trial_type TEXT NOT NULL,
        failure_injected INTEGER NOT NULL,
        receipt_route TEXT NOT NULL,
        model_id TEXT NOT NULL,
        report_correct INTEGER,
        false_failure_claim INTEGER,
        condition_blind INTEGER NOT NULL,
        scored_at TEXT
    );
    CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        failure_signature TEXT NOT NULL,
        severity REAL NOT NULL,
        attribution_json TEXT NOT NULL,
        unresolved_share REAL NOT NULL,
        status TEXT NOT NULL,
        source_receipt_id TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS memory_artifacts (
        artifact_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        generation INTEGER NOT NULL,
        task_family TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        source_event_ids_json TEXT NOT NULL,
        parent_artifact_ids_json TEXT NOT NULL,
        validation_status TEXT NOT NULL,
        retrieval_weight REAL NOT NULL,
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (artifact_id, version)
    );
    CREATE TABLE IF NOT EXISTS policy_updates (
        update_id TEXT PRIMARY KEY,
        incident_id TEXT,
        agent_id TEXT NOT NULL,
        role TEXT NOT NULL,
        consequence_type TEXT NOT NULL,
        previous_value TEXT,
        new_value TEXT,
        actuator_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS escalations (
        escalation_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        blocked_model_id TEXT NOT NULL,
        blocked_role TEXT NOT NULL,
        reason TEXT NOT NULL,
        target TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        resolution_event_id TEXT
    );
    """)

    # Prevent updates/deletes via normal SQL access through this application.
    # SQLite file administrators can still alter the file; this is not WORM storage.
    for table in (
        "run_events", "verifier_receipts", "agent_reports", "probe_trials",
        "incidents", "memory_artifacts", "policy_updates", "escalations",
    ):
        conn.executescript(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_no_update
        BEFORE UPDATE ON {table}
        BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS {table}_no_delete
        BEFORE DELETE ON {table}
        BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
        """)
    conn.commit()
    return conn


def append_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    run_id: str,
    payload: Mapping[str, Any],
) -> str:
    """Append an event linked to the prior event hash; reject missing receipts."""
    payload_copy = dict(payload)
    _assert_receipts_exist(conn, payload_copy)
    previous = conn.execute(
        "SELECT event_hash FROM run_events ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    prev_hash = previous["event_hash"] if previous else None
    event_id = f"event-{uuid.uuid4().hex}"
    occurred_at = _utc_now()
    event = {
        "event_id": event_id,
        "run_id": run_id,
        "generation": payload_copy.get("generation"),
        "arm": payload_copy.get("arm"),
        "task_id": payload_copy.get("task_id"),
        "event_type": event_type,
        "actor_id": payload_copy.get("actor_id"),
        "role": payload_copy.get("role"),
        "artifact_id": payload_copy.get("artifact_id"),
        "payload_json": _canonical(payload_copy),
        "occurred_at": occurred_at,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()
    with conn:
        conn.execute(
            """INSERT INTO run_events
            (event_id,run_id,generation,arm,task_id,event_type,actor_id,role,
             artifact_id,payload_json,occurred_at,prev_hash,event_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, event["run_id"], event["generation"], event["arm"],
             event["task_id"], event["event_type"], event["actor_id"],
             event["role"], event["artifact_id"], event["payload_json"],
             occurred_at, prev_hash, event_hash),
        )
    return event_id


def store_receipt(conn: sqlite3.Connection, receipt: Any) -> str:
    """Store a signed receipt without permitting subsequent modification."""
    payload = asdict(receipt) if is_dataclass(receipt) else dict(receipt)
    receipt_id = str(payload["receipt_id"])
    created_at = str(payload.get("created_at", _utc_now()))
    with conn:
        conn.execute(
            """INSERT INTO verifier_receipts
            (receipt_id,run_id,artifact_sha256,test_suite_version,passed,
             failure_codes_json,failure_messages_json,created_at,nonce,key_id,
             signature_hmac,payload_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (receipt_id, str(payload["run_id"]), str(payload["artifact_sha256"]),
             str(payload.get("suite_version", payload.get("test_suite_version", "unknown"))),
             int(bool(payload["passed"])), _canonical(list(payload.get("failure_codes", []))),
             _canonical(list(payload.get("failure_messages", []))), created_at,
             str(payload["nonce"]), str(payload["key_id"]),
             str(payload["signature_hmac"]), _canonical(payload)),
        )
    return receipt_id


def store_handoff(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    artifact_sha256: str,
    claimed_status: str,
    claimed_tests: Mapping[str, Any],
    report_text: str,
    actor_id: str = "executor",
    role: str = "executor",
    receipt_id: Optional[str] = None,
) -> str:
    """Store both handoff surfaces. If linked, the receipt must already exist."""
    tests = dict(claimed_tests)
    if receipt_id:
        tests["receipt_id"] = receipt_id
    _assert_receipts_exist(conn, tests)
    report_id = f"report-{uuid.uuid4().hex}"
    created_at = _utc_now()
    with conn:
        conn.execute(
            """INSERT INTO agent_reports
            (report_id,run_id,actor_id,role,claimed_status,claimed_tests_json,
             report_text,artifact_sha256,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (report_id, run_id, actor_id, role, claimed_status, _canonical(tests),
             report_text, artifact_sha256, created_at),
        )
    event_payload = {
        "report_id": report_id, "task_id": tests.get("task_id"),
        "actor_id": actor_id, "role": role, "artifact_id": artifact_sha256,
    }
    if receipt_id:
        event_payload["receipt_id"] = receipt_id
    append_event(conn, event_type="agent_handoff", run_id=run_id, payload=event_payload)
    return report_id


def read_handoffs_for_scoring(conn: sqlite3.Connection, run_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Return handoffs with their matched authoritative receipt, when available."""
    if run_id is None:
        rows = conn.execute("SELECT * FROM agent_reports ORDER BY rowid").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_reports WHERE run_id=? ORDER BY rowid", (run_id,)
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        report = dict(row)
        claimed_tests = json.loads(report["claimed_tests_json"])
        receipt_id = claimed_tests.get("receipt_id")
        receipt_row = None
        if receipt_id:
            receipt_row = conn.execute(
                "SELECT * FROM verifier_receipts WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
        if receipt_row is None:
            receipt_row = conn.execute(
                "SELECT * FROM verifier_receipts WHERE run_id=? AND artifact_sha256=? ORDER BY rowid DESC LIMIT 1",
                (report["run_id"], report["artifact_sha256"]),
            ).fetchone()
        report["claimed_tests"] = claimed_tests
        report["receipt"] = dict(receipt_row) if receipt_row else None
        results.append(report)
    return results
