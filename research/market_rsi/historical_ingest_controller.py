"""Controller-owned, hash-bound expansion after a passing historical-data canary.

No market rows, targets, credentials, downloader or evaluation tools are exposed.
The existing data-discovery canary protocol is deliberately left unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

from controller_activity_log import append_activity, read_activity_events, verify_activity_log
from literature_catalog import literature_snapshot
from market_rsi import canonical, digest, file_hash, fresh_json, identifier

DATASET = "gregyoung14/openmarket-btc-polymarket"
REVISION = "74502466d1a7cef56395bfd8d0b465fbebc849cf"
MAX_BYTES = 5_000_000_000
BASE_INSTRUCTIONS = (
    "You are the GLM historical-data researcher in the existing Codex harness. "
    "A prior source canary ran, and the user authorizes continued bounded data "
    "preparation. Now choose an exact larger acquisition manifest, not another copy of "
    "the same canary. Inspect the complete public inventory and measured canary limits. "
    "Compare at least two distinct executable file selections. Use propose_ingest_recipe "
    "to calculate dates and bytes; explicit date lists remain available. You choose the dates and "
    "raw streams, within a 5 GB total compressed-file cap and a 40-date preparation goal. "
    "Forty dates is an acquisition target, not proof of adequate statistical power. "
    "Use only inventory coverage, bytes, clocks, stream availability and scientific "
    "reasoning, not observed price movements or prediction outcomes, to select files. "
    "You may search the supplied frozen literature; describe that as a catalog search, "
    "not live web research. All dates and markets remain unassigned to Train/Dev/Test. "
    "Two canary dates have already been inspected and cannot later be fresh holdouts. "
    "No objective or split is selected here. Missing trade tape, resolution, true "
    "within-timestamp ordering and full-day coverage remain limitations, not repaired "
    "facts. Binance trades are NOT prediction-market trades. Derived lag-pair tables "
    "are not eligible as raw data. Do not claim downloading proves usable features. "
    "Inspect supplemental source-issue evidence: it supersedes an older passing canary. "
    "If token/market identity mismatches exist, raw acquisition may preserve and flag "
    "them for review, but neither automatic relabeling nor training admission is allowed. "
    "You can defer with reasons rather than manufacture a feasible plan. After inspecting "
    "inventory and canary, proposing and comparing plans, submit your first valid decision "
    "with submit_ingest_decision and exit. No extra confirmation or model execution is needed."
)


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("bounded regular JSON input required")
    return json.loads(path.read_bytes())


def _signed(value: dict, field: str) -> None:
    if value.get(field) != digest({k: v for k, v in value.items() if k != field}):
        raise ValueError("input content hash mismatch")


def prepare_workspace(output: Path, *, inventory: Path, canary: Path,
                      session_id: str, experiment_id: str,
                      source_issues: Path | None = None) -> dict:
    identifier(session_id)
    identifier(experiment_id)
    inv, report = load(inventory), load(canary)
    _signed(inv, "inventory_sha256")
    _signed(report, "report_sha256")
    if (inv.get("dataset") != DATASET or inv.get("revision") != REVISION
            or report.get("canary_pass") is not True
            or report.get("source", {}).get("license") != "apache-2.0"
            or report.get("source", {}).get("revision") != REVISION
            or report.get("inventory_sha256") != inv["inventory_sha256"]):
        raise ValueError("passing canary and exact public inventory required")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    visible = {"inventory.json": inv, "canary.json": report,
               "literature.json": literature_snapshot(),
               "constraints.json": {"max_compressed_bytes": MAX_BYTES,
                                    "minimum_tick_dates": 40,
                                    "fresh_holdout_excluded_dates": ["2026-02-22", "2026-05-14"],
                                    "download_is_not_formal_admission": True}}
    if source_issues is not None:
        issue = load(source_issues)
        _signed(issue, "evidence_sha256")
        if (issue.get("dataset") != DATASET or issue.get("revision") != REVISION
                or issue.get("raw_modified") is not False):
            raise ValueError("source issue must bind the same unchanged public revision")
        visible["source-issues.json"] = issue
    for name, body in visible.items():
        fresh_json(output / name, body)
    manifest = {"schema": "market_historical_ingest_workspace_v1",
                "session_id": session_id, "experiment_id": experiment_id,
                "files": {name: file_hash(output / name) for name in visible},
                "dev_present": False, "future_test_present": False}
    fresh_json(output / "workspace.json", manifest)
    return validate_workspace(output)


def validate_workspace(root: Path) -> dict:
    manifest = load(root / "workspace.json")
    if (manifest.get("schema") != "market_historical_ingest_workspace_v1"
            or manifest.get("dev_present") is not False
            or manifest.get("future_test_present") is not False
            or set(manifest.get("files", {})) not in (
                {"inventory.json", "canary.json", "literature.json", "constraints.json"},
                {"inventory.json", "canary.json", "literature.json", "constraints.json", "source-issues.json"})):
        raise ValueError("ingest workspace changed")
    for name, expected in manifest["files"].items():
        load(root / name)
        if file_hash(root / name) != expected:
            raise ValueError("frozen ingest input changed")
    return manifest


def _eligible(record: dict) -> bool:
    path = record.get("path", "")
    parts = PurePosixPath(path).parts
    return (len(parts) >= 4 and parts[0] == "unified" and ".." not in parts
            and path.endswith(".parquet")
            and (parts[1] in {"market_meta", "polymarket_ticks_ms", "binance_ticks_ms", "binance_trades"}
                 or parts[1].startswith("binance_candles_")))


def select_files(inventory: dict, proposal: dict) -> dict:
    expected = {"proposal_id", "tables", "utc_dates", "rationale", "limitations"}
    if set(proposal) != expected:
        raise ValueError("exact proposal fields required")
    identifier(proposal["proposal_id"])
    tables, dates = proposal["tables"], proposal["utc_dates"]
    if (not isinstance(tables, list) or len(set(tables)) != len(tables)
            or not {"market_meta", "polymarket_ticks_ms"} <= set(tables)
            or not isinstance(dates, list) or len(dates) != len(set(dates))
            or len(dates) < 40 or len(dates) > 100):
        raise ValueError("require unique tables including market_meta and polymarket_ticks_ms, and 40-100 unique dates; use propose_ingest_recipe to generate valid dates")
    if any(not isinstance(proposal[key], str) or not 1 <= len(proposal[key]) <= 8000
           for key in ("rationale", "limitations")):
        raise ValueError("bounded scientific rationale and limitations required")
    records = inventory["files"]
    available = {r["path"].split("/")[1] for r in records if _eligible(r)}
    if not set(tables) <= available:
        raise ValueError("unknown or nonraw table")
    selected, tick_dates = [], set()
    for record in records:
        if not _eligible(record) or record["path"].split("/")[1] not in tables:
            continue
        match = re.search(r"/date=(\d{4}-\d{2}-\d{2})/", record["path"])
        day = match.group(1) if match else None
        if day is not None and day not in dates:
            continue
        if not re.fullmatch("[0-9a-f]{64}", record.get("lfs_sha256") or ""):
            raise ValueError("every selected object needs a published SHA-256")
        if type(record.get("bytes")) is not int or record["bytes"] <= 0:
            raise ValueError("positive file bytes required")
        selected.append(dict(record))
        if record["path"].split("/")[1] == "polymarket_ticks_ms":
            tick_dates.add(day)
    if tick_dates != set(dates):
        raise ValueError("requested tick date missing from inventory: " + canonical(sorted(set(dates) - tick_dates)))
    if len({r["path"] for r in selected}) != len(selected):
        raise ValueError("duplicate source paths")
    selected.sort(key=lambda r: r["path"])
    total = sum(r["bytes"] for r in selected)
    if total > MAX_BYTES:
        raise ValueError(f"selected compressed bytes {total} exceed {MAX_BYTES}")
    return {"selected_files": selected, "selected_bytes": total,
            "selected_file_sha256": digest(selected), "tick_dates": sorted(tick_dates),
            "tick_date_count": len(tick_dates), "full_day_coverage_verified": False,
            "formal_dataset_ready": False}


def inventory_summary(inventory: dict) -> dict:
    dates, tables = {}, {}
    for record in inventory["files"]:
        if not _eligible(record):
            continue
        table = record["path"].split("/")[1]
        tables[table] = tables.get(table, 0) + record["bytes"]
        match = re.search(r"/date=(\d{4}-\d{2}-\d{2})/", record["path"])
        if match:
            d = dates.setdefault(match.group(1), {})
            d[table] = d.get(table, 0) + record["bytes"]
    return {"tables_total_bytes": tables,
            "dates": [{"utc_date": day, "table_bytes": value} for day, value in sorted(dates.items())],
            "tick_dates": sorted(day for day, value in dates.items() if "polymarket_ticks_ms" in value)}


def recipe_proposal(inventory: dict, args: dict) -> dict:
    if set(args) != {"proposal_id", "tables", "date_rule", "date_count", "exclude_dates", "rationale", "limitations"}:
        raise ValueError("unexpected recipe fields")
    summary = inventory_summary(inventory)
    if (type(args["date_count"]) is not int or not 40 <= args["date_count"] <= 100
            or not isinstance(args["exclude_dates"], list)):
        raise ValueError("bounded integer date_count and excluded-date list required")
    dates = sorted(set(summary["tick_dates"]) - set(args["exclude_dates"]))
    n = args["date_count"]
    if len(dates) < n:
        raise ValueError(f"only {len(dates)} available tick dates after exclusions, requested {n}")
    rule = args["date_rule"]
    if rule == "earliest":
        chosen = dates[:n]
    elif rule == "latest":
        chosen = dates[-n:]
    elif rule == "evenly_spaced":
        chosen = [dates[i * (len(dates) - 1) // (n - 1)] for i in range(n)]
    elif rule == "hash_seed23":
        chosen = sorted(dates, key=lambda d: hashlib.sha256(("23:" + d).encode()).hexdigest())[:n]
    elif rule == "smallest_compressed_bytes":
        costs = {r["utc_date"]: sum(r["table_bytes"].get(t, 0) for t in args["tables"])
                 for r in summary["dates"]}
        chosen = sorted(dates, key=lambda d: (costs[d], d))[:n]
    else:
        raise ValueError("unsupported recipe; explicit date proposals are also available")
    return {"proposal_id": args["proposal_id"], "tables": args["tables"],
            "utc_dates": sorted(chosen), "rationale": args["rationale"], "limitations": args["limitations"]}


def _tool(name, description, properties=None):
    properties = properties or {}
    return {"name": name, "description": description, "inputSchema": {
        "type": "object", "properties": properties, "required": list(properties),
        "additionalProperties": False}}


STRING = {"type": "string", "minLength": 1, "maxLength": 8000}
STRINGS = {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 100}
TOOLS = [
    _tool("inspect_history_inventory", "Read public date/stream byte inventory and resource constraints."),
    _tool("inspect_source_canary_evidence", "Read measured canary limitations, clocks and provenance."),
    _tool("search_public_literature", "Search the frozen public literature catalog, not the live web.", {"query": STRING}),
    _tool("propose_ingest_plan", "Build and validate a concrete raw-file selection without downloading.",
          {"proposal_id": STRING, "tables": STRINGS, "utc_dates": STRINGS,
           "rationale": STRING, "limitations": STRING}),
    _tool("propose_ingest_recipe", "Compute an exact manifest from your selected date rule; no manual date transcription or download. Smallest-bytes changes the sampled population and must be justified.",
          {"proposal_id": STRING, "tables": STRINGS,
           "date_rule": {"type": "string", "enum": ["earliest", "latest", "evenly_spaced", "hash_seed23", "smallest_compressed_bytes"]},
           "date_count": {"type": "integer", "minimum": 40, "maximum": 100},
           "exclude_dates": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
           "rationale": STRING, "limitations": STRING}),
    _tool("compare_ingest_plans", "Compare at least two distinct executable raw-file selections.", {"proposal_ids": STRINGS}),
    _tool("submit_ingest_decision", "Freeze first valid choice or defer; no data is downloaded by this tool.",
          {"action": {"type": "string", "enum": ["select", "defer"]},
           "proposal_id": STRING, "rationale": STRING}),
]
ALLOWED_TOOLS = tuple(t["name"] for t in TOOLS)


class Broker:
    def __init__(self, workspace: Path):
        self.root = workspace
        self.manifest = validate_workspace(workspace)

    def call(self, name, args):
        validate_workspace(self.root)
        try:
            result = self._call(name, args)
            append_activity(self.root / "ingest-activity.jsonl", {
                "tool": name, "arguments": args, "result": result, "status": "ok"})
            return result
        except Exception as exc:
            append_activity(self.root / "ingest-activity.jsonl", {
                "tool": name, "arguments": args, "status": "error", "error": str(exc)})
            raise

    def _call(self, name, args):
        schema = next((t for t in TOOLS if t["name"] == name), None)
        if schema is None or not isinstance(args, dict) or set(args) != set(schema["inputSchema"]["required"]):
            raise ValueError("unknown tool or unexpected fields")
        if (self.root / "submitted-ingest-decision.json").exists():
            raise ValueError("controller already submitted its one decision")
        if name == "inspect_history_inventory":
            inv = load(self.root / "inventory.json")
            return {"dataset": DATASET, "revision": REVISION,
                    "constraints": load(self.root / "constraints.json"),
                    **inventory_summary(inv),
                    "documented_gap": ["2026-04-22", "2026-05-12"],
                    "available_dates_are_not_complete_days": True}
        if name == "inspect_source_canary_evidence":
            return {"original_canary": load(self.root / "canary.json"),
                    "later_source_issues": (load(self.root / "source-issues.json")
                                            if (self.root / "source-issues.json").is_file() else None)}
        if name == "search_public_literature":
            terms = str(args["query"]).lower().split()
            papers = load(self.root / "literature.json")["papers"]
            ranked = sorted(papers, key=lambda p: -sum(
                (p["title"] + p["abstract"]).lower().count(t) for t in terms))
            return {"source": "frozen_catalog_not_live_search", "results": ranked[:5]}
        if name in {"propose_ingest_plan", "propose_ingest_recipe"}:
            original_recipe = args if name == "propose_ingest_recipe" else None
            if original_recipe is not None:
                args = recipe_proposal(load(self.root / "inventory.json"), args)
            args = dict(args, utc_dates=sorted(args["utc_dates"]))
            identifier(args["proposal_id"])
            plan = {"proposal": args, "audit": select_files(load(self.root / "inventory.json"), args)}
            if original_recipe is not None:
                plan["selection_recipe"] = original_recipe
            fresh_json(self.root / f"plan-{args['proposal_id']}.json", plan)
            return {"proposal_id": args["proposal_id"], **{k: v for k, v in plan["audit"].items() if k != "selected_files"}}
        if name == "compare_ingest_plans":
            ids = args["proposal_ids"]
            if not isinstance(ids, list) or not 2 <= len(ids) <= 8 or len(set(ids)) != len(ids):
                raise ValueError("two to eight unique plans required")
            summaries = []
            for pid in ids:
                identifier(pid)
                plan = load(self.root / f"plan-{pid}.json")
                summaries.append({"proposal_id": pid, "rationale": plan["proposal"]["rationale"],
                                  **{k: v for k, v in plan["audit"].items() if k != "selected_files"}})
            if len({p["selected_file_sha256"] for p in summaries}) != len(summaries):
                raise ValueError("comparisons must differ in actual selected files")
            return {"automatic_selection": False, "plans": summaries}
        if name == "submit_ingest_decision":
            events = read_activity_events(self.root / "ingest-activity.jsonl")
            seen = {e["tool"] for e in events if e["status"] == "ok"}
            if not {"inspect_history_inventory", "inspect_source_canary_evidence"} <= seen:
                raise ValueError("inspect source inventory and measured canary first")
            if args["action"] not in {"select", "defer"}:
                raise ValueError("select or defer required")
            frozen = None
            if args["action"] == "select":
                pid = args["proposal_id"]
                identifier(pid)
                compared = {p["proposal_id"] for e in events
                            if e["tool"] == "compare_ingest_plans" and e["status"] == "ok"
                            for p in e["result"]["plans"]}
                if pid not in compared:
                    raise ValueError("selected plan must have been compared")
                plan = load(self.root / f"plan-{pid}.json")
                if plan["audit"] != select_files(load(self.root / "inventory.json"), plan["proposal"]):
                    raise ValueError("plan audit changed")
                frozen = {"schema": "market_frozen_historical_ingest_v1",
                          "dataset": DATASET, "revision": REVISION,
                          "workspace_manifest_sha256": file_hash(self.root / "workspace.json"),
                          "session_id": self.manifest["session_id"],
                          "experiment_id": self.manifest["experiment_id"],
                          "decision": args, **plan,
                          "identity_policy": "preserve_and_flag_no_training_admission",
                          "source_issues_sha256": (file_hash(self.root / "source-issues.json")
                                                   if (self.root / "source-issues.json").is_file() else None),
                          "max_compressed_bytes": MAX_BYTES, "formal_dataset_ready": False}
                frozen["plan_sha256"] = digest(frozen)
                fresh_json(self.root / "frozen-ingest-plan.json", frozen)
            fresh_json(self.root / "submitted-ingest-decision.json", args)
            return {"submitted": True, "bytes": len(canonical(args).encode()),
                    "action": args["action"], "plan_sha256": frozen["plan_sha256"] if frozen else None}
        raise ValueError("unimplemented tool")


def assess_activity(workspace: Path) -> dict:
    validate_workspace(workspace)
    receipt = verify_activity_log(workspace / "ingest-activity.jsonl")
    events = read_activity_events(workspace / "ingest-activity.jsonl")
    selected = [e for e in events if e["tool"] == "submit_ingest_decision" and e["status"] == "ok"]
    if len(selected) != 1 or load(workspace / "submitted-ingest-decision.json") != selected[0]["arguments"]:
        raise ValueError("exactly one logged controller decision required")
    if selected[0]["arguments"]["action"] == "select":
        frozen = load(workspace / "frozen-ingest-plan.json")
        _signed(frozen, "plan_sha256")
        if frozen["plan_sha256"] != selected[0]["result"]["plan_sha256"]:
            raise ValueError("selected plan changed after submission")
    return {"valid": True, "log": receipt, "action": selected[0]["arguments"]["action"]}


def serve(broker):
    from data_discovery_tools_mcp import reply
    for raw in sys.stdin:
        request = None
        try:
            request = json.loads(raw)
            method, rid = request.get("method"), request.get("id")
            if method == "initialize":
                reply(rid, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                            "serverInfo": {"name": "historical-ingest", "version": "1"}})
            elif method == "ping":
                reply(rid, {})
            elif method == "tools/list":
                reply(rid, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    result = broker.call(params.get("name"), params.get("arguments", {}))
                except (ValueError, FileExistsError) as exc:
                    result = {"accepted": False, "recoverable": True, "message": str(exc)}
                reply(rid, {"content": [{"type": "text", "text": canonical(result)}], "isError": False})
            elif rid is not None:
                reply(rid, error="unsupported MCP method")
        except Exception as exc:
            if isinstance(request, dict) and request.get("id") is not None:
                reply(request["id"], error=exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    os.environ.clear()
    serve(Broker(args.workspace))
