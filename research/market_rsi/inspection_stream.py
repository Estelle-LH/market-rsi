"""Bounded inspection of Train and the label-free public Dev view.

Inspection receives complete permitted Train rows but only decision-time Dev
fields. Dev targets and label-availability metadata remain scorer-private. It
cannot authorize new data, change a split or score itself. Source authenticity
and completed coder-job provenance remain the outer worker's duty. This module
has no provider, filesystem or candidate-code execution entry point.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import secrets
import time

from prediction_stream import PUBLIC_FIELDS, TRAIN_FIELDS, encoded, fingerprint


ARTIFACT_KEYS = {"schema", "experiment_id", "task_id", "split", "feature_names", "rows"}
LIMIT_KEYS = {"timeout_seconds", "max_request_bytes", "max_response_bytes", "max_json_nodes", "max_json_depth"}
OWNER_KEYS = {"experiment_id", "arm", "task_id", "task_index", "step_index", "phase",
              "common_manifest_sha256", "common_text_sha256", "record_sha256", "guide_sha256"}


def json_bound(value, *, max_nodes, max_depth):
    """Bound untrusted JSON without trusting diagnostic field names as scores."""
    stack, nodes = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise ValueError("diagnostic JSON complexity bound exceeded")
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError("JSON string keys required")
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
        elif item is None or type(item) in {str, bool, int}:
            pass
        elif type(item) is float and math.isfinite(item):
            pass
        else:
            raise ValueError("finite JSON-compatible diagnostic required")


def limits_valid(limits):
    if (not isinstance(limits, dict) or set(limits) != LIMIT_KEYS
            or any(type(v) is not int or v <= 0 for v in limits.values())):
        raise ValueError("explicit positive integer inspection limits required")
    if (limits["timeout_seconds"] > 120 or limits["max_request_bytes"] > 8 * 1024 * 1024
            or limits["max_response_bytes"] > 1024 * 1024 or limits["max_json_nodes"] > 100000
            or limits["max_json_depth"] > 32):
        raise ValueError("inspection hard safety ceiling exceeded")


def verify_packet(packet, required):
    if not isinstance(packet, dict) or set(packet) != required | {"packet_sha256"}:
        raise ValueError("exact bound packet required")
    if fingerprint({k: v for k, v in packet.items() if k != "packet_sha256"}) != packet["packet_sha256"]:
        raise ValueError("packet changed after preparation")


def permitted_artifact(raw, catalog_entry, task, feature_names):
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != catalog_entry["sha256"]:
        raise ValueError("artifact bytes do not match the task's permitted catalog")
    artifact = json.loads(raw)
    if (not isinstance(artifact, dict) or set(artifact) != ARTIFACT_KEYS
            or artifact["schema"] != "market_permitted_rows_v1"
            or artifact["split"] != catalog_entry["split"] or artifact["split"] not in {"train", "dev"}
            or artifact["experiment_id"] != task["experiment_id"] or artifact["task_id"] != task["task_id"]
            or artifact["feature_names"] != feature_names
            or not isinstance(artifact["rows"], list)):
        raise ValueError("artifact ownership/split/schema mismatch")
    for row in artifact["rows"]:
        if not isinstance(row, dict) or set(row) != TRAIN_FIELDS:
            raise ValueError("only declared permitted row fields may be exposed")
        # Missing/nonnumeric values are useful inspection evidence; do not clean,
        # impute or reject them merely to make a data-quality diagnosis look good.
        # Identity and field allowlists remain strict. These rows cannot train
        # unless the separate training validator admits their numeric contents.
        for key in ("row_id", "game_id", "market_id"):
            if not isinstance(row[key], str) or not row[key] or len(row[key]) > 100:
                raise ValueError("bounded opaque row identities required")
        if not isinstance(row["features"], dict) or not set(row["features"]) <= set(feature_names):
            raise ValueError("unexpected feature column")
    json_bound(artifact, max_nodes=1000000, max_depth=32)
    return artifact


def prepare_inspection(research_request, coding_request, *, train_id, train_bytes, dev_id, dev_bytes, limits):
    verify_packet(research_request, {"messages", "audit"})
    verify_packet(coding_request, {"prompt", "audit"})
    limits_valid(limits)
    r, c = copy.deepcopy(research_request), copy.deepcopy(coding_request)
    ra, ca = r["audit"], c["audit"]
    if (fingerprint(r["messages"]) != ra["messages_sha256"]
            or ca["research_packet_sha256"] != r["packet_sha256"]
            or ca["entrypoint"] != "inspect" or any(ca[k] != ra[k] for k in OWNER_KEYS)
            or hashlib.sha256(c["prompt"].encode()).hexdigest() != ca["prompt_sha256"]):
        raise ValueError("inspection request does not belong to this researcher/task")
    public = json.loads(r["messages"][1]["content"])
    task, code = public["task"], json.loads(c["prompt"])
    if (fingerprint(task) != ra["task_public_sha256"] or code["research_context"] != r["messages"]
            or code["entrypoint"] != "inspect"
            or code["proposal"]["action"] not in {"inspect", "reject_measurement"}
            or fingerprint(code["proposal"]) != ca["proposal_sha256"]
            or fingerprint(code["runtime"]) != ca["runtime_sha256"]):
        raise ValueError("inspection proposal/context/runtime binding failed")
    catalog = task["data_catalog"]
    by_id = {item["artifact_id"]: item for item in catalog}
    if (len(by_id) != len(catalog) or train_id == dev_id or train_id not in by_id or dev_id not in by_id
            or by_id[train_id]["split"] != "train" or by_id[dev_id]["split"] != "dev"):
        raise ValueError("one catalogued Train and one catalogued Dev artifact required")
    if len(train_bytes) + len(dev_bytes) > limits["max_request_bytes"]:
        raise ValueError("inspection inputs too large; no silent truncation")
    names = code["runtime"]["feature_names"]
    train = permitted_artifact(train_bytes, by_id[train_id], task, names)
    dev = permitted_artifact(dev_bytes, by_id[dev_id], task, names)
    # The trusted runner validates the committed full Dev artifact, then creates
    # the only view serialized into the untrusted inspection sandbox. This is
    # the same label-free field boundary used by the prediction interface.
    public_dev = [{key: copy.deepcopy(row[key]) for key in PUBLIC_FIELDS}
                  for row in dev["rows"]]
    payload = {"train": train["rows"], "dev": public_dev, "feature_names": names}
    audit = {key: copy.deepcopy(ra[key]) for key in OWNER_KEYS}
    audit.update(research_packet_sha256=r["packet_sha256"], coding_packet_sha256=c["packet_sha256"],
                 action=code["proposal"]["action"], train_artifact_id=train_id, dev_artifact_id=dev_id,
                 train_source_sha256=by_id[train_id]["sha256"], dev_source_sha256=by_id[dev_id]["sha256"],
                 payload_sha256=fingerprint(payload), limits=copy.deepcopy(limits))
    result = {"payload": payload, "audit": audit}
    return dict(result, packet_sha256=fingerprint(result))


def inspect_once(exchange, prepared):
    """One already-isolated exchange; caller must preserve failure/protocol logs."""
    verify_packet(prepared, {"payload", "audit"})
    packet = copy.deepcopy(prepared)
    audit, payload = packet["audit"], packet["payload"]
    limits_valid(audit["limits"])
    if (set(payload) != {"train", "dev", "feature_names"}
            or fingerprint(payload) != audit["payload_sha256"]
            or audit["action"] not in {"inspect", "reject_measurement"}):
        raise ValueError("inspection payload changed")
    request = {"type": "inspect", "request_id": secrets.token_hex(16), **payload}
    if len(encoded(request)) + 1 > audit["limits"]["max_request_bytes"]:
        raise ValueError("encoded inspection exceeds frozen request cap")
    start = time.monotonic()
    response = exchange(request, audit["limits"]["timeout_seconds"])
    if time.monotonic() - start >= audit["limits"]["timeout_seconds"]:
        raise TimeoutError("inspection exceeded wall limit")
    if (not isinstance(response, dict) or set(response) != {"type", "request_id", "diagnostic"}
            or response["type"] != "inspection" or response["request_id"] != request["request_id"]):
        raise ValueError("wrong inspection response type/nonce; candidate scores are not trusted")
    json_bound(response["diagnostic"], max_nodes=audit["limits"]["max_json_nodes"],
               max_depth=audit["limits"]["max_json_depth"])
    if len(encoded(response)) + 1 > audit["limits"]["max_response_bytes"]:
        raise ValueError("inspection output too large; preserve failure, do not truncate")
    return {"audit": audit, "request_sha256": fingerprint(request), "response_sha256": fingerprint(response),
            "diagnostic": copy.deepcopy(response["diagnostic"]), "origin": "candidate_code_untrusted_diagnostic",
            "independent_score": None, "scored": False, "scientific_admission": False,
            "logical_exchanges": 1}
