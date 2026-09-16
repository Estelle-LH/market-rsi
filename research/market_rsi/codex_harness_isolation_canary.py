#!/usr/bin/env python3
"""Prove controller tool commands cannot escape their dedicated workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from codex_harness_wire_canary import FIXED_TEXT, _events, _tool_events, command
from market_rsi import canonical, file_hash, fresh_json, identifier


def _output(request: dict) -> str | None:
    rows = [item.get("output") for item in request.get("input", [])
            if item.get("type") == "function_call_output"]
    return rows[-1] if rows else None


def make_handler(output: Path, commands: list[str]):
    state = {"request_count": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            return

        def do_GET(self):
            self.send_error(404)

        def do_POST(self):
            if self.path.rstrip("/") != "/v1/responses":
                self.send_error(404)
                return
            request = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
            with lock:
                state["request_count"] += 1
                number = state["request_count"]
            fresh_json(output / f"captured-request-{number:02d}.json", request)
            response_id = f"resp_isolation_fixture_{number}"
            if number <= len(commands):
                events = _tool_events(response_id, f"fc_isolation_{number}",
                                      f"call_isolation_{number}", commands[number - 1])
            else:
                events = _events(response_id, f"msg_isolation_{number}", FIXED_TEXT)
            raw = ("".join(
                f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
                for event in events) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("content-length", str(len(raw)))
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()

    return Handler


def run(output: Path) -> None:
    output = output.resolve()
    identifier(output.name)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="market-rsi-controller-workspace-") as work_tmp, \
            tempfile.TemporaryDirectory(prefix="market-rsi-controller-outside-") as outside_tmp:
        workspace, outside = Path(work_tmp), Path(outside_tmp)
        allowed = workspace / "allowed.txt"
        forbidden = outside / "forbidden.txt"
        allowed.write_text("ALLOWED_MARKER\n", encoding="utf-8")
        forbidden.write_text("FORBIDDEN_MARKER\n", encoding="utf-8")
        (workspace / "escape-link").symlink_to(forbidden)

        reached = {"value": False}

        class Probe(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_GET(self):
                reached["value"] = True
                self.send_response(200)
                self.end_headers()

        probe = ThreadingHTTPServer(("127.0.0.1", 0), Probe)
        probe_thread = threading.Thread(target=probe.serve_forever, daemon=True)
        probe_thread.start()
        commands = [
            "/bin/cat allowed.txt",
            "/bin/cat " + str(forbidden),
            "/bin/cat escape-link",
            "/bin/cp allowed.txt created.txt",
            "/usr/bin/env",
            f"/usr/bin/curl -sS --max-time 2 http://127.0.0.1:{probe.server_address[1]}/probe",
        ]
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(output, commands))
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            catalog = output / "model-catalog.json"
            # The wire command writes the exact pinned catalog itself only in
            # the caller's output directory; copy its generated path from a
            # fresh wire-style command setup.
            from codex_glm_model_catalog import model_catalog
            fresh_json(catalog, model_catalog())
            answer = output / "last-message.txt"
            base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
            args = command(workspace, answer, base_url, catalog)
            args[-1] = "Complete the fixed isolation diagnostic."
            fresh_json(output / "claim.json", {
                "schema": "codex_glm_isolation_canary_v1",
                "provider_calls": 0,
                "research_result": False,
                "codex_cli_sha256": file_hash(args[0]),
                "source_sha256": file_hash(__file__),
                "outside_marker_sha256": hashlib.sha256(forbidden.read_bytes()).hexdigest(),
            })
            environment = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": os.environ.get("HOME", ""),
                "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
                "CODEX_WIRE_FIXTURE_KEY": "not-a-provider-credential",
                # These sentinels must never enter the tool command environment.
                "TINKER_API_KEY": "ISOLATION_SENTINEL_TINKER",
                "E2B_API_KEY": "ISOLATION_SENTINEL_E2B",
            }
            completed = subprocess.run(args, text=True, capture_output=True, env=environment,
                                       timeout=120, check=False)
            (output / "events.jsonl").write_text(completed.stdout, encoding="utf-8")
            (output / "stderr.log").write_text(completed.stderr, encoding="utf-8")
            requests = [json.loads(path.read_text()) for path in
                        sorted(output.glob("captured-request-*.json"))]
            outputs = [_output(request) for request in requests[1:]]
            permitted_read = len(outputs) >= 1 and "ALLOWED_MARKER" in outputs[0]
            forbidden_read = len(outputs) >= 2 and "FORBIDDEN_MARKER" not in outputs[1]
            symlink_read = len(outputs) >= 3 and "FORBIDDEN_MARKER" not in outputs[2]
            permitted_write = (workspace / "created.txt").read_text() == "ALLOWED_MARKER\n" \
                if (workspace / "created.txt").exists() else False
            environment_clean = len(outputs) >= 5 and all(
                sentinel not in outputs[4] for sentinel in
                ("ISOLATION_SENTINEL_TINKER", "ISOLATION_SENTINEL_E2B")
            )
            network_blocked = len(outputs) >= 6 and not reached["value"]
            answer_text = answer.read_text().strip() if answer.exists() else ""
            assessment = {
                "exit_code": completed.returncode,
                "request_count": len(requests),
                "permitted_read": permitted_read,
                "forbidden_read_blocked": forbidden_read,
                "symlink_escape_blocked": symlink_read,
                "permitted_write": permitted_write,
                "credential_environment_clean": environment_clean,
                "tool_network_blocked": network_blocked,
                "answer": answer_text,
            }
            assessment["passed"] = completed.returncode == 0 and len(requests) == 7 \
                and all(assessment[key] for key in (
                    "permitted_read", "forbidden_read_blocked", "symlink_escape_blocked",
                    "permitted_write", "credential_environment_clean", "tool_network_blocked")) \
                and answer_text == FIXED_TEXT
            fresh_json(output / "assessment.json", assessment)
            print(canonical(assessment))
            if not assessment["passed"]:
                raise RuntimeError("controller isolation canary failed; inspect preserved artifacts")
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)
            probe.shutdown()
            probe.server_close()
            probe_thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
