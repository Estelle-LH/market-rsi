"""Prospective Transfer lifecycle for the formal Archive self-improvement run.

Learning rounds are content-frozen at creation.  The final Transfer population
is bound by a selection-policy hash before learning starts and may be
materialized later, after enough post-boundary games exist.  Transfer remains
invisible until every A0-A3 submission is frozen.
"""
from __future__ import annotations

import json
from pathlib import Path

from data_lifecycle import (DataLifecycle, VIEW_SCHEMA, _dataset, _sha256)
from market_rsi import digest, file_hash, fresh_json, identifier


SCHEMA = "market_prospective_data_lifecycle_v2"


class ProspectiveDataLifecycle(DataLifecycle):
    @classmethod
    def create(cls, root: Path, *, experiment_id: str, rounds: list[dict],
               transfer_policy_sha256: str) -> "ProspectiveDataLifecycle":
        identifier(experiment_id)
        transfer_policy_sha256 = _sha256(transfer_policy_sha256)
        if not isinstance(rounds, list) or not rounds:
            raise ValueError("at least one ordered learning round required")
        frozen_rounds, dataset_ids = [], set()
        for index, round_spec in enumerate(rounds):
            if not isinstance(round_spec, dict) or set(round_spec) != {
                    "round_id", "train_datasets", "dev_datasets"}:
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
            frozen_rounds.append({"round_index": index, "round_id": round_id,
                                  "train_datasets": train, "dev_datasets": dev})
        root = Path(root).resolve()
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        obj = cls(root)
        manifest = {
            "schema": SCHEMA, "experiment_id": experiment_id,
            "rounds": frozen_rounds,
            "transfer_policy_sha256": transfer_policy_sha256,
            "policy": {
                "controller_reads_all_learning_data": True,
                "current_dev_labels_visible": False,
                "dev_scores_per_block": 1,
                "dev_after_score": "train",
                "reuse_consumed_dev_for_evaluation": False,
                "transfer_population": "prospective_policy_bound",
                "transfer_visible_before_final_freeze": False,
            },
            "source_sha256": file_hash(__file__),
        }
        fresh_json(obj.manifest_path, manifest)
        obj._append("created", {"manifest_sha256": digest(manifest)})
        obj.audit()
        return obj

    def _manifest(self) -> dict:
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise ValueError("prospective lifecycle manifest missing or symlinked")
        manifest = json.loads(self.manifest_path.read_bytes())
        if (manifest.get("schema") != SCHEMA
                or manifest.get("source_sha256") != file_hash(__file__)
                or not isinstance(manifest.get("rounds"), list)
                or not manifest["rounds"]):
            raise ValueError("prospective lifecycle source or schema changed")
        _sha256(manifest.get("transfer_policy_sha256"))
        return manifest

    def _state(self, manifest: dict, events: list[dict]) -> dict:
        if not events or events[0]["event"] != "created" or events[0]["payload"] != {
                "manifest_sha256": digest(manifest)}:
            raise ValueError("prospective lifecycle was not bound to this manifest")
        state = {"completed_rounds": [], "active_dev_claim": None,
                 "promoted_dev_ids": [], "transfer_datasets": None,
                 "transfer_materialization_receipt_sha256": None,
                 "transfer_submissions_sha256": None, "transfer_scored": False}
        learning_ids = {item["dataset_id"] for spec in manifest["rounds"]
                        for item in spec["train_datasets"] + spec["dev_datasets"]}
        for record in events[1:]:
            event, payload = record["event"], record["payload"]
            next_index = len(state["completed_rounds"])
            if event == "dev_scoring_claimed":
                if state["active_dev_claim"] is not None or next_index >= len(manifest["rounds"]):
                    raise ValueError("duplicate or out-of-order Dev scoring claim")
                expected = manifest["rounds"][next_index]
                expected_payload = {"round_id": expected["round_id"],
                    "candidate_set_sha256": _sha256(payload.get("candidate_set_sha256")),
                    "dev_dataset_ids": [item["dataset_id"] for item in expected["dev_datasets"]]}
                if payload != expected_payload:
                    raise ValueError("Dev claim differs from frozen round")
                state["active_dev_claim"] = payload
            elif event == "dev_scored_and_promoted":
                if state["active_dev_claim"] is None or next_index >= len(manifest["rounds"]):
                    raise ValueError("Dev completion lacks exact claim")
                expected = manifest["rounds"][next_index]
                promoted = [item["dataset_id"] for item in expected["dev_datasets"]]
                expected_payload = {"round_id": expected["round_id"],
                    "candidate_set_sha256": state["active_dev_claim"]["candidate_set_sha256"],
                    "score_receipt_sha256": _sha256(payload.get("score_receipt_sha256")),
                    "transition": {"from": "dev_sealed", "to": "train"},
                    "promoted_dataset_ids": promoted}
                if payload != expected_payload:
                    raise ValueError("Dev promotion differs from frozen claim")
                state["completed_rounds"].append(expected["round_id"])
                state["promoted_dev_ids"].extend(promoted)
                state["active_dev_claim"] = None
            elif event == "transfer_materialized":
                if state["transfer_datasets"] is not None or state["transfer_submissions_sha256"] is not None:
                    raise ValueError("Transfer population already materialized or frozen")
                datasets = [_dataset(item) for item in payload.get("transfer_datasets", [])]
                if (not datasets or learning_ids.intersection(
                        item["dataset_id"] for item in datasets)):
                    raise ValueError("Transfer datasets missing or overlap learning IDs")
                expected_payload = {
                    "transfer_policy_sha256": manifest["transfer_policy_sha256"],
                    "transfer_datasets": datasets,
                    "materialization_receipt_sha256": _sha256(
                        payload.get("materialization_receipt_sha256")),
                }
                if payload != expected_payload:
                    raise ValueError("Transfer materialization differs from frozen policy")
                state["transfer_datasets"] = datasets
                state["transfer_materialization_receipt_sha256"] = payload[
                    "materialization_receipt_sha256"]
            elif event == "transfer_submissions_frozen":
                if (state["active_dev_claim"] is not None
                        or len(state["completed_rounds"]) != len(manifest["rounds"])
                        or state["transfer_datasets"] is None
                        or state["transfer_submissions_sha256"] is not None):
                    raise ValueError("Transfer submissions frozen at an invalid time")
                expected_payload = {"submissions_sha256": _sha256(
                    payload.get("submissions_sha256")),
                    "transfer_dataset_ids": [item["dataset_id"]
                                             for item in state["transfer_datasets"]]}
                if payload != expected_payload:
                    raise ValueError("Transfer freeze differs from materialized population")
                state["transfer_submissions_sha256"] = payload["submissions_sha256"]
            elif event == "transfer_scored":
                if state["transfer_submissions_sha256"] is None or state["transfer_scored"]:
                    raise ValueError("Transfer scored without one final freeze")
                expected_payload = {"submissions_sha256": state["transfer_submissions_sha256"],
                    "score_receipt_sha256": _sha256(payload.get("score_receipt_sha256"))}
                if payload != expected_payload:
                    raise ValueError("Transfer score differs from frozen submissions")
                state["transfer_scored"] = True
            else:
                raise ValueError("unknown prospective data-exposure event")
        return state

    def audit(self) -> dict:
        manifest = self._manifest()
        state = self._state(manifest, self._events())
        events = self._events()
        return {"valid": True, "experiment_id": manifest["experiment_id"],
                "completed_rounds": list(state["completed_rounds"]),
                "active_dev_claim": state["active_dev_claim"],
                "promoted_dev_ids": list(state["promoted_dev_ids"]),
                "transfer_policy_sha256": manifest["transfer_policy_sha256"],
                "transfer_materialized": state["transfer_datasets"] is not None,
                "transfer_dataset_ids": ([item["dataset_id"] for item in state["transfer_datasets"]]
                                         if state["transfer_datasets"] else []),
                "transfer_submissions_frozen": state["transfer_submissions_sha256"] is not None,
                "transfer_scored": state["transfer_scored"],
                "ledger_tail_sha256": events[-1]["hash"]}

    def materialize_transfer(self, *, transfer_datasets: list[dict],
                             materialization_receipt_sha256: str) -> dict:
        manifest = self._manifest()
        state = self._state(manifest, self._events())
        if state["transfer_datasets"] is not None or state["transfer_submissions_sha256"] is not None:
            raise ValueError("Transfer population already materialized or frozen")
        datasets = [_dataset(item) for item in transfer_datasets]
        learning_ids = {item["dataset_id"] for spec in manifest["rounds"]
                        for item in spec["train_datasets"] + spec["dev_datasets"]}
        if (not datasets
                or len({item["dataset_id"] for item in datasets}) != len(datasets)
                or learning_ids.intersection(item["dataset_id"] for item in datasets)):
            raise ValueError("nonempty unique Transfer datasets required")
        payload = {"transfer_policy_sha256": manifest["transfer_policy_sha256"],
                   "transfer_datasets": datasets,
                   "materialization_receipt_sha256": _sha256(
                       materialization_receipt_sha256)}
        self._append("transfer_materialized", payload)
        return payload

    def freeze_transfer_submissions(self, *, submissions_sha256: str) -> dict:
        manifest = self._manifest()
        state = self._state(manifest, self._events())
        if (state["active_dev_claim"] is not None
                or len(state["completed_rounds"]) != len(manifest["rounds"])
                or state["transfer_datasets"] is None
                or state["transfer_submissions_sha256"] is not None):
            raise ValueError("all learning rounds and Transfer materialization must finish first")
        payload = {"submissions_sha256": _sha256(submissions_sha256),
                   "transfer_dataset_ids": [item["dataset_id"]
                                            for item in state["transfer_datasets"]]}
        self._append("transfer_submissions_frozen", payload)
        return payload
