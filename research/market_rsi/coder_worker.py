"""One subscribed, no-tools code response bound to one research proposal.

Returned source is data. This module NEVER imports or executes it. Execution and
independent scoring belong to the E2B/Harbor outer worker. General live dispatch
remains closed pending independent source and worker admission.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import os
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from bounded_process import run_bounded_process
from coder_probe import command as probe_command, inspect_events
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from researcher_worker import assess_proposal, hash_string


SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["status", "code", "notes"], "properties": {
              "status": {"type": "string", "enum": ["implemented", "unsupported"]},
              "code": {"type": "string"}, "notes": {"type": "string"}}}
LIMIT_KEYS = {"wall_seconds", "max_prompt_bytes", "max_stream_bytes", "max_code_bytes"}
RUNTIME_KEYS = {"feature_names", "prediction_min", "prediction_max", "libraries", "execution_limits"}
REAP_SECONDS = 5
INSTRUCTIONS = (
    "You are the coding component, not a second researcher. Implement the supplied proposal, "
    "without changing its scientific question or frozen evaluation contract. The complete allowed "
    "research context follows. You have no tools, repository, hidden Test data or live-chat access. "
    "Return exactly the requested JSON. Source code will be executed only in a separate isolated "
    "Linux sandbox. Do not call providers, read local files, use network, download packages, "
    "spawn processes or change evaluator files. Use the declared runtime libraries. For an "
    "experiment implement fit(train, feature_names) returning in-memory model state, and "
    "predict(model, row) returning one finite prediction in the fixed range. Each Train row has "
    "row_id, game_id, market_id, decision_ms, feature_available_ms, features, target and "
    "label_available_ms. A prediction row has only the first six fields. You receive one new "
    "row only after the prior prediction is committed; no future rows or evaluation labels "
    "are available. For inspect/reject_measurement implement inspect(train, dev, feature_names) "
    "returning a JSON-compatible diagnostic; these are permitted Train/Dev rows, not hidden Test. "
    "Do not pretend the code was tested. Return status=unsupported and explain if the requested "
    "change cannot be represented by this interface. Do not replace it with another experiment."
)


def _limits(limits):
    if (not isinstance(limits, dict) or set(limits) != LIMIT_KEYS
            or any(type(x) is not int or x <= 0 for x in limits.values())):
        raise ValueError("explicit positive coding bounds required")
    if limits["max_code_bytes"] > limits["max_stream_bytes"]:
        raise ValueError("code cap exceeds response cap")


def prepare_code_request(research_request, raw_research_response, runtime, limits):
    """Use only the already-projected common/owned context, never arbitrary paths.

    The caller must bind this raw response to the completed researcher job. Hash
    integrity here does not prove source-data or researcher-response provenance.
    """
    r = copy.deepcopy(research_request)
    if (not isinstance(r, dict) or set(r) != {"messages", "audit", "packet_sha256"}
            or digest({k: v for k, v in r.items() if k != "packet_sha256"}) != r["packet_sha256"]
            or digest(r["messages"]) != r["audit"]["messages_sha256"]):
        raise ValueError("research request changed")
    proposal = assess_proposal(raw_research_response, r["audit"])
    if not proposal["valid"]:
        raise ValueError("invalid researcher response; no coding resample")
    _limits(limits)
    if not isinstance(runtime, dict) or set(runtime) != RUNTIME_KEYS:
        raise ValueError("exact public runtime contract required")
    names = runtime["feature_names"]
    if (not isinstance(names, list) or not names or len(names) != len(set(names))
            or any(not isinstance(x, str) or not x for x in names)):
        raise ValueError("feature schema required")
    for key in ("prediction_min", "prediction_max"):
        if type(runtime[key]) not in {int, float} or not math.isfinite(runtime[key]):
            raise ValueError("finite prediction bounds required")
    if runtime["prediction_min"] >= runtime["prediction_max"]:
        raise ValueError("invalid prediction range")
    if (not isinstance(runtime["libraries"], dict) or not runtime["libraries"]
            or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v
                   for k, v in runtime["libraries"].items())
            or not isinstance(runtime["execution_limits"], dict)
            or not runtime["execution_limits"]):
        raise ValueError("frozen runtime libraries/limits required")
    action = proposal["proposal"]["action"]
    payload = {"instructions": INSTRUCTIONS, "research_context": r["messages"],
               "proposal": proposal["proposal"], "runtime": runtime,
               "entrypoint": "fit_predict" if action == "experiment" else "inspect"}
    prompt = canonical(payload)
    if len(prompt.encode()) > limits["max_prompt_bytes"]:
        raise ValueError("coding context too large; no silent truncation")
    audit = {key: r["audit"][key] for key in (
        "arm", "experiment_id", "task_id", "task_index", "step_index", "phase",
        "common_manifest_sha256", "common_text_sha256", "record_sha256", "guide_sha256")}
    audit.update(research_packet_sha256=r["packet_sha256"],
                 research_response_sha256=hashlib.sha256(raw_research_response.encode()).hexdigest(),
                 proposal_sha256=digest(proposal["proposal"]), runtime_sha256=digest(runtime),
                 prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                 entrypoint=payload["entrypoint"], limits=copy.deepcopy(limits))
    result = {"prompt": prompt, "audit": audit}
    return dict(result, packet_sha256=digest(result))


def load_pin(path):
    path = Path(path)
    pin = json.loads(path.read_text())
    if (pin.get("schema") != "subscribed_coder_pin_v1" or pin.get("authentication") != "chatgpt"
            or pin.get("reasoning_effort") != "medium"):
        raise ValueError("subscribed coding pin required")
    identifier(pin["model"])
    for key in ("cli_sha256", "catalog_sha256"):
        hash_string(pin[key])
    catalog_name = pin["catalog_file"]
    if Path(catalog_name).name != catalog_name:
        raise ValueError("catalog must be a sibling artifact")
    catalog_path = path.parent / catalog_name
    if file_hash(catalog_path) != pin["catalog_sha256"] or file_hash(pin["cli_path"]) != pin["cli_sha256"]:
        raise ValueError("coding binary or catalog changed")
    catalog = json.loads(catalog_path.read_text())
    rows = [r for r in catalog["models"] if r["slug"] == pin["model"]]
    if (len(rows) != 1 or rows[0].get("visibility") != "list"
            or not any(r["effort"] == pin["reasoning_effort"] for r in rows[0]["supported_reasoning_levels"])):
        raise ValueError("model/effort missing from pinned catalog")
    return pin, catalog_path


def coding_command(workspace, schema, answer, pin, catalog_path):
    args = probe_command(workspace, schema, answer)[:-1]
    args[0] = pin["cli_path"]
    args += ["--model", pin["model"], "-c", 'forced_login_method="chatgpt"',
             "-c", 'model_provider="openai"',
             "-c", "model_catalog_json=" + json.dumps(str(catalog_path))]
    return args + ["-"]


def minimal_environment(source):
    # Auth stays with the CLI, not in the model prompt. No API/proxy/provider vars.
    return {k: source[k] for k in ("HOME", "PATH", "TMPDIR", "LANG", "USER") if k in source}


def run_bounded(args, prompt, env, directory, limits, *, deadline_monotonic=None):
    """Bound a trusted text-only CLI, not arbitrary generated programs on the Mac.

    Preserve both streams up to explicit limits, including failure evidence.
    The caller makes one invocation. Internal CLI transport request counts are
    not established by this helper; do not report one provider HTTP request.
    """
    _limits(limits)
    wire = prompt.encode()
    if len(wire) > limits["max_prompt_bytes"]:
        raise ValueError("input exceeds coding limit")
    directory = Path(directory)
    stdout_path, stderr_path = directory / "events.jsonl", directory / "stderr.log"
    began, offset, failure = time.monotonic(), 0, None
    deadline = began + limits["wall_seconds"]
    if deadline_monotonic is not None:
        if type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic):
            raise ValueError("finite shared coding deadline required")
        deadline = min(deadline, deadline_monotonic)
    counts, buffer = {"stdout": 0, "stderr": 0}, b""
    proc = None
    with stdout_path.open("xb") as out, stderr_path.open("xb") as err, selectors.DefaultSelector() as sel:
        streams = {"stdout": out, "stderr": err}
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError("coding preparation exhausted wall limit before invocation")
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env=env, start_new_session=True)
            fresh_json(directory / "process.json", {"pid": proc.pid, "own_process_group": proc.pid})
            for pipe, event, name in ((proc.stdin, selectors.EVENT_WRITE, "stdin"),
                                       (proc.stdout, selectors.EVENT_READ, "stdout"),
                                       (proc.stderr, selectors.EVENT_READ, "stderr")):
                os.set_blocking(pipe.fileno(), False)
                sel.register(pipe, event, name)
            while sel.get_map():
                if time.monotonic() >= deadline:
                    raise TimeoutError("coding wall limit reached")
                for key, _ in sel.select(timeout=0.05):
                    pipe, name = key.fileobj, key.data
                    if name == "stdin":
                        try:
                            offset += os.write(pipe.fileno(), wire[offset:offset + 16384])
                        except BrokenPipeError:
                            sel.unregister(pipe)
                            pipe.close()
                            continue
                        if offset == len(wire):
                            sel.unregister(pipe)
                            pipe.close()
                        continue
                    block = os.read(pipe.fileno(), 16384)
                    if not block:
                        sel.unregister(pipe)
                        pipe.close()
                        continue
                    allowed = max(0, limits["max_stream_bytes"] - counts[name])
                    streams[name].write(block[:allowed])
                    counts[name] += len(block)
                    if len(block) > allowed:
                        raise ValueError("coding output exceeds bound")
                    if name == "stdout":
                        buffer += block
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            if not line.strip():
                                continue
                            check = inspect_events(line.decode())
                            if check["event_failures"] or check["unexpected_item_types"]:
                                raise ValueError("coding tool/error event; stop without retry")
            if buffer.strip():
                raise ValueError("incomplete coding event stream")
            proc.wait(timeout=max(0.001, deadline - time.monotonic()))
        except Exception as error:
            failure = type(error).__name__
        finally:
            if proc is not None:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        if proc.poll() is None:
                            raise
                proc.wait(timeout=REAP_SECONDS)
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    if not pipe.closed:
                        pipe.close()
            for stream in streams.values():
                stream.flush()
                os.fsync(stream.fileno())
    result = {"exit_code": proc.returncode if proc is not None else None,
              "failure_type": failure, "elapsed_seconds": time.monotonic() - began,
              "stream_bytes_observed": counts, "input_bytes_written": offset,
              "process_reaped": proc is not None and proc.poll() is not None,
              "internal_provider_request_count": None}
    fresh_json(directory / "transport.json", result)
    return result


def assess_code(body, entrypoint, max_bytes):
    """Syntax/interface inspection only; ast.parse does not execute source."""
    if (not isinstance(body, dict) or set(body) != {"status", "code", "notes"}
            or body["status"] not in {"implemented", "unsupported"}
            or not isinstance(body["code"], str) or not isinstance(body["notes"], str)):
        return {"valid": False, "reason": "invalid coding response schema"}
    if len(body["code"].encode()) > max_bytes:
        return {"valid": False, "reason": "source exceeds code bound"}
    if body["status"] == "unsupported":
        return {"valid": False, "reason": "coder reports unsupported proposal"}
    try:
        tree = ast.parse(body["code"])
    except (SyntaxError, ValueError, RecursionError):
        return {"valid": False, "reason": "source syntax invalid"}
    required = {"fit": 2, "predict": 2} if entrypoint == "fit_predict" else {"inspect": 3}
    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for name, nargs in required.items():
        matching = [n for n in functions if n.name == name]
        if (len(matching) != 1 or isinstance(matching[0], ast.AsyncFunctionDef)
                or len(matching[0].args.posonlyargs + matching[0].args.args) != nargs
                or matching[0].args.kwonlyargs or matching[0].args.vararg or matching[0].args.kwarg):
            return {"valid": False, "reason": "source interface invalid"}
    return {"valid": True, "source_sha256": hashlib.sha256(body["code"].encode()).hexdigest(),
            "executed": False, "scientific_merit_verified": False}


def dispatch_code_once(prepared, transport, output, *, admission_check=None,
                       deadline_monotonic=None):
    r = copy.deepcopy(prepared)
    if (not isinstance(r, dict) or set(r) != {"prompt", "audit", "packet_sha256"}
            or digest({k: v for k, v in r.items() if k != "packet_sha256"}) != r["packet_sha256"]
            or hashlib.sha256(r["prompt"].encode()).hexdigest() != r["audit"]["prompt_sha256"]):
        raise ValueError("coding packet changed")
    audit = r["audit"]
    _limits(audit["limits"])
    if getattr(transport, "live", True):
        if admission_check is None or admission_check(copy.deepcopy(audit)) is not True:
            raise RuntimeError("independent live data/worker admission is incomplete")
        if type(transport) is not CodexCLITransport:
            raise RuntimeError("live coding requires the exact bounded subscribed transport")
        if (type(deadline_monotonic) not in (int, float)
                or not math.isfinite(deadline_monotonic)):
            raise RuntimeError("live coding requires the runner's shared step deadline")
    elif not audit["experiment_id"].startswith("fixture-"):
        raise ValueError("mock code jobs require a fixture experiment")
    output = Path(output)
    identifier(output.name)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    fresh_json(output / "claim.json", {"audit": audit, "code_sha256": file_hash(__file__),
               "transport_code_sha256": file_hash(__file__), "live": getattr(transport, "live", True),
               "dependencies": {name: file_hash(Path(__file__).parent / name) for name in
                                ("coder_probe.py", "researcher_worker.py", "market_rsi.py", "bounded_process.py")},
               "logical_dispatches": 1, "automatic_reinvocation": False, "scored": False})
    fresh_json(output / "request.json", r)
    began = time.monotonic()
    coding_deadline = began + audit["limits"]["wall_seconds"]
    if deadline_monotonic is not None:
        if type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic):
            raise ValueError("finite shared coding deadline required")
        coding_deadline = min(coding_deadline, deadline_monotonic)
    try:
        if getattr(transport, "live", True):
            transport.bind_process_deadline(output, coding_deadline)
        identity = transport.check_ready()
        fresh_json(output / "runtime.json", identity)
        if getattr(transport, "live", True) and admission_check(copy.deepcopy(audit)) is not True:
            raise RuntimeError("coding admission changed during preparation")
        remaining = coding_deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("coding preflight exhausted wall cap")
        fresh_json(output / "dispatch.json", {"started_at_unix": time.time(), "identity_sha256": digest(identity)})
        result = transport.run(r["prompt"], output, audit["limits"])
        fresh_json(output / "response.json", result)
        checks = inspect_events(result["events"])
        terminal_messages = [event["item"].get("text") for line in result["events"].splitlines()
                             if line.strip() for event in [json.loads(line)]
                             if event.get("type") == "item.completed"
                             and event.get("item", {}).get("type") == "agent_message"]
        try:
            response_matches_event = (len(terminal_messages) == 1
                                      and json.loads(terminal_messages[0]) == result["body"])
        except (ValueError, TypeError):
            response_matches_event = False
        usage = checks["usage"]
        if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                               for k in ("input_tokens", "output_tokens"))):
            raise ValueError("terminal subscription usage missing")
        fresh_json(output / "subscription-usage.json", {"usage": usage,
                   "authentication": identity["authentication"], "model_requested": identity["model"],
                   "elapsed_seconds": time.monotonic() - began, "allocated_cost_usd": None,
                   "additional_api_cost_usd": "0" if getattr(transport, "live", True) else None,
                   "economic_cost_complete": False, "provider_request_count": None})
        assessment = assess_code(result["body"], audit["entrypoint"], audit["limits"]["max_code_bytes"])
        assessment.update(event_checks=checks, executed=False, scored=False,
                          response_matches_saved_event=response_matches_event,
                          elapsed_seconds=time.monotonic() - began)
        if (result["exit_code"] != 0 or not checks["completed_once"] or checks["event_failures"]
                or checks["unexpected_item_types"] or result.get("transport_failure") or not response_matches_event
                or time.monotonic() >= coding_deadline):
            assessment.update(valid=False, reason="incomplete/failed/bounded-out coding run")
        fresh_json(output / "assessment.json", assessment)
        # Source remains text in response.json, not imported into this process.
        return assessment
    except Exception as error:
        fresh_json(output / "failure.json", {"error_type": type(error).__name__,
                   "elapsed_seconds": time.monotonic() - began,
                   "note": "No automatic retry; preserve first output and any terminal usage."})
        raise


class CodexCLITransport:
    live = True

    def __init__(self, pin_path):
        self.pin_path = Path(pin_path)

    def bind_process_deadline(self, output, deadline):
        if hasattr(self, "deadline"):
            raise RuntimeError("one subscribed transport belongs to one permanent job")
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("finite coding deadline required")
        self.output, self.deadline = Path(output).absolute(), deadline

    def _readiness_command(self, operation, command, env):
        if not hasattr(self, "deadline"):
            raise RuntimeError("bind one coding deadline before readiness")
        # Both preflights and the text generation share the original request
        # deadline; they do not each gain a fresh ten-second allowance.
        remaining = self.deadline - time.monotonic() - 2
        if remaining <= 0:
            raise TimeoutError("coding preflight exhausted wall cap")
        root = self.output / (operation + "-process")
        receipt = run_bounded_process(command, b"", env, root,
            wall_seconds=min(10, remaining), max_stdout_bytes=65536,
            max_stderr_bytes=65536, reap_seconds=2)
        if (receipt["failure"] is not None or receipt["exit_code"] != 0
                or receipt["process_reaped"] is not True):
            raise RuntimeError("coding readiness process failed or timed out")
        return {name: (root / (name + ".bin")).read_text() for name in ("stdout", "stderr")}

    def check_ready(self):
        if not hasattr(self, "deadline"):
            raise RuntimeError("bind one coding deadline before readiness")
        pin, catalog = load_pin(self.pin_path)
        env = minimal_environment(os.environ)
        version = self._readiness_command("version", [pin["cli_path"], "--version"], env)["stdout"].strip()
        login = self._readiness_command("auth", [pin["cli_path"], "login", "status"], env)
        if version != pin["cli_version"] or "Logged in using ChatGPT" not in login["stdout"] + login["stderr"]:
            raise RuntimeError("pinned CLI or subscribed authentication unavailable")
        self.ready = {"model": pin["model"], "effort": pin["reasoning_effort"], "authentication": "chatgpt",
                "cli_version": version, "cli_sha256": pin["cli_sha256"],
                "cli_path": pin["cli_path"],
                "catalog_sha256": pin["catalog_sha256"], "pin_sha256": file_hash(self.pin_path),
                "exact_provider_snapshot": None, "token_cap_enforced": False,
                "bounds": "one CLI invocation; wall, prompt bytes, stream bytes and code bytes"}
        return copy.deepcopy(self.ready)

    def run(self, prompt, output, limits):
        if not hasattr(self, "deadline") or Path(output).absolute() != self.output:
            raise RuntimeError("coding generation requires its original process deadline")
        pin, catalog = load_pin(self.pin_path)
        if not hasattr(self, "ready") or file_hash(self.pin_path) != self.ready["pin_sha256"]:
            raise RuntimeError("coding pin changed after readiness check")
        with tempfile.TemporaryDirectory(prefix="market-rsi-code-") as tmp:
            workspace = Path(tmp)
            schema, answer = workspace / "answer.schema.json", workspace / "answer.json"
            fresh_json(schema, SCHEMA)
            args = coding_command(workspace, schema, answer, pin, catalog)
            fresh_json(output / "command.json", {"args": args, "schema": SCHEMA})
            report = run_bounded(args, prompt, minimal_environment(os.environ), output, limits,
                deadline_monotonic=self.deadline)
            body = None
            if answer.is_file():
                if answer.stat().st_size > limits["max_stream_bytes"]:
                    raise ValueError("coding response file exceeds bound")
                raw = answer.read_text()
                fresh_json(output / "raw-answer.json", {"text": raw})
                try:
                    body = json.loads(raw)
                except ValueError:
                    pass
            return {"body": body, "events": (output / "events.jsonl").read_text(),
                    "exit_code": report["exit_code"], "transport_failure": report["failure_type"]}
