"""Read-only local status view for the Market RSI supervisor artifacts.

This is an observation tool, not an experiment runner. It never calls a model,
E2B, Tinker, or a protected evaluator. It binds only to localhost.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MARKET = Path(__file__).resolve().parents[2]
STATE = MARKET / "supervisor_harness/RESEARCH_STATE.md"
JOURNAL = MARKET / "artifacts/supervisor-global-state-20260917-01/journal.jsonl"
LAST_KNOWN_CANARY_ID = "market-rsi-protocol-canary-20260917-03"
INDEX = Path(__file__).with_name("index.html")
LOG_SOURCES = {
    "activity": MARKET / "supervisor_harness/LOCAL_DEBUG_ACTIVITY_2026-09-17.md",
    "protocol": MARKET / "supervisor_harness/LIVE_PROTOCOL_DEBUG_LOG_2026-09-17.md",
    "progress": MARKET / "supervisor_harness/HUMAN_PROGRESS.md",
}
AGENT_LOG_INDEX = MARKET / "supervisor_harness/AGENT_LOG_INDEX_2026-09-17.json"
WORKER_NAMES = (
    "protocol_canary_entry.py",
    "protocol_canary_runner.py",
    "dual_e2b_canary.py",
    "run_research_cycle_fixture.py",
    "run_codex_glm_controller.py",
    "data_scientist_harness/run_controller.py",
)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def curated_path(path: Path, *, tail: int | None = 18) -> dict:
    try:
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise OSError("log missing or too large")
        content = path.read_text(encoding="utf-8")
        # Human-readable logs are curated, but still fail closed on obvious
        # credential-shaped strings before exposing them to a localhost page.
        content = re.sub(r"(?i)\b(?:sk|e2b|tinker)[-_][a-z0-9]{24,}\b",
                         "[REDACTED]", content)
        content = re.sub(r"(?im)\b(?:api[_-]?key|authorization|password|secret)\s*[:=]\s*\S+",
                         "[REDACTED FIELD]", content)
        lines = content.splitlines()
        if tail is not None:
            lines = lines[-tail:]
        return {"source": str(path.relative_to(MARKET)),
                "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "text": "\n".join(lines)}
    except (OSError, UnicodeError):
        return {"source": str(path.relative_to(MARKET)),
                "modified_at_utc": None, "text": "Log unavailable"}


def curated_log(name: str, *, tail: int | None = 18) -> dict:
    return curated_path(LOG_SOURCES[name], tail=tail)


def agent_logs(*, tail: int | None = 18) -> list[dict]:
    index = read_json(AGENT_LOG_INDEX)
    agents = index.get("agents", [])
    if not isinstance(agents, list):
        return []
    result = []
    log_dir = AGENT_LOG_INDEX.parent
    for agent in agents[:20]:
        if not isinstance(agent, dict):
            continue
        agent_id, filename = agent.get("id"), agent.get("log")
        if not isinstance(agent_id, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", agent_id):
            continue
        if not isinstance(filename, str) or not re.fullmatch(r"AGENT_LOG_[A-Z0-9_-]+\.md", filename):
            continue
        path = log_dir / filename
        entry = curated_path(path, tail=tail)
        entry.update({"id": agent_id,
                      "title": str(agent.get("title", agent_id))[:100],
                      "task": str(agent.get("task", ""))[:240],
                      "status": str(agent.get("status", "未标注"))[:100],
                      "next": str(agent.get("next", "待指定"))[:240]})
        result.append(entry)
    return result


def read_state() -> dict[str, str]:
    try:
        lines = STATE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    fields = {}
    for line in lines:
        if not line.startswith("| "):
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            fields[parts[1].strip()] = parts[2].strip().replace("**", "").replace("`", "")
    return fields


def journal_status() -> tuple[list[dict], list[dict]]:
    try:
        lines = JOURNAL.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], []
    recent: list[dict] = []
    active: dict[str, dict] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        payload = event.get("payload", {})
        cycle_id = payload.get("cycle_id")
        if event.get("event") == "cycle_claim" and cycle_id:
            active[cycle_id] = event
        elif event.get("event") == "cycle_close" and cycle_id:
            active.pop(cycle_id, None)
        recent.append({
            "time": event.get("time"),
            "seq": event.get("seq"),
            "event": event.get("event"),
            "cycle_id": cycle_id,
            "outcome": payload.get("outcome"),
        })
    return recent[-10:][::-1], [
        {"cycle_id": name, "time": event.get("time")}
        for name, event in active.items()
    ]


def known_workers() -> list[dict] | None:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    matches = []
    for line in result.stdout.splitlines():
        if any(name in line for name in WORKER_NAMES):
            pid = line.strip().split(None, 1)[0]
            if pid.isdigit():
                matches.append({"pid": int(pid), "kind": "known Market RSI worker candidate"})
    return matches


def snapshot() -> dict:
    state = read_state()
    events, active = journal_status()
    canary_id = next((event["cycle_id"] for event in events
                      if isinstance(event.get("cycle_id"), str)
                      and re.fullmatch(r"market-rsi-protocol-canary-[a-z0-9-]+",
                                       event["cycle_id"])), LAST_KNOWN_CANARY_ID)
    canary = MARKET / "artifacts" / canary_id
    terminal = read_json(canary / "parent-terminal.json")
    account = read_json(canary / "parent-account-check.json")
    child_failure = read_json(canary / "child-failure.json")
    a_id = read_json(canary / "controller-sandbox-id.json")
    b_id = read_json(canary / "researcher-sandbox-id.json")
    a_boundary = read_json(canary / "controller-boundary.json")
    b_boundary = read_json(canary / "researcher-boundary.json")
    a_policy = read_json(canary / "controller-policy-verdict.json")
    b_policy = read_json(canary / "researcher-policy-verdict.json")
    b_local = read_json(canary / "a-to-b/peer-local-positive.json")
    a_to_b_failure = read_json(canary / "a-to-b/failure.json")
    b_to_a_failure = read_json(canary / "b-to-a/failure.json")
    cleanup = read_json(canary / "child-cleanup.json")
    budget_match = re.search(r"effective \$([0-9.]+)", state.get("Current branch", ""))
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": state.get("Decision / review", "State document unavailable"),
        "immediate_question": state.get("Immediate question", "Unavailable"),
        "next_progress": state.get("Meaningful next progress", "Unavailable"),
        "budget_occupied_usd": budget_match.group(1) if budget_match else None,
        "budget_cap_usd": 200,
        "budget_note": "Conservative ledger occupancy, not paid invoices",
        "canary": {
            "id": canary_id,
            "outcome": terminal.get("outcome"),
            "active": any(item["cycle_id"] == canary_id for item in active),
            "isolation_proven": terminal.get("isolation_proven"),
            "model_authorship_proven": terminal.get("model_authorship_proven"),
            "prediction_result": terminal.get("prediction_result"),
            "cost_status": terminal.get("cost_status"),
        },
        "last_account_check": {
            "time": account.get("checked_at_utc"),
            "active_market_rsi_sandboxes": account.get("active_market_rsi_sandboxes"),
        },
        "last_probe_trace": {
            "a_id": a_id.get("sandbox_id"),
            "b_id": b_id.get("sandbox_id"),
            "a_policy_echo_accepted": a_policy.get("policy_echo_accepted"),
            "b_policy_echo_accepted": b_policy.get("policy_echo_accepted"),
            "a_missing_policy_fields": a_policy.get("missing_fields", []),
            "b_missing_policy_fields": b_policy.get("missing_fields", []),
            "a_boundary_passed": all(a_boundary.get(k) is True for k in
                                     ("host_home_absent", "paid_keys_absent", "peer_file_absent")),
            "b_boundary_passed": all(b_boundary.get(k) is True for k in
                                     ("host_home_absent", "paid_keys_absent", "peer_file_absent")),
            "b_local_service_responded": b_local.get("local_service_responded"),
            "failed_stage": child_failure.get("stage"),
            "a_to_b_error_type": a_to_b_failure.get("error_type"),
            "a_to_b_failure_stage": a_to_b_failure.get("stage"),
            "b_to_a_error_type": b_to_a_failure.get("error_type"),
            "a_to_b_attempt_exists": (canary / "a-to-b/attempt.json").is_file(),
            "a_to_b_report_exists": (canary / "a-to-b/report.json").is_file(),
            "b_to_a_attempt_exists": (canary / "b-to-a/attempt.json").is_file(),
            "b_to_a_report_exists": (canary / "b-to-a/report.json").is_file(),
            "a_kill_acknowledged": cleanup.get("controller", {}).get("kill_acknowledged"),
            "b_kill_acknowledged": cleanup.get("researcher", {}).get("kill_acknowledged"),
        },
        "journal": {"events": events, "active_cycles": active},
        "logs": {name: curated_log(name) for name in LOG_SOURCES},
        "agent_logs": agent_logs(),
        "known_worker_candidates": known_workers(),
        "visibility_limit": "Role-by-role tool events are not yet connected. This page does not infer hidden work.",
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        host = self.headers.get("Host", "")
        if not re.fullmatch(r"(?:127\.0\.0\.1|localhost):\d+", host):
            self.send_error(403)
            return
        if self.path == "/":
            body = INDEX.read_bytes()
            content_type = "text/html; charset=utf-8"
        elif self.path == "/api/status":
            body = json.dumps(snapshot(), ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif self.path.startswith("/log/agent/") and re.fullmatch(r"[a-z0-9_]{1,40}", self.path.rsplit("/", 1)[-1]):
            agent_id = self.path.rsplit("/", 1)[-1]
            entry = next((item for item in agent_logs(tail=None) if item["id"] == agent_id), None)
            if entry is None:
                self.send_error(404)
                return
            body = entry["text"].encode("utf-8")
            content_type = "text/plain; charset=utf-8"
        elif self.path.startswith("/log/") and self.path.rsplit("/", 1)[-1] in LOG_SOURCES:
            name = self.path.rsplit("/", 1)[-1]
            body = curated_log(name, tail=None)["text"].encode("utf-8")
            content_type = "text/plain; charset=utf-8"
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 51361), Handler)
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
