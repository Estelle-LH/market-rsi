"""Hash-bind one formal Archive learning round to its exact data lifecycle.

The data builder writes component blocks and cumulative controller inputs.  A
formal paid process must not trust paths alone: this module reconstructs the
cumulative Train and current Dev from the lifecycle commitments, verifies the
builder and source materializations, and freezes one small binding receipt.
It performs no model call, sandbox work, scoring, or lifecycle mutation.
"""
from __future__ import annotations

import json
from pathlib import Path

from build_archive_formal_data import SCHEMA as DATA_SCHEMA
from build_archive_formal_data import ROW_FIELDS
from market_rsi import digest, file_hash, fresh_json, identifier
from prospective_data_lifecycle import ProspectiveDataLifecycle


SCHEMA = "market_archive_formal_round_binding_v1"
MAX_JSON_BYTES = 16 * 1024 * 1024


def _regular_json(path: Path, maximum: int = MAX_JSON_BYTES):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized formal-round input")
    return json.loads(path.read_bytes())


def _sha(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError("lowercase SHA-256 commitment required")
    return value


def _artifact(path: Path, *, split: str, expected_sha256: str) -> dict:
    path = Path(path).resolve()
    if file_hash(path) != _sha(expected_sha256):
        raise ValueError("formal-round artifact hash changed")
    value = _regular_json(path)
    if (not isinstance(value, dict)
            or value.get("schema") != "market_permitted_rows_v1"
            or value.get("split") != split
            or not isinstance(value.get("rows"), list)
            or not value["rows"]):
        raise ValueError("invalid formal-round permitted-row artifact")
    if any(not isinstance(row, dict) or set(row) != set(ROW_FIELDS)
           for row in value["rows"]):
        raise ValueError("formal-round row fields changed")
    return value


def validate_data_root(data_root: Path) -> dict:
    data_root = Path(data_root).resolve()
    receipt = _regular_json(data_root / "receipt.json")
    rounds = _regular_json(data_root / "lifecycle-rounds.json")
    inputs = _regular_json(data_root / "round-inputs.json")
    transfer_policy = _regular_json(data_root / "transfer-policy.json")
    from build_archive_formal_data import __file__ as builder_source
    from build_archive_continuation_data import (SCHEMA as CONTINUATION_SCHEMA,
                                                 __file__ as continuation_builder)

    schema = receipt.get("schema") if isinstance(receipt, dict) else None
    expected_builder = (builder_source if schema == DATA_SCHEMA
                        else continuation_builder if schema == CONTINUATION_SCHEMA
                        else None)

    if (not isinstance(receipt, dict)
            or expected_builder is None
            or receipt.get("builder_source_sha256") != file_hash(expected_builder)
            or receipt.get("lifecycle_rounds_sha256") != digest(rounds)
            or receipt.get("round_inputs_sha256") != digest(inputs)
            or receipt.get("transfer_policy_sha256") != digest(transfer_policy)
            or receipt.get("transfer_materialized") is not False
            or receipt.get("formal_lineage_ready") is not False
            or receipt.get("future_test_used") is not False):
        raise ValueError("formal learning-data receipt changed")
    if schema == CONTINUATION_SCHEMA:
        parent_root = Path(receipt.get("parent_data_root", "")).resolve()
        if parent_root == data_root:
            raise ValueError("continuation data cannot parent itself")
        parent = validate_data_root(parent_root)
        if (receipt.get("parent_data_receipt_sha256") != digest(parent["receipt"])
                or receipt.get("starting_round_id")
                != rounds[0].get("round_id")):
            raise ValueError("continuation parent or starting round changed")
    if not isinstance(receipt.get("source_materializations"), list):
        raise ValueError("formal learning-data sources missing")
    objective_id = receipt.get("objective_id")
    objective_contract_sha256 = receipt.get("objective_contract_sha256")
    if (objective_id is None) != (objective_contract_sha256 is None):
        raise ValueError("formal learning-data objective binding is incomplete")
    if objective_id is not None:
        identifier(objective_id)
        _sha(objective_contract_sha256)
    for source in receipt["source_materializations"]:
        if (not isinstance(source, dict) or set(source) != {
                "path", "sha256", "source_bundle_sha256", "rows"}):
            raise ValueError("formal learning-data source receipt changed")
        if file_hash(Path(source["path"])) != _sha(source["sha256"]):
            raise ValueError("historical source materialization changed")
    if (not isinstance(rounds, list) or not rounds
            or not isinstance(inputs, list) or len(inputs) != len(rounds)):
        raise ValueError("formal learning rounds missing")
    return {"root": data_root, "receipt": receipt, "rounds": rounds,
            "inputs": inputs, "transfer_policy": transfer_policy}


def _component(data_root: Path, dataset_id: str, expected_sha256: str) -> dict:
    identifier(dataset_id)
    path = data_root / "blocks" / f"{dataset_id}.json"
    value = _regular_json(path)
    split = value.get("split")
    if split not in {"train", "dev"}:
        raise ValueError("formal component split changed")
    checked = _artifact(path, split=split, expected_sha256=expected_sha256)
    if checked.get("task_id") != dataset_id:
        raise ValueError("formal component dataset identity changed")
    return checked


def build_binding(data_root: Path, lifecycle_root: Path, round_id: str) -> dict:
    """Validate and return the canonical binding for the next visible round."""
    identifier(round_id)
    data = validate_data_root(data_root)
    objective_id = data["receipt"].get("objective_id")
    objective_contract_sha256 = data["receipt"].get(
        "objective_contract_sha256"
    )
    lifecycle = ProspectiveDataLifecycle(Path(lifecycle_root))
    audit = lifecycle.audit()
    manifest = lifecycle._manifest()
    if (manifest["experiment_id"] != data["receipt"]["experiment_id"]
            or manifest["transfer_policy_sha256"]
            != data["receipt"]["transfer_policy_sha256"]):
        raise ValueError("formal lifecycle belongs to different data or policy")
    lifecycle_rounds = [{key: spec[key] for key in (
        "round_id", "train_datasets", "dev_datasets")} for spec in manifest["rounds"]]
    if lifecycle_rounds != data["rounds"]:
        raise ValueError("formal lifecycle learning rounds changed")

    view = lifecycle.controller_view(round_id)
    matches = [item for item in data["inputs"] if item.get("round_id") == round_id]
    if len(matches) != 1:
        raise ValueError("formal round input does not exist exactly once")
    item = matches[0]
    train_ids = [entry["dataset_id"] for entry in view["train_full_access"]]
    dev_ids = [entry["dataset_id"] for entry in view["dev_feature_only"]]
    if train_ids != item.get("train_dataset_ids") or dev_ids != item.get("dev_dataset_ids"):
        raise ValueError("materialized round inputs differ from controller lifecycle view")

    train_rows, seen = [], set()
    components = []
    for entry in view["train_full_access"]:
        component = _component(data["root"], entry["dataset_id"], entry["content_sha256"])
        for row in component["rows"]:
            if row["row_id"] in seen:
                raise ValueError("row repeated across formal Train components")
            seen.add(row["row_id"])
            train_rows.append(row)
        components.append({"dataset_id": entry["dataset_id"],
                           "origin_role": entry["origin_role"],
                           "content_sha256": entry["content_sha256"]})
    train_rows.sort(key=lambda row: (row["decision_ms"], row["row_id"]))
    train_path = Path(item["train"]["path"]).resolve()
    if train_path.parent != data["root"] / "blocks":
        raise ValueError("cumulative Train escaped frozen data root")
    cumulative = _artifact(train_path, split="train",
                           expected_sha256=item["train"]["sha256"])
    if (cumulative.get("task_id") != item.get("task_id")
            or cumulative["rows"] != train_rows
            or item["train"].get("rows") != len(train_rows)
            or item["train"].get("games") != len({row["game_id"] for row in train_rows})
            or item["train"].get("bytes") != train_path.stat().st_size):
        raise ValueError("cumulative Train is not the exact lifecycle concatenation")

    dev_rows, dev_components = [], []
    for entry in view["dev_feature_only"]:
        component = _component(data["root"], entry["dataset_id"], entry["content_sha256"])
        dev_rows.extend(component["rows"])
        dev_components.append({"dataset_id": entry["dataset_id"],
                               "content_sha256": entry["content_sha256"]})
    dev_rows.sort(key=lambda row: (row["decision_ms"], row["row_id"]))
    dev_path = Path(item["dev"]["path"]).resolve()
    if dev_path.parent != data["root"] / "blocks":
        raise ValueError("sealed Dev escaped frozen data root")
    dev = _artifact(dev_path, split="dev", expected_sha256=item["dev"]["sha256"])
    if (dev.get("task_id") != item.get("task_id") or dev["rows"] != dev_rows
            or item["dev"].get("rows") != len(dev_rows)
            or item["dev"].get("games") != len({row["game_id"] for row in dev_rows})
            or item["dev"].get("bytes") != dev_path.stat().st_size):
        raise ValueError("sealed Dev is not the exact lifecycle component")
    if max(row["label_available_ms"] for row in train_rows) >= min(
            row["feature_available_ms"] for row in dev_rows):
        raise ValueError("formal Train labels overlap current sealed Dev")

    expected_materialization = digest({
        "round_id": round_id,
        "components": [{"dataset_id": entry["dataset_id"],
                        "content_sha256": entry["content_sha256"]}
                       for entry in view["train_full_access"]],
        "cumulative_train_sha256": item["train"]["sha256"],
        "dev_sha256": item["dev"]["sha256"],
    })
    if expected_materialization != item.get("materialization_sha256"):
        raise ValueError("formal round materialization commitment changed")
    result = {
        "schema": SCHEMA,
        "experiment_id": manifest["experiment_id"],
        "round_id": round_id,
        "task_id": item["task_id"],
        "data_root": str(data["root"]),
        "data_receipt_sha256": digest(data["receipt"]),
        "lifecycle_root": str(Path(lifecycle_root).resolve()),
        "lifecycle_manifest_sha256": digest(manifest),
        "lifecycle_audit_sha256": digest(audit),
        "controller_view": view,
        "controller_view_sha256": digest(view),
        "train_components": components,
        "train_path": str(train_path),
        "train_sha256": item["train"]["sha256"],
        "train_rows": len(train_rows),
        "dev_components": dev_components,
        "dev_path": str(dev_path),
        "dev_sha256": item["dev"]["sha256"],
        "dev_rows": len(dev_rows),
        "materialization_sha256": expected_materialization,
        "transfer_policy_sha256": manifest["transfer_policy_sha256"],
        "dev_labels_visible_to_controller": False,
        "transfer_visible_to_controller": False,
    }
    if objective_id is not None:
        result["objective_id"] = objective_id
        result["objective_contract_sha256"] = objective_contract_sha256
    return result


def freeze_binding(path: Path, data_root: Path, lifecycle_root: Path,
                   round_id: str) -> dict:
    binding = build_binding(data_root, lifecycle_root, round_id)
    fresh_json(path, binding)
    return binding


def validate_binding(path: Path) -> dict:
    path = Path(path)
    value = _regular_json(path)
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("invalid formal round binding")
    rebuilt = build_binding(Path(value.get("data_root", "")),
                            Path(value.get("lifecycle_root", "")),
                            value.get("round_id"))
    if value != rebuilt:
        raise ValueError("formal round binding or lifecycle state changed")
    return value
