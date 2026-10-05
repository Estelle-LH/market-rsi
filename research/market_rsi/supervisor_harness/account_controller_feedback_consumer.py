"""Once-only reviewed numerical feedback transport; no model text is executed."""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess

from supervisor_harness.opened_train_discovery_worker import save as _save, sha
from supervisor_harness.continuous_discovery_batch import _digest

CLI = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
CLI_SHA = "6b582e8813ce7e8ed4c52814ee5cf230dba647bf2292df747a4003f2657ef201"
MODEL = "gpt-6.1-sol"
DEADLINE, CUTOFF = "2026-10-05T19:27:11Z", "2026-10-05T19:12:11Z"
ROLES = {"feedback", "review", "scorecard", "predictions", "supplement", "memory", "history", "pool", "authority", "overhead", "request"}
FLAGS = {"external_fetch": False, "paid_provider": False, "route_dev_opened": False, "sealed_final_opened": False, "promotion_authorized": False}
NUMERIC_KEYS = ("aggregate", "folds", "paired_grouped_evidence", "source_denominator", "correction_diagnostics")
OMITTED = {"reliability_table", "by_schedule_date", "per_schedule_date_correction_diagnostics", "trainer"}


def _compact(value):
    if isinstance(value, dict): return {key: _compact(item) for key, item in value.items() if key not in OMITTED}
    if isinstance(value, list): return [_compact(item) for item in value]
    return value


def save(path, value):
    _save(path, value)
    descriptor = os.open(Path(path).parent, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _json(data):
    def pairs(items):
        result = dict(items)
        if len(result) != len(items): raise ValueError("duplicate JSON keys")
        return result
    result = json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    json.dumps(result, allow_nan=False)
    return result


def _read(binding, binary=False):
    if set(binding) != {"path", "sha256"}: raise ValueError("exact file binding required")
    path = Path(binding["path"])
    if not path.is_absolute() or path.resolve() != path or not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError("file hash/path drift")
    return path.read_bytes() if binary else _json(path.read_bytes())


def _time(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if moment.tzinfo is None: raise ValueError("timezone required")
    return moment


def check_budget(authority, now):
    expected = {"attempts": 6, "statistical_fits": 24, "live_candidate_processes": 2, "threads_per_candidate": 1, "per_attempt_seconds": 900, "sampled_rss_bytes": 1073741824, "paid_provider_calls": 0, "paid_provider_spend_usd": "0"}
    if authority["limits"] != expected or authority["deadline_utc"] != DEADLINE or authority["selection_cutoff_utc"] != CUTOFF:
        raise ValueError("outer authority changed")
    attempts = authority["attempts"]
    if _time(now) < _time(authority["start_utc"]) or _time(now) >= _time(CUTOFF) or len(attempts) >= 6:
        raise ValueError("outer selection stop")
    if len({item["attempt_id"] for item in attempts}) != len(attempts): raise ValueError("duplicate outer attempt")
    if any(type(item["fits_reserved"]) is not int or type(item["actual_fits"]) is not int or not 0 <= item["actual_fits"] <= item["fits_reserved"] <= 4 for item in attempts):
        raise ValueError("invalid actual/reserved fits")
    if sum(item["fits_reserved"] for item in attempts) + 4 > 24 or sum(item["status"] in {"claimed", "running", "execution_claimed", "execution_reserved"} for item in attempts) >= 2:
        raise ValueError("shared fit/concurrency ceiling")


def prepare_input(bindings, batch, repo, now):
    """Called by the trusted Supervisor after review; copies real numbers, not hashes alone."""
    if set(bindings) != ROLES: raise ValueError("exact feedback file roles required")
    data = {role: _read(binding, role == "predictions") for role, binding in bindings.items()}
    feedback, review, card, supplement, request = [data[name] for name in ("feedback", "review", "scorecard", "supplement", "request")]
    branch = next(item for item in batch.snapshot()["branches"] if item["attempt_id"] == feedback["attempt_id"])
    if (branch["stage"] != "controller_feedback_ready" or branch["feedback_packet"] != feedback or branch["feedback_packet_sha256"] != _digest(feedback)
            or feedback["independently_reviewed"] is not True or review["passed"] is not True
            or feedback["review_sha256"] != bindings["review"]["sha256"] or feedback["scorecard_sha256"] != bindings["scorecard"]["sha256"]
            or review["candidate_id"] != feedback["candidate_id"] or card["task_id"] != feedback["candidate_id"]
            or review["supplement_sha256"] != bindings["supplement"]["sha256"]
            or supplement["scorecard_sha256"] != bindings["scorecard"]["sha256"] or supplement["predictions_sha256"] != bindings["predictions"]["sha256"]
            or card["research_parent_sha256"] != feedback["research_parent_sha256"] or supplement["actual_parent_source_sha256"] != feedback["research_parent_sha256"]):
        raise ValueError("feedback/review/parent/supplement admission drift")
    if any(card.get(key) is not value for key, value in FLAGS.items()): raise ValueError("protected permission flag changed")
    if card.get("historical_event_clock_only") is not True or card.get("provider_cost_usd") != 0: raise ValueError("historical/cost flag changed")
    if card["source_denominator"] != {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2, "check_events": 87, "check_dates": 20, "check_game_weeks": 7}:
        raise ValueError("frozen population changed")
    if [fold["fit_events"] for fold in card["folds"]] != [106, 132, 148, 176] or [fold["check_events"] for fold in card["folds"]] != [26, 16, 28, 17]:
        raise ValueError("chronological check geometry changed")
    runner = "research/market_rsi/" + request["module"].replace(".", "/") + ".py"
    if (review["source_commit"] != request["source_commit"] or request["memory_sha256"] != bindings["memory"]["sha256"]
            or request["candidate_id"] != feedback["candidate_id"] or request["attempt_id"] != feedback["attempt_id"]
            or request["files"].get(runner) != feedback["runner_sha256"]):
        raise ValueError("source/memory binding changed")
    for name, expected in request["files"].items():
        path = Path(repo) / name
        if Path(name).is_absolute() or ".." in Path(name).parts or path.resolve() != path or sha(path) != expected:
            raise ValueError("source byte drift")
        original = subprocess.check_output(["git", "show", request["source_commit"] + ":" + name], cwd=repo)
        if hashlib.sha256(original).hexdigest() != expected: raise ValueError("source commit drift")
    if sha(request["python"]) != request["python_sha256"]: raise ValueError("runtime byte drift")
    check_budget(data["authority"], now)
    numeric = _compact({key: card[key] for key in NUMERIC_KEYS})
    result = {"schema": "controller_feedback_input_v1", "bindings": bindings, "feedback": feedback, "numerical": numeric,
        "supplement": _compact(supplement), "omitted_from_prompt": sorted(OMITTED), "memory": data["memory"], "history": data["history"], "pool": data["pool"], "authority": data["authority"], "overhead": data["overhead"]}
    _digest(result)
    return _json(json.dumps(result, allow_nan=False))


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
EVIDENCE = _object({"sha256": TEXT, "finding": TEXT, "choice_consequence": TEXT})
BRANCH = _object({"parent_sha256": TEXT, "method_family": TEXT, "reason": TEXT})
SCHEMA = _object({"schema": {"const": "controller_next_decision_v1"}, "input_sha256": TEXT, "feedback_sha256": TEXT,
    "requested_model": {"const": MODEL}, "serving_snapshot": {"const": "unknown"}, "action": {"enum": ["propose_candidate", "stop_in_scope", "request_closed_authority"]},
    "candidate_id": TEXT, "question_id": TEXT, "actual_parent_sha256": TEXT, "comparison_incumbent_sha256": TEXT, "hypothesis": TEXT, "recipe": TEXT, "expected_evidence": TEXT,
    "evidence_used": {"type": "array", "items": EVIDENCE, "minItems": 1}, "active_pool": {"type": "array", "items": BRANCH, "minItems": 2, "maxItems": 3},
    "memory_additions": TEXT, "stopped_exact_recipes": TEXT, "attribution": TEXT,
    "resources": _object({"fits": {"const": 4}, "seconds": {"const": 900}, "threads": {"const": 1}, "rss_bytes": {"const": 1073741824}, "provider_calls": {"const": 0}}),
    "boundary": {"const": "resident_train_only_fixed_scoring_no_external_no_protected_no_release"}})


def _validate(value, schema):
    if "const" in schema and (type(value) != type(schema["const"]) or value != schema["const"]): raise ValueError("response constant drift")
    if "enum" in schema and value not in schema["enum"]: raise ValueError("response enum drift")
    if schema.get("type") == "object":
        if type(value) is not dict or set(value) != set(schema["required"]): raise ValueError("strict response fields")
        for key, child in schema["properties"].items(): _validate(value[key], child)
    if schema.get("type") == "array":
        if type(value) is not list or not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", len(value)): raise ValueError("response array bounds")
        for item in value: _validate(item, schema["items"])
    if schema.get("type") == "string" and (type(value) is not str or not value.strip()): raise ValueError("nonempty response string")


def _command(directory):
    return [str(CLI), "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--sandbox", "read-only", "--cd", str(directory), "--model", MODEL, "--json", "--output-schema", str(directory / "schema.json"), "--output-last-message", str(directory / "response.json"), "-"]


def _hashes(value):
    if isinstance(value, dict): return set().union(*(_hashes(item) for item in value.values())) if value else set()
    if isinstance(value, list): return set().union(*(_hashes(item) for item in value)) if value else set()
    return {value} if type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value) else set()


def _transport(directory, packet, timeout):
    if sha(CLI) != CLI_SHA: raise ValueError("CLI source drift")
    prompt = "No tools, file/data/network/credentials access or authority changes. Use only this verified numerical evidence and prior memory. Return one non-executable evidence-cited scientific next decision; no invented results or preselected model.\n" + json.dumps(packet, allow_nan=False)
    command = _command(directory)
    with (directory / "events.jsonl").open("xb") as stdout, (directory / "stderr").open("xb") as stderr:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
        save(directory / "process.json", {"pid": child.pid, "command": command, "cli_sha256": CLI_SHA, "input_sha256": _digest(packet)})
        timed_out = False
        try: child.communicate(prompt.encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True; os.killpg(child.pid, signal.SIGKILL); child.wait()
        stdout.flush(); os.fsync(stdout.fileno()); stderr.flush(); os.fsync(stderr.fileno())
    names = ["process.json", "events.jsonl", "stderr", "schema.json", "input.json"]
    if (directory / "response.json").exists(): names.append("response.json")
    save(directory / "completion.json", {"exit_code": child.returncode, "timed_out": timed_out, "hashes": {name: sha(directory / name) for name in names}})


def _recover(directory, packet):
    completion = _json((directory / "completion.json").read_bytes())
    required = {"process.json", "events.jsonl", "stderr", "schema.json", "input.json", "response.json"}
    if completion["exit_code"] != 0 or completion["timed_out"] is not False or set(completion["hashes"]) != required:
        raise RuntimeError("original process incomplete/failed; do not resample")
    for name, digest in completion["hashes"].items(): _read({"path": str(directory / name), "sha256": digest}, True)
    process = _json((directory / "process.json").read_bytes())
    if process["cli_sha256"] != CLI_SHA or process["input_sha256"] != _digest(packet) or process["command"] != _command(directory): raise ValueError("original process identity drift")
    usage, completed, message = None, False, None
    for line in (directory / "events.jsonl").read_text().splitlines():
        event = _json(line)
        if event.get("type") not in {"thread.started", "turn.started", "item.started", "item.updated", "item.completed", "turn.completed"} or ("item" in event and event["item"].get("type") not in {"agent_message", "reasoning"}):
            raise ValueError("observed tool/failed event; not scientific refutation")
        if event.get("type") == "item.completed" and event["item"].get("type") == "agent_message": message = _json(event["item"]["text"])
        if event.get("type") == "turn.completed": usage, completed = event.get("usage"), True
    response = _json((directory / "response.json").read_bytes()); _validate(response, SCHEMA)
    if not completed or message != response: raise ValueError("original final message/completion missing or differs")
    hashes = {item["sha256"] for item in packet["bindings"].values()} | _hashes(packet["memory"]) | _hashes(packet["history"])
    ranked = packet["feedback"]["next_pool_selection_hint"]["ranked_research_parents"]
    parents = {item["candidate_sha256"] for item in ranked if
        (item["research_credit"] == 2 and (item["research_outcome"], item["route_action"]) in {("support", "continue"), ("refute", "branch")})
        or (item["research_credit"] == 1 and item["research_outcome"] == "inconclusive" and item["route_action"] == "bounded_followup" and item["followups_remaining"] == 1)
        or (item["research_credit"] == 0 and item["research_outcome"] == "baseline" and item["route_action"] == "batch_start")}
    parents.discard(packet["pool"].get("C2_consumed", {}).get("source_sha256"))
    if response["input_sha256"] != _digest(packet) or response["feedback_sha256"] != packet["bindings"]["feedback"]["sha256"] or response["comparison_incumbent_sha256"] != packet["feedback"]["comparison_incumbent_sha256"]:
        raise ValueError("response input/control binding drift")
    if response["actual_parent_sha256"] not in parents or any(item["sha256"] not in hashes for item in response["evidence_used"]): raise ValueError("unprovided evidence/parent")
    if (len({item["method_family"] for item in response["active_pool"]}) < 2 or len({item["parent_sha256"] for item in response["active_pool"]}) != len(response["active_pool"])
            or any(item["parent_sha256"] not in parents for item in response["active_pool"])): raise ValueError("global pool diversity/eligibility")
    ack = {"input_sha256": _digest(packet), "feedback_sha256": packet["bindings"]["feedback"]["sha256"], "decision_sha256": _digest(response), "completion_sha256": sha(directory / "completion.json"), "usage": usage, "serving_snapshot": "unknown", "provider_calls": 0}
    if (directory / "ack.json").exists():
        if _json((directory / "ack.json").read_bytes()) != ack: raise ValueError("acknowledgement drift")
    else: save(directory / "ack.json", ack)
    return response


def consume(packet, root, *, batch, repo, now=None, transport=None):
    """One invocation per feedback. Recovery never calls transport a second time."""
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root: raise ValueError("call root drift")
    root.mkdir(parents=True, exist_ok=True)
    key = packet["bindings"]["feedback"]["sha256"]
    if len(key) != 64 or any(char not in "0123456789abcdef" for char in key): raise ValueError("feedback digest required")
    directory = root / key; directory.mkdir(exist_ok=True)
    if directory.resolve() != directory: raise ValueError("call directory symlink")
    with (directory / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        claim = {"input_sha256": _digest(packet), "schema_sha256": _digest(SCHEMA), "cli_sha256": CLI_SHA}
        if (directory / "claim.json").exists():
            if _json((directory / "claim.json").read_bytes()) != claim: raise ValueError("same feedback changed")
            if _json((directory / "input.json").read_bytes()) != packet or _json((directory / "schema.json").read_bytes()) != SCHEMA:
                raise ValueError("original input/schema changed")
        else:
            if sha(CLI) != CLI_SHA or prepare_input(packet["bindings"], batch, repo, now) != packet: raise ValueError("CLI drift/unverified numerical input")
            save(directory / "input.json", packet); save(directory / "schema.json", SCHEMA); save(directory / "claim.json", claim)
            try: (transport or _transport)(directory, packet, min(120., (_time(DEADLINE) - _time(now)).total_seconds()))
            except Exception as error:
                save(directory / "failure.json", {"error": str(error), "no_resample": True}); raise
        try: return _recover(directory, packet)
        except Exception as error:
            if not (directory / "failure.json").exists(): save(directory / "failure.json", {"error": str(error), "no_resample": True})
            raise
