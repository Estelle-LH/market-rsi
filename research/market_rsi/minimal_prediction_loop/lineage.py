"""Minimal, auditable KEEP/REVERT lineage for prediction-first experiments.

This module stores commitments and aggregate Dev evidence only.  It never
stores prediction rows, labels, outcomes, candidate source, or Final feedback.
The caller remains responsible for keeping evaluator data in a separate trust
boundary.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_rsi import canonical, digest, fresh_json, identifier


SCHEMA = "minimal_prediction_lineage_v1"
LEDGER_SCHEMA = "minimal_prediction_lineage_ledger_v1"
CHECKPOINT_SCHEMA = "minimal_prediction_lineage_checkpoint_v1"
ZERO_HASH = "0" * 64
MEMORY_METRICS = {
    "candidate_brier",
    "market_brier",
    "candidate_minus_market_brier",
    "candidate_log_loss",
    "market_log_loss",
    "candidate_minus_market_log_loss",
    "coverage",
    "rows",
    "events",
    "dates",
}
SCORE_COMMITMENT_FIELDS = {
    "complete_mask_sha256",
    "dev_dataset_sha256",
    "trusted_rows_sha256",
    "public_rows_sha256",
    "candidate_records_sha256",
    "prediction_journal_sha256",
    "prediction_receipt_sha256",
    "scorer_spec_sha256",
    "full_score_sha256",
}
SCORE_FIELDS = MEMORY_METRICS | {"schema", "dev_id"} | SCORE_COMMITMENT_FIELDS


def _sha256(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError("lowercase SHA-256 commitment required")
    return value


def _finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("finite numeric aggregate required")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("finite numeric aggregate required")
    return value


def _positive_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("positive aggregate count required")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_json(path: Path, value: dict[str, Any]) -> None:
    pending = path.with_name(path.name + ".next")
    with pending.open("x") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)
    _fsync_directory(path.parent)


def _validate_memory(value: Any, *, expected: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "summary_code", "aggregate_metrics", "failure_codes"
    }:
        raise ValueError("memory must use the bounded aggregate-only schema")
    summary_code = value["summary_code"]
    if summary_code not in {"kept", "reverted"}:
        raise ValueError("memory summary code is not allowlisted")
    metrics = value["aggregate_metrics"]
    if (
        not isinstance(metrics, dict)
        or set(metrics) != MEMORY_METRICS
    ):
        raise ValueError("memory metrics are not approved aggregates")
    frozen_metrics: dict[str, int | float] = {}
    for key, raw in metrics.items():
        if key in {"rows", "events", "dates"}:
            frozen_metrics[key] = _positive_count(raw)
        else:
            frozen_metrics[key] = _finite(raw)
    failures = value["failure_codes"]
    if (
        not isinstance(failures, list)
        or len(failures) > 1
        or len(set(failures)) != len(failures)
        or any(item not in {"no_brier_improvement", "insufficient_breadth"} for item in failures)
    ):
        raise ValueError("failure memory must be a bounded unique list")
    frozen = {
        "summary_code": summary_code,
        "aggregate_metrics": frozen_metrics,
        "failure_codes": list(failures),
    }
    if frozen != expected:
        raise ValueError("memory must be the exact code-derived score projection")
    return frozen


def _validate_score(
    value: Any,
    *,
    expected_dev_id: str,
    expected_prediction_journal_sha256: str,
    expected_prediction_receipt_sha256: str,
    expected_public_rows_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SCORE_FIELDS:
        raise ValueError("score receipt must contain aggregate fields only")
    if value["schema"] != "minimal_prediction_score_receipt_v1":
        raise ValueError("unexpected score receipt schema")
    if identifier(value["dev_id"]) != expected_dev_id:
        raise ValueError("score receipt Dev identity mismatch")
    frozen: dict[str, Any] = {
        "schema": value["schema"],
        "dev_id": expected_dev_id,
    }
    for key in SCORE_COMMITMENT_FIELDS:
        frozen[key] = _sha256(value[key])
    if frozen["prediction_journal_sha256"] != expected_prediction_journal_sha256:
        raise ValueError("score receipt is not bound to the active prediction journal")
    if frozen["prediction_receipt_sha256"] != expected_prediction_receipt_sha256:
        raise ValueError("score receipt is not bound to the active prediction receipt")
    if frozen["public_rows_sha256"] != expected_public_rows_sha256:
        raise ValueError("score receipt is not bound to the active public rows")
    if frozen["trusted_rows_sha256"] != frozen["dev_dataset_sha256"]:
        raise ValueError("score receipt is not bound to the frozen Dev dataset")
    for key in MEMORY_METRICS:
        raw = value[key]
        frozen[key] = (
            _positive_count(raw) if key in {"rows", "events", "dates"} else _finite(raw)
        )
    if not 0.0 <= frozen["coverage"] <= 1.0:
        raise ValueError("coverage must be in [0,1]")
    if not 0.0 <= frozen["candidate_brier"] <= 1.0:
        raise ValueError("candidate Brier must be in [0,1]")
    if not 0.0 <= frozen["market_brier"] <= 1.0:
        raise ValueError("market Brier must be in [0,1]")
    if frozen["candidate_log_loss"] < 0.0 or frozen["market_log_loss"] < 0.0:
        raise ValueError("log loss cannot be negative")
    if frozen["events"] > frozen["rows"] or frozen["dates"] > frozen["rows"]:
        raise ValueError("breadth counts cannot exceed scored rows")
    if not math.isclose(
        frozen["candidate_minus_market_brier"],
        frozen["candidate_brier"] - frozen["market_brier"],
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("Brier delta is inconsistent")
    if not math.isclose(
        frozen["candidate_minus_market_log_loss"],
        frozen["candidate_log_loss"] - frozen["market_log_loss"],
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("log-loss delta is inconsistent")
    return frozen


def _derived_memory(
    rule: dict[str, Any], score: dict[str, Any], decision: str
) -> dict[str, Any]:
    failure_codes: list[str] = []
    if decision == "REVERT":
        failure_codes = [
            "no_brier_improvement"
            if score[rule["metric"]] >= rule["threshold"]
            else "insufficient_breadth"
        ]
    return {
        "summary_code": "kept" if decision == "KEEP" else "reverted",
        "aggregate_metrics": {key: score[key] for key in sorted(MEMORY_METRICS)},
        "failure_codes": failure_codes,
    }


class PredictionLineage:
    """One-parent experiment state machine backed by an append-only ledger."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.manifest_path = self.root / "manifest.json"
        self.ledger_path = self.root / "ledger.jsonl"
        self.checkpoint_path = self.root / "ledger-head.json"
        self.lock_path = self.root / ".lock"

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        experiment_id: str,
        initial_parent_sha256: str,
        keep_rule: dict[str, Any],
    ) -> "PredictionLineage":
        if not isinstance(keep_rule, dict) or set(keep_rule) != {
            "metric", "operator", "threshold", "minimum_rows", "minimum_events", "minimum_dates"
        }:
            raise ValueError("exact preregistered KEEP rule required")
        if (
            keep_rule["metric"] != "candidate_minus_market_brier"
            or keep_rule["operator"] != "<"
        ):
            raise ValueError("first-loop KEEP rule must minimize paired Brier delta")
        frozen_rule = {
            "metric": keep_rule["metric"],
            "operator": keep_rule["operator"],
            "threshold": _finite(keep_rule["threshold"]),
            "minimum_rows": _positive_count(keep_rule["minimum_rows"]),
            "minimum_events": _positive_count(keep_rule["minimum_events"]),
            "minimum_dates": _positive_count(keep_rule["minimum_dates"]),
        }
        root = Path(root).resolve()
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        obj = cls(root)
        manifest = {
            "schema": SCHEMA,
            "experiment_id": identifier(experiment_id),
            "initial_parent_sha256": _sha256(initial_parent_sha256),
            "keep_rule": frozen_rule,
            "policy": {
                "evaluation_role": "dev_only",
                "dev_receipts_per_id": 1,
                "final_feedback_allowed": False,
                "memory": "bounded_aggregates_only",
            },
        }
        fresh_json(obj.manifest_path, manifest)
        with obj.ledger_path.open("x") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        obj._write_checkpoint([])
        obj._append("created", {"manifest_sha256": digest(manifest)})
        obj.audit()
        return obj

    def _manifest(self) -> dict[str, Any]:
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise ValueError("lineage manifest missing or symlinked")
        value = json.loads(self.manifest_path.read_bytes())
        if (
            not isinstance(value, dict)
            or set(value) != {
                "schema", "experiment_id", "initial_parent_sha256", "keep_rule", "policy"
            }
            or value.get("schema") != SCHEMA
            or identifier(value.get("experiment_id")) != value["experiment_id"]
            or _sha256(value.get("initial_parent_sha256")) != value["initial_parent_sha256"]
            or value.get("policy") != {
                "evaluation_role": "dev_only",
                "dev_receipts_per_id": 1,
                "final_feedback_allowed": False,
                "memory": "bounded_aggregates_only",
            }
        ):
            raise ValueError("lineage manifest schema changed")
        keep_rule = value["keep_rule"]
        if (
            not isinstance(keep_rule, dict)
            or set(keep_rule) != {
                "metric", "operator", "threshold", "minimum_rows", "minimum_events", "minimum_dates"
            }
            or keep_rule["metric"] != "candidate_minus_market_brier"
            or keep_rule["operator"] != "<"
        ):
            raise ValueError("lineage KEEP rule changed")
        _finite(keep_rule["threshold"])
        for key in ("minimum_rows", "minimum_events", "minimum_dates"):
            _positive_count(keep_rule[key])
        return value

    def _events(self) -> list[dict[str, Any]]:
        if self.ledger_path.is_symlink():
            raise ValueError("lineage ledger cannot be a symlink")
        if not self.ledger_path.is_file():
            raise ValueError("lineage ledger is missing")
        if self.checkpoint_path.with_name(self.checkpoint_path.name + ".next").exists():
            raise ValueError("lineage checkpoint update is incomplete")
        if self.checkpoint_path.is_symlink() or not self.checkpoint_path.is_file():
            raise ValueError("lineage checkpoint is missing or symlinked")
        ledger_bytes = self.ledger_path.read_bytes()
        records: list[dict[str, Any]] = []
        previous = ZERO_HASH
        for line in ledger_bytes.splitlines():
            record = json.loads(line)
            if set(record) != {"schema", "seq", "previous", "time", "event", "payload", "hash"}:
                raise ValueError("unexpected lineage ledger fields")
            body = {key: record[key] for key in record if key != "hash"}
            if (
                record["schema"] != LEDGER_SCHEMA
                or record["seq"] != len(records)
                or record["previous"] != previous
                or record["hash"] != digest(body)
            ):
                raise ValueError("lineage ledger integrity failure")
            previous = record["hash"]
            records.append(record)
        checkpoint = json.loads(self.checkpoint_path.read_bytes())
        if checkpoint != {
            "schema": CHECKPOINT_SCHEMA,
            "ledger_entries": len(records),
            "ledger_head_sha256": records[-1]["hash"] if records else ZERO_HASH,
            "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "ledger_bytes": len(ledger_bytes),
        }:
            raise ValueError("lineage ledger differs from its durable checkpoint")
        return records

    def _write_checkpoint(self, records: list[dict[str, Any]]) -> None:
        ledger_bytes = self.ledger_path.read_bytes()
        _replace_json(self.checkpoint_path, {
            "schema": CHECKPOINT_SCHEMA,
            "ledger_entries": len(records),
            "ledger_head_sha256": records[-1]["hash"] if records else ZERO_HASH,
            "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "ledger_bytes": len(ledger_bytes),
        })

    def _append(self, event: str, payload: dict[str, Any]) -> None:
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            records = self._events()
            body = {
                "schema": LEDGER_SCHEMA,
                "seq": len(records),
                "previous": records[-1]["hash"] if records else ZERO_HASH,
                "time": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "payload": payload,
            }
            with self.ledger_path.open("a") as stream:
                record = {**body, "hash": digest(body)}
                stream.write(canonical(record) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._write_checkpoint([*records, record])
            fcntl.flock(lock, fcntl.LOCK_UN)

    def _state(self, manifest: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events or events[0]["event"] != "created" or events[0]["payload"] != {
            "manifest_sha256": digest(manifest)
        }:
            raise ValueError("lineage is not bound to its manifest")
        state: dict[str, Any] = {
            "parent_sha256": manifest["initial_parent_sha256"],
            "active_round": None,
            "used_round_ids": [],
            "used_dev_ids": [],
            "decisions": [],
            "memory": [],
        }
        for record in events[1:]:
            event = record["event"]
            payload = record["payload"]
            if event == "round_started":
                if not isinstance(payload, dict) or set(payload) != {
                    "round_id", "changed_stage", "candidate_sha256",
                    "prediction_journal_sha256", "prediction_receipt_sha256",
                    "public_rows_sha256", "dev_id", "evaluation_role",
                    "parent_before_sha256",
                }:
                    raise ValueError("unexpected round-start fields")
                identifier(payload["round_id"])
                identifier(payload["changed_stage"])
                identifier(payload["dev_id"])
                _sha256(payload["candidate_sha256"])
                _sha256(payload["prediction_journal_sha256"])
                _sha256(payload["prediction_receipt_sha256"])
                _sha256(payload["public_rows_sha256"])
                _sha256(payload["parent_before_sha256"])
                if payload["evaluation_role"] != "dev":
                    raise ValueError("non-Dev feedback entered the lineage")
                if state["active_round"] is not None:
                    raise ValueError("cannot overlap prediction rounds")
                if payload["round_id"] in state["used_round_ids"]:
                    raise ValueError("round identity replay")
                if payload["dev_id"] in state["used_dev_ids"]:
                    raise ValueError("Dev identity replay")
                if payload["parent_before_sha256"] != state["parent_sha256"]:
                    raise ValueError("round parent differs from current lineage")
                state["active_round"] = {**payload, "score_receipt": None, "score_receipt_sha256": None}
                state["used_round_ids"].append(payload["round_id"])
                state["used_dev_ids"].append(payload["dev_id"])
            elif event == "dev_score_bound":
                if not isinstance(payload, dict) or set(payload) != {
                    "round_id", "score_receipt", "score_receipt_sha256"
                }:
                    raise ValueError("unexpected Dev-score fields")
                active = state["active_round"]
                if active is None or active["score_receipt"] is not None:
                    raise ValueError("duplicate or unclaimed Dev score")
                if payload["round_id"] != active["round_id"]:
                    raise ValueError("score bound to the wrong round")
                score = _validate_score(
                    payload["score_receipt"],
                    expected_dev_id=active["dev_id"],
                    expected_prediction_journal_sha256=active["prediction_journal_sha256"],
                    expected_prediction_receipt_sha256=active["prediction_receipt_sha256"],
                    expected_public_rows_sha256=active["public_rows_sha256"],
                )
                if payload["score_receipt_sha256"] != digest(score):
                    raise ValueError("score receipt commitment mismatch")
                active["score_receipt"] = score
                active["score_receipt_sha256"] = payload["score_receipt_sha256"]
            elif event == "round_decided":
                active = state["active_round"]
                if active is None or active["score_receipt"] is None:
                    raise ValueError("decision lacks one bound Dev score")
                expected = self._expected_decision(manifest["keep_rule"], active["score_receipt"])
                parent_after = (
                    active["candidate_sha256"] if expected == "KEEP" else active["parent_before_sha256"]
                )
                expected_memory = _derived_memory(
                    manifest["keep_rule"], active["score_receipt"], expected
                )
                if payload != {
                    "round_id": active["round_id"],
                    "decision": expected,
                    "parent_before_sha256": active["parent_before_sha256"],
                    "parent_after_sha256": parent_after,
                    "score_receipt_sha256": active["score_receipt_sha256"],
                    "memory": _validate_memory(
                        payload.get("memory"), expected=expected_memory
                    ),
                }:
                    raise ValueError("decision differs from preregistered transition")
                state["parent_sha256"] = parent_after
                state["decisions"].append({key: payload[key] for key in payload if key != "memory"})
                state["memory"].append(payload["memory"])
                state["active_round"] = None
            else:
                raise ValueError("unknown lineage event")
        return state

    @staticmethod
    def _expected_decision(rule: dict[str, Any], score: dict[str, Any]) -> str:
        breadth_ok = (
            score["rows"] >= rule["minimum_rows"]
            and score["events"] >= rule["minimum_events"]
            and score["dates"] >= rule["minimum_dates"]
            and score["coverage"] == 1.0
        )
        improved = score[rule["metric"]] < rule["threshold"]
        return "KEEP" if breadth_ok and improved else "REVERT"

    def audit(self) -> dict[str, Any]:
        manifest = self._manifest()
        events = self._events()
        state = self._state(manifest, events)
        return {
            "schema": SCHEMA,
            "experiment_id": manifest["experiment_id"],
            "parent_sha256": state["parent_sha256"],
            "active_round": state["active_round"],
            "used_round_ids": list(state["used_round_ids"]),
            "used_dev_ids": list(state["used_dev_ids"]),
            "decisions": list(state["decisions"]),
            "memory": list(state["memory"]),
            "final_feedback_allowed": False,
            "ledger_tail_sha256": events[-1]["hash"],
            "ledger_checkpoint": json.loads(self.checkpoint_path.read_bytes()),
        }

    def start_round(
        self,
        *,
        round_id: str,
        changed_stage: str,
        candidate_sha256: str,
        prediction_journal_sha256: str,
        prediction_receipt_sha256: str,
        public_rows_sha256: str,
        dev_id: str,
        evaluation_role: str,
    ) -> dict[str, Any]:
        if evaluation_role != "dev":
            raise ValueError("only Dev feedback may enter research lineage; Final is sealed")
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            manifest = self._manifest()
            state = self._state(manifest, self._events())
            if state["active_round"] is not None:
                raise ValueError("a prediction round is already active")
            frozen_round = identifier(round_id)
            frozen_dev = identifier(dev_id)
            if frozen_round in state["used_round_ids"] or frozen_dev in state["used_dev_ids"]:
                raise ValueError("round or Dev identity already consumed")
            payload = {
                "round_id": frozen_round,
                "changed_stage": identifier(changed_stage),
                "candidate_sha256": _sha256(candidate_sha256),
                "prediction_journal_sha256": _sha256(prediction_journal_sha256),
                "prediction_receipt_sha256": _sha256(prediction_receipt_sha256),
                "public_rows_sha256": _sha256(public_rows_sha256),
                "dev_id": frozen_dev,
                "evaluation_role": "dev",
                "parent_before_sha256": state["parent_sha256"],
            }
            self._append_unlocked("round_started", payload)
            fcntl.flock(lock, fcntl.LOCK_UN)
        return self.audit()

    def bind_dev_score(self, *, round_id: str, score_receipt: dict[str, Any]) -> dict[str, Any]:
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            manifest = self._manifest()
            state = self._state(manifest, self._events())
            active = state["active_round"]
            if active is None or active["round_id"] != identifier(round_id):
                raise ValueError("no matching active round")
            if active["score_receipt"] is not None:
                raise ValueError("Dev score is one-shot")
            frozen_score = _validate_score(
                score_receipt,
                expected_dev_id=active["dev_id"],
                expected_prediction_journal_sha256=active["prediction_journal_sha256"],
                expected_prediction_receipt_sha256=active["prediction_receipt_sha256"],
                expected_public_rows_sha256=active["public_rows_sha256"],
            )
            self._append_unlocked("dev_score_bound", {
                "round_id": active["round_id"],
                "score_receipt": frozen_score,
                "score_receipt_sha256": digest(frozen_score),
            })
            fcntl.flock(lock, fcntl.LOCK_UN)
        return self.audit()

    def decide(self, *, round_id: str) -> dict[str, Any]:
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            manifest = self._manifest()
            state = self._state(manifest, self._events())
            active = state["active_round"]
            if active is None or active["round_id"] != identifier(round_id):
                raise ValueError("no matching active round")
            if active["score_receipt"] is None:
                raise ValueError("cannot decide before the one-shot Dev score")
            decision = self._expected_decision(manifest["keep_rule"], active["score_receipt"])
            frozen_memory = _derived_memory(
                manifest["keep_rule"], active["score_receipt"], decision
            )
            parent_after = (
                active["candidate_sha256"] if decision == "KEEP" else active["parent_before_sha256"]
            )
            self._append_unlocked("round_decided", {
                "round_id": active["round_id"],
                "decision": decision,
                "parent_before_sha256": active["parent_before_sha256"],
                "parent_after_sha256": parent_after,
                "score_receipt_sha256": active["score_receipt_sha256"],
                "memory": frozen_memory,
            })
            fcntl.flock(lock, fcntl.LOCK_UN)
        return self.audit()

    def _append_unlocked(self, event: str, payload: dict[str, Any]) -> None:
        records = self._events()
        body = {
            "schema": LEDGER_SCHEMA,
            "seq": len(records),
            "previous": records[-1]["hash"] if records else ZERO_HASH,
            "time": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        with self.ledger_path.open("a") as stream:
            record = {**body, "hash": digest(body)}
            stream.write(canonical(record) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._write_checkpoint([*records, record])
