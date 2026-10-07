"""Explicit evidence-only consumer mode; synthetic proof never enables an account.

The trusted Supervisor vets manifest contents and runtime attestation separately.
This module binds prepared broker outputs to original completed tool events;
it does not supply arbitrary-code isolation or grant a new account/batch budget.
"""
import hashlib
import json
from pathlib import Path
import re

from supervisor_harness import controller_research_evidence_tools as broker


READER_SHA = "01980b4117b5242a16728bc60392623a5efd13dd48e0390ebf29fd810404f7c4"
PYTHON_SHA = "ac60cfe0268614638d0ffa35f3b0284fc7b3a11482723793455e17eeb278509e"
CLI_SHA = "6b582e8813ce7e8ed4c52814ee5cf230dba647bf2292df747a4003f2657ef201"
PYTHON = Path("/Users/estelle/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3").resolve()
READER = Path(broker.__file__).resolve()
SERVER = "controller_evidence"
SCHEMA = "controller_evidence_session_v1"
TOOLS = {"list_evidence", "read_evidence"}
CEILINGS = {"file_bytes": 16_777_216, "page_bytes": 65_536, "output_bytes": 4_194_304, "tool_calls": 1000}
RESOURCE_HELPERS = {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource", "request_user_input"}
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "remote_plugin",
    "browser_use", "browser_use_external", "browser_use_full_cdp_access",
    "computer_use", "multi_agent", "multi_agent_v2", "agent_message_board",
    "view_image", "image_generation", "workspace_dependencies", "skill_search",
    "skill_mcp_dependency_install", "hooks", "memories", "shell_snapshot",
    "goals", "sleep_tool", "tool_suggest", "daemon_auto_start",
    "analytics_plan_history", "enable_request_compression", "code_mode_host",
)
PROFILE = {"features": {**{key: False for key in DISABLED_FEATURES}, "skip_host_skill_discovery": True,
                       "code_mode": {"enabled": False}}, "agents": {"enabled": False},
           "apps": {"_default": {"enabled": False}}, "web_search": "disabled",
           "project_doc_max_bytes": 0, "approval_policy": "never",
           "analytics": {"enabled": False}, "feedback": {"enabled": False},
           "check_for_update_on_startup": False, "history": {"persistence": "none"}}


def digest(value):
    return hashlib.sha256(broker.encode(value)).hexdigest()


def binding_read(binding, cap=1_048_576):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("exact evidence session file binding required")
    raw = broker.read_file(binding["path"], cap)
    if broker.digest(raw) != binding["sha256"]:
        raise ValueError("evidence session file drift")
    return raw


def profile_sha256():
    return digest({"config": PROFILE, "reader_sha256": READER_SHA,
                   "python_sha256": PYTHON_SHA, "cli_sha256": CLI_SHA,
                   "server": SERVER, "tools": sorted(TOOLS)})


def validate(session, directory=None, *, account=False):
    # The local fixture is not account-runtime parity. An editable scope string
    # must never turn that synthetic observation into live permission.
    if account:
        raise ValueError("account evidence activation not independently verified; closed")
    if not isinstance(session, dict) or set(session) != {"schema", "policy", "runtime_attestation"} or session["schema"] != SCHEMA:
        raise ValueError("explicit evidence session schema required")
    if broker.digest(broker.read_file(str(READER), 1_048_576)) != READER_SHA or broker.digest(broker.read_file(str(PYTHON), 33_554_432)) != PYTHON_SHA:
        raise ValueError("evidence reader/runtime drift")
    policy = broker.strict_json(binding_read(session["policy"]))
    if type(policy) is not dict or set(policy) != {"schema", "evidence", "limits", "audit_path"} or policy["schema"] != broker.SCHEMA:
        raise ValueError("evidence policy schema drift")
    limits = policy["limits"]
    if (type(limits) is not dict or set(limits) != set(CEILINGS)
            or any(type(limits[k]) is not int or not 1 <= limits[k] <= maximum
                   for k, maximum in CEILINGS.items()) or limits["page_bytes"] < 4
            or type(policy["evidence"]) is not list or not 1 <= len(policy["evidence"]) <= 64):
        raise ValueError("evidence limits/manifest drift")
    if directory is not None and policy["audit_path"] != str(Path(directory) / "evidence-audit.jsonl"):
        raise ValueError("audit must stay inside original call directory")
    ids = set()
    for record in policy["evidence"]:
        if (type(record) is not dict or set(record) != {"id", "path", "sha256", "kind", "controller_payload_approved"}
                or record["controller_payload_approved"] is not True
                or not all(type(record[k]) is str and record[k] for k in ("id", "path", "sha256", "kind"))
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", record["id"])
                or record["id"] in ids or record["kind"] not in {"source", "evidence", "memory"}
                or len(record["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in record["sha256"])
                or not Path(record["path"]).is_absolute()):
            raise ValueError("unapproved evidence payload")
        ids.add(record["id"])
    proof = broker.strict_json(binding_read(session["runtime_attestation"]))
    expected = {"schema": "controller_evidence_runtime_attestation_v1", "profile_sha256": profile_sha256(),
                "cli_sha256": CLI_SHA, "reader_sha256": READER_SHA, "python_sha256": PYTHON_SHA,
                "requested_model": "catalog-fixture", "protected_channel_check": "passed"}
    if type(proof) is not dict or any(proof.get(key) != value for key, value in expected.items()) or proof.get("scope") != "synthetic":
        raise ValueError("runtime attestation mismatch")
    if (not isinstance(proof.get("effective_tools"), list)
            or not all(type(item) is str for item in proof["effective_tools"])
            or set(proof["effective_tools"]) != {"mcp__controller_evidence__list_evidence", "mcp__controller_evidence__read_evidence"} | RESOURCE_HELPERS
            or len(proof["effective_tools"]) != 6):
        raise ValueError("effective tool catalog mismatch")
    return policy


def _toml(value):
    if isinstance(value, dict): return "{" + ",".join(json.dumps(k) + "=" + _toml(v) for k, v in value.items()) + "}"
    if isinstance(value, list): return "[" + ",".join(_toml(v) for v in value) + "]"
    return json.dumps(value)


def config_overrides(session, directory):
    validate(session, directory)
    result = []
    for key, value in PROFILE.items(): result += ["-c", key + "=" + _toml(value)]
    server = {"command": str(PYTHON), "args": ["-I", "-S", "-B", str(READER),
              "--policy", session["policy"]["path"], "--policy-sha256", session["policy"]["sha256"]],
              "cwd": str(directory), "env_vars": [], "required": True,
              "enabled_tools": sorted(TOOLS), "default_tools_approval_mode": "prompt",
              "tools": {name: {"approval_mode": "approve"} for name in sorted(TOOLS)},
              "startup_timeout_sec": 10, "tool_timeout_sec": 5}
    return ["--strict-config"] + result + ["-c", "mcp_servers=" + _toml({SERVER: server})]


def verify_events(session, directory, events):
    """Correlate actual completed requests/results with durable broker receipts.

    Evidence merely listed in a catalog is not read evidence. Resource helpers
    are not retrieval evidence and are rejected in accepted decision traces.
    """
    policy = validate(session, directory)
    audit = broker.read_file(policy["audit_path"], 4_194_304)
    receipts = [broker.strict_json(line) for line in audit.splitlines()]
    completed, ids, observed, seen = [], set(), set(), set()
    # The last completed agent message is the final decision; earlier notes
    # remain allowed. No observation delivered afterwards can support it.
    decision_at = max((i for i, event in enumerate(events) if event.get("type") == "item.completed"
                       and event.get("item", {}).get("type") == "agent_message"), default=len(events))
    terminal_at = next((i for i, event in enumerate(events) if event.get("type") == "turn.completed"), len(events))
    for position, event in enumerate(events):
        item = event.get("item", {})
        if item.get("type") != "mcp_tool_call": continue
        if position > min(decision_at, terminal_at):
            raise ValueError("tool observation after final decision or terminal turn")
        if item.get("server") != SERVER or item.get("tool") not in TOOLS:
            raise ValueError("unapproved tool event")
        if type(item.get("id")) is not str or not item["id"]:
            raise ValueError("tool observation identity required")
        observed.add(item["id"])
        if event["type"] == "item.completed":
            if item.get("id") in ids or not isinstance(item.get("id"), str): raise ValueError("duplicate tool completion")
            ids.add(item["id"]); completed.append(item)
    if observed != ids or len(completed) != len(receipts): raise ValueError("unrecorded or incomplete tool observation")
    records = {r["id"]: r for r in policy["evidence"]}
    total = 0
    for number, (item, receipt) in enumerate(zip(completed, receipts), 1):
        if item.get("status") != "completed" or item.get("error") is not None: raise ValueError("failed tool transaction")
        arguments = item.get("arguments")
        if isinstance(arguments, str): arguments = broker.strict_json(arguments)
        result = item.get("result")
        if (not isinstance(result, dict) or result.get("structured_content") is not None
                or not isinstance(result.get("content"), list) or len(result["content"]) != 1):
            raise ValueError("tool observation shape drift")
        content = result["content"][0]
        if content.get("type") != "text" or not isinstance(content.get("text"), str): raise ValueError("unsupported tool media")
        value = broker.strict_json(content["text"])
        payload = broker.encode(value)
        expected = {"sequence": number, "policy_sha256": session["policy"]["sha256"],
                    "tool": item["tool"], "request_sha256": digest({"name": item["tool"], "arguments": arguments}),
                    "payload_bytes": len(payload), "payload_sha256": broker.digest(payload),
                    "status": "success" if value.get("ok") is True else "denied", "delivery": "not_confirmed"}
        if any(receipt.get(k) != v for k, v in expected.items()): raise ValueError("broker observation/audit drift")
        total += len(payload)
        if value.get("ok") is True and item["tool"] == "read_evidence":
            record = records.get(value.get("evidence_id"))
            if record is None or value.get("sha256") != record["sha256"] or receipt.get("evidence_id") != record["id"]:
                raise ValueError("retrieved source identity drift")
            if type(value.get("text")) is not str:
                raise ValueError("retrieved source text missing")
            if value["text"]: seen.add(record["sha256"])
    if len(receipts) > policy["limits"]["tool_calls"] or total > policy["limits"]["output_bytes"]:
        raise ValueError("evidence session budget drift")
    return seen
