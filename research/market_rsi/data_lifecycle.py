"""Fail-closed data lifecycle for the Codex/GLM research harness.

The controller may read every item that has become learning data.  Current Dev
labels and sealed Transfer data remain runner-owned.  A Dev block is scored at
most once; the same atomic ledger event then promotes it into the next round's
Train pool.  This is enforced state, not a prompt instruction.

This module stores commitments and access state, not market rows or labels.
The workspace materializer must use ``controller_view`` before mounting data.
"""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier


SCHEMA = "market_data_lifecycle_v1"
VIEW_SCHEMA = "market_controller_data_view_v1"
ZERO_HASH = "0" * 64
LEDGER_NAME = "data-exposure-ledger.jsonl"


def _sha256(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError("lowercase SHA-256 commitment required")
    return value


def _dataset(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"dataset_id", "content_sha256"}:
        raise ValueError("dataset requires only ID and content commitment")
    return {
        "dataset_id": identifier(value["dataset_id"]),
        "content_sha256": _sha256(value["content_sha256"]),
    }


def _event_body(seq: int, previous: str, event: str, payload: dict) -> dict:
    return {
        "seq": seq,
        "previous": previous,
        "time": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "payload": payload,
    }


class DataLifecycle:
    """Runner-owned state machine for one permanent experiment lineage."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.manifest_path = self.root / "manifest.json"
        self.ledger_path = self.root / LEDGER_NAME
        self.lock_path = self.root / ".lock"

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        experiment_id: str,
        rounds: list[dict],
        transfer_datasets: list[dict],
    ) -> "DataLifecycle":
        identifier(experiment_id)
        if not isinstance(rounds, list) or not rounds:
            raise ValueError("at least one ordered learning round required")
        if not isinstance(transfer_datasets, list) or not transfer_datasets:
            raise ValueError("sealed Transfer datasets required")

        frozen_rounds = []
        dataset_ids: set[str] = set()
        for index, round_spec in enumerate(rounds):
            if not isinstance(round_spec, dict) or set(round_spec) != {
                "round_id", "train_datasets", "dev_datasets"
            }:
                raise ValueError("unexpected learning-round fields")
            round_id = identifier(round_spec["round_id"])
            train = [_dataset(item) for item in round_spec["train_datasets"]]
            dev = [_dataset(item) for item in round_spec["dev_datasets"]]
            if not train or not dev:
                raise ValueError("each round needs nonempty Train and Dev")
            current_ids = [item["dataset_id"] for item in train + dev]
            if len(set(current_ids)) != len(current_ids) or dataset_ids.intersection(current_ids):
                raise ValueError("dataset reused across rounds or roles")
            dataset_ids.update(current_ids)
            frozen_rounds.append({
                "round_index": index,
                "round_id": round_id,
                "train_datasets": train,
                "dev_datasets": dev,
            })

        transfer = [_dataset(item) for item in transfer_datasets]
        transfer_ids = [item["dataset_id"] for item in transfer]
        if (
            len(set(transfer_ids)) != len(transfer_ids)
            or dataset_ids.intersection(transfer_ids)
        ):
            raise ValueError("Transfer datasets overlap learning data")

        root = Path(root).resolve()
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        obj = cls(root)
        manifest = {
            "schema": SCHEMA,
            "experiment_id": experiment_id,
            "rounds": frozen_rounds,
            "transfer_datasets": transfer,
            "policy": {
                "controller_reads_all_learning_data": True,
                "current_dev_labels_visible": False,
                "dev_scores_per_block": 1,
                "dev_after_score": "train",
                "reuse_consumed_dev_for_evaluation": False,
                "transfer_labels_visible_before_final_freeze": False,
            },
            "source_sha256": file_hash(__file__),
        }
        fresh_json(obj.manifest_path, manifest)
        obj._append("created", {"manifest_sha256": digest(manifest)})
        obj.audit()
        return obj

    def _manifest(self) -> dict:
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise ValueError("data-lifecycle manifest missing or symlinked")
        manifest = json.loads(self.manifest_path.read_bytes())
        if (
            manifest.get("schema") != SCHEMA
            or manifest.get("source_sha256") != file_hash(__file__)
        ):
            raise ValueError("data-lifecycle source or schema changed")
        return manifest

    def _events(self) -> list[dict]:
        records, previous = [], ZERO_HASH
        if not self.ledger_path.exists():
            return records
        if self.ledger_path.is_symlink() or not self.ledger_path.is_file():
            raise ValueError("data-exposure ledger missing or symlinked")
        for line in self.ledger_path.read_text().splitlines():
            record = json.loads(line)
            if set(record) != {"seq", "previous", "time", "event", "payload", "hash"}:
                raise ValueError("unexpected data-exposure event fields")
            body = {key: record[key] for key in record if key != "hash"}
            if (
                body["seq"] != len(records)
                or body["previous"] != previous
                or record["hash"] != digest(body)
            ):
                raise ValueError("data-exposure ledger integrity failure")
            previous = record["hash"]
            records.append(record)
        return records

    def _append(self, event: str, payload: dict) -> None:
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            records = self._events()
            body = _event_body(
                len(records), records[-1]["hash"] if records else ZERO_HASH, event, payload
            )
            with self.ledger_path.open("a") as stream:
                stream.write(canonical({**body, "hash": digest(body)}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            fcntl.flock(lock, fcntl.LOCK_UN)

    def _state(self, manifest: dict, events: list[dict]) -> dict:
        if not events or events[0]["event"] != "created" or events[0]["payload"] != {
            "manifest_sha256": digest(manifest)
        }:
            raise ValueError("data lifecycle was not bound to this manifest")
        state = {
            "completed_rounds": [],
            "active_dev_claim": None,
            "promoted_dev_ids": [],
            "transfer_submissions_sha256": None,
            "transfer_scored": False,
        }
        rounds = manifest["rounds"]
        for record in events[1:]:
            event, payload = record["event"], record["payload"]
            next_index = len(state["completed_rounds"])
            if event == "dev_scoring_claimed":
                if state["active_dev_claim"] is not None or next_index >= len(rounds):
                    raise ValueError("duplicate or out-of-order Dev scoring claim")
                expected = rounds[next_index]
                if payload != {
                    "round_id": expected["round_id"],
                    "candidate_set_sha256": _sha256(payload.get("candidate_set_sha256")),
                    "dev_dataset_ids": [item["dataset_id"] for item in expected["dev_datasets"]],
                }:
                    raise ValueError("Dev claim differs from frozen round")
                state["active_dev_claim"] = payload
            elif event == "dev_scored_and_promoted":
                if state["active_dev_claim"] is None or next_index >= len(rounds):
                    raise ValueError("Dev completion lacks exact claim")
                expected = rounds[next_index]
                promoted = [item["dataset_id"] for item in expected["dev_datasets"]]
                if payload != {
                    "round_id": expected["round_id"],
                    "candidate_set_sha256": state["active_dev_claim"]["candidate_set_sha256"],
                    "score_receipt_sha256": _sha256(payload.get("score_receipt_sha256")),
                    "transition": {"from": "dev_sealed", "to": "train"},
                    "promoted_dataset_ids": promoted,
                }:
                    raise ValueError("Dev promotion differs from frozen claim")
                state["completed_rounds"].append(expected["round_id"])
                state["promoted_dev_ids"].extend(promoted)
                state["active_dev_claim"] = None
            elif event == "transfer_submissions_frozen":
                if (
                    state["active_dev_claim"] is not None
                    or len(state["completed_rounds"]) != len(rounds)
                    or state["transfer_submissions_sha256"] is not None
                ):
                    raise ValueError("Transfer submissions frozen at an invalid time")
                state["transfer_submissions_sha256"] = _sha256(
                    payload.get("submissions_sha256")
                )
                if payload != {
                    "submissions_sha256": state["transfer_submissions_sha256"],
                    "transfer_dataset_ids": [
                        item["dataset_id"] for item in manifest["transfer_datasets"]
                    ],
                }:
                    raise ValueError("Transfer freeze differs from manifest")
            elif event == "transfer_scored":
                if (
                    state["transfer_submissions_sha256"] is None
                    or state["transfer_scored"]
                ):
                    raise ValueError("Transfer scored without one final freeze")
                if payload != {
                    "submissions_sha256": state["transfer_submissions_sha256"],
                    "score_receipt_sha256": _sha256(payload.get("score_receipt_sha256")),
                }:
                    raise ValueError("Transfer score differs from frozen submissions")
                state["transfer_scored"] = True
            else:
                raise ValueError("unknown data-exposure event")
        return state

    def audit(self) -> dict:
        manifest = self._manifest()
        events = self._events()
        state = self._state(manifest, events)
        return {
            "valid": True,
            "experiment_id": manifest["experiment_id"],
            "completed_rounds": list(state["completed_rounds"]),
            "active_dev_claim": state["active_dev_claim"],
            "promoted_dev_ids": list(state["promoted_dev_ids"]),
            "transfer_submissions_frozen": state["transfer_submissions_sha256"] is not None,
            "transfer_scored": state["transfer_scored"],
            "ledger_tail_sha256": events[-1]["hash"],
        }

    def controller_view(self, round_id: str) -> dict:
        """Return commitments the workspace materializer may expose this round."""
        manifest = self._manifest()
        events = self._events()
        state = self._state(manifest, events)
        index = len(state["completed_rounds"])
        if state["active_dev_claim"] is not None:
            raise ValueError("controller data view frozen during Dev scoring")
        if index >= len(manifest["rounds"]):
            raise ValueError("all learning rounds are complete")
        current = manifest["rounds"][index]
        if identifier(round_id) != current["round_id"]:
            raise ValueError("only the next frozen learning round is visible")

        train = []
        promoted = set(state["promoted_dev_ids"])
        for round_spec in manifest["rounds"][: index + 1]:
            train.extend(round_spec["train_datasets"])
            train.extend(
                {**item, "origin_role": "dev"}
                for item in round_spec["dev_datasets"]
                if item["dataset_id"] in promoted
            )
        train = [
            item if "origin_role" in item else {**item, "origin_role": "train"}
            for item in train
        ]
        return {
            "schema": VIEW_SCHEMA,
            "experiment_id": manifest["experiment_id"],
            "round_id": current["round_id"],
            "train_full_access": train,
            "dev_feature_only": current["dev_datasets"],
            "dev_labels_visible": False,
            "transfer_visible": False,
            "policy_sha256": digest(manifest["policy"]),
            "ledger_tail_sha256": events[-1]["hash"],
        }

    def claim_dev_score(self, round_id: str, *, candidate_set_sha256: str) -> dict:
        manifest = self._manifest()
        state = self._state(manifest, self._events())
        index = len(state["completed_rounds"])
        if state["active_dev_claim"] is not None or index >= len(manifest["rounds"]):
            raise ValueError("Dev is already claimed or all rounds are complete")
        current = manifest["rounds"][index]
        if identifier(round_id) != current["round_id"]:
            raise ValueError("cannot score a future or consumed Dev block")
        payload = {
            "round_id": current["round_id"],
            "candidate_set_sha256": _sha256(candidate_set_sha256),
            "dev_dataset_ids": [item["dataset_id"] for item in current["dev_datasets"]],
        }
        self._append("dev_scoring_claimed", payload)
        return payload

    def complete_dev_score(self, round_id: str, *, score_receipt_sha256: str) -> dict:
        manifest = self._manifest()
        state = self._state(manifest, self._events())
        claim = state["active_dev_claim"]
        if claim is None or identifier(round_id) != claim["round_id"]:
            raise ValueError("exact Dev scoring claim required")
        current = manifest["rounds"][len(state["completed_rounds"])]
        payload = {
            "round_id": current["round_id"],
            "candidate_set_sha256": claim["candidate_set_sha256"],
            "score_receipt_sha256": _sha256(score_receipt_sha256),
            "transition": {"from": "dev_sealed", "to": "train"},
            "promoted_dataset_ids": [item["dataset_id"] for item in current["dev_datasets"]],
        }
        self._append("dev_scored_and_promoted", payload)
        return payload

    def freeze_transfer_submissions(self, *, submissions_sha256: str) -> dict:
        manifest = self._manifest()
        state = self._state(manifest, self._events())
        if (
            state["active_dev_claim"] is not None
            or len(state["completed_rounds"]) != len(manifest["rounds"])
            or state["transfer_submissions_sha256"] is not None
        ):
            raise ValueError("all learning rounds must finish before one final freeze")
        payload = {
            "submissions_sha256": _sha256(submissions_sha256),
            "transfer_dataset_ids": [
                item["dataset_id"] for item in manifest["transfer_datasets"]
            ],
        }
        self._append("transfer_submissions_frozen", payload)
        return payload

    def complete_transfer_score(self, *, score_receipt_sha256: str) -> dict:
        manifest = self._manifest()
        state = self._state(manifest, self._events())
        if state["transfer_submissions_sha256"] is None or state["transfer_scored"]:
            raise ValueError("Transfer requires one frozen submission set and one score")
        payload = {
            "submissions_sha256": state["transfer_submissions_sha256"],
            "score_receipt_sha256": _sha256(score_receipt_sha256),
        }
        self._append("transfer_scored", payload)
        return payload

