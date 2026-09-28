"""Offline child for the production-CLI Gate 1 acceptance canary.

This executable uses the real Gate 1 live-entry function and exact production
arguments. It substitutes only publication verification and the provider
backend with explicit offline fixtures. It cannot be selected through the
production CLI and never reads a real provider credential.
"""
from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from glm_canary import HF_MODEL
from market_rsi import digest, load_json
from supervisor_harness import p0_gate1_controller_live_entry as live_entry
from supervisor_harness import protocol_source_release
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake, SUBMIT_TOOL,
)


def _decision() -> dict:
    options = live_entry.adapter.expected_packet()["prospective_source_scope_decision"]
    pair = options["source_response_options"][1]
    split = options["split_policy"]
    cutoff = options["cutoff_contract"]
    return {
        "scientific_source_response": {
            "source_registry_entry_id": pair["source_registry_entry_id"],
            "response_class_id": pair["response_class_id"],
        },
        "intended_uses": {"requested_use_ids": ["model_training", "private_research"]},
        "future_role_split": {
            "requested_future_role": "train_candidate",
            "split_policy_id": split["split_policy_id"],
            "split_policy_sha256": split["split_policy_sha256"],
            "exposure_ledger_id": "not_yet_created",
        },
        "horizon_cutoff": {
            "claim_semantics": "prospective_point_in_time",
            "prediction_horizon_us": 60_000_000,
            "cutoff_semantics_id": cutoff["cutoff_semantics_id"],
            "cutoff_contract_sha256": cutoff["cutoff_contract_sha256"],
            "label_window_start_relation": "strictly_after_cutoff",
            "label_window_end_relation": "at_or_before_cutoff_plus_horizon",
        },
        "bounded_investigation": {
            "mode": "first_party_document_review_only",
            "max_documents_proposed": 1,
            "max_provider_requests_proposed": 0,
            "max_raw_bytes_proposed": 0,
            "max_elapsed_seconds_proposed": 300,
        },
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


_OFFLINE_KEY_SENTINEL = object()
_OFFLINE_ENVIRONMENT = b"MARKET_RSI_OFFLINE_CANARY=1\n"


class _OfflineOnlyBackendFactory:
    """One-shot constructor that cannot construct a live provider backend."""

    def __init__(self, backend: OfflineGate1ProviderFake,
                 expected_cache: Path):
        self.backend = backend
        self.expected_cache = Path(expected_cache)
        self.calls = 0

    def __call__(self, key, tokenizer_cache: Path):
        self.calls += 1
        if (self.calls != 1 or key is not _OFFLINE_KEY_SENTINEL
                or Path(tokenizer_cache) != self.expected_cache):
            raise RuntimeError("offline-only backend construction changed")
        return self.backend


def _offline_environment(path: Path) -> dict:
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.resolve() != path
            or path.read_bytes() != _OFFLINE_ENVIRONMENT):
        raise ValueError("exact credential-free canary environment required")
    return {"TINKER_API_KEY": _OFFLINE_KEY_SENTINEL}


def _bootstrap_verifier(args):
    """Return an exact verifier override only for the typed bootstrap proof."""
    if Path(args.prior_canary_receipt).name != (
            live_entry.gate1_canary_receipt.FIRST_CANARY_BOOTSTRAP_FILE):
        return nullcontext()
    expected = live_entry.gate1_canary_receipt.verify_first_canary_bootstrap(
        args.prior_canary_receipt,
        expected_bootstrap_sha256=args.prior_canary_sha256,
        expected_source_sha256=args.expected_source_sha256,
        expected_runtime_sha256=digest(
            live_entry.shared_entry._regular_json(args.runtime_receipt)),
        expected_release_tag=args.release_tag,
        expected_release_commit=args.expected_release_commit,
        expected_release_tag_object=args.expected_release_tag_object,
        expected_child_entry=Path(__file__).resolve(),
    )

    def verify(receipt_path, **commitments):
        observed = live_entry.gate1_canary_receipt.verify_first_canary_bootstrap(
            receipt_path,
            expected_bootstrap_sha256=commitments[
                "expected_receipt_sha256"],
            expected_source_sha256=commitments["expected_source_sha256"],
            expected_runtime_sha256=commitments["expected_runtime_sha256"],
            expected_release_tag=commitments["expected_release_tag"],
            expected_release_commit=commitments["expected_release_commit"],
            expected_release_tag_object=commitments[
                "expected_release_tag_object"],
            expected_child_entry=Path(__file__).resolve(),
        )
        if observed != expected:
            raise ValueError("first-canary bootstrap commitments changed")
        return observed

    return patch.object(
        live_entry.gate1_canary_receipt,
        "verify_gate1_canary_receipt", side_effect=verify)


def run(args) -> dict:
    sources = protocol_source_release.source_hashes()
    source_sha = digest(sources)
    if args.expected_source_sha256 != source_sha:
        raise ValueError("canary source manifest differs from exact CLI input")
    publication = {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": "synthetic-offline-production-cli-canary",
        "tag": args.release_tag,
        "commit": args.expected_release_commit,
        "tag_object": args.expected_release_tag_object,
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
    backend_factory = _OfflineOnlyBackendFactory(
        backend, args.tokenizer_cache)
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
                     new=backend_factory),
        patch.object(live_entry, "dotenv_values",
                     side_effect=_offline_environment),
        _bootstrap_verifier(args),
        catalog_override,
    ):
        result = live_entry.run(args)
    adapter_root = Path(args.root) / "adapter" / args.cycle_id
    provider_receipt = load_json(adapter_root / "provider-receipt.json")
    meter = load_json(Path(args.budget_root) / f"{args.cycle_id}.metering.json")
    if (backend_factory.calls != 1
            or backend.encode_calls != 1 or backend.sample_calls != 1
            or result.get("execution_mode") != "offline_fake"):
        raise RuntimeError("offline production-CLI child did not run once")
    if (provider_receipt.get("provider_called") is not False
            or meter.get("provider_called") is not False):
        raise RuntimeError("offline production-CLI child provider boundary changed")
    return result


if __name__ == "__main__":
    print(json.dumps(
        run(live_entry.parser().parse_args()), sort_keys=True))
