#!/usr/bin/env python3
"""One completion-only diagnostic from preserved Alico research; never retries."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from edgar_forecast_openai import (REPO, RUNTIME, PILOT, PLAN_HASH, credential,
    OpenAIHTTP, ProviderHTTPError, attempt_output, final_request,
    predictions_from_output, budgeted_response, unit)
from edgar_forecast_budget import PilotBudget, BudgetStop
from edgar_forecast_model_pilot import digest, write_json
from edgar_forecast_tools import FilingTools

PARENT_ID = "attempt-03-timeout180"
PARENT_HASH = "84e751f738eb66840e116c647c1764ca4629adf76ed8dc3d37d2d73386eade75"
BASE_COST = 2_390_297_000


def parent_history(parent, company, rates, expected_hash=PARENT_HASH):
    summary_path = parent / "failure-summary.json"
    if parent.is_symlink() or summary_path.is_symlink() or digest(summary_path.read_bytes()) != expected_hash:
        raise ValueError("Preserved parent summary changed")
    summary = json.loads(summary_path.read_text())
    if summary["completed_model_turns"] != 23 or summary["provider_incomplete_reason"] != "max_output_tokens":
        raise ValueError("Not the diagnosed 23-turn research parent")
    names = set()
    for receipt in summary["receipts"]:
        name = receipt["path"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in names:
            raise ValueError("Unsafe or duplicate parent receipt")
        names.add(name)
        path = parent / name
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != receipt["sha256"]:
            raise ValueError("Preserved parent receipt changed")
    if not {"identity.json", "24-request.json"} <= names:
        raise ValueError("Missing parent identity or pre-final request")
    identity = json.loads((parent / "identity.json").read_text())
    saved = json.loads((parent / "24-request.json").read_text())["payload"]
    if identity["cik"] != company["cik"] or identity["pilot_plan_sha256"] != PLAN_HASH or identity["rates"] != rates or saved["model"] != rates["api_model"]:
        raise ValueError("Parent model/company/data identity differs")
    history = saved["input"]
    if not isinstance(history, list) or not history or history[0] != {"role": "user", "content": FilingTools(company).files["questions.md"]} or history[-1].get("type") != "function_call_output":
        raise ValueError("Pre-final question/research handoff differs")
    return history, {"parent_attempt_id": parent.name, "parent_summary_sha256": expected_hash,
                     "parent_source_commit": identity["source_commit"], "reused_research_turns": 23,
                     "reused_tool_calls": sum(summary["tool_calls_by_name"].values()),
                     "parent_pre_final_request_sha256": digest((parent / "24-request.json").read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ValueError("Committed source required")
    pins = {}
    for name in ["tools/edgar_forecast_completion_trial.py", "tools/edgar_forecast_openai.py", "tools/edgar_forecast_tools.py",
                 "tools/edgar_forecast_budget.py", "tools/edgar_forecast_model_pilot.py", "tools/edgar_forecast_audit.py",
                 str(RUNTIME.relative_to(REPO))]:
        data = subprocess.run(["git", "show", args.source_commit + ":" + name], cwd=REPO, check=True, capture_output=True).stdout
        if data != (REPO / name).read_bytes():
            raise ValueError("Trial source differs from committed bytes")
        pins[name] = digest(data)
    if digest((PILOT / "pilot-plan.json").read_bytes()) != PLAN_HASH:
        raise ValueError("Pilot data manifest changed")
    config = json.loads(RUNTIME.read_text())
    rates = config["models"]["gpt-5.5"]
    company = next(c for c in json.loads((PILOT / "pilot-plan.json").read_text())["companies"] if c["cik"] == "CIK0000003545")
    files = FilingTools(company)
    parent = attempt_output("gpt-5.5", company["cik"], PARENT_ID)
    history, provenance = parent_history(parent, company, rates)
    output = attempt_output("gpt-5.5", company["cik"], args.attempt_id)
    if args.preflight_only:
        print(json.dumps({"status": "COMPLETION_PREFLIGHT_PASS", "files": len(files.files), **provenance}))
        return
    budget = PilotBudget(PILOT / "api-budget.sqlite3")
    try:
        budget.active()
        before = budget.summary()
        maximum = config["max_input_tokens"] * max(unit(rates[k]) for k in ["input", "cached", "write"] if rates[k] is not None) + config["max_output_tokens"] * unit(rates["output"])
        charged = budget.db.execute("SELECT COALESCE(SUM(charged),0) FROM requests").fetchone()[0]
        if not 49 <= before["generation_requests_reserved"] < 52 or not BASE_COST <= charged <= BASE_COST + 5_000_000_000 - maximum:
            raise BudgetStop("Completion repair's three-trial/USD5 sub-ceiling exceeded")
        client = OpenAIHTTP(credential(), config["request_timeout_seconds"])
        output.mkdir(parents=True, exist_ok=False)
        write_json(output / "identity.json", {"source_commit": args.source_commit, "source_pins": pins,
                   "attempt_id": args.attempt_id, "pilot_plan_sha256": PLAN_HASH, "rates": rates,
                   "config": config, "cik": company["cik"], **provenance,
                   "execution_mode": "COMPLETION_FROM_PRESERVED_RESEARCH",
                   "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        start = time.monotonic()
        try:
            targets = re.findall(r"^### (T\d+) \|", files.files["questions.md"], re.M)
            response = budgeted_response(client, final_request(history, rates, targets), rates, config, budget, output, 24)
            predictions = predictions_from_output(response["output"], targets)
            write_json(output / "predictions.json", predictions)
            result = {"status": "COMPLETED", "turns": 1, "tool_calls": 0, "strict_single_number_errors": [], **provenance}
        except Exception as error:
            result = {"status": "FAILED_NO_RETRY", "error_type": type(error).__name__, **provenance}
            if isinstance(error, ProviderHTTPError):
                result.update(error.detail)
        result.update(execution_mode="COMPLETION_FROM_PRESERVED_RESEARCH", wall_seconds=time.monotonic() - start)
        write_json(output / "budget-summary.json", budget.summary())
        write_json(output / "result.json", result)
        print(json.dumps(result))
    finally:
        budget.close()


if __name__ == "__main__":
    main()
