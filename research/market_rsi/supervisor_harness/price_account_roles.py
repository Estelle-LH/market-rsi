"""Once-only signed-in account role calls; no returned text is executed here."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness.coevo_pilot_transaction import input_limit

ROLES = {"author", "input_review", "source_review", "result_review"}
DESTINATION = "User's signed-in Codex account author and independent reviewer via the existing pinned local CodexCLI"
DISABLED = ("shell_tool", "unified_exec", "shell_snapshot", "apps", "plugins", "remote_plugin",
    "browser_use", "browser_use_external", "computer_use", "in_app_browser", "multi_agent",
    "multi_agent_v2", "goals", "view_image", "sleep_tool", "code_mode", "code_mode_host",
    "image_generation", "memories", "skill_search", "skill_mcp_dependency_install", "tool_suggest",
    "workspace_dependencies", "unbounded_connection_retries")


def call_limits(roles):
    """Legacy120 remains exact; longer reviews need an explicit bound grant."""
    maximum = roles.get("max_call_seconds")
    limits = roles.get("call_seconds")
    if limits is None and "call_seconds" not in roles:
        if type(maximum) is not int or maximum != 120:
            raise ValueError("legacy role timeout must remain120")
        return {role: 120 for role in ROLES}
    if (type(limits) is not dict or set(limits) != ROLES
            or any(type(value) is not int or not 0 < value <= (120 if role == "author" else 300)
                   for role, value in limits.items())
            or type(maximum) is not int or maximum != max(limits.values())):
        raise ValueError("explicit bounded per-role timeouts required")
    return dict(limits)


def _grant(root, binding):
    if (not root.is_absolute() or root.resolve() != root or not root.is_dir()
            or binding.get("path") != str(root / "authorization.json")):
        raise ValueError("exact permanent batch grant required")
    grant = c._read(binding)
    account, roles = grant.get("account_transfer", {}), grant.get("account_roles", {})
    input_limit(grant, "account_roles")
    call_limits(roles)
    caps = roles.get("caps", {})
    if (grant.get("granted") is not True or grant.get("batch_id") != root.name
            or grant.get("schema") != "market_rsi_bounded_coevo_pilot_authorization_v1"
            or account.get("requested_model") != c.MODEL or account.get("serving_snapshot") != "unknown"
            or roles.get("approved") is not True or roles.get("destination") != DESTINATION
            or roles.get("requested_model") != c.MODEL or roles.get("serving_snapshot") != "unknown"
            or set(caps) != ROLES or any(type(n) is not int or not 0 < n <= 2 for n in caps.values())
            or any(roles.get(key) is not False for key in ("raw_train_transfer", "tools_enabled", "automatic_retry"))
            or grant.get("closed") != {key: True for key in
                ("Dev", "Final", "external_data", "external_literature", "paid_provider", "release", "push", "promotion")}):
        raise ValueError("explicit whole-role compact payload/tools/caps grant required")
    start, cutoff, deadline = [c._time(grant[key]) for key in ("start_utc", "selection_cutoff_utc", "deadline_utc")]
    if not start < cutoff < deadline or (deadline - start).total_seconds() > 2700:
        raise ValueError("fresh role window must be ordered and within45minutes")
    return grant


def _command(directory):
    return native_command(directory)


def native_command(directory):
    settings = ["features." + name + "=false" for name in DISABLED] + [
        'web_search="disabled"', "features.hooks=false", "agents.enabled=false", "mcp_servers={}",
        "apps._default.enabled=false", "project_doc_max_bytes=0", 'forced_login_method="chatgpt"',
        'sandbox_mode="read-only"']
    return [str(c.CLI), "app-server", "--listen", "stdio://", "--strict-config"] + [
        arg for value in settings for arg in ("-c", value)]


def transport_contract():
    return {"schema": "price_native_account_transport_contract_v1", "source": {"path": str(Path(__file__).resolve()),
        "sha256": c.sha(Path(__file__).resolve())}, "cli_sha256": c.CLI_SHA, "command": native_command(None),
        "thread_environments": [], "turn_environments": [], "dynamic_tools": [], "hosted_search": "disabled",
        "hooks": False, "serving_snapshot": "unknown", "automatic_retry": False}


def _thread_params(directory):
    return {"model": c.MODEL, "cwd": str(directory), "sandbox": "read-only", "approvalPolicy": "never",
        "ephemeral": True, "environments": [], "dynamicTools": [], "allowProviderModelFallback": False,
        "baseInstructions": "Text-only bounded role; use supplied input only. No tools, environment, authority changes or invented evidence."}


def _normalize_native(event):
    """One-way projection; original wire messages remain saved without alteration."""
    method, params = event.get("method"), event.get("params", {})
    if "method" in event and "id" in event: raise ValueError("unexpected server tool/approval request; execution closed")
    if method == "error": raise RuntimeError("original native turn failed; no retries")
    if method == "thread/started": return {"type": "thread.started", "thread_id": params["thread"]["id"]}
    if method == "turn/started": return {"type": "turn.started"}
    if method in {"item/started", "item/completed"}:
        item = params["item"]
        if item.get("type") == "userMessage": return None
        if item.get("type") not in {"agentMessage", "reasoning"}: raise ValueError("non-text native item; original retained without retry")
        if item.get("type") == "agentMessage" and item.get("phase") == "commentary": return None
        mapped = dict(item); mapped["type"] = {"agentMessage": "agent_message", "reasoning": "reasoning"}[item["type"]]
        return {"type": method.replace("/", "."), "item": mapped}
    if method == "turn/completed":
        if params["turn"].get("status") != "completed": raise RuntimeError("native original failed/interrupted")
        return {"type": "turn.completed", "usage": None}
    return None


def _validate(value, schema):
    c._validate(value, schema)
    kind = schema.get("type")
    if kind in {"integer", "number"}:
        if (type(value) is not int if kind == "integer" else type(value) not in (int, float)):
            raise ValueError("exact response numeric type required")
        if value < schema.get("minimum", value) or value > schema.get("maximum", value): raise ValueError("response numeric bounds")
    if kind == "boolean" and type(value) is not bool: raise ValueError("exact response boolean required")
    if kind == "object":
        for key, child in schema["properties"].items(): _validate(value[key], child)
    if kind == "array":
        for item in value: _validate(item, schema["items"])


def _prompt(packet, controller=False):
    # Persisted JSON is canonicalized by save(); derive the wire input from that
    # same canonical value so completed replay cannot depend on insertion order.
    canonical = c._json(json.dumps(packet, sort_keys=True, allow_nan=False))
    return c._prompt(canonical) if controller else ("Read supplied bounded evidence and return exact schema JSON. "
        "Do not invent execution, source, metrics, serving versions or authority.\n" + json.dumps(canonical, allow_nan=False))


def native_transport(directory, packet, timeout, *, controller=False, preflight_only=False):
    """The model cannot acquire an execution environment; no runtime hook bypass.

    RPC thread acknowledgement must report [] environments and the exact model
    before turn/start. Any unexpected server request terminates this original.
    """
    directory = Path(directory)
    if c.sha(c.CLI) != c.CLI_SHA: raise ValueError("pinned CLI drift")
    source = c.sha(Path(__file__).resolve()); started = time.monotonic()
    prompt = _prompt(packet, controller)
    if not preflight_only:
        claim = c._json((directory / "claim.json").read_bytes())
        binding = claim["authorization"]
        grant = _grant(Path(binding["path"]).parent, binding)
        if (claim["input_sha256"] != c._digest(packet)
                or controller and packet.get("authority") != grant):
            raise ValueError("native input differs from original claim/grant")
        limit = input_limit(grant, "account_transfer" if controller else "account_roles")
        if len(prompt.encode("utf-8")) > limit:
            raise ValueError("full account prompt exceeds authorized input byte budget before process")
    child, usage, response, final, selector = None, None, None, False, None
    contract = transport_contract()
    try:
        with (directory / "native-events.jsonl").open("xb") as native, (directory / "events.jsonl").open("xb") as out, (directory / "stderr").open("xb") as err:
            child = subprocess.Popen(native_command(directory), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, start_new_session=True)
            identity = c._identity() if controller else {"source_sha256": source}
            c.save(directory / "process.json", {"pid": child.pid, "command": native_command(directory),
                "cli_sha256": c.CLI_SHA, "input_sha256": c._digest(packet), "transport_contract": contract, **identity})
            def send(value):
                data = json.dumps(value, allow_nan=False).encode() + b"\n"
                native.write(json.dumps({"direction": "request", "message": value}, allow_nan=False).encode() + b"\n")
                native.flush(); os.fsync(native.fileno()); child.stdin.write(data); child.stdin.flush()
            send({"id": 0, "method": "initialize", "params": {"clientInfo": {"name": "market_rsi_bounded_text_roles", "version": "1"},
                "capabilities": {"experimentalApi": True}}})
            selector = selectors.DefaultSelector(); selector.register(child.stdout, selectors.EVENT_READ)
            buffer, thread_id = b"", None
            while not final:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0: raise subprocess.TimeoutExpired(native_command(directory), timeout)
                if not selector.select(min(remaining, .2)):
                    if child.poll() is not None: raise RuntimeError("native transport closed before original completed")
                    continue
                chunk = os.read(child.stdout.fileno(), 65536)
                if not chunk: raise RuntimeError("native original EOF")
                buffer += chunk
                if len(buffer) > 1048576: raise ValueError("native event exceeds bounded record")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1); event = c._json(line)
                    native.write(json.dumps({"direction": "response", "message": event}, allow_nan=False).encode() + b"\n")
                    native.flush(); os.fsync(native.fileno())
                    if event.get("error") is not None: raise RuntimeError("native RPC rejected; original preserved")
                    if event.get("id") == 0:
                        send({"method": "initialized", "params": {}})
                        send({"id": 1, "method": "thread/start", "params": _thread_params(directory)})
                    elif event.get("id") == 1:
                        result = event["result"]; thread = result["thread"]
                        if thread.get("environments") != [] or result.get("model") != c.MODEL or result.get("instructionSources") != []:
                            raise ValueError("native no-environment/model/instruction binding not acknowledged")
                        thread_id = thread["id"]; c.save(directory / "runtime-policy.json", {"contract": contract,
                            "thread_id": thread_id, "thread_start_result": result, "environment_acknowledged": True})
                        if preflight_only: final = True; break
                        send({"id": 2, "method": "turn/start", "params": {"threadId": thread_id, "environments": [],
                            "input": [{"type": "text", "text": prompt}], "model": c.MODEL,
                            "outputSchema": c._json((directory / "schema.json").read_bytes())}})
                    elif event.get("method") == "thread/tokenUsage/updated":
                        usage = event.get("params", {}).get("tokenUsage", {}).get("last")
                    mapped = _normalize_native(event)
                    if mapped is not None:
                        if mapped["type"] == "item.completed" and mapped["item"]["type"] == "agent_message": response = c._json(mapped["item"]["text"])
                        if mapped["type"] == "turn.completed": mapped["usage"] = usage; final = True
                        out.write(json.dumps(mapped, allow_nan=False).encode() + b"\n")
            selector.close(); child.stdin.close(); c._terminate(child)
            out.flush(); os.fsync(out.fileno()); native.flush(); os.fsync(native.fileno()); err.flush(); os.fsync(err.fileno())
        if preflight_only: return c._json((directory / "runtime-policy.json").read_bytes())
        if response is None: raise ValueError("native final response missing")
        c.save(directory / "response.json", response)
        names = ["input.json", "schema.json", "process.json", "events.jsonl", "stderr", "response.json", "native-events.jsonl", "runtime-policy.json"]
        c.save(directory / "completion.json", {"exit_code": 0, "timed_out": False, "process_exit_code": child.returncode,
            "transport_contract": contract, **identity, "hashes": {name: c.sha(directory / name) for name in names}})
    except BaseException:
        if child is not None: c._terminate(child)
        raise
    finally:
        if selector is not None: selector.close()
        if child is not None:
            for stream in (child.stdin, child.stdout):
                if stream is not None:
                    try: stream.close()
                    except OSError: pass  # Preserve the original failure after reap.


def _transport(directory, packet, timeout):
    return native_transport(directory, packet, timeout)


def _verify_native(directory, contract, packet, schema):
    """Replay the saved wire evidence, not just an adapter-authored receipt."""
    acknowledgement, turns, final, normalized, usage = None, [], None, [], None
    for line in (directory / "native-events.jsonl").read_text().splitlines():
        record = c._json(line); event = record["message"]
        if record["direction"] == "request":
            if event.get("method") == "thread/start" and event["params"] != _thread_params(directory): raise ValueError("native initial environment/config drift")
            if event.get("method") == "turn/start": turns.append(event)
        elif record["direction"] == "response":
            if event.get("id") == 1: acknowledgement = event["result"]
            if event.get("method") == "thread/tokenUsage/updated": usage = event.get("params", {}).get("tokenUsage", {}).get("last")
            mapped = _normalize_native(event)
            if mapped is not None:
                if mapped["type"] == "turn.completed": mapped["usage"] = usage
                if mapped["type"] == "item.completed" and mapped["item"]["type"] == "agent_message": final = c._json(mapped["item"]["text"])
                normalized.append(mapped)
        else: raise ValueError("unknown native trace direction")
    if (acknowledgement is None or acknowledgement.get("model") != c.MODEL
            or acknowledgement.get("instructionSources") != [] or acknowledgement["thread"].get("environments") != []
            or len(turns) != 1 or turns[0]["params"].get("environments") != []
            or turns[0]["params"].get("model") != c.MODEL or turns[0]["params"].get("outputSchema") != schema
            or turns[0]["params"].get("input") != [{"type": "text", "text": _prompt(packet, "role" not in packet)}]
            or turns[0]["params"].get("threadId") != acknowledgement["thread"]["id"]):
        raise ValueError("native no-environment/original turn binding drift")
    policy = c._json((directory / "runtime-policy.json").read_bytes())
    if policy.get("contract") != contract or policy.get("thread_start_result") != acknowledgement or policy.get("environment_acknowledged") is not True:
        raise ValueError("actual runtime acknowledgement drift")
    saved = [c._json(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    if normalized != saved or final != c._json((directory / "response.json").read_bytes()): raise ValueError("normalized events differ from actual native trace")


def _recover(directory, claim, schema):
    if c._read({"path": str(directory / "claim.json"), "sha256": c.sha(directory / "claim.json")}) != claim:
        raise ValueError("once-only role claim drift")
    completion = c._json((directory / "completion.json").read_bytes())
    names = {"input.json", "schema.json", "process.json", "events.jsonl", "stderr", "response.json", "native-events.jsonl", "runtime-policy.json"}
    if (completion.get("exit_code") != 0 or completion.get("timed_out") is not False
            or completion.get("source_sha256") != claim["source_sha256"] or set(completion.get("hashes", {})) != names):
        raise RuntimeError("incomplete/failed original role; no automatic retry or refund")
    for name, digest in completion["hashes"].items(): c._read({"path": str(directory / name), "sha256": digest}, True)
    if (c._digest(c._json((directory / "input.json").read_bytes())) != claim["input_sha256"]
            or c._json((directory / "schema.json").read_bytes()) != schema):
        raise ValueError("original role input/schema drift")
    process = c._json((directory / "process.json").read_bytes())
    if (process.get("command") != _command(directory) or process.get("cli_sha256") != c.CLI_SHA
            or process.get("source_sha256") != claim["source_sha256"] or process.get("input_sha256") != claim["input_sha256"]):
        raise ValueError("original role process drift")
    if not type(process.get("pid")) is int or process["pid"] <= 0: raise ValueError("original real process identity required")
    if process.get("transport_contract") != transport_contract() or completion.get("transport_contract") != transport_contract(): raise ValueError("native role transport contract drift")
    _verify_native(directory, transport_contract(), c._json((directory / "input.json").read_bytes()), schema)
    completed, message, usage = False, None, None
    for line in (directory / "events.jsonl").read_text().splitlines():
        event = c._json(line)
        if (event.get("type") not in {"thread.started", "turn.started", "item.started", "item.updated", "item.completed", "turn.completed"}
                or ("item" in event and event["item"].get("type") not in {"reasoning", "agent_message"})):
            raise ValueError("tool/failed/unknown role event; original preserved, no retry")
        if event.get("type") == "item.completed" and event["item"].get("type") == "agent_message": message = c._json(event["item"]["text"])
        if event.get("type") == "turn.completed": completed, usage = True, event.get("usage")
    response = c._json((directory / "response.json").read_bytes()); _validate(response, schema)
    if not completed or message != response: raise ValueError("original role final response differs")
    return {"response": response, **{key + "_binding": {"path": str(directory / name), "sha256": c.sha(directory / name)}
        for key, name in (("input", "input.json"), ("response", "response.json"), ("process", "process.json"), ("completion", "completion.json"))},
        "usage": usage, "call_id": claim["role_id"], "serving_snapshot": "unknown", "paid_provider_calls": 0,
        "paid_provider_dollar_cost": 0, "account_cost": "unmetered", "total_dollar_cost": "unknown"}


def native_preflight(root, grant_binding):
    """Fresh authorized metadata-only thread, no turn/model or private payload.

    Exact acknowledgement is required before the scientific decision reservation.
    Preserve a failed original preflight; no automatic repeat of its ID.
    """
    root = Path(root); grant = _grant(root, grant_binding)
    directory = root / "account-runtime-preflight"
    binding = root / "account-runtime-preflight.json"
    expected = {"authorization": grant_binding, "transport_contract": transport_contract()}
    if directory.exists():
        if not binding.exists(): raise RuntimeError("uncertain original account runtime preflight; no retry")
        result = c._json(binding.read_bytes())
        if any(result.get(k) != v for k, v in expected.items()): raise ValueError("original runtime preflight source/grant drift")
        for path, digest in result["evidence"].items(): c._read({"path": path, "sha256": digest}, True)
        return result
    now = datetime.now(timezone.utc)
    if not c._time(grant["start_utc"]) <= now < c._time(grant["selection_cutoff_utc"]): raise ValueError("fresh role selection window closed")
    directory.mkdir()
    try:
        result = native_transport(directory, {"schema": "public_metadata_preflight_v1"}, 15, preflight_only=True)
        proof = {**expected, "operational_ready": result["environment_acknowledged"] is True,
            "evidence": {str(directory / name): c.sha(directory / name) for name in
                ("process.json", "native-events.jsonl", "runtime-policy.json", "events.jsonl", "stderr")},
            "model_calls": 0, "private_payload_transfer": False, "note": "Real no-environment acknowledgement; no turn/start. Tool schema emptiness/arbitrary candidate containment not claimed."}
        c.save(binding, proof); return proof
    except BaseException as error:
        c.save(directory / "failure.json", {"error": str(error), "no_retry": True}); raise


def role_call(role, packet, schema, *, root, grant_binding, role_id, timeout_seconds=120, _test_transport=None, _test_policy=None):
    """Fresh role ID once-only; completed replay does not invoke the account."""
    root = Path(root); grant = _grant(root, grant_binding)
    if role not in ROLES or not isinstance(role_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", role_id):
        raise ValueError("exact bounded role/operation ID required")
    allowed_timeout = call_limits(grant["account_roles"])[role]
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= allowed_timeout:
        raise ValueError("bounded role timeout required")
    envelope = {"role": role, "role_id": role_id, "payload": packet, "requested_model": c.MODEL, "serving_snapshot": "unknown"}
    if len(_prompt(envelope).encode("utf-8")) > input_limit(grant, "account_roles"):
        raise ValueError("role input exceeds authorized input byte budget")
    json.dumps(schema, allow_nan=False)
    source = c.sha(Path(__file__).resolve())
    claim = {"role": role, "role_id": role_id, "input_sha256": c._digest(envelope), "schema_sha256": c._digest(schema),
        "authorization": grant_binding, "source_sha256": source, "cli_sha256": c.CLI_SHA,
        "requested_timeout_seconds": timeout_seconds, "allowed_timeout_seconds": allowed_timeout}
    calls = root / "role_calls"
    if calls.exists() and calls.resolve() != calls: raise ValueError("role directory symlink")
    calls.mkdir(exist_ok=True)
    with os.fdopen(os.open(calls / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        directory = calls / role / role_id
        if directory.parent.exists() and directory.parent.resolve() != directory.parent:
            raise ValueError("role parent directory symlink")
        if directory.exists(): return _recover(directory, claim, schema)
        now = datetime.now(timezone.utc)
        if not c._time(grant["start_utc"]) <= now < c._time(grant["selection_cutoff_utc"]): raise ValueError("fresh role selection window closed")
        originals = list(calls.glob("*/*/claim.json"))
        if any(not (path.parent / "completion.json").exists() for path in originals):
            raise RuntimeError("uncertain original role; inspect without retry")
        if sum(path.parent.parent.name == role for path in originals) >= grant["account_roles"]["caps"][role]: raise RuntimeError("original role cap reached")
        proof = (_test_policy or (lambda: native_preflight(root, grant_binding)))()
        if proof.get("operational_ready") is not True:
            raise RuntimeError("runtime tools-closed enforcement unverified; no role reservation or account call")
        now = datetime.now(timezone.utc)  # Metadata verification used actual window time.
        if not c._time(grant["start_utc"]) <= now < c._time(grant["selection_cutoff_utc"]):
            raise ValueError("fresh role selection window closed after runtime verification")
        effective_timeout = min(timeout_seconds, (c._time(grant["deadline_utc"]) - now).total_seconds())
        directory.mkdir(parents=True, exist_ok=False)
        if directory.resolve() != directory: raise ValueError("role operation directory symlink")
        c.save(directory / "policy.json", proof); c.save(directory / "input.json", envelope)
        c.save(directory / "schema.json", schema); c.save(directory / "claim.json", claim)
        c.save(directory / "timeout.json", {"requested_seconds": timeout_seconds,
            "allowed_seconds": allowed_timeout, "effective_seconds": effective_timeout,
            "deadline_utc": grant["deadline_utc"], "admitted_at_utc": now.isoformat()})
        started = time.monotonic()
        try:
            remaining = (c._time(grant["deadline_utc"]) - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                raise TimeoutError("batch deadline reached before original role process")
            (_test_transport or _transport)(directory, envelope, min(effective_timeout, remaining))
            result = _recover(directory, claim, schema)
            c.save(directory / "timing.json", {"wall_seconds": time.monotonic() - started, "usage": result["usage"]})
            return result
        except BaseException as error:
            c.save(directory / "failure.json", {"error": str(error), "wall_seconds": time.monotonic() - started, "no_retry": True})
            raise


class AccountRoles:
    def __init__(self, root, authorization_binding):
        self.root, self.authorization_binding = Path(root), authorization_binding
        _grant(self.root, authorization_binding)

    def call(self, role, payload, schema, *, operation_id, timeout_seconds=120):
        return role_call(role, payload, schema, root=self.root, grant_binding=self.authorization_binding,
            role_id=operation_id, timeout_seconds=timeout_seconds)

    def preflight(self): return native_preflight(self.root, self.authorization_binding)

    def controller_transport(self, directory, packet, timeout):
        return native_transport(directory, packet, timeout, controller=True)
