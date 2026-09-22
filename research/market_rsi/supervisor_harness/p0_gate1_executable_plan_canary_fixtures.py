"""Frozen offline fixtures for the Gate 1 executable-plan canary.

This module is data-only authority for a synthetic canary.  It never invokes a
provider, opens a socket, fetches public data, or admits data.  The integration
compiler and canary runner may import these fixtures, but production code must
not treat the synthetic catalog commitment as a real catalog admission.
"""
from __future__ import annotations

from copy import deepcopy

from market_rsi import canonical


FIXTURE_SCHEMA = "market_p0_gate1_executable_plan_canary_fixture_v1"
CATALOG_COMMITMENT_ID = "gate1_synthetic_train_catalog_v1"
EXACT_SAMPLE_RULE = (
    "Select the first, middle, and last games by game_date and game_id from "
    "the frozen public Train catalog."
)

VALID_DECISION = {
    "schema": "market_p0_gate1_controller_decision_v2",
    "investigation_id": "gate1-executable-plan-canary",
    "question_id": "2025_whole_season_trade_access",
    "source_id": "polymarket_official_trades",
    "hypothesis": (
        "Three fixed public Train markets may expose bounded historical "
        "trade rows through the official trade interface."
    ),
    "fixed_sample_rule": EXACT_SAMPLE_RULE,
    "requested_operations": ["fetch_fixed_public_sample"],
    "expected_evidence": (
        "One exact six-request manifest bound to three deterministic Train "
        "sample IDs, fixed windows, and canonical hashes."
    ),
    "max_requests": 6,
    "max_bytes": 2_000_000,
    "max_minutes": 15,
    "max_provider_cost_usd": "0",
    "stop_rule": (
        "Stop before dispatch; this canary only compiles an offline request "
        "manifest and authorizes no fetch."
    ),
}

_DATES_AND_STARTS = (
    ("2025-09-04", 1_757_016_000),
    ("2025-09-11", 1_757_620_800),
    ("2025-09-18", 1_758_225_600),
    ("2025-09-25", 1_758_830_400),
    ("2025-10-02", 1_759_435_200),
)

FROZEN_TRAIN_CATALOG = {
    "schema": "market_p0_gate1_train_catalog_v1",
    "catalog_id": "gate1-train-canary-catalog-v1",
    "source_id": "polymarket_public_trades_v1",
    "data_scope": "public_train_only",
    "rows": [
        {
            "game_date": game_date,
            "game_id": f"train-game-{number:03d}",
            "split_role": "market_train",
            "condition_id": "0x" + f"{number:064x}",
            "asset_ids": [str(10_000 + number), str(20_000 + number)],
            "start_timestamp": start,
            "end_timestamp": start + 61_200,
        }
        for number, (game_date, start) in enumerate(_DATES_AND_STARTS, 1)
    ],
}

EXPECTED_REQUEST_PLAN_INPUTS = [
    {
        "sample_id": "train-game-001",
        "condition_id": "0x" + "0" * 63 + "1",
        "asset_ids": ["10001", "20001"],
        "start_timestamp": 1_757_016_000,
        "end_timestamp": 1_757_077_200,
        "input_sha256": (
            "59f996c99e7354a1ba5c7c6c4436432df1c31937908ecfed2f5b3e8e6d552150"
        ),
    },
    {
        "sample_id": "train-game-003",
        "condition_id": "0x" + "0" * 63 + "3",
        "asset_ids": ["10003", "20003"],
        "start_timestamp": 1_758_225_600,
        "end_timestamp": 1_758_286_800,
        "input_sha256": (
            "8438fd07898fe1ed8923bb84a839d779fa40ae32e0ead8860783bab2f515de53"
        ),
    },
    {
        "sample_id": "train-game-005",
        "condition_id": "0x" + "0" * 63 + "5",
        "asset_ids": ["10005", "20005"],
        "start_timestamp": 1_759_435_200,
        "end_timestamp": 1_759_496_400,
        "input_sha256": (
            "b7a713ca70c5b18f041b665812814dba2d01ba3d14d7cc7ad566f1072e78dd7d"
        ),
    },
]

EXPECTED_WAVE1 = {
    "catalog_file_sha256": (
        "33722e897d13213298c00009511e962cfae3b72464cc053345e183dc21a02068"
    ),
    "catalog_canonical_sha256": (
        "33722e897d13213298c00009511e962cfae3b72464cc053345e183dc21a02068"
    ),
    "selected_sample_ids": [
        "train-game-001", "train-game-003", "train-game-005",
    ],
    "selected_rows_sha256": (
        "5012a3d00cf65e08af8829daf67cc4e9b80123f363ce01a08bd9776f2f87d234"
    ),
    "request_plan_inputs_sha256": (
        "784147a202221932dcf7d29221581b54bb3dc8c71085e066d64be76e211ab410"
    ),
    "materialization_body_sha256": (
        "b8a96e3a6c6d80a39439fc839392b74da82d25e9bf7d2362ff381c64ad15a113"
    ),
    "materialization_canonical_sha256": (
        "1917efd8487010634cc09e9c4fba7cb71980d1f023af1f54a0e7944a1f982abb"
    ),
    "materialization_file_sha256": (
        "2e33b6c0ab1a0ed40a7ca01855f3e70373d6a21f3eb0ca6b2e13cb999c7ab29f"
    ),
    "trade_builder_input_sha256": (
        "ec81737835f5d2d02cafbab4afe9015b4056371ffffbb8e077a37eb7bfb3368c"
    ),
    "trade_request_manifest_sha256": (
        "62d5fa5ab1d30ff2fe93a8bcf236eb498a49a96f61d208778356d86b22334207"
    ),
    "trade_request_manifest_file_sha256": (
        "269934e2347f1b569b65d8aa81a8b1a0542b9c6eb2fb294c51b85415eebf2305"
    ),
    "execution_receipt_contract_sha256": (
        "ee83c6807da13820452887dd0a5b82aebe935379c70252a2f95fc5290b524049"
    ),
    "execution_receipt_contract_file_sha256": (
        "7bc490b69da3f2a0317b2883dc6df05ce0b5b1f9f741a5a9b65bbb70b2a5dc5d"
    ),
    "request_url_sha256": [
        "af6032c6bc26aaec76d965803ab00e988684f623bdcb469220f26695d768a649",
        "0065ad0eb1f3af318994c5afc951d687a6dec437219e9d47f434bd785d5da307",
        "b56092b5c2ce877d962bfd4121ecef1cda3af201797bdbf0855b6b16b5460863",
        "f8b15a8107e4fc525449278261119d5ac3c74eda21d1093f80882f52d080124b",
        "c42289513128c1381b9dd4862d937e05a4b083aafe6ef4887de82d51eed5f6d3",
        "920917cab126c20d79dcde3ae162c0dc47d88acbdc02ce7beca531eb6c32de4e",
    ],
}

EXPECTED_COMPILED = {
    "broker_task_canonical_sha256": (
        "a50bd521b0f1b4ebf859d35ec0f9d4b85c6f50fd2ece32c7b80b2b15aaca23b0"
    ),
    "broker_task_file_sha256": (
        "22b81f2fa6e3bcb51b346d876be22d237c47d3c01aa3968db85a2527d182ff4a"
    ),
    "exact_manifest_canonical_sha256": (
        "4ac764ede080f6528de9c462fae18c88cc29393e52c375744a385f519c37edb6"
    ),
    "exact_manifest_file_sha256": (
        "04d21b0a30debf2b8a203da0dca935be5c0236573ca760a56afd7008559fae9e"
    ),
    "execution_receipt_contract_canonical_sha256": (
        "ecd84d9eb97b32d58f01a6576bc4dcd3824d4ec7dfa96c8bb5bcb2348ab6f5fa"
    ),
    "execution_receipt_contract_file_sha256": (
        "7c939168e21712e7a333619212f18ac16ff460f291f755020be277a06eeef3db"
    ),
    "compiled_bundle_canonical_sha256": (
        "26683f69053390bcc9125ab141ac73303fbff0583aab5adff505652469252bf9"
    ),
    "compiled_bundle_file_sha256": (
        "8a057d009041d8de070115aa9bd6d7338779caa103d15fc662228504e86b9180"
    ),
}

ZERO_SIDE_EFFECT_ASSERTIONS = {
    "provider_calls": 0,
    "provider_cost_usd": "0",
    "network_requests_made": 0,
    "bytes_fetched": 0,
    "public_fetch_performed": False,
    "dev_data_read": False,
    "final_data_read": False,
    "formal_data_admitted": False,
}

# Each mutation is declarative so the future canary runner can apply it without
# importing executable payloads from fixture data.  ``must_fail_before`` is the
# first artifact that must not exist after the rejection.
ADVERSARIAL_VECTORS = (
    {
        "case_id": "decision_model_url_injection",
        "threats": ["url_injection", "authority_injection"],
        "stage": "decision",
        "mutation": {"op": "add", "path": "/url",
                     "value": "https://example.invalid/trades"},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "decision_handler_authority_injection",
        "threats": ["authority_injection"],
        "stage": "decision",
        "mutation": {"op": "add", "path": "/handler_id",
                     "value": "caller.supplied:v999"},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "decision_unknown_operation",
        "threats": ["unknown_operation"],
        "stage": "decision",
        "mutation": {"op": "set", "path": "/requested_operations/0",
                     "value": "download_everything"},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "decision_dev_final_request",
        "threats": ["dev_final"],
        "stage": "decision",
        "mutation": {"op": "set", "path": "/hypothesis",
                     "value": "Read route_dev and sealed_final rows."},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "decision_request_budget_expansion",
        "threats": ["budget_expansion"],
        "stage": "decision",
        "mutation": {"op": "set", "path": "/max_requests", "value": 7},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "decision_duplicate_field",
        "threats": ["duplicate_field"],
        "stage": "decision_json",
        "mutation": {"op": "append_duplicate_member",
                     "member": "max_requests", "value": 6},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "packet_registry_shallow_alias_mutation",
        "threats": ["authority_injection", "hash_tamper"],
        "stage": "packet",
        "mutation": {"op": "mutate_after_build",
                     "path": "/allowed_sources/1/url",
                     "value": "https://example.invalid/alias"},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "packet_rights_shallow_alias_mutation",
        "threats": ["authority_injection", "hash_tamper"],
        "stage": "packet",
        "mutation": {"op": "mutate_after_build",
                     "path": "/trusted_rights_policy/policy_id",
                     "value": "weakened"},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "packet_hard_limits_tamper",
        "threats": ["budget_expansion", "hash_tamper"],
        "stage": "packet_and_decision",
        "mutation": {"op": "expand_packet_and_decision_limits",
                     "max_bytes": 999_999_999, "max_minutes": 999_999},
        "must_fail_before": "broker_task",
    },
    {
        "case_id": "catalog_changed_with_old_hash",
        "threats": ["hash_tamper"],
        "stage": "catalog",
        "mutation": {"op": "set", "path": "/rows/0/game_id",
                     "value": "tampered-game"},
        "must_fail_before": "materialization",
    },
    {
        "case_id": "catalog_changed_with_caller_rehash",
        "threats": ["hash_tamper", "authority_injection"],
        "stage": "catalog",
        "mutation": {"op": "set_then_rehash", "path": "/rows/0/game_id",
                     "value": "caller-rehashed-game"},
        "must_fail_before": "materialization",
    },
    {
        "case_id": "catalog_duplicate_field",
        "threats": ["duplicate_field"],
        "stage": "catalog_json",
        "mutation": {"op": "append_duplicate_member",
                     "member": "catalog_id", "value": "duplicate"},
        "must_fail_before": "materialization",
    },
    {
        "case_id": "catalog_dev_row",
        "threats": ["dev_final"],
        "stage": "catalog",
        "mutation": {"op": "set", "path": "/rows/1/split_role",
                     "value": "route_dev"},
        "must_fail_before": "materialization",
    },
    {
        "case_id": "catalog_final_scope",
        "threats": ["dev_final"],
        "stage": "catalog",
        "mutation": {"op": "set", "path": "/data_scope",
                     "value": "sealed_final"},
        "must_fail_before": "materialization",
    },
    {
        "case_id": "catalog_duplicate_sample_id",
        "threats": ["non_unique_sample"],
        "stage": "catalog",
        "mutation": {"op": "copy", "from": "/rows/0/game_id",
                     "path": "/rows/1/game_id"},
        "must_fail_before": "materialization",
    },
    {
        "case_id": "catalog_only_two_rows",
        "threats": ["non_unique_sample"],
        "stage": "catalog",
        "mutation": {"op": "truncate_rows", "length": 2},
        "must_fail_before": "materialization",
    },
    {
        "case_id": "materialization_commitment_tamper",
        "threats": ["hash_tamper"],
        "stage": "materialization",
        "mutation": {"op": "set", "path": "/materialization_sha256",
                     "value": "0" * 64},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "materialization_input_hash_tamper",
        "threats": ["hash_tamper"],
        "stage": "materialization",
        "mutation": {"op": "set",
                     "path": "/request_plan_inputs/0/input_sha256",
                     "value": "f" * 64},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "materialization_missing_commitment",
        "threats": ["hash_tamper"],
        "stage": "materialization",
        "mutation": {"op": "remove", "path": "/materialization_sha256"},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "materialization_missing_request_inputs_commitment",
        "threats": ["hash_tamper"],
        "stage": "materialization",
        "mutation": {"op": "remove",
                     "path": "/request_plan_inputs_sha256"},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_arbitrary_well_formed_input_hash",
        "threats": ["hash_tamper"],
        "stage": "trade_builder_input",
        "mutation": {"op": "set",
                     "path": "/request_plan_inputs/0/input_sha256",
                     "value": "e" * 64},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_limit_pagination_gap",
        "threats": ["unknown_parameter", "budget_expansion"],
        "stage": "trade_builder_input",
        "mutation": {"op": "set", "path": "/limit", "value": 50},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_unknown_parameter",
        "threats": ["unknown_parameter"],
        "stage": "trade_builder_input",
        "mutation": {"op": "add", "path": "/query",
                     "value": {"maker": "caller"}},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_url_injection",
        "threats": ["url_injection"],
        "stage": "trade_builder_input",
        "mutation": {"op": "add", "path": "/url",
                     "value": "https://example.invalid/trades"},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_budget_expansion",
        "threats": ["budget_expansion"],
        "stage": "trade_builder_input",
        "mutation": {"op": "set", "path": "/max_total_bytes",
                     "value": 2_000_001},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_retry_injection",
        "threats": ["retry"],
        "stage": "trade_builder_input",
        "mutation": {"op": "add", "path": "/retry_count", "value": 1},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_redirect_injection",
        "threats": ["redirect"],
        "stage": "trade_builder_input",
        "mutation": {"op": "add", "path": "/follow_redirects",
                     "value": True},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_auth_injection",
        "threats": ["auth"],
        "stage": "trade_builder_input",
        "mutation": {"op": "add", "path": "/authorization",
                     "value": "Bearer fixture-not-a-secret"},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_paid_injection",
        "threats": ["paid"],
        "stage": "trade_builder_input",
        "mutation": {"op": "add", "path": "/paid_access_allowed",
                     "value": True},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "builder_write_injection",
        "threats": ["write"],
        "stage": "trade_builder_input",
        "mutation": {"op": "add", "path": "/method", "value": "POST"},
        "must_fail_before": "exact_request_manifest",
    },
    {
        "case_id": "compiled_manifest_url_hash_tamper",
        "threats": ["hash_tamper", "url_injection"],
        "stage": "compiled_bundle",
        "mutation": {"op": "set",
                     "path": "/exact_request_manifest/requests/0/url",
                     "value": "https://example.invalid/tampered"},
        "must_fail_before": "canary_pass",
    },
    {
        "case_id": "compiled_source_mapping_tamper",
        "threats": ["authority_injection", "hash_tamper"],
        "stage": "compiled_bundle",
        "mutation": {"op": "set",
                     "path": ("/exact_request_manifest/source_mapping/"
                              "execution_source_registry_id"),
                     "value": "caller_execution_source"},
        "must_fail_before": "canary_pass",
    },
    {
        "case_id": "compiled_offline_builder_mislabeled_as_executor",
        "threats": ["authority_injection", "write", "hash_tamper"],
        "stage": "compiled_bundle",
        "mutation": {"op": "set",
                     "path": ("/exact_request_manifest/handler_chain/"
                              "future_executor_handler_id"),
                     "value": "p0_gate1_trade_query.build_bundle:v1"},
        "must_fail_before": "canary_pass",
    },
    {
        "case_id": "compiled_policy_retry_redirect_auth_paid_write_tamper",
        "threats": ["retry", "redirect", "auth", "paid", "write",
                    "hash_tamper"],
        "stage": "compiled_bundle",
        "mutation": {"op": "weaken_execution_policy"},
        "must_fail_before": "canary_pass",
    },
)

REQUIRED_THREATS = frozenset({
    "hash_tamper", "url_injection", "authority_injection",
    "unknown_operation", "unknown_parameter", "dev_final",
    "budget_expansion", "duplicate_field", "non_unique_sample", "retry",
    "redirect", "auth", "paid", "write",
})


def frozen_catalog_bytes() -> bytes:
    """Return the exact no-newline catalog bytes bound by EXPECTED_WAVE1."""
    return canonical(FROZEN_TRAIN_CATALOG).encode("utf-8")


def trade_builder_input() -> dict:
    """Return the exact trusted builder envelope expected after materialization."""
    return {
        "schema": "market_p0_gate1_trade_query_input_v1",
        "source_id": "polymarket_public_trades_v1",
        "data_scope": "public_train_only",
        "request_plan_inputs": deepcopy(EXPECTED_REQUEST_PLAN_INPUTS),
        "limit": 100,
        "offsets": [0, 100],
        "max_requests": 6,
        "max_total_bytes": 2_000_000,
        "max_elapsed_seconds": 900,
    }


def fixture() -> dict:
    """Return a caller-mutable copy of the complete synthetic fixture."""
    return {
        "schema": FIXTURE_SCHEMA,
        "catalog_commitment_id": CATALOG_COMMITMENT_ID,
        "decision": deepcopy(VALID_DECISION),
        "frozen_train_catalog": deepcopy(FROZEN_TRAIN_CATALOG),
        "expected_wave1": deepcopy(EXPECTED_WAVE1),
        "expected_compiled": deepcopy(EXPECTED_COMPILED),
        "zero_side_effect_assertions": deepcopy(ZERO_SIDE_EFFECT_ASSERTIONS),
        "adversarial_vectors": deepcopy(ADVERSARIAL_VECTORS),
    }
