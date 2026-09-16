#!/usr/bin/env python3
"""Run one permanent GLM controller session inside the Codex CLI harness."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from codex_glm_model_catalog import (CONTROLLER_BASE_INSTRUCTIONS,
                                     DATA_DISCOVERY_BASE_INSTRUCTIONS,
                                     OBJECTIVE_DISCOVERY_BASE_INSTRUCTIONS,
                                     model_catalog)
from codex_glm_provider import ControllerSession, TinkerGLMBackend
from controller_activity_log import assess_activity_logs
from controller_provenance import validate_source_manifest
from controller_harness_contract import (ALLOWED_TOOLS as MODEL_ALLOWED_TOOLS,
                                         MAX_FINAL_DECISION_BYTES,
                                         MAX_WALL_SECONDS)
from objective_discovery_activity import assess_objective_activity
from objective_discovery_tools_mcp import ALLOWED_TOOLS as OBJECTIVE_ALLOWED_TOOLS
from data_discovery_activity import assess_data_discovery_activity
from data_discovery_tools_mcp import ALLOWED_TOOLS as DATA_ALLOWED_TOOLS
from historical_ingest_controller import (ALLOWED_TOOLS as INGEST_ALLOWED_TOOLS,
                                          BASE_INSTRUCTIONS as INGEST_BASE_INSTRUCTIONS,
                                          assess_activity as assess_ingest_activity)
from historical_data_use_controller import (ALLOWED_TOOLS as DATA_USE_ALLOWED_TOOLS,
                                            BASE_INSTRUCTIONS as DATA_USE_BASE_INSTRUCTIONS,
                                            assess_activity as assess_data_use_activity)
from historical_grid_objective_controller import (ALLOWED_TOOLS as GRID_OBJECTIVE_ALLOWED_TOOLS,
                                                  BASE_INSTRUCTIONS as GRID_OBJECTIVE_BASE_INSTRUCTIONS,
                                                  assess_activity as assess_grid_objective_activity)
from historical_grid_learning_controller import (ALLOWED_TOOLS as GRID_LEARNING_ALLOWED_TOOLS,
                                                 BASE_INSTRUCTIONS as GRID_LEARNING_BASE_INSTRUCTIONS,
                                                 assess_activity as assess_grid_learning_activity)
from glm_canary import MODEL
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from paid_budget import PaidBudget


CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"
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


def codex_harness_identity(*, catalog: Path, instructions: Path,
                           command: list[str]) -> dict:
    """Describe the exact local Codex workbench used for one controller run."""
    completed = subprocess.run(
        [CODEX, "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
        check=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    version = completed.stdout.strip()
    if not version or len(version.encode()) > 4_096:
        raise ValueError("bounded Codex CLI version required")
    if not catalog.is_file() or not instructions.is_file():
        raise ValueError("frozen model catalog and instructions required")
    return {
        "schema": "market_codex_harness_runtime_v1",
        "engine": "codex",
        "codex_cli": {
            "path": CODEX,
            "sha256": file_hash(CODEX),
            "version": version,
        },
        "controller_model": MODEL,
        "model_catalog_sha256": file_hash(catalog),
        "model_instructions_sha256": file_hash(instructions),
        "command_sha256": digest({"args": command}),
        "disabled_features": list(DISABLED) + ["shell_tool"],
        "strict_config": True,
        "ignore_user_config": True,
        "ignore_project_rules": True,
        "ephemeral_session": True,
    }


def _sse(events: list[dict]) -> bytes:
    return (
        "".join(
            f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
            for event in events
        )
        + "data: [DONE]\n\n"
    ).encode()


def make_handler(session: ControllerSession, bearer: str, catalog: dict | None = None):
    catalog = model_catalog() if catalog is None else catalog

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            return

        def _authorized(self) -> bool:
            return secrets.compare_digest(
                self.headers.get("authorization", ""), f"Bearer {bearer}"
            )

        def do_GET(self):
            if not self._authorized():
                self.send_error(401)
                return
            if self.path.split("?", 1)[0].rstrip("/") != "/v1/models":
                self.send_error(404)
                return
            raw = canonical(catalog).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            if not self._authorized():
                self.send_error(401)
                return
            if self.path.rstrip("/") != "/v1/responses":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("content-length") or 0)
                if not 0 < length <= 2_000_000:
                    raise ValueError("bounded Responses body required")
                request = json.loads(self.rfile.read(length))
                raw = _sse(session.handle(request))
            except Exception as error:
                if hasattr(session, "record_request_failure"):
                    session.record_request_failure(error, stage="loopback_http_request")
                body = canonical({"error": {"type": type(error).__name__,
                                             "message": str(error)}}).encode()
                self.send_response(500)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.send_header("connection", "close")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("content-length", str(len(raw)))
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()

    return Handler


def codex_command(
    *, workspace: Path, answer: Path, base_url: str, catalog: Path, instructions: Path,
    tool_mode: str, controller_stage: str = "model",
) -> list[str]:
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
        'model_provider="tinker_glm_loopback"',
        "-c",
        "model_catalog_json=" + json.dumps(str(catalog)),
        "-c",
        'model_providers.tinker_glm_loopback.name="Pinned local Tinker GLM adapter"',
        "-c",
        f'model_providers.tinker_glm_loopback.base_url="{base_url}"',
        "-c",
        'model_providers.tinker_glm_loopback.env_key="CODEX_GLM_LOOPBACK_KEY"',
        "-c",
        'model_providers.tinker_glm_loopback.wire_api="responses"',
        "-c",
        "model_providers.tinker_glm_loopback.request_max_retries=0",
        "-c",
        "model_providers.tinker_glm_loopback.stream_max_retries=0",
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
        "model_instructions_file=" + json.dumps(str(instructions)),
        "-c",
        'shell_environment_policy.inherit="none"',
        "-c",
        'history.persistence="none"',
        "-c",
        "mcp_servers.controller_tools.command=" + json.dumps(sys.executable),
        "-c",
        "mcp_servers.controller_tools.args=" + json.dumps(
            ([str(Path(__file__).with_name("controller_tools_mcp.py")),
              "--workspace", str(workspace), "--mode", tool_mode]
             if controller_stage == "model" else
             [str(Path(__file__).with_name(
                 "objective_discovery_tools_mcp.py" if controller_stage == "objective"
                 else "historical_ingest_controller.py" if controller_stage == "ingest"
                 else "historical_data_use_controller.py" if controller_stage == "data_use"
                 else "historical_grid_objective_controller.py" if controller_stage == "grid_objective"
                 else "historical_grid_learning_controller.py" if controller_stage == "grid_learning"
                 else "data_discovery_tools_mcp.py")),
              "--workspace", str(workspace)])
        ),
        "-c",
        'mcp_servers.controller_tools.default_tools_approval_mode="approve"',
        "-c",
        "mcp_servers.controller_tools.supports_parallel_tool_calls=true",
        "-c",
        "mcp_servers.controller_tools.startup_timeout_sec=10",
        "-c",
        # Research tools are mandatory. Optional MCP discovery has a shorter
        # initial-catalog grace period and can race cold data imports/loading.
        "mcp_servers.controller_tools.required=true",
    ]
    if controller_stage == "grid_learning":
        args += ["-c", 'mcp_servers.controller_tools.env={OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1"}']
    for feature in DISABLED:
        args += ["--disable", feature]
    args += ["--disable", "shell_tool"]
    return args + ["-"]


def _parse_owned_process_groups(root_pid: int, listing: str, own_group: int) -> list[int]:
    rows = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            rows.append(tuple(map(int, parts)))
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid, _pgid in rows:
            if ppid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sorted({pgid for pid, _ppid, pgid in rows
                   if pid in descendants and pgid > 1 and pgid != own_group}, reverse=True)


def _owned_process_groups(root_pid: int) -> list[int]:
    """Snapshot descendant process groups before their parent can be orphaned."""
    completed = subprocess.run(
        ["/bin/ps", "-axo", "pid=,ppid=,pgid="],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=5,
        check=True,
    )
    return _parse_owned_process_groups(root_pid, completed.stdout, os.getpgrp())


def _terminate_owned_process_tree(process: subprocess.Popen) -> None:
    """Terminate only the exact controller tree, including MCP child sessions."""
    try:
        groups = _owned_process_groups(process.pid)
    except Exception:
        groups = [process.pid]
    for signal_number in (signal.SIGTERM, signal.SIGKILL):
        for group in groups:
            try:
                os.killpg(group, signal_number)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            continue
        break


def run_process(args: list[str], prompt: str, env: dict, output: Path) -> dict:
    started = time.monotonic()
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    fresh_json(output / "process.json", {"pid": process.pid, "own_process_group": process.pid})
    failure = None
    try:
        stdout, stderr = process.communicate(prompt, timeout=MAX_WALL_SECONDS)
    except subprocess.TimeoutExpired:
        failure = "TimeoutExpired"
        _terminate_owned_process_tree(process)
        stdout, stderr = process.communicate(timeout=5)
    except KeyboardInterrupt:
        failure = "KeyboardInterrupt"
        _terminate_owned_process_tree(process)
        stdout, stderr = process.communicate(timeout=5)
    (output / "events.jsonl").write_text(stdout, encoding="utf-8")
    (output / "stderr.log").write_text(stderr, encoding="utf-8")
    return {
        "exit_code": process.returncode,
        "failure_type": failure,
        "elapsed_seconds": time.monotonic() - started,
        "process_reaped": process.poll() is not None,
    }


def reconcile_unresolved_session_dispatches(
    *, session_id: str, budget: PaidBudget, output: Path, transport: dict
) -> list[dict]:
    """Conservatively close any provider request orphaned by local termination."""
    snapshot = budget.snapshot()
    unresolved = [job_id for job_id, job in snapshot["jobs"].items()
                  if job_id.startswith(f"{session_id}-turn-")
                  and job["state"] == "dispatched"]
    if len(unresolved) > 1:
        raise ValueError("multiple unresolved controller turns require manual audit")
    receipts = []
    for job_id in unresolved:
        evidence = output / "process.json"
        receipt = {
            "terminal_local": True,
            "process_reaped": transport.get("process_reaped") is True,
            "remote_usage_unknown": True,
            "automatic_retry": False,
            "evidence_sha256": file_hash(evidence),
            "note": (
                "The exact local controller process ended before a provider usage receipt; "
                "the request is terminal and conservatively charged at its reserved upper bound."
            ),
        }
        budget.settle_uncertain_at_upper(job_id, receipt)
        receipts.append({"job_id": job_id, "accounting": "uncertain_upper_bound",
                         "upper_usd": snapshot["jobs"][job_id]["upper_usd"]})
    return receipts


def main(args) -> None:
    # CPU/source-research transport does not need Harbor. For formal sandbox
    # execution, require it before loading credentials or constructing a backend.
    if args.controller_stage == "model" and args.tool_mode == "formal":
        from controller_execution_service import ControllerExecutionService
    identifier(args.session_id)
    output = args.output.resolve()
    workspace = args.workspace.resolve()
    if not workspace.is_dir() or workspace == output or output in workspace.parents:
        raise ValueError("existing dedicated controller workspace required")
    prompt = args.prompt.read_text(encoding="utf-8")
    if not prompt.strip() or len(prompt.encode()) > 262_144:
        raise ValueError("nonempty bounded controller prompt required")
    from dotenv import dotenv_values

    key = dotenv_values(args.env_file).get("TINKER_API_KEY")
    backend = TinkerGLMBackend(key, args.tokenizer_cache)
    budget = PaidBudget(args.budget)
    budget.snapshot()
    submit_tool = ({"model": "submit_decision",
                    "objective": "submit_objective_decision",
                    "data": "submit_data_decision",
                    "ingest": "submit_ingest_decision",
                    "data_use": "submit_data_use_decision",
                    "grid_objective": "submit_grid_objective_decision",
                    "grid_learning": "submit_grid_learning_decision"}[args.controller_stage])
    allowed_tools = ({"model": MODEL_ALLOWED_TOOLS,
                      "objective": OBJECTIVE_ALLOWED_TOOLS,
                      "data": DATA_ALLOWED_TOOLS,
                      "ingest": INGEST_ALLOWED_TOOLS,
                      "data_use": DATA_USE_ALLOWED_TOOLS,
                      "grid_objective": GRID_OBJECTIVE_ALLOWED_TOOLS,
                      "grid_learning": GRID_LEARNING_ALLOWED_TOOLS}[args.controller_stage])
    session = ControllerSession(
        session_id=args.session_id,
        output=output,
        backend=backend,
        budget=budget,
        budget_bucket=args.budget_bucket,
        submit_tool=submit_tool,
        allowed_tools=allowed_tools,
    )
    catalog = output / "model-catalog.json"
    instructions = output / "model-instructions.md"
    answer = output / "last-message.txt"
    base_instructions = ({"model": CONTROLLER_BASE_INSTRUCTIONS,
                          "objective": OBJECTIVE_DISCOVERY_BASE_INSTRUCTIONS,
                          "data": DATA_DISCOVERY_BASE_INSTRUCTIONS,
                          "ingest": INGEST_BASE_INSTRUCTIONS,
                          "data_use": DATA_USE_BASE_INSTRUCTIONS,
                          "grid_objective": GRID_OBJECTIVE_BASE_INSTRUCTIONS,
                          "grid_learning": GRID_LEARNING_BASE_INSTRUCTIONS}[args.controller_stage])
    stage_catalog = model_catalog(base_instructions)
    fresh_json(catalog, stage_catalog)
    instructions.write_text(base_instructions, encoding="utf-8")
    bearer = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 make_handler(session, bearer, stage_catalog))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    execution_service = None
    execution_state = None
    source_manifest = None
    try:
        if args.controller_stage == "model" and args.tool_mode == "formal":
            if args.runner_config is None or args.source_manifest is None:
                raise ValueError("formal controller requires trusted runner and source manifests")
            source_manifest = validate_source_manifest(args.source_manifest.resolve())
            execution_service = ControllerExecutionService(
                workspace, args.runner_config.resolve(), output / "candidate-executions")
            execution_service.start()
        elif args.runner_config is not None or args.source_manifest is not None:
            raise ValueError("this controller stage cannot accept runner/source manifests")
        if args.controller_stage == "objective":
            from objective_discovery_workspace import validate_workspace
            validate_workspace(workspace)
        elif args.controller_stage == "data":
            from data_discovery_workspace import validate_workspace
            validate_workspace(workspace)
        elif args.controller_stage == "ingest":
            from historical_ingest_controller import validate_workspace
            validate_workspace(workspace)
        elif args.controller_stage == "data_use":
            from historical_data_use_controller import validate_workspace
            validate_workspace(workspace)
        elif args.controller_stage == "grid_objective":
            from historical_grid_objective_controller import validate_workspace
            validate_workspace(workspace)
        elif args.controller_stage == "grid_learning":
            from historical_grid_learning_controller import validate_workspace
            validate_workspace(workspace)
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        command = codex_command(workspace=workspace, answer=answer, base_url=base_url,
                                catalog=catalog, instructions=instructions,
                                tool_mode=args.tool_mode,
                                controller_stage=args.controller_stage)
        # Do not persist the random bearer or an environment snapshot.
        fresh_json(output / "command.json", {"args": command})
        harness_runtime = codex_harness_identity(
            catalog=catalog, instructions=instructions, command=command
        )
        fresh_json(output / "harness-runtime.json", harness_runtime)
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", ""),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            "CODEX_GLM_LOOPBACK_KEY": bearer,
        }
        transport = run_process(command, prompt, environment, output)
        harness_runtime_unchanged = (
            codex_harness_identity(
                catalog=catalog, instructions=instructions, command=command
            ) == harness_runtime
        )
        unresolved_accounting = reconcile_unresolved_session_dispatches(
            session_id=args.session_id, budget=budget, output=output,
            transport=transport,
        )
        if execution_service is not None:
            execution_service.stop()
            execution_service.join()
            execution_state = execution_service.snapshot()
        text = answer.read_text(encoding="utf-8") if answer.exists() else ""
        decision = workspace / ({"model": "submitted-decision.json",
                                "objective": "submitted-objective-decision.json",
                                "data": "submitted-data-decision.json",
                                "ingest": "submitted-ingest-decision.json",
                                "data_use": "submitted-data-use-decision.json",
                                "grid_objective": "submitted-grid-objective-decision.json",
                                "grid_learning": "submitted-grid-learning-decision.json"}[args.controller_stage])
        handshake_path = output / "terminal-handshake.json"
        terminal_handshake = (json.loads(handshake_path.read_text())
                              if handshake_path.is_file() else None)
        try:
            activity_logs = ({"model": assess_activity_logs,
                              "objective": assess_objective_activity,
                              "data": assess_data_discovery_activity,
                              "ingest": assess_ingest_activity,
                              "data_use": assess_data_use_activity,
                              "grid_objective": assess_grid_objective_activity,
                              "grid_learning": assess_grid_learning_activity}[args.controller_stage](workspace))
        except Exception as error:
            activity_logs = {"valid": False, "error_type": type(error).__name__,
                             "error": str(error)}
        conceptual_tools = [name.rsplit("__", 1)[-1] for name in session.tool_call_names]
        required_tools_complete = (
            not args.require_all_tools
            or set(conceptual_tools) == set(allowed_tools)
        )
        assessment = {
            **transport,
            "model": MODEL,
            "controller_stage": args.controller_stage,
            "turns": session.turns,
            "tool_calls": session.tool_calls,
            "tool_call_names": conceptual_tools,
            "failed": session.failed,
            "final_message_bytes": len(text.encode()),
            "final_message": text.strip(),
            "final_message_origin": ("codex_harness_terminal_handshake" if terminal_handshake
                                     else "unsubmitted_codex_output_not_a_decision"),
            "decision_bytes": decision.stat().st_size if decision.is_file() else 0,
            "submitted_decision_present": decision.is_file(),
            "terminal_handshake": terminal_handshake,
            "all_tools_required": args.require_all_tools,
            "required_tools_complete": required_tools_complete,
            "execution_service": execution_state,
            "unresolved_accounting": unresolved_accounting,
            "activity_logs": activity_logs,
            "controller_integrity": (
                activity_logs.get("controller_integrity")
                if args.controller_stage == "model" else {
                    "schema": "market_controller_integrity_assessment_v1",
                    "valid": True,
                    "not_applicable": f"{args.controller_stage}_discovery_stage",
                }
            ),
            "valid": transport["exit_code"] == 0 and not session.failed
                     and text.strip() == "Controller decision submitted; session complete."
                     and isinstance(terminal_handshake, dict)
                     and terminal_handshake.get("provider_called") is False
                     and terminal_handshake.get("paid_turn_added") is False
                     and decision.is_file() and required_tools_complete
                     and activity_logs["valid"] is True
                    and (args.controller_stage != "model"
                         or activity_logs.get("controller_integrity", {}).get("valid") is True)
                    and harness_runtime_unchanged
                    and (args.controller_stage != "model"
                         or args.tool_mode == "canary" or (
                         execution_state is not None
                         and execution_state["failure"] is None
                         and execution_state["request_count"] >= 1
                         and not execution_state["pending_requests"])),
            "provider_cost": budget.snapshot(),
            "codex_cli_sha256": harness_runtime["codex_cli"]["sha256"],
            "codex_harness_runtime": harness_runtime,
            "codex_harness_runtime_unchanged": harness_runtime_unchanged,
            "python_runtime": {"executable": sys.executable,
                               "target": str(Path(sys.executable).resolve()),
                               "prefix": sys.prefix,
                               "sha256": file_hash(Path(sys.executable))},
            "source_manifest": (source_manifest
                                if args.controller_stage == "model"
                                and args.tool_mode == "formal" else None),
        }
        fresh_json(output / "assessment.json", assessment)
        print(canonical(assessment))
        if not assessment["valid"]:
            raise RuntimeError("controller session failed; inspect permanent artifacts")
    finally:
        if execution_service is not None:
            execution_service.stop()
            execution_service.join()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--budget-bucket", default="setup")
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--tokenizer-cache", required=True, type=Path)
    parser.add_argument("--tool-mode", choices=("canary", "formal"), default="formal")
    parser.add_argument("--controller-stage", choices=("model", "objective", "data", "ingest", "data_use", "grid_objective", "grid_learning"),
                        default="model")
    parser.add_argument("--runner-config", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--require-all-tools", action="store_true")
    main(parser.parse_args())
