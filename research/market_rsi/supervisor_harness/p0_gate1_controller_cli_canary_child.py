"""Offline child for the production-CLI Gate 1 acceptance canary.

This executable uses the real Gate 1 live-entry function and exact production
arguments. It substitutes only publication verification and the provider
backend with explicit offline fixtures. It cannot be selected through the
production CLI and never reads a real provider credential.
"""
from __future__ import annotations

import json
from contextlib import nullcontext
from unittest.mock import patch

from glm_canary import HF_MODEL
from market_rsi import digest
from supervisor_harness import p0_gate1_controller_live_entry as live_entry
from supervisor_harness import protocol_source_release
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake, SUBMIT_TOOL,
)


def _decision() -> dict:
    return {
        "choice_id": "pm_trades_docs_one",
        "question_id": "2025_whole_season_trade_access",
        "hypothesis": (
            "The official interface documents historical market trade access."
        ),
        "expected_evidence": (
            "A bounded page hash and documented interface fields."
        ),
        "stop_rule": (
            "Stop after one response or any redirect, error, timeout, or "
            "rights uncertainty."
        ),
    }


def _submission(value: dict) -> str:
    arguments = []
    for key, item in value.items():
        encoded = item if isinstance(item, str) else json.dumps(
            item, separators=(",", ":"))
        arguments.append(
            f"<arg_key>{key}</arg_key><arg_value>{encoded}</arg_value>")
    return ("offline reasoning</think>\n"
            f"<tool_call>{SUBMIT_TOOL}" + "".join(arguments)
            + "</tool_call>")


def run(args) -> dict:
    sources = protocol_source_release.source_hashes()
    source_sha = digest(sources)
    if args.expected_source_sha256 != source_sha:
        raise ValueError("canary source manifest differs from exact CLI input")
    publication = {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": "synthetic-offline-production-cli-canary",
        "tag": args.release_tag,
        "commit": "1" * 40,
        "tag_object": "2" * 40,
        "source_sha256": source_sha,
        "source_hashes": sources,
        "isolation_proven": False,
        "model_authorship_proven": False,
    }
    raw = _submission(_decision())
    backend = OfflineGate1ProviderFake({
        "text": raw,
        "output_tokens": [601, 602, 603],
        "cached_input_tokens": 0,
        "finish_reason": "stop",
        "provider": {
            "reported_model": HF_MODEL,
            "session_id": "offline-production-cli-canary-session",
            "sampling_session_id": (
                "offline-production-cli-canary-sampling"
            ),
        },
    })
    runtime = live_entry.shared_entry._regular_json(args.runtime_receipt)
    # Synthetic fixture is accepted only inside this offline child. The
    # production entry continues to require a reviewed real commitment.
    catalog_override = nullcontext()
    if args.catalog is not None:
        catalog_json = args.catalog.read_bytes()
        if live_entry.file_hash(args.catalog) != args.expected_catalog_file_sha256:
            raise ValueError("synthetic canary catalog differs from frozen hash")
        catalog_override = patch.object(
            live_entry, "_reviewed_catalog", return_value=(
                catalog_json, args.catalog_commitment_id))
    with (
        patch.object(live_entry.outer, "_publication",
                     return_value=publication),
        patch.object(live_entry.shared_outer, "_runtime",
                     return_value=runtime),
        patch.object(live_entry, "TinkerGLMBackend",
                     return_value=backend),
        catalog_override,
    ):
        result = live_entry.run(args)
    if (backend.encode_calls != 1 or backend.sample_calls != 1
            or result.get("execution_mode") != "offline_fake"):
        raise RuntimeError("offline production-CLI child did not run once")
    return result


if __name__ == "__main__":
    print(json.dumps(
        run(live_entry.parser().parse_args()), sort_keys=True))
