# src/cost_guard.py
"""Reserve-before-call API budget guard with persistent local state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import uuid
import yaml


class BudgetExceeded(RuntimeError):
    """Raised before a call if it would breach the configured cost cap."""


@dataclass(frozen=True)
class CostReservation:
    reservation_id: str
    reserved_usd: float


class CostGuard:
    """Single-process persistent token budget guard for a solo experiment."""

    def __init__(self, *, cap_usd: float, input_usd_per_million: float,
                 output_usd_per_million: float, state_path: Path | str):
        if cap_usd <= 0 or input_usd_per_million < 0 or output_usd_per_million < 0:
            raise ValueError("Invalid cap or token pricing")
        self.cap_usd = float(cap_usd)
        self.input_rate = float(input_usd_per_million) / 1_000_000
        self.output_rate = float(output_usd_per_million) / 1_000_000
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write({"spent_usd": 0.0, "reservations": {}, "hard_stopped": False,
                         "created_at": datetime.now(timezone.utc).isoformat()})

    @classmethod
    def from_yaml(cls, config_path: Path | str = "experiment.yaml",
                  state_path: Path | str = ".local/api_cost_state.json") -> "CostGuard":
        """Construct from experiment.yaml's cost cap and pricing keys."""
        with Path(config_path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        cost = config["cost"]
        pricing = cost["pricing_usd_per_million_tokens"]
        return cls(cap_usd=float(cost["cap_usd"]),
                   input_usd_per_million=float(pricing["input"]),
                   output_usd_per_million=float(pricing["output"]),
                   state_path=state_path)

    def _read(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"spent_usd": 0.0, "reservations": {}, "hard_stopped": False}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write(self, state: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(prefix="cost-state-", dir=str(self.state_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, sort_keys=True, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def estimate_usd(self, input_tokens: int, output_tokens: int) -> float:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative")
        return input_tokens * self.input_rate + output_tokens * self.output_rate

    def reserve_before_call(self, *, input_tokens: int, max_output_tokens: int,
                            call_id: str | None = None) -> CostReservation:
        """Reserve worst-case expected spend before calling the external API."""
        amount = self.estimate_usd(input_tokens, max_output_tokens)
        state = self._read()
        reserved = sum(float(r["reserved_usd"]) for r in state["reservations"].values())
        if state.get("hard_stopped") or float(state["spent_usd"]) + reserved + amount > self.cap_usd:
            # A rejected reservation has incurred no cost, so it must not
            # permanently stop smaller future calls. Hard-stop only once the
            # ledger records that spend/reservations have actually reached cap.
            if float(state["spent_usd"]) + reserved >= self.cap_usd:
                state["hard_stopped"] = True
                self._write(state)
            raise BudgetExceeded(
                f"API cost cap reached: spent=${state['spent_usd']:.4f}, "
                f"reserved=${reserved:.4f}, requested=${amount:.4f}, cap=${self.cap_usd:.2f}"
            )
        reservation_id = call_id or f"reservation-{uuid.uuid4().hex}"
        if reservation_id in state["reservations"]:
            raise ValueError(f"Duplicate reservation ID: {reservation_id}")
        state["reservations"][reservation_id] = {
            "reserved_usd": amount,
            "input_tokens_reserved": int(input_tokens),
            "output_tokens_reserved": int(max_output_tokens),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write(state)
        return CostReservation(reservation_id, amount)

    def commit_after_call(self, reservation_id: str, *, actual_input_tokens: int,
                          actual_output_tokens: int) -> float:
        """Replace reservation with actual usage and permanently account for spend."""
        state = self._read()
        if reservation_id not in state["reservations"]:
            raise KeyError(f"Unknown cost reservation: {reservation_id}")
        actual = self.estimate_usd(actual_input_tokens, actual_output_tokens)
        del state["reservations"][reservation_id]
        state["spent_usd"] = float(state["spent_usd"]) + actual
        reserved_other = sum(float(r["reserved_usd"]) for r in state["reservations"].values())
        if state["spent_usd"] + reserved_other >= self.cap_usd:
            state["hard_stopped"] = True
        self._write(state)
        if state["spent_usd"] > self.cap_usd:
            raise BudgetExceeded(
                f"Actual charge exceeded the reserved budget and cap: "
                f"spent=${state['spent_usd']:.4f}, cap=${self.cap_usd:.2f}. "
                "The overage is recorded; all later calls are blocked."
            )
        return actual

    def cancel_reservation(self, reservation_id: str) -> None:
        """Release a reservation if no API request was successfully made."""
        state = self._read()
        if reservation_id not in state["reservations"]:
            return
        del state["reservations"][reservation_id]
        self._write(state)

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of cap, spend, reservations and hard-stop state."""
        state = self._read()
        return {
            **state,
            "cap_usd": self.cap_usd,
            "reserved_usd": sum(float(r["reserved_usd"]) for r in state["reservations"].values()),
            "remaining_unreserved_usd": self.cap_usd - float(state["spent_usd"]) - sum(
                float(r["reserved_usd"]) for r in state["reservations"].values()
            ),
        }
