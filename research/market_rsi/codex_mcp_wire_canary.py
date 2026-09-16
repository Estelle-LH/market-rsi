#!/usr/bin/env python3
"""Verify Codex exposes only the six controller MCP tools to the GLM wire."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from codex_glm_model_catalog import model_catalog
from codex_harness_wire_canary import FIXED_TEXT, _events, _tool_events, command
from controller_harness_contract import ALLOWED_TOOLS
from market_rsi import canonical, file_hash, fresh_json, identifier


def make_handler(output: Path):
    state = {"requests": 0, "selected_name": None}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            return

        def do_GET(self):
            self.send_error(404)

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
            state["requests"] += 1
            number = state["requests"]
            fresh_json(output / f"captured-request-{number:02d}.json", request)
            if number == 1:
                namespace = next((tool for tool in request.get("tools", [])
                                  if tool.get("type") == "namespace"
                                  and tool.get("name") == "mcp__controller_tools"), None)
                selected = "inspect_train_dev" if namespace else None
                state["selected_name"] = selected
                events = _tool_events("resp_mcp_1", "fc_mcp_1", "call_mcp_1",
                                      name=selected or "missing_tool",
                                      namespace="mcp__controller_tools" if selected else None,
                                      arguments={})
            else:
                events = _events("resp_mcp_2", "msg_mcp_2", FIXED_TEXT)
            raw = ("".join(f"event: {event['type']}\ndata: "
                           f"{json.dumps(event, separators=(',', ':'))}\n\n"
                           for event in events) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(raw)))
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def run(output: Path) -> None:
    output = output.resolve()
    identifier(output.name)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="market-rsi-mcp-") as tmp:
        workspace = Path(tmp)
        fresh_json(workspace / "train-dev-summary.json", {"train_rows": 10, "dev_rows": 5})
        fresh_json(workspace / "own-history.json", {"rounds": []})
        catalog = output / "model-catalog.json"
        fresh_json(catalog, model_catalog())
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(output))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            answer = output / "last-message.txt"
            base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
            args = command(workspace, answer, base_url, catalog)[:-1]
            mcp_args = [str(Path(__file__).with_name("controller_tools_mcp.py")),
                        "--workspace", str(workspace), "--mode", "canary"]
            args += [
                "--disable", "shell_tool",
                "-c", "mcp_servers.controller_tools.command=" + json.dumps(sys.executable),
                "-c", "mcp_servers.controller_tools.args=" + json.dumps(mcp_args),
                "-c", 'mcp_servers.controller_tools.default_tools_approval_mode="approve"',
                "-c", "mcp_servers.controller_tools.supports_parallel_tool_calls=true",
                "-c", "mcp_servers.controller_tools.startup_timeout_sec=10",
                "Use inspect_train_dev once, then return exactly WIRE_CANARY_OK.",
            ]
            fresh_json(output / "claim.json", {"schema": "codex_controller_mcp_wire_v1",
                "provider_calls": 0, "research_result": False,
                "mcp_source_sha256": file_hash(Path(__file__).with_name("controller_tools_mcp.py"))})
            completed = subprocess.run(args, text=True, capture_output=True, timeout=120,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                     "HOME": os.environ.get("HOME", ""),
                     "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
                     "CODEX_WIRE_FIXTURE_KEY": "not-a-provider-credential"}, check=False)
            (output / "events.jsonl").write_text(completed.stdout)
            (output / "stderr.log").write_text(completed.stderr)
            paths = sorted(output.glob("captured-request-*.json"))
            requests = [json.loads(path.read_text()) for path in paths]
            first_tools = requests[0].get("tools", []) if requests else []
            namespace = next((tool for tool in first_tools if tool.get("type") == "namespace"
                              and tool.get("name") == "mcp__controller_tools"), {})
            names = sorted(tool.get("name") for tool in first_tools)
            suffixes = sorted(tool.get("name") for tool in namespace.get("tools", []))
            answer_text = answer.read_text().strip() if answer.exists() else ""
            tool_output = ""
            if len(requests) >= 2:
                tool_output = next((item.get("output", "")
                    for item in requests[1].get("input", [])
                    if item.get("type") == "function_call_output"), "")
            tool_output_text = (tool_output if isinstance(tool_output, str)
                                else json.dumps(tool_output, sort_keys=True))
            assessment = {"exit_code": completed.returncode, "request_count": len(requests),
                "wire_tool_names": names, "conceptual_tool_names": suffixes,
                "answer": answer_text, "tool_output": tool_output}
            assessment["passed"] = completed.returncode == 0 and len(requests) == 2 \
                and suffixes == sorted(ALLOWED_TOOLS) and answer_text == FIXED_TEXT \
                and "train_rows" in tool_output_text \
                and "unsupported call" not in tool_output_text \
                and "requires approval" not in tool_output_text
            fresh_json(output / "assessment.json", assessment)
            print(canonical(assessment))
            if not assessment["passed"]:
                raise RuntimeError("controller MCP wire canary failed; inspect artifacts")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
