"""Compile one unchanged archived candidate; never generate, retry or settle."""
import json
from pathlib import Path
import re
import sqlite3

import earnings_controller as controller
import earnings_entry as entry
from earnings_loop_policy import validate_envelope
from edgar_forecast_openai import token, unit

NAMES = {"response": "01-response.json", "count": "01-count.json", "request": "01-request.json",
         "failure_result": "result.json", "identity": "identity.json"}
FIELDS = set(NAMES) | {"input_packet", "original_source_commit"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def path(value):
    if type(value) is not str:
        raise ValueError("Canonical archive path required")
    result = Path(value)
    if not result.is_absolute() or str(result) != value or result.resolve() != result:
        raise ValueError("Canonical archive path required")
    return result


def read(binding, expected):
    if (type(binding) is not dict or set(binding) != {"path", "sha256"}
            or path(binding["path"]) != expected or type(binding["sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])):
        raise ValueError("Exact archive slot/hash binding required")
    return entry.strict_json(entry.checked(binding).decode())


def accounting(config, count, request, response):
    limits = {"max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600}
    rates = config["runtime_config"]["models"][config["model"]]
    counted = token(count["input_tokens"])
    if counted > limits["max_input_tokens"]:
        raise ValueError("Original count exceeds fixed Controller limit")
    usage = response["usage"]
    inp, out = token(usage["input_tokens"]), token(usage["output_tokens"])
    cached = token(usage["input_tokens_details"]["cached_tokens"])
    if (response.get("model") != rates["api_model"] or response.get("service_tier") != "default"
            or token(usage["total_tokens"]) != inp + out or cached > inp or inp > counted or out > 16384):
        raise ValueError("Original response model/tier/usage exceeds reservation")
    ceiling = max(unit(rates[k]) for k in ("input", "cached", "write") if rates[k] is not None)
    reserved = counted * ceiling + 16384 * unit(rates["output"])
    charge = (inp - cached) * ceiling + cached * unit(rates["cached"]) + out * unit(rates["output"])
    if (type(request.get("request_id")) is not str or not request["request_id"]
            or type(request.get("reserved_nano_usd")) is not int or request["reserved_nano_usd"] != reserved):
        raise ValueError("Original request reservation differs")
    ledger = path(config["ledger"])
    if not ledger.is_file():
        raise ValueError("Existing sole ledger required; no initialization")
    db = sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)
    try:
        db.execute("BEGIN")
        row = db.execute("SELECT model,reserved,charged,status FROM requests WHERE id=?", (request["request_id"],)).fetchone()
        if (row is None or row[:2] != (rates["api_model"], reserved)
                or row[3] not in ("settled", "settled_upper_bound")
                or (row[3] == "settled" and row[2] != charge)
                or (row[3] == "settled_upper_bound" and (row[2] != reserved or row[2] < charge))):
            raise ValueError("Original charge is absent, uncertain or inconsistent")
    finally:
        db.close()
    return {"request_id": request["request_id"], "model": row[0], "reserved_nano_usd": reserved,
            "computed_charge_nano_usd": charge, "accounted_charge_nano_usd": row[2], "status": row[3]}


def archive_proposal(envelope, packet_binding, round_index):
    company, _, _ = validate_envelope(envelope)
    if type(round_index) is not int or round_index != 1:
        raise ValueError("Archived candidate is only the first Controller slot")
    config = envelope["baseline_config"]
    selector = config.get("archived_first_controller")
    if (type(selector) is not dict or set(selector) != FIELDS
            or type(selector["original_source_commit"]) is not str
            or not re.fullmatch(r"[0-9a-f]{40}", selector["original_source_commit"])
            or selector["original_source_commit"] == envelope["source_commit"]):
        raise ValueError("Exact distinct original-generation selector required")
    old = path(selector["response"]["path"]).parent
    output = path(envelope["controllers"][0])
    if old.parent != entry.ARCHIVE / "controllers" or output == old:
        raise ValueError("Original Controller directory cannot be reused")
    # All locations are checked before any old body is read.
    for key, name in NAMES.items():
        if path(selector[key]["path"]) != old / name:
            raise ValueError("Original Controller files must share exact directory")
    original_packet_path = entry.ARCHIVE / "loops" / "earnings-feedback-01" / "packet-01.json"
    if path(selector["input_packet"]["path"]) != original_packet_path:
        raise ValueError("Original first packet location differs")
    new_packet = read(packet_binding, path(envelope["root"]) / "packet-01.json")
    original_packet = read(selector["input_packet"], original_packet_path)
    bodies = {key: read(selector[key], old / name) for key, name in NAMES.items()}
    failed, identity = bodies["failure_result"], bodies["identity"]
    limits = {"max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600}
    if (failed.get("status") != "FAILED_NO_RETRY" or failed.get("error_type") != "ValueError"
            or identity.get("source_commit") != selector["original_source_commit"]
            or identity.get("input_packet") != selector["input_packet"]
            or type(identity.get("round_index")) is not int or identity["round_index"] != 1
            or canonical(identity.get("limits")) != canonical(limits)
            or config.get("inherited_clock", {}).get("source_commit") != selector["original_source_commit"]
            or identity.get("clock") != config["inherited_clock"]["binding"]):
        raise ValueError("Original failure/source/input/limits identity differs")
    original_input, new_input = controller.safe_input(original_packet), controller.safe_input(new_packet)
    if (canonical(original_input) != canonical(new_input) or new_packet["task_id"] != config["task_id"]
            or new_packet["questions"] != entry.FilingTools(company).files["questions.md"]):
        raise ValueError("Original and recovery Controller context differ")
    payload = bodies["request"]["payload"]
    rates = config["runtime_config"]["models"][config["model"]]
    if (set(payload) != {"model", "reasoning", "tools", "tool_choice", "parallel_tool_calls", "instructions", "input"}
            or payload["model"] != rates["api_model"] or payload["reasoning"] != {"effort": rates["effort"]}
            or payload["tools"] != [] or payload["tool_choice"] != "none" or payload["parallel_tool_calls"] is not False
            or type(payload["instructions"]) is not str or not payload["instructions"]
            or len(payload["input"]) != 1 or set(payload["input"][0]) != {"role", "content"}
            or payload["input"][0]["role"] != "user"
            or canonical(entry.strict_json(payload["input"][0]["content"])) != canonical(original_input)):
        raise ValueError("Original counted Controller payload differs")
    recipe = controller.parse_recipe(bodies["response"], original_packet)
    instructions = recipe["research_instructions"]
    if not instructions.isascii() or not 2000 < len(instructions) <= 2200 or len(instructions.encode()) > 4096:
        raise ValueError("Only the original character-cap boundary may be relaxed")
    charged = accounting(config, bodies["count"], bodies["request"], bodies["response"])
    output.mkdir(parents=True, exist_ok=False)
    entry.durable_json(output / "identity.json", {"source_commit": envelope["source_commit"],
        "loop_policy_sha256": envelope["loop_policy_sha256"], "round_index": 1, "input_packet": packet_binding,
        "limits": limits, "clock": config["inherited_clock"]["binding"],
        "generation_mode": "archived_candidate_compilation"})
    entry.durable_json(output / "archive-origin.json", {"schema": "earnings_controller_archive_origin_v1",
        "original_generation_source_commit": selector["original_source_commit"],
        "current_compiler_source_commit": envelope["source_commit"], "original_bindings": selector,
        "original_status": "FAILED_NO_RETRY", "original_error_type": "ValueError",
        "original_accounting": charged, "new_input_packet": packet_binding, "new_provider_calls": 0,
        "new_generations": 0, "original_generations": 1, "research_instructions_characters": len(instructions)})
    proposal = {"recipe": recipe, "input_packet": packet_binding, "source_commit": envelope["source_commit"]}
    entry.durable_json(output / "proposal.json", proposal)
    entry.durable_json(output / "result.json", {"status": "COMPLETED_ARCHIVED_PROPOSAL", "new_provider_calls": 0,
        "new_generations": 0, "original_status": "FAILED_NO_RETRY"})
    result = output / "proposal.json"
    return {"path": str(result), "sha256": entry.digest(result.read_bytes())}
