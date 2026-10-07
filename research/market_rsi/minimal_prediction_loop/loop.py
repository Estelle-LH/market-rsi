"""Two-round synthetic proof for the minimal prediction-first loop.

This runner deliberately uses synthetic rows and a trusted in-process fixture.
It demonstrates the information-flow and state transitions needed before any
real-data or isolation canary is considered.  It is not evidence of predictive
improvement and grants no promotion or trading authority.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from data_lifecycle import DataLifecycle, LEDGER_NAME
from market_rsi import canonical, digest, fresh_json, identifier

from .lineage import PredictionLineage
from .prediction_protocol import (
    LabelFreePredictionProtocol,
    prediction_submission,
    run_label_free_protocol,
)
from .probability_contract import build_candidate_views
from .proper_scoring import ProperScoreSpec, score_probability_forecasts


SCHEMA = "minimal_prediction_two_round_synthetic_loop_v1"
DAY_MS = 86_400_000
BASE_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
LIFECYCLE_CHECKPOINT_SCHEMA = "minimal_prediction_lifecycle_checkpoint_v1"
TRUSTED_SCORE_DIRECTORY = "trusted-score-artifacts"


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


class _CheckpointedLifecycle:
    """DataLifecycle adapter with an externally expected durable ledger head."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.lifecycle = DataLifecycle(self.root)
        self.ledger_path = self.root / LEDGER_NAME
        self.checkpoint_path = self.root / "trusted-ledger-head.json"
        self.lock_path = self.root / ".trusted-checkpoint.lock"

    @classmethod
    def create(cls, root: Path, **kwargs: Any) -> "_CheckpointedLifecycle":
        DataLifecycle.create(root, **kwargs)
        obj = cls(root)
        obj._write_checkpoint()
        obj.audit()
        return obj

    @classmethod
    def resume(cls, root: Path) -> "_CheckpointedLifecycle":
        obj = cls(root)
        obj.audit()
        return obj

    @contextmanager
    def _locked(self):
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _observed_checkpoint(self) -> dict[str, Any]:
        if self.ledger_path.is_symlink() or not self.ledger_path.is_file():
            raise ValueError("data lifecycle ledger is missing or symlinked")
        ledger_bytes = self.ledger_path.read_bytes()
        audit = self.lifecycle.audit()
        return {
            "schema": LIFECYCLE_CHECKPOINT_SCHEMA,
            "ledger_entries": len(ledger_bytes.splitlines()),
            "ledger_head_sha256": audit["ledger_tail_sha256"],
            "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "ledger_bytes": len(ledger_bytes),
        }

    def _verify_checkpoint(self) -> dict[str, Any]:
        if self.checkpoint_path.with_name(self.checkpoint_path.name + ".next").exists():
            raise ValueError("data lifecycle checkpoint update is incomplete")
        if self.checkpoint_path.is_symlink() or not self.checkpoint_path.is_file():
            raise ValueError("data lifecycle checkpoint is missing or symlinked")
        checkpoint = json.loads(self.checkpoint_path.read_bytes())
        if checkpoint != self._observed_checkpoint():
            raise ValueError("data lifecycle ledger differs from its durable checkpoint")
        return checkpoint

    def _write_checkpoint(self) -> dict[str, Any]:
        checkpoint = self._observed_checkpoint()
        _replace_json(self.checkpoint_path, checkpoint)
        return checkpoint

    def audit(self) -> dict[str, Any]:
        with self._locked():
            checkpoint = self._verify_checkpoint()
            return {**self.lifecycle.audit(), "ledger_checkpoint": checkpoint}

    def controller_view(self, round_id: str) -> dict:
        with self._locked():
            self._verify_checkpoint()
            return self.lifecycle.controller_view(round_id)

    def frozen_dev_commitment(self, round_id: str, dev_id: str) -> str:
        """Return the exact Dev content commitment frozen in the manifest."""

        with self._locked():
            self._verify_checkpoint()
            frozen_round_id = identifier(round_id)
            frozen_dev_id = identifier(dev_id)
            matches = [
                item
                for item in self.lifecycle._manifest()["rounds"]
                if item["round_id"] == frozen_round_id
            ]
            if len(matches) != 1:
                raise ValueError("exactly one frozen lifecycle round required")
            dev_datasets = matches[0]["dev_datasets"]
            if len(dev_datasets) != 1 or dev_datasets[0]["dataset_id"] != frozen_dev_id:
                raise ValueError("exactly one matching frozen Dev dataset required")
            return dev_datasets[0]["content_sha256"]

    def claim_dev_score(self, round_id: str, *, candidate_set_sha256: str) -> dict:
        with self._locked():
            self._verify_checkpoint()
            result = self.lifecycle.claim_dev_score(
                round_id, candidate_set_sha256=candidate_set_sha256
            )
            self._write_checkpoint()
            return result

    def complete_dev_score(self, round_id: str, *, score_receipt_sha256: str) -> dict:
        with self._locked():
            self._verify_checkpoint()
            result = self.lifecycle.complete_dev_score(
                round_id, score_receipt_sha256=score_receipt_sha256
            )
            self._write_checkpoint()
            return result


def _row(
    event_id: str,
    market_id: str,
    cutoff_day: int,
    outcome_day: int,
    market_probability: float,
    outcome: int,
) -> dict:
    cutoff_ms = BASE_MS + cutoff_day * DAY_MS
    return {
        "event_id": event_id,
        "market_id": market_id,
        "cutoff_ms": cutoff_ms,
        "feature_available_ms": cutoff_ms,
        "market_probability": market_probability,
        "outcome_available_ms": BASE_MS + outcome_day * DAY_MS,
        "outcome": outcome,
    }


def _synthetic_rows() -> dict[str, list[dict]]:
    train_round_1 = [
        _row("history-a", "history-a-yes", 0, 1, 0.55, 1),
        _row("history-b", "history-b-yes", 0, 1, 0.45, 0),
    ]
    dev_round_1 = [
        _row("event-a", "event-a-yes", day, 5, 0.60, 1)
        for day in (3, 4)
    ] + [
        _row("event-b", "event-b-yes", day, 5, 0.40, 0)
        for day in (3, 4)
    ]
    train_round_2_base = [
        _row("history-c", "history-c-yes", 6, 7, 0.55, 1),
        _row("history-d", "history-d-yes", 6, 7, 0.45, 0),
    ]
    dev_round_2 = [
        _row("event-c", "event-c-yes", day, 10, 0.60, 1)
        for day in (8, 9)
    ] + [
        _row("event-d", "event-d-yes", day, 10, 0.40, 0)
        for day in (8, 9)
    ]
    # The scorer canonicalizes by cutoff/event/market; keeping fixtures in that
    # order also makes the protocol's strict ordering explicit.
    return {
        "train_round_1": sorted(
            train_round_1, key=lambda row: (row["cutoff_ms"], row["event_id"], row["market_id"])
        ),
        "dev_round_1": sorted(
            dev_round_1, key=lambda row: (row["cutoff_ms"], row["event_id"], row["market_id"])
        ),
        "train_round_2_base": sorted(
            train_round_2_base,
            key=lambda row: (row["cutoff_ms"], row["event_id"], row["market_id"]),
        ),
        "dev_round_2": sorted(
            dev_round_2, key=lambda row: (row["cutoff_ms"], row["event_id"], row["market_id"])
        ),
    }


def _dataset(dataset_id: str, rows: list[dict]) -> dict:
    return {"dataset_id": dataset_id, "content_sha256": digest(rows)}


def _score_receipt(
    dev_id: str,
    score: dict,
    *,
    dev_dataset_sha256: str,
    prediction_journal_sha256: str,
    prediction_receipt_sha256: str,
) -> dict:
    return {
        "schema": "minimal_prediction_score_receipt_v1",
        "dev_id": dev_id,
        "dev_dataset_sha256": dev_dataset_sha256,
        "complete_mask_sha256": score["input_commitments"]["complete_mask_sha256"],
        "trusted_rows_sha256": score["input_commitments"]["trusted_rows_sha256"],
        "public_rows_sha256": score["input_commitments"]["public_rows_sha256"],
        "candidate_records_sha256": score["input_commitments"]["candidate_records_sha256"],
        "prediction_journal_sha256": prediction_journal_sha256,
        "prediction_receipt_sha256": prediction_receipt_sha256,
        "scorer_spec_sha256": score["input_commitments"]["scorer_spec_sha256"],
        "full_score_sha256": score["score_receipt_sha256"],
        **score["aggregate_metrics"],
    }


def _trusted_score_artifact_path(
    root: Path, *, round_id: str, full_score_sha256: str
) -> Path:
    return (
        root
        / TRUSTED_SCORE_DIRECTORY
        / f"{identifier(round_id)}-{full_score_sha256}.json"
    )


def _persist_trusted_score_artifact(
    root: Path, *, round_id: str, score: dict
) -> tuple[Path, dict]:
    """Persist the canonical trusted score body under its declared digest."""

    full_score_sha256 = score.get("score_receipt_sha256")
    body = {key: value for key, value in score.items() if key != "score_receipt_sha256"}
    if digest(body) != full_score_sha256:
        raise ValueError("full trusted score does not match its declared commitment")
    directory = root / TRUSTED_SCORE_DIRECTORY
    if directory.exists():
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("trusted score artifact directory is not a real directory")
    else:
        directory.mkdir(mode=0o700)
        _fsync_directory(root)
    path = _trusted_score_artifact_path(
        root, round_id=round_id, full_score_sha256=full_score_sha256
    )
    with path.open("xb") as stream:
        stream.write(canonical(body).encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(directory)
    return _verify_trusted_score_artifact(
        root, round_id=round_id, full_score_sha256=full_score_sha256
    )


def _verify_trusted_score_artifact(
    root: Path, *, round_id: str, full_score_sha256: str
) -> tuple[Path, dict]:
    path = _trusted_score_artifact_path(
        root, round_id=round_id, full_score_sha256=full_score_sha256
    )
    if path.is_symlink() or not path.is_file():
        raise ValueError("trusted score artifact is missing or symlinked")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != full_score_sha256:
        raise ValueError("trusted score artifact bytes differ from the bound score")
    try:
        body = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("trusted score artifact is not canonical JSON") from error
    if canonical(body).encode("utf-8") != payload or digest(body) != full_score_sha256:
        raise ValueError("trusted score artifact is not the bound canonical score")
    if not isinstance(body, dict):
        raise ValueError("trusted score artifact body must be an object")
    return path, body


def _score_receipt_from_artifact(
    *,
    dev_id: str,
    dev_dataset_sha256: str,
    prediction_journal_sha256: str,
    prediction_receipt_sha256: str,
    full_score_sha256: str,
    score_body: dict,
) -> dict:
    score = {**score_body, "score_receipt_sha256": full_score_sha256}
    return _score_receipt(
        dev_id,
        score,
        dev_dataset_sha256=dev_dataset_sha256,
        prediction_journal_sha256=prediction_journal_sha256,
        prediction_receipt_sha256=prediction_receipt_sha256,
    )


def _run_round(
    root: Path,
    *,
    round_id: str,
    dev_id: str,
    train_rows: list[dict],
    dev_rows: list[dict],
    candidate_name: str,
    probabilities: dict[str, float],
    lifecycle: _CheckpointedLifecycle,
    lineage: PredictionLineage,
) -> dict:
    candidate_sha256 = digest({
        "schema": "synthetic_candidate_fixture_v1",
        "candidate_name": candidate_name,
        "event_probabilities": probabilities,
    })
    views = build_candidate_views(train_rows, dev_rows)
    def predict(release: dict) -> dict:
        if set(release).intersection({
            "outcome", "label", "outcome_available_ms", "evaluator_path", "final"
        }):
            raise AssertionError("candidate-visible release contains a forbidden field")
        probability = probabilities[release["event_id"]]
        return prediction_submission(release, probability)

    protocol_receipt = run_label_free_protocol(
        root / "prediction-runs",
        run_key=round_id,
        candidate_sha256=candidate_sha256,
        public_rows=views["evaluation"],
        predict=predict,
    )
    if protocol_receipt["real_isolation_admitted"] is not False:
        raise ValueError("synthetic protocol must not claim real isolation")

    with LabelFreePredictionProtocol.resume(
        root / "prediction-runs",
        candidate_sha256=candidate_sha256,
        public_rows=views["evaluation"],
        run_id=protocol_receipt["run_id"],
    ) as verified_protocol:
        if verified_protocol.completion_receipt() != protocol_receipt:
            raise ValueError("prediction completion receipt changed before scoring")
        verified_predictions = verified_protocol.prediction_records()

    dev_dataset_sha256 = lifecycle.frozen_dev_commitment(round_id, dev_id)
    lifecycle.claim_dev_score(round_id, candidate_set_sha256=candidate_sha256)
    lineage.start_round(
        round_id=round_id,
        changed_stage="prediction",
        candidate_sha256=candidate_sha256,
        prediction_journal_sha256=protocol_receipt["journal_sha256"],
        prediction_receipt_sha256=protocol_receipt["receipt_sha256"],
        public_rows_sha256=protocol_receipt["public_rows_sha256"],
        dev_id=dev_id,
        evaluation_role="dev",
    )
    score = score_probability_forecasts(
        dev_rows,
        verified_predictions,
        spec=ProperScoreSpec(bootstrap_replicates=200),
    )
    if score["input_commitments"]["public_rows_sha256"] != protocol_receipt["public_rows_sha256"]:
        raise ValueError("scorer public rows differ from the verified prediction protocol")
    if score["input_commitments"]["trusted_rows_sha256"] != dev_dataset_sha256:
        raise ValueError("scored trusted rows differ from the frozen Dev dataset commitment")
    score_artifact, score_body = _persist_trusted_score_artifact(
        root, round_id=round_id, score=score
    )
    compact_score = _score_receipt_from_artifact(
        dev_id=dev_id,
        dev_dataset_sha256=dev_dataset_sha256,
        prediction_journal_sha256=protocol_receipt["journal_sha256"],
        prediction_receipt_sha256=protocol_receipt["receipt_sha256"],
        full_score_sha256=score["score_receipt_sha256"],
        score_body=score_body,
    )
    lineage.bind_dev_score(round_id=round_id, score_receipt=compact_score)
    expected_decision = (
        "KEEP" if compact_score["candidate_minus_market_brier"] < 0.0 else "REVERT"
    )
    lifecycle.complete_dev_score(
        round_id, score_receipt_sha256=compact_score["full_score_sha256"]
    )
    lifecycle_state = lifecycle.audit()
    if round_id not in lifecycle_state["completed_rounds"]:
        raise ValueError("Dev was not durably promoted before parent decision")
    lineage_state = lineage.decide(round_id=round_id)
    actual_decision = lineage_state["decisions"][-1]["decision"]
    if actual_decision != expected_decision:
        raise ValueError("lineage decision differs from the preregistered synthetic expectation")
    return {
        "round_id": round_id,
        "dev_id": dev_id,
        "candidate_sha256": candidate_sha256,
        "protocol_run_id": protocol_receipt["run_id"],
        "prediction_journal_sha256": protocol_receipt["journal_sha256"],
        "prediction_receipt_sha256": protocol_receipt["receipt_sha256"],
        "score_receipt_sha256": compact_score["full_score_sha256"],
        "score_artifact_relative_path": str(score_artifact.relative_to(root)),
        "score_receipt": compact_score,
        "decision": actual_decision,
        "parent_after_sha256": lineage_state["parent_sha256"],
        "lifecycle_checkpoint": lifecycle_state["ledger_checkpoint"],
        "lineage_checkpoint": lineage_state["ledger_checkpoint"],
        "real_isolation_admitted": False,
    }


def recover_bound_round(root: str | Path, *, round_id: str) -> dict:
    """Finish the safe post-score crash window without rescoring or replay."""

    root = Path(root).resolve()
    lifecycle = _CheckpointedLifecycle.resume(root / "data-lifecycle")
    lineage = PredictionLineage(root / "lineage")
    lineage_before = lineage.audit()
    active = lineage_before["active_round"]
    if active is None or active["round_id"] != round_id:
        raise ValueError("no exact score-bound lineage round is recoverable")
    score = active["score_receipt"]
    if score is None:
        raise ValueError("recovery cannot score or recreate missing Dev evidence")
    dev_dataset_sha256 = lifecycle.frozen_dev_commitment(round_id, active["dev_id"])
    if (
        score["dev_dataset_sha256"] != dev_dataset_sha256
        or score["trusted_rows_sha256"] != dev_dataset_sha256
    ):
        raise ValueError("bound score differs from the frozen Dev dataset commitment")
    score_artifact, score_body = _verify_trusted_score_artifact(
        root,
        round_id=round_id,
        full_score_sha256=score["full_score_sha256"],
    )
    expected_score = _score_receipt_from_artifact(
        dev_id=active["dev_id"],
        dev_dataset_sha256=dev_dataset_sha256,
        prediction_journal_sha256=active["prediction_journal_sha256"],
        prediction_receipt_sha256=active["prediction_receipt_sha256"],
        full_score_sha256=score["full_score_sha256"],
        score_body=score_body,
    )
    if score != expected_score:
        raise ValueError("compact lineage score differs from the trusted score artifact")
    lifecycle_before = lifecycle.audit()
    claim = lifecycle_before["active_dev_claim"]
    if claim is not None:
        if (
            claim["round_id"] != round_id
            or claim["candidate_set_sha256"] != active["candidate_sha256"]
        ):
            raise ValueError("lifecycle claim differs from the score-bound lineage round")
        lifecycle.complete_dev_score(
            round_id, score_receipt_sha256=score["full_score_sha256"]
        )
    elif round_id not in lifecycle_before["completed_rounds"]:
        raise ValueError("lifecycle has neither the exact active claim nor completion")
    lifecycle_after = lifecycle.audit()
    if round_id not in lifecycle_after["completed_rounds"]:
        raise ValueError("Dev promotion is not durably complete")
    lineage_after = lineage.decide(round_id=round_id)
    return {
        "round_id": round_id,
        "decision": lineage_after["decisions"][-1]["decision"],
        "parent_after_sha256": lineage_after["parent_sha256"],
        "score_receipt_sha256": score["full_score_sha256"],
        "score_artifact_relative_path": str(score_artifact.relative_to(root)),
        "lifecycle_checkpoint": lifecycle_after["ledger_checkpoint"],
        "lineage_checkpoint": lineage_after["ledger_checkpoint"],
        "recovered_without_rescore": True,
    }


def run_two_round_synthetic_loop(root: str | Path) -> dict:
    """Run one synthetic KEEP followed by one synthetic REVERT exactly once."""

    root = Path(root).resolve()
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    rows = _synthetic_rows()
    final_commitment = digest({"schema": "sealed_synthetic_final_v1", "opened": False})
    lifecycle = _CheckpointedLifecycle.create(
        root / "data-lifecycle",
        experiment_id="prediction-first-synthetic-loop",
        rounds=[
            {
                "round_id": "round-1",
                "train_datasets": [_dataset("train-1", rows["train_round_1"])],
                "dev_datasets": [_dataset("dev-1", rows["dev_round_1"])],
            },
            {
                "round_id": "round-2",
                "train_datasets": [_dataset("train-2", rows["train_round_2_base"])],
                "dev_datasets": [_dataset("dev-2", rows["dev_round_2"])],
            },
        ],
        transfer_datasets=[{
            "dataset_id": "final-sealed-1",
            "content_sha256": final_commitment,
        }],
    )
    initial_parent_sha256 = digest({
        "schema": "synthetic_parent_v1",
        "name": "decision-time-market-probability",
    })
    lineage = PredictionLineage.create(
        root / "lineage",
        experiment_id="prediction-first-synthetic-loop",
        initial_parent_sha256=initial_parent_sha256,
        keep_rule={
            "metric": "candidate_minus_market_brier",
            "operator": "<",
            "threshold": 0.0,
            "minimum_rows": 4,
            "minimum_events": 2,
            "minimum_dates": 2,
        },
    )

    round_1_view = lifecycle.controller_view("round-1")
    first = _run_round(
        root,
        round_id="round-1",
        dev_id="dev-1",
        train_rows=rows["train_round_1"],
        dev_rows=rows["dev_round_1"],
        candidate_name="synthetic-better-than-market",
        probabilities={"event-a": 0.80, "event-b": 0.20},
        lifecycle=lifecycle,
        lineage=lineage,
    )
    if first["decision"] != "KEEP":
        raise ValueError("first synthetic round must KEEP")

    # Exercise restart read-back between rounds.  The consumed first Dev block
    # must now be present only as a Train commitment in the second-round view.
    lifecycle = _CheckpointedLifecycle.resume(root / "data-lifecycle")
    lineage = PredictionLineage(root / "lineage")
    second_view = lifecycle.controller_view("round-2")
    promoted = {
        item["dataset_id"]: item["origin_role"]
        for item in second_view["train_full_access"]
    }
    if promoted.get("dev-1") != "dev":
        raise ValueError("consumed first-round Dev was not promoted to later Train")
    with LabelFreePredictionProtocol.resume(
        root / "prediction-runs",
        candidate_sha256=first["candidate_sha256"],
        public_rows=build_candidate_views(
            rows["train_round_1"], rows["dev_round_1"]
        )["evaluation"],
        run_id=first["protocol_run_id"],
    ) as restarted_protocol:
        restarted_receipt = restarted_protocol.completion_receipt()
    if restarted_receipt["receipt_sha256"] != first["prediction_receipt_sha256"]:
        raise ValueError("completed first-round prediction receipt changed after restart")

    second = _run_round(
        root,
        round_id="round-2",
        dev_id="dev-2",
        train_rows=rows["dev_round_1"] + rows["train_round_2_base"],
        dev_rows=rows["dev_round_2"],
        candidate_name="synthetic-worse-than-market",
        probabilities={"event-c": 0.20, "event-d": 0.80},
        lifecycle=lifecycle,
        lineage=lineage,
    )
    if second["decision"] != "REVERT":
        raise ValueError("second synthetic round must REVERT")

    final_lifecycle = _CheckpointedLifecycle.resume(root / "data-lifecycle").audit()
    final_lineage = PredictionLineage(root / "lineage").audit()
    if (
        final_lifecycle["transfer_submissions_frozen"]
        or final_lifecycle["transfer_scored"]
        or final_lineage["active_round"] is not None
    ):
        raise ValueError("synthetic loop crossed its sealed-Final boundary")
    if final_lineage["parent_sha256"] != first["candidate_sha256"]:
        raise ValueError("REVERT changed the kept parent")

    receipt = {
        "schema": SCHEMA,
        "scope": "synthetic_orchestration_only",
        "rounds": [first, second],
        "decisions": [first["decision"], second["decision"]],
        "initial_parent_sha256": initial_parent_sha256,
        "final_parent_sha256": final_lineage["parent_sha256"],
        "used_round_ids": final_lineage["used_round_ids"],
        "used_dev_ids": final_lineage["used_dev_ids"],
        "promoted_dev_ids": final_lifecycle["promoted_dev_ids"],
        "ledger_checkpoints": {
            "lifecycle": final_lifecycle["ledger_checkpoint"],
            "lineage": final_lineage["ledger_checkpoint"],
        },
        "round_1_dev_promoted_into_round_2_train": promoted.get("dev-1") == "dev",
        "restart_receipts_stable": True,
        "candidate_views": {
            "round_1_dev_labels_visible": round_1_view["dev_labels_visible"],
            "round_1_final_visible": round_1_view["transfer_visible"],
            "round_2_dev_labels_visible": second_view["dev_labels_visible"],
            "round_2_final_visible": second_view["transfer_visible"],
        },
        "authority": {
            "real_data_admitted": False,
            "real_isolation_admitted": False,
            "provider_calls": 0,
            "network_calls": 0,
            "paid_calls": 0,
            "protected_dev_opened": False,
            "final_opened": False,
            "final_scored": False,
            "promotion_authorized": False,
            "pnl_evaluated": False,
            "pmb_used": False,
        },
        "claim": (
            "reproducible synthetic KEEP/REVERT orchestration only; no predictive, "
            "isolation, data-admission, promotion, PnL, or PMB evidence"
        ),
    }
    receipt["receipt_sha256"] = digest(receipt)
    fresh_json(root / "integration-receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    result = run_two_round_synthetic_loop(args.output)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
