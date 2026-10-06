"""One reviewed original R/H/C proposal transaction; text is never executed.

User-directed bootstrap H, not Controller self-evolution. Supervisor owns input,
independent review, the permanent ledger and any subsequent source activation.
"""
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import time

from supervisor_harness import account_controller_feedback_consumer as c

CHANGE = c._object({key: c.TEXT for key in (
    "version", "component", "problem", "proposal", "expected_effect", "matched_test", "downstream_use")})
SCHEMA = c._object({"schema": {"type": "string", "const": "controller_coevolution_proposal_v1"},
    "input_sha256": c.TEXT, "feedback_sha256": c.TEXT,
    "requested_model": {"type": "string", "const": c.MODEL},
    "serving_snapshot": {"type": "string", "const": "unknown"},
    "researcher_change": CHANGE, "harness_change": CHANGE, "candidate": c.SCHEMA,
    "attribution": c.TEXT})
BATCH = "market-rsi-coevo-pilot-20261006-01"
DESTINATION = "User's signed-in Codex account Controller via the existing pinned local CodexCLI"
LIMITS = {"candidate_attempts": 2, "statistical_fits": 8, "original_controller_decisions": 2,
    "live_candidate_processes": 2, "threads_per_candidate": 1, "per_attempt_seconds": 900,
    "sampled_rss_bytes": 1073741824, "paid_provider_calls": 0}
TIMES = {"start_utc": "2026-10-06T17:31:25Z", "selection_cutoff_utc": "2026-10-06T18:11:25Z",
         "deadline_utc": "2026-10-06T18:16:25Z"}
ROOT = Path("/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts") / BATCH


def _configuration(binding, root):
    """Reviewed Supervisor input within the approved small-pilot hard ceiling."""
    if binding is None:
        return {"batch_id": BATCH, "root": str(ROOT), "limits": LIMITS, **TIMES}
    value = c._read(binding)
    fields = {"schema", "batch_id", "root", "limits", *TIMES}
    import re
    if (set(value) != fields or value["schema"] != "supervisor_reviewed_pilot_configuration_v1"
            or binding["path"] != str(root / "configuration.json")
            or value["root"] != str(root)
            or not isinstance(value["batch_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value["batch_id"])
            or root.name != value["batch_id"]):
        raise ValueError("exact Supervisor configuration/root required")
    limits = value["limits"]
    if (type(limits) is not dict or set(limits) != set(LIMITS)
            or any(type(item) is not int for item in limits.values())
            or any(limits[key] <= 0 for key in limits if key != "paid_provider_calls")
            or limits["candidate_attempts"] > 3 or limits["statistical_fits"] > 12
            or limits["original_controller_decisions"] > 3
            or limits["paid_provider_calls"] != 0 or limits["threads_per_candidate"] != 1
            or limits["live_candidate_processes"] != 1 or limits["per_attempt_seconds"] > 900
            or limits["sampled_rss_bytes"] > 1073741824
            or limits["statistical_fits"] != 4 * limits["candidate_attempts"]
            or limits["original_controller_decisions"] > limits["candidate_attempts"]):
        raise ValueError("configuration exceeds fixed 3decision/3attempt/12fit ceiling")
    start, cutoff, deadline = [c._time(value[key]) for key in TIMES]
    if (not start < cutoff < deadline or (deadline - start).total_seconds() > 2700
            or any(value[key] != c._time(value[key]).strftime("%Y-%m-%dT%H:%M:%SZ") for key in TIMES)):
        raise ValueError("configuration requires ordered exact UTC times within45minutes")
    return value


def _file(path):
    path = Path(path)
    return c._read({"path": str(path), "sha256": c.sha(path)})


def _ledger(path, value):
    temporary = path.with_name(".ledger-pending.json")
    if temporary.exists(): raise RuntimeError("uncertain ledger update; inspect without retry")
    c.save(temporary, value); os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _review(packet, input_binding, authorization_binding, review_binding, repo, *, configuration_binding=None, config=None):
    review, authorization = c._read(review_binding), c._read(authorization_binding)
    expected = {"passed": True, "authorization_sha256": authorization_binding["sha256"],
        "input_sha256": input_binding["sha256"], "transaction_source_sha256": c.sha(Path(__file__).resolve()),
        "consumer_source_sha256": c.sha(Path(c.__file__).resolve()), "cli_sha256": c.CLI_SHA,
        "requested_model": c.MODEL}
    if configuration_binding is not None:
        expected["configuration_sha256"] = configuration_binding["sha256"]
    if any(type(review.get(key)) is not type(value) or review.get(key) != value for key, value in expected.items()):
        raise ValueError("independent input/source/operation review drift")
    transfer = authorization.get("account_transfer", {})
    config = config or _configuration(configuration_binding, Path(authorization_binding["path"]).parent)
    if (authorization.get("schema") != "market_rsi_bounded_coevo_pilot_authorization_v1"
            or authorization.get("batch_id") != config["batch_id"] or authorization.get("granted") is not True
            or c._digest(authorization.get("limits")) != c._digest(config["limits"])
            or any(authorization.get(key) != config[key] for key in TIMES)
            or transfer.get("approved") is not True or transfer.get("destination") != DESTINATION
            or transfer.get("requested_model") != c.MODEL or transfer.get("serving_snapshot") != "unknown"
            or any(transfer.get(key) is not False for key in ("raw_train_transfer", "tools_enabled", "automatic_retry"))
            or authorization.get("closed") != {key: True for key in
                ("Dev", "Final", "external_data", "external_literature", "paid_provider", "release", "push", "promotion")}):
        raise ValueError("exact user grant/model/destination/time/permission boundary required")
    if configuration_binding is not None and (
            transfer.get("max_input_bytes") != 32768 or type(transfer.get("max_input_bytes")) is not int
            or transfer.get("payload_scope") != ["private Train-derived aggregate feedback", "research memory/history", "relevant candidate source context"]):
        raise ValueError("exact compact payload authorization required")
    if (len(Path(input_binding["path"]).read_bytes()) > 32768 or "evidence_session" in packet
            or not {"bindings", "feedback", "memory", "history", "pool", "authority", "overhead",
                    "provided_parents", "provided_source_sha256"} <= set(packet)
            or type(packet["provided_parents"]) is not list or not packet["provided_parents"]
            or type(packet["provided_source_sha256"]) is not list):
        raise ValueError("compact reviewed tools-closed packet required")
    if packet["authority"] != authorization: raise ValueError("packet's current authority differs from exact grant")
    Path(input_binding["path"]).read_bytes().decode("utf-8")
    if any(type(item) is not str or c._hashes(item) != {item} for item in packet["provided_parents"] + packet["provided_source_sha256"]):
        raise ValueError("provided parent/source hashes required")
    if "source_commit" in review:
        head = c.subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True, timeout=10).strip()
        if head != review["source_commit"]: raise ValueError("reviewed source commit drift")
    if c.sha(c.CLI) != c.CLI_SHA: raise ValueError("pinned CLI drift")
    return review


def _recover(directory, packet, claim):
    if _file(directory / "claim.json") != claim or _file(directory / "input.json") != packet or _file(directory / "schema.json") != SCHEMA:
        raise ValueError("original transaction claim/input/schema drift")
    completion = _file(directory / "completion.json")
    names = {"process.json", "events.jsonl", "stderr", "schema.json", "input.json", "response.json"}
    if completion.get("exit_code") != 0 or completion.get("timed_out") is not False or set(completion.get("hashes", {})) != names:
        raise RuntimeError("original incomplete/failed transaction; no resample")
    for key, value in c._identity().items():
        if completion.get(key) != value: raise ValueError("completion source provenance drift")
    for name, digest in completion["hashes"].items(): c._read({"path": str(directory / name), "sha256": digest}, True)
    process = _file(directory / "process.json")
    expected = {"command": c._command(directory), "cli_sha256": c.CLI_SHA,
                "input_sha256": c._digest(packet), **c._identity()}
    if any(process.get(key) != value for key, value in expected.items()) or type(process.get("pid")) is not int or process["pid"] <= 0:
        raise ValueError("original process identity drift")
    completed, message, usage = False, None, None
    for line in (directory / "events.jsonl").read_text().splitlines():
        event = c._json(line)
        if (event.get("type") not in {"thread.started", "turn.started", "item.started", "item.updated", "item.completed", "turn.completed"}
                or ("item" in event and event["item"].get("type") not in {"reasoning", "agent_message"})):
            raise ValueError("tools or failed/unknown event observed; no executable proposal")
        if event.get("type") == "item.completed" and event["item"].get("type") == "agent_message": message = c._json(event["item"]["text"])
        if event.get("type") == "turn.completed": completed, usage = True, event.get("usage")
    response = _file(directory / "response.json"); c._validate(response, SCHEMA)
    if not completed or message != response: raise ValueError("original completed final response differs")
    candidate = response["candidate"]
    for decision in (response, candidate):
        if decision["input_sha256"] != c._digest(packet) or decision["feedback_sha256"] != packet["bindings"]["feedback"]["sha256"]:
            raise ValueError("response input/feedback binding drift")
    parents = set(packet["provided_parents"])
    hashes = {item["sha256"] for item in packet["bindings"].values()} | c._hashes(packet["memory"]) | c._hashes(packet["history"]) | set(packet["provided_source_sha256"])
    if (candidate["actual_parent_sha256"] not in parents
            or candidate["comparison_incumbent_sha256"] != packet["feedback"]["comparison_incumbent_sha256"]
            or any(item["sha256"] not in hashes for item in candidate["evidence_used"])
            or any(item["parent_sha256"] not in parents for item in candidate["active_pool"])
            or len({item["method_family"] for item in candidate["active_pool"]}) < 2
            or len({item["parent_sha256"] for item in candidate["active_pool"]}) != len(candidate["active_pool"])):
        raise ValueError("unprovided candidate/evidence/parent or comparator drift")
    ack = {"decision_sha256": c._digest(response), "completion_sha256": c.sha(directory / "completion.json"),
           "usage": usage, "serving_snapshot": "unknown", "provider_calls": 0, "nonexecutable": True}
    if (directory / "ack.json").exists():
        if _file(directory / "ack.json") != ack: raise ValueError("original acknowledgement drift")
    else: c.save(directory / "ack.json", ack)
    return response


def _finish(root, directory, packet, result, *, batch_id=BATCH):
    path = root / "ledger.json"; ledger = _file(path)
    if ledger.get("schema") != "market_rsi_coevo_pilot_ledger_v1" or ledger.get("batch_id") != batch_id:
        raise ValueError("original recovery ledger identity drift")
    matches = [item for item in ledger["controller_decisions"] if item["feedback_sha256"] == packet["bindings"]["feedback"]["sha256"]]
    if len(matches) != 1 or matches[0]["input_sha256"] != c._digest(packet):
        raise RuntimeError("original reservation missing/drifted; no new reservation")
    update = {"status": "completed", "decision_sha256": c._digest(result),
              "completion_sha256": c.sha(directory / "completion.json")}
    if matches[0]["status"] == "completed":
        if any(matches[0].get(key) != value for key, value in update.items()): raise ValueError("completed original ledger drift")
    else:
        matches[0].update(update); _ledger(path, ledger)
    return result


def call(root, input_binding, authorization_binding, review_binding, repo, *, transport=None, configuration_binding=None):
    """Hold the Supervisor global lock through one durable original transaction."""
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root or not root.is_dir(): raise ValueError("permanent original pilot root required")
    config = _configuration(configuration_binding, root)
    if authorization_binding["path"] != str(root / "authorization.json") or (transport is None and (
            (configuration_binding is None and root != ROOT)
            or (configuration_binding is not None and root.parent != ROOT.parent))):
        raise ValueError("original grant and sole permanent pilot root required")
    packet = c._read(input_binding)
    key = packet["bindings"]["feedback"]["sha256"]
    if type(key) is not str or len(key) != 64 or c._hashes(key) != {key}: raise ValueError("exact feedback hash required")
    directory = root / "decisions" / key
    descriptor = os.open(root / ".pilot.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        claim = {"input_sha256": c._digest(packet), "input_binding": input_binding,
            "authorization": authorization_binding, "review": review_binding,
            "schema_sha256": c._digest(SCHEMA), "transaction_source_sha256": c.sha(Path(__file__).resolve()),
            "cli_sha256": c.CLI_SHA, **c._identity()}
        if configuration_binding is not None: claim["configuration_sha256"] = configuration_binding["sha256"]
        if (directory / "claim.json").exists(): return _finish(root, directory, packet, _recover(directory, packet, claim), batch_id=config["batch_id"])
        _review(packet, input_binding, authorization_binding, review_binding, repo,
                configuration_binding=configuration_binding, config=config)
        now = datetime.now(timezone.utc)
        if not c._time(config["start_utc"]) <= now < c._time(config["selection_cutoff_utc"]):
            raise ValueError("pilot selection window closed or not started")
        ledger_path = root / "ledger.json"; ledger = _file(ledger_path)
        decisions = ledger.get("controller_decisions", [])
        if (ledger.get("schema") != "market_rsi_coevo_pilot_ledger_v1" or ledger.get("batch_id") != config["batch_id"]
                or ledger.get("status") != "open" or type(decisions) is not list or len(decisions) >= config["limits"]["original_controller_decisions"]
                or any(item.get("feedback_sha256") == key or item.get("status") == "reserved" for item in decisions)):
            raise RuntimeError("pilot cap or unresolved original reservation; no retry")
        if directory.parent.exists() and directory.parent.resolve() != directory.parent:
            raise ValueError("original decisions directory symlink")
        directory.mkdir(parents=True, exist_ok=True)
        if directory.resolve() != directory: raise ValueError("original transaction directory symlink")
        reservation = {"feedback_sha256": key, "input_sha256": c._digest(packet), "status": "reserved"}
        decisions.append(reservation); _ledger(ledger_path, ledger)
        c.save(directory / "input.json", packet); c.save(directory / "schema.json", SCHEMA); c.save(directory / "claim.json", claim)
        started = time.monotonic()
        try:
            (transport or c._transport)(directory, packet, min(120., (c._time(config["deadline_utc"]) - now).total_seconds()))
            result = _recover(directory, packet, claim)
        except BaseException as error:
            c.save(directory / "failure.json", {"error": str(error), "no_resample": True,
                                                "wall_seconds": time.monotonic() - started})
            raise
        timing = {"wall_seconds": time.monotonic() - started, "usage": _file(directory / "ack.json")["usage"]}
        c.save(directory / "timing.json", timing)
        return _finish(root, directory, packet, result, batch_id=config["batch_id"])
