"""Opt-in actual-CLI catalog probe: synthetic loopback, never a model/account.

Default tests do not bind sockets. To run the pinned CLI fixture explicitly:
MARKET_RSI_RUN_CATALOG_PROBE=1 python -B -m unittest <this module>
The child has no inherited credentials/config and OS-denied external network.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from supervisor_harness import controller_evidence_session as session_tools

CLI = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
CLI_SHA = "6b582e8813ce7e8ed4c52814ee5cf230dba647bf2292df747a4003f2657ef201"
READER = Path(__file__).with_name("controller_research_evidence_tools.py")
READER_SHA = "01980b4117b5242a16728bc60392623a5efd13dd48e0390ebf29fd810404f7c4"
SESSION_SHA = "bfa4844e47ef0f54c2bdce85ff3223e02b72febde8f2b1aadc978f607b5bde0f"
EXPECTED = {"mcp__controller_evidence__list_evidence", "mcp__controller_evidence__read_evidence"}
ADAPTERS = {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource", "request_user_input"}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def names(tools):
    result = set()
    for tool in tools:
        if tool.get("type") == "function":
            result.add(tool["name"])
        elif tool.get("type") == "namespace":
            result.update(tool["name"] + "__" + name for name in names(tool["tools"]))
    return result


def production_overrides(port, session, directory):
    args = session_tools.config_overrides(session, directory)
    provider = {"name": "Synthetic loopback fixture", "base_url": f"http://127.0.0.1:{port}/v1",
                "wire_api": "responses", "requires_openai_auth": False, "request_max_retries": 0,
                "stream_max_retries": 0, "stream_idle_timeout_ms": 10000, "supports_websockets": False}
    for key, value in {"model_provider": "catalog_fixture", "model_providers": {"catalog_fixture": provider},
                       "cli_auth_credentials_store": "ephemeral"}.items():
        args.extend(["-c", key + "=" + session_tools._toml(value)])
    return args


def sse(output):
    response = {"id": "resp_fixture", "object": "response", "created_at": 0,
                "status": "completed", "model": "catalog-fixture", "output": [output],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
    events = [{"type": "response.created", "response": dict(response, status="in_progress", output=[])},
              {"type": "response.output_item.added", "output_index": 0, "item": output},
              {"type": "response.output_item.done", "output_index": 0, "item": output},
              {"type": "response.completed", "response": response}]
    return b"".join(b"event: " + event["type"].encode() + b"\ndata: " + encoded(event) + b"\n\n" for event in events)


def probe():
    if hashlib.sha256(CLI.read_bytes()).hexdigest() != CLI_SHA:
        raise RuntimeError("pinned CLI drift")
    if hashlib.sha256(READER.read_bytes()).hexdigest() != READER_SHA:
        raise RuntimeError("pinned reader drift")
    if hashlib.sha256(Path(session_tools.__file__).read_bytes()).hexdigest() != SESSION_SHA:
        raise RuntimeError("production session source drift")
    with tempfile.TemporaryDirectory(prefix="controller-catalog-fixture-") as directory:
        root = Path(directory).resolve()
        content = b"SYNTHETIC_APPROVED_EVIDENCE_ONLY\n"
        evidence = root / "evidence.txt"
        evidence.write_bytes(content)
        sentinel = root / "unapproved.txt"
        sentinel.write_bytes(b"SYNTHETIC_UNAPPROVED_HOST_SECRET")
        policy = root / "policy.json"
        policy.write_bytes(encoded({"schema": "controller_research_evidence_policy_v1",
            "evidence": [{"id": "fixture", "path": str(evidence), "sha256": hashlib.sha256(content).hexdigest(),
                          "kind": "evidence", "controller_payload_approved": True}],
            "limits": {"file_bytes": 4096, "page_bytes": 512, "output_bytes": 8192, "tool_calls": 4},
            "audit_path": str(root / "evidence-audit.jsonl")}))
        policy_sha = hashlib.sha256(policy.read_bytes()).hexdigest()
        proof_path = root / "runtime-attestation.json"
        proof_path.write_bytes(encoded({"schema": "controller_evidence_runtime_attestation_v1",
            "profile_sha256": session_tools.profile_sha256(), "cli_sha256": CLI_SHA, "reader_sha256": READER_SHA,
            "python_sha256": session_tools.PYTHON_SHA, "requested_model": "catalog-fixture", "scope": "synthetic",
            "protected_channel_check": "passed", "effective_tools": sorted(EXPECTED | ADAPTERS)}))
        # This declared synthetic fixture input cannot unlock account=True.
        session = {"schema": session_tools.SCHEMA, "policy": {"path": str(policy), "sha256": policy_sha},
                   "runtime_attestation": {"path": str(proof_path), "sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest()}}
        fixture_home = root / "codex-home"
        fixture_home.mkdir()
        # Child-only CODEX_HOME retains its actual meaning; no user config/auth is copied.
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
               "TMPDIR": str(root), "CODEX_HOME": str(fixture_home)}
        received, errors = [], []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if len(received) >= 8:
                    self.send_error(429)
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/v1/responses" or size > 1_000_000 or self.headers.get("Authorization"):
                    errors.append("unexpected endpoint/size/auth")
                    self.send_error(400)
                    return
                payload = json.loads(self.rfile.read(size))
                received.append(payload)
                if len(received) == 1 and names(payload.get("tools", [])) == EXPECTED | ADAPTERS:
                    output = {"id": "fc_fixture", "type": "function_call", "call_id": "call_fixture",
                              "namespace": "mcp__controller_evidence", "name": "read_evidence",
                              "arguments": "{\"evidence_id\":\"fixture\"}", "status": "completed"}
                elif len(received) == 2:
                    output = {"id": "fc_denial", "type": "function_call", "call_id": "call_denial",
                              "name": "read_mcp_resource", "arguments": json.dumps({"server": "controller_evidence",
                              "uri": "file://" + str(sentinel)}), "status": "completed"}
                else:
                    output = {"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
                              "content": [{"type": "output_text", "text": "SYNTHETIC_PROBE_COMPLETE", "annotations": []}]}
                response = sse(output)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            command = [str(CLI), "exec", "--ignore-user-config", "--ignore-rules",
                       "--skip-git-repo-check", "--ephemeral", "--json", "--sandbox", "read-only",
                       "--model", "catalog-fixture", "--cd", str(root)]
            config = production_overrides(server.server_port, session, root)
            command.extend(config)
            command.append("Synthetic fixture. Read fixture only if that tool is available. No host context.")
            # Defense in depth for this diagnostic: no external endpoint is reachable.
            profile = ('(version 1)(allow default)(deny network*)(allow network-outbound '
                       '(remote ip "localhost:*"))(deny file-read* file-write* (subpath "/Users/estelle"))'
                       '(allow file-read* (subpath "/Users/estelle/.cache/codex-runtimes/codex-primary-runtime") '
                       '(literal ' + json.dumps(str(READER)) + '))')
            run = subprocess.run(["/usr/bin/sandbox-exec", "-p", profile] + command,
                                 cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=35)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        audit_path = root / "evidence-audit.jsonl"
        audit = audit_path.read_text() if audit_path.exists() else ""
        return {"cli_sha256": CLI_SHA, "reader_sha256": READER_SHA, "requests": received,
                "errors": errors, "exit_code": run.returncode, "stderr": run.stderr.decode(errors="replace"),
                "events": run.stdout.decode(errors="replace"), "audit": audit,
                "overrides": config, "profile_sha256": session_tools.profile_sha256(), "session_sha256": SESSION_SHA}


class RuntimeCatalogTests(unittest.TestCase):
    def test_disabled_channels_are_explicit(self):
        self.assertFalse(session_tools.PROFILE["features"]["shell_tool"])
        self.assertTrue(session_tools.PROFILE["features"]["skip_host_skill_discovery"])
        self.assertEqual(session_tools.PROFILE["web_search"], "disabled")
        self.assertFalse(session_tools.PROFILE["agents"]["enabled"])
        self.assertNotIn("OPENAI_API_KEY", json.dumps(session_tools.PROFILE))

    @unittest.skipUnless(os.environ.get("MARKET_RSI_RUN_CATALOG_PROBE") == "1", "actual CLI fixture is opt-in")
    def test_actual_catalog_and_approved_observation(self):
        result = probe()
        summary = {key: result[key] for key in ("cli_sha256", "reader_sha256", "session_sha256", "profile_sha256", "errors", "exit_code", "stderr", "events", "audit", "overrides")}
        summary["catalog"] = sorted(names(result["requests"][0].get("tools", []))) if result["requests"] else []
        summary["requests"] = len(result["requests"])
        summary["request_sha256"] = [hashlib.sha256(encoded(request)).hexdigest() for request in result["requests"]]
        print("SYNTHETIC_RUNTIME_PROBE " + json.dumps(summary, sort_keys=True))
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertFalse(result["errors"])
        self.assertEqual(len(result["requests"]), 3)
        self.assertEqual(names(result["requests"][0].get("tools", [])), EXPECTED | ADAPTERS)
        self.assertTrue(all(tool["type"] in {"function", "namespace"} for tool in result["requests"][0]["tools"]))
        self.assertIn("SYNTHETIC_APPROVED_EVIDENCE_ONLY", json.dumps(result["requests"][1]["input"]))
        self.assertNotIn("SYNTHETIC_UNAPPROVED_HOST_SECRET", json.dumps(result["requests"]))
        self.assertIn("call_denial", json.dumps(result["requests"][2]["input"]))
        self.assertEqual(len(result["audit"].splitlines()), 1)
        self.assertIn('"status": "success"', result["audit"])
        events = [json.loads(line) for line in result["events"].splitlines()]
        completed = [event["item"] for event in events if event.get("type") == "item.completed"
                     and event.get("item", {}).get("type") == "mcp_tool_call"]
        self.assertEqual([item["tool"] for item in completed], ["read_evidence", "read_mcp_resource"])
        self.assertEqual(completed[0]["status"], "completed")
        self.assertEqual(completed[1]["status"], "failed")
        self.assertIsNone(completed[1]["result"])
        self.assertIn("invalid RPC request", completed[1]["error"]["message"])
        returned = json.loads(completed[0]["result"]["content"][0]["text"])
        receipt = json.loads(result["audit"].splitlines()[0])
        # Broker hashes JSON with spaces, so match its exact emitted encoding.
        self.assertEqual(receipt["payload_sha256"], hashlib.sha256(
            json.dumps(returned, sort_keys=True, ensure_ascii=False).encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
