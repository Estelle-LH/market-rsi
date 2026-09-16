#!/usr/bin/env python3
"""Capture one local Codex Responses request without contacting a model.

This is an engineering wire canary only.  A local fixture server returns a
fixed assistant message, so the run has no research content and no provider
cost.  Its purpose is to freeze the exact Responses payload that the installed
Codex CLI expects before a Tinker/GLM adapter is implemented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from codex_glm_model_catalog import CONTROLLER_BASE_INSTRUCTIONS, model_catalog
from glm_canary import MODEL
from market_rsi import canonical, file_hash, fresh_json, identifier


CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"
FIXED_TEXT = "WIRE_CANARY_OK"
TOOL_COMMAND = "pwd"
DISABLED = (
    "apps",
    "hooks",
    "plugins",
    "remote_plugin",
    "memories",
    "multi_agent",
    "goals",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "in_app_browser",
    "image_generation",
    "workspace_dependencies",
    "view_image",
    "skill_search",
    "sleep_tool",
    "unbounded_connection_retries",
)


def _response(response_id: str, message_id: str, text: str) -> dict:
    now = int(time.time())
    item = {
        "id": message_id,
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }
    return {
        "id": response_id,
        "object": "response",
        "created_at": now,
        "completed_at": now,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": 65_536,
        "model": MODEL,
        "output": [item],
        "parallel_tool_calls": False,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "temperature": 1.0,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
        "truncation": "disabled",
        "usage": {
            "input_tokens": 1,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 1,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 2,
        },
        "metadata": {},
    }


def _events(response_id: str, message_id: str, text: str) -> list[dict]:
    response = _response(response_id, message_id, text)
    item = response["output"][0]
    pending_item = dict(item, status="in_progress", content=[])
    return [
        {"type": "response.created", "sequence_number": 0,
         "response": dict(response, status="in_progress", completed_at=None, output=[])},
        {"type": "response.output_item.added", "sequence_number": 1,
         "output_index": 0, "item": pending_item},
        {"type": "response.content_part.added", "sequence_number": 2,
         "item_id": message_id, "output_index": 0, "content_index": 0,
         "part": {"type": "output_text", "text": "", "annotations": []}},
        {"type": "response.output_text.delta", "sequence_number": 3,
         "item_id": message_id, "output_index": 0, "content_index": 0,
         "delta": text},
        {"type": "response.output_text.done", "sequence_number": 4,
         "item_id": message_id, "output_index": 0, "content_index": 0,
         "text": text},
        {"type": "response.content_part.done", "sequence_number": 5,
         "item_id": message_id, "output_index": 0, "content_index": 0,
         "part": item["content"][0]},
        {"type": "response.output_item.done", "sequence_number": 6,
         "output_index": 0, "item": item},
        {"type": "response.completed", "sequence_number": 7, "response": response},
    ]


def _tool_events(
    response_id: str,
    item_id: str,
    call_id: str,
    command: str = TOOL_COMMAND,
    *,
    name: str = "exec_command",
    namespace: str | None = None,
    arguments: dict | None = None,
) -> list[dict]:
    now = int(time.time())
    arguments = json.dumps(
        {"cmd": command, "yield_time_ms": 10_000} if arguments is None else arguments
    )
    item = {
        "id": item_id,
        "type": "function_call",
        "status": "completed",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
    }
    if namespace is not None:
        item["namespace"] = namespace
    pending_item = dict(item, status="in_progress", arguments="")
    response = {
        "id": response_id,
        "object": "response",
        "created_at": now,
        "completed_at": now,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": 65_536,
        "model": MODEL,
        "output": [item],
        "parallel_tool_calls": False,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "temperature": 1.0,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
        "truncation": "disabled",
        "usage": {
            "input_tokens": 1,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 1,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 2,
        },
        "metadata": {},
    }
    return [
        {"type": "response.created", "sequence_number": 0,
         "response": dict(response, status="in_progress", completed_at=None, output=[])},
        {"type": "response.output_item.added", "sequence_number": 1,
         "output_index": 0, "item": pending_item},
        {"type": "response.function_call_arguments.delta", "sequence_number": 2,
         "item_id": item_id, "output_index": 0, "delta": arguments},
        {"type": "response.function_call_arguments.done", "sequence_number": 3,
         "item_id": item_id, "output_index": 0, "arguments": arguments},
        {"type": "response.output_item.done", "sequence_number": 4,
         "output_index": 0, "item": item},
        {"type": "response.completed", "sequence_number": 5, "response": response},
    ]


def make_handler(output: Path):
    state = {"request_count": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            return

        def do_GET(self):
            if self.path.split("?", 1)[0].rstrip("/") != "/v1/models":
                self.send_error(404)
                return
            body = json.dumps({"object": "list", "data": [{
                "id": MODEL, "object": "model", "created": int(time.time()),
                "owned_by": "local-fixture"}]}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path.rstrip("/") != "/v1/responses":
                self.send_error(404)
                return
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length)
            request = json.loads(body)
            with lock:
                state["request_count"] += 1
                request_count = state["request_count"]
            fresh_json(output / f"captured-request-{request_count:02d}.json", request)
            response_id = f"resp_wire_fixture_{request_count}"
            message_id = f"msg_wire_fixture_{request_count}"
            events = (
                _tool_events(response_id, "fc_wire_fixture", "call_wire_fixture")
                if request_count == 1
                else _events(response_id, message_id, FIXED_TEXT)
            )
            payload = "".join(
                f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
                for event in events
            ) + "data: [DONE]\n\n"
            raw = payload.encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("content-length", str(len(raw)))
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()

    return Handler


def command(workspace: Path, answer: Path, base_url: str, catalog_path: Path) -> list[str]:
    instruction_path = workspace / "controller-model-instructions.md"
    instruction_path.write_text(CONTROLLER_BASE_INSTRUCTIONS, encoding="utf-8")
    permission_profile = (
        '{description="Controller workspace only",filesystem={'
        '":minimal"="read",":workspace_roots"="write"},network={enabled=false}}'
    )
    args = [
        CODEX,
        "exec",
        "--ignore-user-config",
        "--strict-config",
        "--ignore-rules",
        "--ephemeral",
        "--json",
        "--skip-git-repo-check",
        "-C",
        str(workspace),
        "-o",
        str(answer),
        "--model",
        MODEL,
        "-c",
        'model_provider="wire_fixture"',
        "-c",
        "model_catalog_json=" + json.dumps(str(catalog_path)),
        "-c",
        'model_providers.wire_fixture.name="Local wire fixture"',
        "-c",
        f'model_providers.wire_fixture.base_url="{base_url}"',
        "-c",
        'model_providers.wire_fixture.env_key="CODEX_WIRE_FIXTURE_KEY"',
        "-c",
        'model_providers.wire_fixture.wire_api="responses"',
        "-c",
        "model_providers.wire_fixture.request_max_retries=0",
        "-c",
        "model_providers.wire_fixture.stream_max_retries=0",
        "-c",
        'approval_policy="never"',
        "-c",
        'default_permissions="controller_isolated"',
        "-c",
        "permissions.controller_isolated=" + permission_profile,
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        "features.skip_host_skill_discovery=true",
        "-c",
        "skills.include_instructions=false",
        "-c",
        "suppress_unstable_features_warning=true",
        "-c",
        'web_search="disabled"',
        "-c",
        "tools.experimental_request_user_input.enabled=false",
        "-c",
        "include_permissions_instructions=false",
        "-c",
        "include_apps_instructions=false",
        "-c",
        "include_collaboration_mode_instructions=false",
        "-c",
        "include_environment_context=false",
        "-c",
        "model_instructions_file=" + json.dumps(str(instruction_path)),
        "-c",
        'shell_environment_policy.inherit="none"',
        "-c",
        'history.persistence="none"',
    ]
    for feature in DISABLED:
        args += ["--disable", feature]
    return args + ["Return exactly WIRE_CANARY_OK. Do not call tools."]


def main(output: Path) -> None:
    output = output.resolve()
    identifier(output.name)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    fresh_json(output / "claim.json", {
        "schema": "codex_glm_wire_canary_v1",
        "provider_calls": 0,
        "research_result": False,
        "fixed_response": FIXED_TEXT,
        "codex_cli_sha256": file_hash(CODEX),
        "source_sha256": file_hash(__file__),
    })
    catalog_path = output / "model-catalog.json"
    fresh_json(catalog_path, model_catalog())
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(output))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="market-rsi-wire-") as tmp:
            workspace = Path(tmp)
            answer = output / "last-message.txt"
            base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
            args = command(workspace, answer, base_url, catalog_path)
            fresh_json(output / "command.json", {"args": args})
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": os.environ.get("HOME", ""),
                "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
                "CODEX_WIRE_FIXTURE_KEY": "not-a-provider-credential",
            }
            completed = subprocess.run(
                args,
                text=True,
                capture_output=True,
                env=env,
                timeout=120,
                check=False,
            )
            (output / "events.jsonl").write_text(completed.stdout, encoding="utf-8")
            (output / "stderr.log").write_text(completed.stderr, encoding="utf-8")
            captured_paths = sorted(output.glob("captured-request-*.json"))
            captured = [json.loads(path.read_text()) for path in captured_paths]
            first = captured[0] if captured else {}
            second = captured[1] if len(captured) > 1 else {}
            answer_text = answer.read_text(encoding="utf-8").strip() if answer.exists() else ""
            tool_outputs = [item for item in second.get("input", [])
                            if item.get("type") == "function_call_output"]
            assessment = {
                "exit_code": completed.returncode,
                "request_count": len(captured),
                "request_streaming": all(request.get("stream") is True for request in captured),
                "model": first.get("model"),
                "tool_types": sorted({str(tool.get("type")) for tool in first.get("tools", [])}),
                "tool_names": sorted(str(tool.get("name")) for tool in first.get("tools", [])),
                "has_input": bool(first.get("input")),
                "tool_output_returned": len(tool_outputs) == 1
                and tool_outputs[0].get("call_id") == "call_wire_fixture",
                "requested_max_output_tokens": first.get("max_output_tokens"),
                "answer": answer_text,
                "passed": completed.returncode == 0 and len(captured) == 2
                and sorted(str(tool.get("name")) for tool in first.get("tools", []))
                == ["exec_command", "write_stdin"]
                and len(tool_outputs) == 1 and answer_text == FIXED_TEXT,
                "captured_requests_sha256": hashlib.sha256(canonical(captured).encode()).hexdigest()
                if captured else None,
            }
            fresh_json(output / "assessment.json", assessment)
            print(canonical(assessment))
            if not assessment["passed"]:
                raise RuntimeError("local Codex wire canary failed; inspect preserved artifacts")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.output)
