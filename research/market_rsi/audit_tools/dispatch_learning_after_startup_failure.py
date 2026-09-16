"""One guarded continuation after a proven zero-sample startup failure.

No automatic retry loop. Every prepared session remains permanently claimed.
The scientific prompt, original model results, objective and budget are unchanged.
"""
import argparse
import fcntl
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_grid_learning_controller import validate_workspace
from market_rsi import canonical, file_hash, fresh_json, load_json
from paid_budget import PaidBudget, money


def run(prepared, failed, probe, extension_audit, failed_probe=None):
    root = Path(__file__).resolve().parents[1]
    p = load_json(prepared / "preparation.json")
    command = p["command"]
    budget = PaidBudget(Path(command[command.index("--budget") + 1]))
    with (root / "artifacts/historical-ingest-controller.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (prepared / "dispatch-claim.json").exists() or (prepared / "session").exists():
            raise ValueError("permanent prepared session already dispatched")
        assessment = load_json(failed / "session/assessment.json")
        if (assessment.get("valid") is not False or not assessment.get("process_reaped")
                or assessment.get("turns") != 0 or assessment.get("tool_calls") != 0
                or list((failed / "session").glob("turn-*"))):
            raise ValueError("this recovery only admits proven pre-sample startup failures")
        state = budget.snapshot()
        if any(k.startswith((prepared.name + "-", failed.name + "-")) for k in state["jobs"]):
            raise ValueError("a paid job exists for the failed or prepared session")
        if any(v["state"] == "dispatched" and "-turn-" in k for k, v in state["jobs"].items()):
            raise ValueError("another unresolved paid controller turn exists")
        if money(state["buckets"]["learning"]["available_usd"]) < money("2"):
            raise ValueError("insufficient existing learning allocation")
        diagnostic = load_json(probe / "result.json")
        if (diagnostic["exit_code"] != 0 or diagnostic["provider_calls"] != 0
                or diagnostic["fits"] != 0 or diagnostic["requests"] != 1
                or not all(d["input_conversion_ok"] and d["tokenizer_ok"]
                           for d in diagnostic["diagnostics"])):
            raise ValueError("exact local startup probe did not pass")
        prompt_sha = file_hash(prepared / "prompt.txt")
        if not (prompt_sha == p["prompt_sha256"] == file_hash(failed / "prompt.txt")
                == diagnostic["exact_learning_prompt_sha256"]):
            raise ValueError("scientific startup prompt changed")
        causal_fix = None
        if failed_probe is not None:
            before = load_json(failed_probe/'result.json')
            failure = load_json(failed/'session/request-failure.json')
            if (before['provider_calls'] != 0 or before['fits'] != 0 or before['requests'] != 1
                    or before['exact_learning_prompt_sha256'] != prompt_sha
                    or before['diagnostics'][0].get('error') != 'controller harness tools are missing'
                    or failure.get('stage') != 'input_conversion'
                    or failure.get('provider_invoked_for_request') is not False
                    or 'mcp_servers.controller_tools.required=true' not in load_json(probe/'command.json')['args']):
                raise ValueError('exact missing-tool reproduction and mandatory-startup repair required')
            causal_fix = {'failed_probe_sha256':file_hash(failed_probe/'result.json'),
                'request_failure_sha256':file_hash(failed/'session/request-failure.json'),
                'cause':'Research MCP tools absent at first request under optional startup grace; reproduced without provider call.',
                'repair':'Make the configured research tool server required, keeping 10-second startup timeout, same prompt/model/scientific data.',
                'official_reference':'https://learn.chatgpt.com/docs/extend/mcp?surface=cli'}
        canary = load_json(prepared / "transport-canary.json")
        if not canary["passed"] or canary["new_model_calls"] or canary["new_fits"]:
            raise ValueError("prepared interface canary did not pass")
        if load_json(extension_audit / "audit.json")["passed"] is not True:
            raise ValueError("additive input audit failed")
        for name, sha in p["source_hashes"].items():
            if file_hash(root / name) != sha or file_hash(prepared / "source-snapshot" / name) != sha:
                raise ValueError("scientific source freeze changed")
        if (file_hash(command[0]) != p["runtime_sha256"]
                or file_hash(prepared / "workspace/workspace.json") != p["workspace_sha256"]):
            raise ValueError("runtime or workspace changed")
        validate_workspace(prepared / "workspace")
        # Read process metadata only; never print process environment or arguments.
        rows = subprocess.check_output(["/bin/ps", "-axo", "pid=,command="], text=True).splitlines()
        live = [int(row.strip().split(None, 1)[0]) for row in rows
                if str(root / "run_codex_glm_controller.py") in row
                or str(root / "bounded_historical_ingest.py") in row]
        if live:
            raise ValueError("another exact controller or ingest worker is active")
        fresh_json(prepared / "startup-recovery.json", {
            "failed_session": failed.name,
            "failed_assessment_sha256": file_hash(failed / "session/assessment.json"),
            "zero_provider_dispatch_proven_by_ledger_and_turn_inventory": True,
            "original_error_cause": causal_fix['cause'] if causal_fix else "unknown; generic Codex high-demand message was not a provider receipt",
            "local_probe_sha256": file_hash(probe / "result.json"),
            "repair": causal_fix['repair'] if causal_fix else "record exact request stage and redacted traceback locations before a paid turn exists",
            "causal_fix_evidence": causal_fix,
            "automatic_retry_loop": False, "scientific_prompt_changed": False,
            "new_fits_before_dispatch": 0, "budget_before": {k: v for k, v in state.items() if k != "jobs"},
        })
        fresh_json(prepared / "dispatch-claim.json", {
            "session_id": prepared.name, "claimed_unix_ns": time.time_ns(),
            "preparation_sha256": file_hash(prepared / "preparation.json"),
            "canary_sha256": file_hash(prepared / "transport-canary.json"),
            "extension_audit_sha256": file_hash(extension_audit / "audit.json"),
            "startup_recovery_sha256": file_hash(prepared / "startup-recovery.json"),
            "dispatcher_sha256": file_hash(Path(__file__)),
        })
        with (prepared / "runner.log").open("x") as log:
            process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, pass_fds=(lock.fileno(),))
        result = {"pid": process.pid, "process_group": process.pid, "command": command,
                  "lock_inherited": True, "started_unix_ns": time.time_ns()}
        fresh_json(prepared / "runner-process.json", result)
        return {"pid": process.pid, "session_id": prepared.name, "launched_once": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("prepared", "failed", "probe", "extension-audit"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument('--failed-probe',type=Path)
    print(canonical(run(**{k: v.resolve() if v is not None else None for k, v in vars(parser.parse_args()).items()})))
