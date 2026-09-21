"""Offline child for the production-CLI Gate 1 acceptance canary.

This executable uses the real Gate 1 live-entry function and exact production
arguments. It substitutes only publication verification and the provider
backend with explicit offline fixtures. It cannot be selected through the
production CLI and never reads a real provider credential.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from glm_canary import HF_MODEL
from market_rsi import digest
from supervisor_harness import p0_gate1_controller_live_entry as live_entry
from supervisor_harness import protocol_source_release
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake,
)
from supervisor_harness.p0_gate1_research_contract import DECISION_SCHEMA


def _decision() -> dict:
    return {
        "schema": DECISION_SCHEMA,
        "investigation_id": "gate1-production-cli-canary-plan",
        "question_id": "2025_whole_season_trade_access",
        "source_id": "polymarket_official_trades",
        "hypothesis": (
            "The official interface documents historical market trade access."
        ),
        "fixed_sample_rule": (
            "Inspect the one frozen official documentation page."
        ),
        "requested_operations": ["inspect_official_documentation"],
        "expected_evidence": (
            "A bounded page hash and documented interface fields."
        ),
        "rights_check": "Record only rights stated by the official source.",
        "max_requests": 1,
        "max_bytes": 100000,
        "max_minutes": 10,
        "max_provider_cost_usd": "0",
        "stop_rule": (
            "Stop after one response or any redirect, error, timeout, or "
            "rights uncertainty."
        ),
    }


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
    raw = "offline reasoning</think>\n" + json.dumps(
        _decision(), sort_keys=True)
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
    with (
        patch.object(live_entry.outer, "_publication",
                     return_value=publication),
        patch.object(live_entry.shared_outer, "_runtime",
                     return_value=runtime),
        patch.object(live_entry, "TinkerGLMBackend",
                     return_value=backend),
    ):
        result = live_entry.run(args)
    if (backend.encode_calls != 1 or backend.sample_calls != 1
            or result.get("execution_mode") != "offline_fake"):
        raise RuntimeError("offline production-CLI child did not run once")
    return result


if __name__ == "__main__":
    print(json.dumps(
        run(live_entry.parser().parse_args()), sort_keys=True))
