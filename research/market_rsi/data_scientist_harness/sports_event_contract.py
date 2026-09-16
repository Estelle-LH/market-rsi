"""Synthetic contract check for event-aligned sports-market research.

This module validates declarations.  It never reads market data, certifies a
provider, admits a source, or turns a historical timestamp into live latency
evidence.
"""
from market_rsi import digest


TEXT = {"type": "string", "minLength": 1}
STATUS = {"type": "string", "enum": ["verified", "partial", "missing"]}
YES_NO = {"type": "string", "enum": ["yes", "no"]}


def obj(fields):
    return {
        "type": "object",
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }


SCHEMA = obj({
    "sport": TEXT,
    "season": TEXT,
    "requested_stage": {"type": "string", "enum": [
        "state_prediction", "market_response", "lead_lag", "executable_pnl",
    ]},
    "identity": obj({
        "canonical_game_mapping": STATUS,
        "home_away_orientation": STATUS,
        "market_outcome_orientation": STATUS,
        "resolution_rule_compatibility": STATUS,
    }),
    "play_by_play": obj({
        "provider": TEXT,
        "manifest_sha256": TEXT,
        "games": {"type": "integer"},
        "plays": {"type": "integer"},
        "coverage": STATUS,
        "immutable_raw": STATUS,
        "event_id": STATUS,
        "game_clock": STATUS,
        "provider_wall_clock": STATUS,
        "provider_publish_time": STATUS,
        "local_receive_time": STATUS,
        "correction_or_overturn_state": STATUS,
        "historical_backfill": YES_NO,
    }),
    "market": obj({
        "venue": TEXT,
        "manifest_sha256": TEXT,
        "games": {"type": "integer"},
        "streams": {"type": "array", "items": {"type": "string", "enum": [
            "market_metadata", "resolutions", "prices", "candles", "trades",
            "top_of_book", "full_depth",
        ]}},
        "immutable_raw": STATUS,
        "game_contract_mapping": STATUS,
        "source_timestamp": STATUS,
        "local_receive_time": STATUS,
        "sequence_or_snapshot_reset_state": STATUS,
        "research_storage_permission": {"type": "string", "enum": [
            "verified_for_research", "unresolved", "not_permitted",
        ]},
    }),
    "execution": obj({
        "fee_schedule": STATUS,
        "order_send_time": STATUS,
        "order_acknowledgement": STATUS,
        "fill_confirmation": STATUS,
        "cancel_acknowledgement": STATUS,
    }),
    "evaluation": obj({
        "split_unit": {"type": "string", "enum": ["game"]},
        "train_games": {"type": "integer"},
        "dev_games": {"type": "integer"},
        "final_games": {"type": "integer"},
        "chronological": YES_NO,
        "final_opened": YES_NO,
    }),
})


STAGES = ("state_prediction", "market_response", "lead_lag", "executable_pnl")


def _need(blockers, condition, message):
    if not condition:
        blockers.append(message)


def _base_blockers(contract):
    p = contract["play_by_play"]
    e = contract["evaluation"]
    blockers = []
    _need(blockers, p["games"] > 0 and p["plays"] > 0,
          "play-by-play needs positive game and play counts")
    _need(blockers, p["coverage"] == "verified", "play-by-play coverage is not verified")
    _need(blockers, p["immutable_raw"] == "verified", "immutable raw play-by-play is not verified")
    _need(blockers, p["event_id"] == "verified", "stable play/event identity is not verified")
    _need(blockers, p["game_clock"] == "verified", "game clock is not verified")
    _need(blockers, p["correction_or_overturn_state"] == "verified",
          "correction/overturn handling is not verified")
    _need(blockers, contract["identity"]["canonical_game_mapping"] == "verified",
          "canonical game mapping is not verified")
    _need(blockers, contract["identity"]["home_away_orientation"] == "verified",
          "home/away orientation is not verified")
    _need(blockers, e["split_unit"] == "game", "all rows from one game must stay in one split")
    _need(blockers, min(e["train_games"], e["dev_games"], e["final_games"]) >= 0,
          "split counts cannot be negative")
    _need(blockers, e["chronological"] == "yes", "evaluation must be chronological")
    _need(blockers, e["final_opened"] == "no", "final games have already been opened")
    _need(blockers, e["final_games"] >= 20, "final evaluation needs at least 20 untouched games")
    return blockers


def probe(contract):
    """Classify which claim layers the declared evidence could support.

    A passing result is only a software-policy check.  Independent runner
    evidence must still verify every declaration against exact source bytes.
    """
    p, m, x = contract["play_by_play"], contract["market"], contract["execution"]
    gates = {}

    state = _base_blockers(contract)
    gates["state_prediction"] = state

    response = list(state)
    _need(response, m["games"] >= 20, "market stream covers fewer than 20 games")
    _need(response, m["immutable_raw"] == "verified", "immutable raw market data is not verified")
    _need(response, m["game_contract_mapping"] == "verified",
          "game-to-contract mapping is not verified")
    _need(response, contract["identity"]["market_outcome_orientation"] == "verified",
          "YES/NO or home/away market orientation is not verified")
    _need(response, contract["identity"]["resolution_rule_compatibility"] == "verified",
          "settlement-rule compatibility is not verified")
    _need(response, m["research_storage_permission"] == "verified_for_research",
          "research storage/reuse permission is unresolved or not permitted")
    _need(response, {"market_metadata", "resolutions"}.issubset(set(m["streams"])),
          "market metadata and resolutions are both required")
    _need(response, bool({"prices", "candles", "trades", "top_of_book", "full_depth"}
                         & set(m["streams"])), "no historical market observation stream is declared")
    _need(response, p["provider_wall_clock"] == "verified",
          "descriptive play-to-market response needs a verified play wall clock")
    _need(response, m["source_timestamp"] == "verified",
          "descriptive market response needs a verified market source timestamp")
    gates["market_response"] = response

    lead = list(response)
    _need(lead, p["local_receive_time"] == "verified",
          "lead/lag needs observed local PBP receive time, not historical backfill time")
    _need(lead, m["local_receive_time"] == "verified",
          "lead/lag needs observed local market receive time")
    _need(lead, m["sequence_or_snapshot_reset_state"] == "verified",
          "lead/lag needs sequence-gap/reset handling")
    gates["lead_lag"] = lead

    pnl = list(lead)
    for field, label in (
        ("fee_schedule", "date/market-specific fee schedule"),
        ("order_send_time", "order send time"),
        ("order_acknowledgement", "order acknowledgement"),
        ("fill_confirmation", "account-confirmed fills"),
        ("cancel_acknowledgement", "cancel acknowledgement"),
    ):
        _need(pnl, x[field] == "verified", f"executable P&L needs verified {label}")
    gates["executable_pnl"] = pnl

    requested = contract["requested_stage"]
    result = {
        "schema": "sports_event_contract_probe_v1",
        "contract": contract,
        "contract_sha256": digest(contract),
        "stage_gates": {
            stage: {"policy_passed": not gates[stage], "blockers": gates[stage]}
            for stage in STAGES
        },
        "requested_stage": requested,
        "requested_stage_policy_passed": not gates[requested],
        "historical_backfill_is_live_latency_evidence": False,
        "displayed_depth_is_fill_evidence": False,
        "software_probe_only": True,
        "source_admitted": False,
        "evidence_validated_on_source_bytes": False,
    }
    result["probe_sha256"] = digest(result)
    return result


def bound_probe(store, record_id):
    record = store.get(record_id, "probe_sports_event_contract")
    result = record["result"]
    if (result.get("schema") != "sports_event_contract_probe_v1"
            or result.get("contract_sha256") != digest(result.get("contract"))
            or result.get("probe_sha256") != digest({
                k: v for k, v in result.items() if k != "probe_sha256"
            })):
        raise ValueError("sports event contract probe changed")
    return result
