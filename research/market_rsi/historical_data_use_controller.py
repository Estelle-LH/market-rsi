"""GLM/Codex review of existing historical data; no download or scoring tool.

Produces a first-valid controller-owned data-use proposal for a diagnostic
materializer. A valid proposal is NOT a claim that training or evaluation is ready.
"""
import argparse
import json
import os
from pathlib import Path
import sys

from controller_activity_log import append_activity, read_activity_events, verify_activity_log
from historical_ingest_controller import load, _signed, _tool
from historical_source_contract import contract, CLOCK_ASSUMPTION
from literature_catalog import literature_snapshot
from market_rsi import canonical, digest, file_hash, fresh_json, identifier


BASE_INSTRUCTIONS = (
    "You are the GLM researcher using the existing Codex harness. Review measured historical "
    "source quality and decide how to use the existing corpus for a diagnostic learning pilot. "
    "The prior smallest-file acquisition did not establish 40 complete sessions. Do not defend "
    "that assumption or treat hundreds of millions of rows as independent samples. Inspect "
    "quality, actual UTC coverage, the executable field/clock contract and canary. Synthetic "
    "IDs repeat across unrelated events. PM price_change is a book delta, not a trade. Binance "
    "trades are not PM trades; no verified Binance midpoint, PM trade tape or resolution labels "
    "are present. You choose open Train dates, input sources, cadence, max age and feature ideas; "
    "the runner does not choose them. No new download, target selection, Dev creation or model "
    "scoring is available in this stage. Nominal contract windows are not settlement proof. "
    "You may inspect/search a frozen public literature catalog, not live web search. Choose "
    "a data-use proposal or defer if a causal implementation cannot be justified. A selected "
    "proposal must still pass a fresh runner-owned materializer canary before objective research. "
    "State limitations and tradeoffs. Submit your first valid decision and exit; no resampling "
    "for score, no extra confirmation. No formal out-of-sample or profitability claims."
)


def prepare_workspace(output, *, feedback, coverage, source_canary, session_id, experiment_id):
    identifier(session_id); identifier(experiment_id)
    report = load(feedback); _signed(report, "feedback_sha256")
    cov = load(coverage)
    canary = load(source_canary / "result.json")
    claim = load(source_canary / "claim.json")
    spec = load(source_canary / "source-contract.json")
    if (canary.get("canary_pass") is not True or canary.get("training_admitted") is not False
            or claim["plan_sha256"] != report["source_plan_sha256"]
            or claim.get("contract_source_sha256") != file_hash(Path(__file__).with_name("historical_source_contract.py"))
            or report.get("source_artifact_sha256", {}).get("coverage") != file_hash(coverage)
            or cov["rows"] != report["acquisition"]["pm_tick_rows"] or spec != contract()):
        raise ValueError("matching tested source contract and coverage required")
    output.mkdir(exist_ok=False, parents=True, mode=0o700)
    (output / "proposals").mkdir()
    opened_dates = sorted(set(["2026-02-22", "2026-05-14"] +
        report.get("open_train_materialization", {}).get("opened_utc_dates", [])))
    visible = {
        "quality.json": report, "source-contract.json": spec,
        "canary.json": canary,
        "coverage-calendar.json": {"dates": cov["actual_utc_receipt_day_event_bins"],
            "observed_markets": cov["observed_markets"],
            "dates_are_not_verified_complete_sessions": True},
        "literature.json": literature_snapshot(),
        "constraints.json": {"purpose": "diagnostic_learning_pilot", "max_materialized_rows": 500_000,
            "additional_downloads_allowed": False, "choose_objective_here": False,
            "designate_dev_or_future_test_here": False, "automatic_training_admission": False,
            "known_opened_dates_not_fresh_holdout": opened_dates,
            "all_future_holdout_claims_require_exposure_audit": True},
    }
    for name, value in visible.items():fresh_json(output / name, value)
    manifest = {"schema": "historical_data_use_workspace_v1", "session_id": session_id,
                "experiment_id": experiment_id, "source_plan_sha256": report["source_plan_sha256"],
                "files": {name: file_hash(output / name) for name in visible},
                "dev_present": False, "future_test_present": False}
    fresh_json(output / "workspace.json", manifest)
    return validate_workspace(output)


def validate_workspace(root):
    m = load(root / "workspace.json")
    required = {"quality.json", "source-contract.json", "canary.json", "coverage-calendar.json",
                "literature.json", "constraints.json"}
    if (m.get("schema") != "historical_data_use_workspace_v1" or set(m.get("files", {})) != required
            or m.get("dev_present") is not False or m.get("future_test_present") is not False):
        raise ValueError("data-use workspace changed")
    for name, sha in m["files"].items():
        load(root / name)
        if file_hash(root / name) != sha:raise ValueError("frozen data-use input changed")
    if load(root / "source-contract.json") != contract():
        raise ValueError("executable source contract changed")
    return m


def validate_proposal(plan, workspace):
    fields = {"purpose", "open_train_utc_dates", "primary_observation", "context_streams",
              "cadence_ms", "max_age_ms", "market_time_scope", "max_materialized_rows",
              "clock_assumption", "feature_ideas", "rationale", "limitations"}
    if not isinstance(plan, dict) or set(plan) != fields:
        raise ValueError("data-use proposal fields missing or changed")
    dates = plan["open_train_utc_dates"]
    available = {r["utc_date"] for r in load(workspace / "coverage-calendar.json")["dates"]}
    if (not isinstance(dates, list) or not all(isinstance(d, str) for d in dates)
            or len(dates) < 2 or len(set(dates)) != len(dates) or not set(dates) <= available):
        raise ValueError("at least two distinct available UTC Train dates required")
    if plan["purpose"] != "diagnostic_learning_pilot" or plan["clock_assumption"] != CLOCK_ASSUMPTION:
        raise ValueError("explicit diagnostic purpose and publisher clock assumption required")
    if plan["primary_observation"] not in {"pm_reported_bbo", "pm_book_level_deltas"}:
        raise ValueError("unsupported primary observation; request an extension or defer")
    allowed = {"binance_ticks_ms", "binance_trades", *contract()["streams"].keys()} - {"binance_candles", "polymarket_ticks_ms"}
    allowed |= {f"binance_candles_{v}" for v in ("1s", "5s", "1m", "5m", "15m", "1h")}
    context = plan["context_streams"]
    if (not isinstance(context, list) or not all(isinstance(s, str) for s in context)
            or len(set(context)) != len(context) or not set(context) <= allowed):
        raise ValueError("unsupported context stream")
    for key in ("cadence_ms", "max_age_ms", "max_materialized_rows"):
        if type(plan[key]) is not int or plan[key] < (0 if key == "max_age_ms" else 1):
            raise ValueError("explicit nonnegative age and positive cadence/row bound required")
    if plan["max_materialized_rows"] > 500_000:
        raise ValueError("bounded local materializer supports at most 500000 output rows")
    if plan["market_time_scope"] not in {"observed_arrival_interval", "nominal_15m_window"}:
        raise ValueError("unsupported market clock scope")
    if (not isinstance(plan["feature_ideas"], list) or not 1 <= len(plan["feature_ideas"]) <= 16
            or not all(isinstance(v, str) and 1 <= len(v) <= 4000 for v in plan["feature_ideas"])):
        raise ValueError("bounded controller feature ideas required")
    if not all(isinstance(plan[k], str) and 1 <= len(plan[k]) <= 12000 for k in ("rationale", "limitations")):
        raise ValueError("rationale and limitations required")
    return {**plan, "open_train_utc_dates": sorted(dates), "context_streams": sorted(context)}


STRING = {"type": "string", "minLength": 1, "maxLength": 12000}
PLAN_SCHEMA = {"type": "object", "description": "Complete data-use proposal; inspect_source_contract returns required shape."}
TOOLS = [
    _tool("inspect_data_readiness", "Read all aggregate source QA; no market rows or forecast scores."),
    _tool("inspect_source_contract", "Inspect field/clock safeguards and the required proposal shape."),
    _tool("inspect_coverage_calendar", "Read actual UTC receipt coverage, not filename dates or verified full days."),
    _tool("search_public_literature", "Search the frozen public literature catalog; not live web.", {"query": STRING}),
    _tool("propose_data_use", "Validate and archive a diagnostic data-use proposal; does not execute it.",
          {"proposal_id": STRING, "plan": PLAN_SCHEMA}),
    _tool("submit_data_use_decision", "First valid select/defer decision. Exit afterwards.",
          {"action": {"type": "string", "enum": ["select", "defer"]},
           "proposal_id": {"type": "string"}, "reason": STRING}),
]
ALLOWED_TOOLS = tuple(t["name"] for t in TOOLS)


class Broker:
    def __init__(self, workspace):self.root = workspace;validate_workspace(workspace)

    def call(self, name, arguments):
        validate_workspace(self.root)
        if (self.root / "submitted-data-use-decision.json").exists():
            raise ValueError("decision already submitted; do not resample")
        if name not in ALLOWED_TOOLS or not isinstance(arguments, dict):
            raise ValueError("unknown data-use tool")
        try:
            result = self._call(name, arguments)
        except Exception as exc:
            append_activity(self.root / "data-use-activity.jsonl", {"tool": name, "arguments": arguments,
                "status": "error", "error": str(exc)})
            raise
        append_activity(self.root / "data-use-activity.jsonl", {"tool": name, "arguments": arguments,
                        "status": "ok", "result": result})
        return result

    def _call(self, name, a):
        if name == "inspect_data_readiness":return load(self.root / "quality.json")
        if name == "inspect_coverage_calendar":return load(self.root / "coverage-calendar.json")
        if name == "inspect_source_contract":
            return {"contract": contract(), "constraints": load(self.root / "constraints.json"),
                    "canary": load(self.root / "canary.json"),
                    "proposal_fields": ["purpose=diagnostic_learning_pilot", "open_train_utc_dates (>=2)",
                        "primary_observation=pm_reported_bbo|pm_book_level_deltas", "context_streams (optional Binance tables)",
                        "cadence_ms (>0)", "max_age_ms (>=0)", "market_time_scope=observed_arrival_interval|nominal_15m_window",
                        "max_materialized_rows (<=500000)", "clock_assumption="+CLOCK_ASSUMPTION,
                        "feature_ideas (1..16 strings)", "rationale", "limitations"]}
        if name == "search_public_literature":
            terms = set(a["query"].lower().split())
            papers = load(self.root / "literature.json")["papers"]
            ranked = sorted(papers, key=lambda p: -sum(t in canonical(p).lower() for t in terms))
            return {"mode": "frozen_catalog_not_live_search", "papers": ranked[:8]}
        if name == "propose_data_use":
            identifier(a["proposal_id"])
            plan = validate_proposal(a["plan"], self.root)
            body = {"proposal_id": a["proposal_id"], "plan": plan, "contract_sha256": contract()["contract_sha256"],
                    "materializer_execution_verified": False, "objective_selected": False, "training_admitted": False}
            body["proposal_sha256"] = digest(body)
            fresh_json(self.root / "proposals" / (a["proposal_id"] + ".json"), body)
            return body
        if name == "submit_data_use_decision":
            events = read_activity_events(self.root / "data-use-activity.jsonl")
            seen = {e["tool"] for e in events if e["status"] == "ok"}
            if not {"inspect_data_readiness", "inspect_source_contract", "inspect_coverage_calendar"} <= seen:
                raise ValueError("inspect quality, source contract and actual coverage before deciding")
            if not isinstance(a.get("reason"), str) or not a["reason"].strip():
                raise ValueError("decision rationale required")
            if a["action"] == "select":
                identifier(a["proposal_id"])
                body = load(self.root / "proposals" / (a["proposal_id"] + ".json"));_signed(body,"proposal_sha256")
                validate_proposal(body["plan"],self.root)
                fresh_json(self.root / "frozen-data-use-proposal.json", body)
            elif a["action"] != "defer":raise ValueError("invalid action")
            fresh_json(self.root / "submitted-data-use-decision.json", a)
            return {"submitted": True, "bytes": len(canonical(a).encode()),
                    "action": a["action"], "training_admitted": False,
                    "materializer_execution_verified": False}
        raise ValueError("unknown tool")


def assess_activity(root):
    validate_workspace(root)
    log = verify_activity_log(root / "data-use-activity.jsonl")
    events = read_activity_events(root / "data-use-activity.jsonl")
    selected = [e for e in events if e["tool"] == "submit_data_use_decision" and e["status"] == "ok"]
    if len(selected) != 1 or load(root / "submitted-data-use-decision.json") != selected[0]["arguments"]:
        raise ValueError("exactly one logged first-valid decision required")
    if selected[0]["arguments"]["action"] == "select":
        body = load(root / "frozen-data-use-proposal.json");_signed(body,"proposal_sha256")
        proposed = [e for e in events if e["tool"] == "propose_data_use" and e["status"] == "ok" and e["result"] == body]
        if len(proposed) != 1:raise ValueError("selected proposal missing matching logged creation")
    return {"valid": True, "log": log, "action": selected[0]["arguments"]["action"],
            "materializer_execution_verified": False}


def serve(broker):
    from data_discovery_tools_mcp import reply
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line);method = request.get("method");rid = request.get("id")
            if method == "initialize":reply(rid, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                "serverInfo": {"name": "historical-data-use", "version": "1"}})
            elif method == "ping":reply(rid, {})
            elif method == "tools/list":reply(rid, {"tools": TOOLS})
            elif method == "tools/call":
                p=request.get("params", {})
                try:result=broker.call(p.get("name"), p.get("arguments", {}));failed=False
                except (ValueError, FileExistsError, KeyError) as exc:result={"accepted": False, "message": str(exc)};failed=True
                reply(rid, {"content": [{"type": "text", "text": canonical(result)}], "isError": failed})
        except Exception as exc:
            if isinstance(request, dict) and request.get("id") is not None:reply(request["id"], error=exc)


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--workspace", type=Path, required=True)
    args=parser.parse_args();os.environ.clear();serve(Broker(args.workspace))
