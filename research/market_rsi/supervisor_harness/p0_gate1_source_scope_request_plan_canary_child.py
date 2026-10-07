"""Zero-effect child for the exact reviewed D0-to-request-plan bridge.

This entry reads only immutable local evidence, compiles the bridge twice, and
writes a non-executable request-plan bundle.  It deliberately has no import or
argument surface for a provider, public fetch, watched fetch, URL, credential,
budget, dataset, Train/Dev/Final, training, or evaluation operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any

# The parent launches this file with ``python -I`` and a minimal environment.
# Add only the immutable source root derived from this exact entry path.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_rsi import canonical, digest, file_hash, fresh_json
from supervisor_harness import p0_gate1_source_scope_request_plan as bridge
from supervisor_harness.supervisor_watchdog_local_control import (
    process_command_sha256,
)


CANARY_ID = (
    "market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01"
)
CANARY_CHILD_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_child_v1"
)
SUPERVISOR_CLAIM_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_supervisor_claim_v1"
)
REQUEST_PLAN_CANONICAL_SHA256 = (
    "34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c"
)
REQUEST_BUNDLE_CANONICAL_SHA256 = (
    "7f340e20702a03200628cbad06f300257252d06a8b564985cbbf60ad8535b931"
)
RELEASE_TAG = "market-rsi-protocol-v0.1.26"
PUBLISHED_ORIGIN = "https://github.com/Estelle-LH/market-rsi.git"

D0_FILE_SHA256 = {
    "decision": "01054900be9075f0fef57b9e1481abb73f722b2223d664df24db8e6c81dcc216",
    "submission": "ed1e391532112f413962d13ab1e6d9718cf92eb0e90ace8caeb31473e4f402d6",
    "provenance": "bcd768989e33af91e42ba4d3db35201f294fb6be6d9a3182165f890140eeec65",
    "raw_response": "126a5a1309251721a45b86ecc51955083234b60a9b40ffe09f4cf03e0f89fd27",
    "packet": "bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd",
    "publication": "a11e41473a1ddb70335239e466a46bca63451b85caf8c2771687f48d9210f527",
    "result": "6c41f67aa9832abc812f5b422e650bccf3724a45f5c5558fbb96434e1536e02e",
    "review": "676a549ff9a1289afd08c0ee283182babf528d85ce9f3bcccb2e59a7358d144f",
}
D0_CANONICAL_SHA256 = {
    "decision": bridge.D0_DECISION_SHA256,
    "submission": bridge.D0_SUBMISSION_SHA256,
    "provenance": bridge.D0_PROVENANCE_SHA256,
    "packet": bridge.FROZEN_PACKET_CANONICAL_SHA256,
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_MAX_FILE_BYTES = 16 * 1024 * 1024


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _read_regular(path: Path, label: str) -> bytes:
    path = Path(path)
    _require(path.is_absolute(), f"{label} path must be absolute")
    try:
        _require(path.parent.resolve(strict=True) == path.parent,
                 f"{label} path must be canonical")
        current = Path(path.anchor)
        ancestors = []
        for component in path.parts[1:-1]:
            current = current / component
            info = current.lstat()
            _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                     f"{label} ancestor must be a non-symlink directory")
            ancestors.append((current, (info.st_dev, info.st_ino, info.st_mode)))
        before = path.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"missing or unsafe {label}") from exc
    _require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
             f"{label} must be a non-symlink regular file")
    _require(before.st_size <= _MAX_FILE_BYTES, f"{label} exceeds safe size")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        _require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                 f"{label} changed during open")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            _require(total <= _MAX_FILE_BYTES, f"{label} exceeds safe size")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    current = path.lstat()
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size,
                             item.st_mtime_ns, item.st_ctime_ns)
    _require(identity(opened) == identity(after) == identity(current),
             f"{label} changed while read")
    for ancestor, expected in ancestors:
        observed = ancestor.lstat()
        _require(stat.S_ISDIR(observed.st_mode)
                 and not stat.S_ISLNK(observed.st_mode)
                 and (observed.st_dev, observed.st_ino, observed.st_mode) == expected,
                 f"{label} ancestor changed while read")
    return b"".join(chunks)


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {item}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid {label} JSON") from exc
    pending = [value]
    while pending:
        item = pending.pop()
        if type(item) is float and not math.isfinite(item):
            raise ValueError(f"invalid {label} JSON")
        if type(item) is dict:
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    _require(type(value) is dict, f"{label} must be a JSON object")
    return value


def _load_bound(path: Path, label: str, expected_sha256: str) -> tuple[dict, bytes]:
    raw = _read_regular(path, label)
    _require(hashlib.sha256(raw).hexdigest() == expected_sha256,
             f"{label} file commitment changed")
    return _parse_json(raw, label), raw


def _await_claim(path: Path, seconds: float = 10.0) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            raw = _read_regular(path, "supervisor claim")
        except ValueError as exc:
            if "missing" not in str(exc):
                raise
            time.sleep(0.02)
            continue
        return _parse_json(raw, "supervisor claim")
    raise TimeoutError("supervisor claim did not arrive")


def _verify_supervisor_claim(args: argparse.Namespace) -> tuple[dict, str]:
    claim = _await_claim(args.supervisor_claim)
    required = {
        "schema", "cycle_id", "task_id", "pid", "process_command_sha256",
        "supervisor_pid", "supervisor_command_sha256", "watchdog_head_sha256",
        "release", "runtime_sha256", "request_plan_canonical_sha256",
        "request_bundle_canonical_sha256", "permanent_claim_sha256",
        "automatic_retry",
    }
    _require(set(claim) == required, "invalid supervisor claim fields")
    release = claim.get("release")
    _require(
        claim["schema"] == SUPERVISOR_CLAIM_SCHEMA
        and claim["cycle_id"] == CANARY_ID
        and claim["task_id"] == CANARY_ID
        and claim["pid"] == os.getpid()
        and claim["supervisor_pid"] == os.getppid()
        and claim["automatic_retry"] is False
        and claim["request_plan_canonical_sha256"] == REQUEST_PLAN_CANONICAL_SHA256
        and claim["request_bundle_canonical_sha256"] == REQUEST_BUNDLE_CANONICAL_SHA256
        and claim["runtime_sha256"] == args.runtime_sha256
        and release == {
            "tag": args.release_tag,
            "commit": args.release_commit,
            "tag_object": args.release_tag_object,
            "source_sha256": args.source_sha256,
        },
        "supervisor claim binding changed",
    )
    observed, present = process_command_sha256(os.getpid())
    parent_observed, parent_present = process_command_sha256(os.getppid())
    _require(present and observed == claim["process_command_sha256"],
             "child process identity changed")
    _require(parent_present and parent_observed == claim["supervisor_command_sha256"],
             "supervisor process identity changed")
    for key in ("watchdog_head_sha256", "permanent_claim_sha256"):
        _require(type(claim[key]) is str and _SHA256.fullmatch(claim[key]) is not None,
                 f"invalid {key}")
    return claim, file_hash(args.supervisor_claim)


def _verify_d0(args: argparse.Namespace) -> tuple[dict, dict, dict]:
    paths = {
        "decision": args.d0_decision,
        "submission": args.d0_submission,
        "provenance": args.d0_provenance,
        "raw_response": args.d0_raw_response,
        "packet": args.d0_packet,
        "publication": args.d0_publication,
        "result": args.d0_result,
        "review": args.d0_review,
    }
    loaded: dict[str, dict] = {}
    for name, path in paths.items():
        raw = _read_regular(path, f"D0 {name}")
        _require(hashlib.sha256(raw).hexdigest() == D0_FILE_SHA256[name],
                 f"D0 {name} file commitment changed")
        if name != "raw_response":
            loaded[name] = _parse_json(raw, f"D0 {name}")
    for name, expected in D0_CANONICAL_SHA256.items():
        _require(digest(loaded[name]) == expected,
                 f"D0 {name} canonical commitment changed")
    _require(loaded["submission"] == bridge._controller_submission(loaded["decision"]),
             "D0 submission does not reconstruct from the decision")
    publication = loaded["publication"]
    _require(
        publication.get("schema") == "market_rsi_protocol_publication_v1"
        and publication.get("origin") == PUBLISHED_ORIGIN
        and publication.get("tag") == bridge.D0_RELEASE_TAG
        and publication.get("commit") == bridge.D0_RELEASE_COMMIT
        and publication.get("tag_object") == bridge.D0_RELEASE_TAG_OBJECT
        and publication.get("source_sha256") == bridge.D0_CONTROLLED_SOURCE_SHA256,
        "D0 publication binding changed",
    )
    result, review = loaded["result"], loaded["review"]
    _require(
        result.get("schema") == "market_p0_gate1_controller_outer_result_v1"
        and result.get("cycle_id") == bridge.D0_CYCLE_ID
        and result.get("passed") is True
        and result.get("submission_kind") == "source_scope_decision"
        and result.get("compiled_plan_sha256") is None
        and result.get("formal_data_admitted") is False
        and result.get("public_fetch_performed") is False
        and result.get("automatic_retry") is False
        and result.get("review_sha256") == D0_FILE_SHA256["review"],
        "D0 terminal result semantics changed",
    )
    _require(
        review.get("schema") == "market_p0_gate1_controller_review_v1"
        and review.get("cycle_id") == bridge.D0_CYCLE_ID
        and review.get("adapter_passed") is True
        and review.get("compiled_plan_sha256") is None
        and review.get("formal_data_admitted") is False
        and review.get("public_fetch_performed") is False
        and review.get("automatic_retry") is False,
        "D0 independent review semantics changed",
    )
    return loaded["decision"], loaded["provenance"], loaded["packet"]


def run(args: argparse.Namespace) -> dict:
    _require(args.cycle_id == CANARY_ID, "exact canary ID required")
    _require(args.release_tag == RELEASE_TAG, "exact v0.1.26 release tag required")
    _require(_SHA1.fullmatch(args.release_commit) is not None,
             "full release commit required")
    _require(_SHA1.fullmatch(args.release_tag_object) is not None,
             "full annotated tag object required")
    for value, label in ((args.source_sha256, "source"),
                         (args.runtime_sha256, "runtime")):
        _require(_SHA256.fullmatch(value) is not None, f"invalid {label} SHA256")
    artifacts = Path(args.artifacts)
    _require(artifacts.is_absolute() and artifacts.resolve() == artifacts,
             "canonical absolute artifacts path required")
    artifacts.mkdir(parents=False, mode=0o700)

    claim, claim_sha256 = _verify_supervisor_claim(args)
    decision, provenance, packet = _verify_d0(args)
    preflight = {
        "schema": "market_p0_gate1_source_scope_request_plan_canary_preflight_v1",
        "canary_id": CANARY_ID,
        "release": claim["release"],
        "runtime_sha256": args.runtime_sha256,
        "d0_evidence_sha256": dict(D0_FILE_SHA256),
        "request_plan_canonical_sha256": REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": REQUEST_BUNDLE_CANONICAL_SHA256,
        "provider_calls": 0,
        "network_requests": 0,
        "external_bytes_received": 0,
        "automatic_retry": False,
    }
    fresh_json(artifacts / "preflight.json", preflight)

    first = bridge.compile_document_request_plan(
        decision, provenance, packet,
        d0_source_sha256=bridge.D0_CONTROLLED_SOURCE_SHA256,
    )
    second = bridge.compile_document_request_plan(
        decision, provenance, packet,
        d0_source_sha256=bridge.D0_CONTROLLED_SOURCE_SHA256,
    )
    _require(first == second, "bridge compilation is not deterministic")
    _require(first["request_plan_canonical_sha256"] == REQUEST_PLAN_CANONICAL_SHA256,
             "request plan canonical commitment changed")
    _require(digest(first) == REQUEST_BUNDLE_CANONICAL_SHA256,
             "request bundle canonical commitment changed")
    _require(first["future_fetch_admission_requirements"]["fetch_authorized"] is False,
             "compiled bridge unexpectedly authorizes fetch")
    authority = first["request_plan"]["authority"]
    _require(authority.get("plan_only") is True and all(
        value is False for key, value in authority.items() if key != "plan_only"
    ), "compiled bridge authority widened")
    boundaries = first["request_plan"]["claim_boundaries"]
    _require(boundaries.get("provider_or_model_called") is False
             and boundaries.get("network_request_performed") is False
             and boundaries.get("external_bytes_received") is False
             and boundaries.get("snapshot_retained") is False
             and boundaries.get("prediction_data_admitted") is False
             and boundaries.get("train_dev_or_final_read") is False
             and boundaries.get("training_or_evaluation_performed") is False,
             "compiled bridge effect boundary widened")

    bundle_path = artifacts / "request-plan-bundle.json"
    fresh_json(bundle_path, first)
    result = {
        "schema": CANARY_CHILD_SCHEMA,
        "canary_id": CANARY_ID,
        "passed": True,
        "release": claim["release"],
        "runtime_sha256": args.runtime_sha256,
        "d0_evidence_sha256": dict(D0_FILE_SHA256),
        "request_plan_canonical_sha256": REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": REQUEST_BUNDLE_CANONICAL_SHA256,
        "request_bundle_file_sha256": file_hash(bundle_path),
        "supervisor_claim_sha256": claim_sha256,
        "provider_calls": 0,
        "network_requests": 0,
        "actual_provider_cost_usd": "0",
        "external_bytes_received": 0,
        "public_fetch_performed": False,
        "snapshot_retained": False,
        "data_admitted": False,
        "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "automatic_retry": False,
    }
    fresh_json(artifacts / "result.json", result)
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--artifacts", required=True, type=Path)
    value.add_argument("--supervisor-claim", required=True, type=Path)
    value.add_argument("--cycle-id", required=True)
    value.add_argument("--release-tag", required=True)
    value.add_argument("--release-commit", required=True)
    value.add_argument("--release-tag-object", required=True)
    value.add_argument("--source-sha256", required=True)
    value.add_argument("--runtime-sha256", required=True)
    value.add_argument("--d0-decision", required=True, type=Path)
    value.add_argument("--d0-submission", required=True, type=Path)
    value.add_argument("--d0-provenance", required=True, type=Path)
    value.add_argument("--d0-raw-response", required=True, type=Path)
    value.add_argument("--d0-packet", required=True, type=Path)
    value.add_argument("--d0-publication", required=True, type=Path)
    value.add_argument("--d0-result", required=True, type=Path)
    value.add_argument("--d0-review", required=True, type=Path)
    return value


def main() -> None:
    print(canonical(run(parser().parse_args())))


if __name__ == "__main__":
    main()
