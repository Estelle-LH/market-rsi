#!/usr/bin/env python3
"""Offline public EDGAR audit: verified pure scorer ASTs, no runner/model calls."""
from __future__ import annotations
import argparse
import ast
import collections
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

REVISION = "6b406d516802d91f2c987390aac837e1a546602f"
SCORER_BLOB = "62ae646a1c3f3a3c6e0ae2315a283db389540062"
PURE = {"normalize_text", "_numeric_scale_multipliers", "_dedupe_numeric_candidates",
        "_numeric_surface_candidates", "_parse_numeric_surface",
        "_ground_truth_numeric_candidates", "_score_forecast_candidate_sets",
        "_score_single_forecast", "score_forecast_predictions"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def remap(value):
    prefix = "sec_parser/edgar_forecast_bench_runs/"
    if not value.startswith(prefix):
        raise ValueError(f"Unexpected upstream path: {value}")
    path = Path("runs") / value[len(prefix):]
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe path")
    return path


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load_scorer(path):
    data = path.read_bytes()
    if git_blob(data) != SCORER_BLOB:
        raise ValueError("Unreviewed scorer version")
    selected = [n for n in ast.parse(data).body if isinstance(n, ast.FunctionDef) and n.name in PURE]
    if {n.name for n in selected} != PURE:
        raise ValueError("Incomplete scorer")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    tree = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
    namespace = {"math": math, "re": re}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace["score_forecast_predictions"], hashlib.sha256(data).hexdigest()


def audit(root, metadata):
    if metadata["sha"] != REVISION:
        raise ValueError("Revision mismatch")
    inventory, errors, replay, bundles = [], [], [], []
    for item in metadata["siblings"]:
        name = item["rfilename"]
        path = root / name
        if path.is_symlink() or not path.is_file():
            errors.append({"path": name, "error": "missing_or_symlink"})
            continue
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        expected = item.get("lfs", {}).get("sha256")
        valid = sha256 == expected if expected else git_blob(data) == item["blobId"]
        if len(data) != item["size"] or not valid:
            errors.append({"path": name, "error": "size_or_hash"})
        inventory.append({"path": name, "bytes": len(data), "sha256": sha256})
    instances = read_json(root / "benchmark_manifest.json")["instances"]
    score, source_hash = load_scorer(root / "scripts/edgar_forecast_bench.py")
    model_stats = collections.defaultdict(lambda: {"bundles": 0, "targets": 0, "points": 0.0,
        "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        "latency_seconds": 0.0})
    for item in instances:
        bundle = root / item["staged_bundle_path"]
        company = bundle.parents[1]
        for filename in ["forecast_benchmark_doc.md", "forecast_benchmark_qa.json", "forecast_targets.json", "bundle_manifest.json"]:
            if not (bundle / filename).is_file():
                errors.append({"cik": item["cik"], "missing": filename})
        qa = read_json(bundle / "forecast_benchmark_qa.json")
        targets = qa["targets"]
        if len(targets) != 5 or len({t["target_id"] for t in targets}) != 5:
            errors.append({"cik": item["cik"], "error": "invalid_targets"})
        bm = read_json(bundle / "bundle_manifest.json")
        date = dt.datetime.strptime(bm["target_date_filed"].replace("-", ""), "%Y%m%d").date()
        cutoff = min(dt.date(2026, 2, 1), date - dt.timedelta(days=1))
        rows = [json.loads(line) for line in (company / "filing_list.jsonl").read_text().splitlines() if line]
        if len({r["accession"] for r in rows}) != len(rows):
            errors.append({"cik": item["cik"], "error": "duplicate_accessions"})
        for row in rows:
            path = root / remap(row["source_path"])
            if not path.is_file() or not path.stat().st_size:
                errors.append({"cik": item["cik"], "missing_filing": row["accession"]})
            if row["accession"] == item["target_accession"] or dt.date.fromisoformat(row["date_filed"]) > cutoff:
                errors.append({"cik": item["cik"], "error": "target_or_post_cutoff", "accession": row["accession"]})
        bundles.append({"cik": item["cik"], "targets": len(targets), "target_date": date.isoformat(),
            "cutoff": cutoff.isoformat(), "filings": len(rows),
            "original_path_works": (root / bm["visible_filings_dir"]).is_dir(),
            "stage_stats_present": (bundle / "sandbox_stage_stats.json").is_file()})
        for pred in sorted(bundle.rglob("*_predictions.json")):
            model = str(pred.relative_to(bundle)).removeprefix("forecast_benchmark_doc_").removesuffix("_predictions.json")
            saved = read_json(pred.with_name(pred.name.replace("_predictions.json", "_score.json")))
            actual = score(predictions_payload=read_json(pred), benchmark_qa_payload=qa)
            same = actual["score_out_of_5"] == saved["score_out_of_5"]
            per_target_same = [(r["target_id"], r["points_awarded"]) for r in actual["per_target"]] == [(r["target_id"], r["points_awarded"]) for r in saved["per_target"]]
            if not same or not per_target_same:
                errors.append({"cik": item["cik"], "model": model, "error": "score_replay_mismatch"})
            replay.append({"cik": item["cik"], "model": model, "points": actual["score_out_of_5"],
                "points_match": same, "target_points_match": per_target_same, "full_payload_match": actual == saved})
            stat = model_stats[model]
            stat["bundles"] += 1
            stat["targets"] += len(targets)
            stat["points"] += actual["score_out_of_5"]
            usage = read_json(pred.with_name(pred.name.replace("_predictions.json", "_usage.json")))
            for key in ["input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"]:
                stat[key] += int(usage.get("token_usage_total", {}).get(key, 0))
            stat["latency_seconds"] += float(usage.get("eval_latency_seconds", 0))
    for stat in model_stats.values():
        stat["score_percent"] = 100 * stat["points"] / stat["targets"]
    dummy = {"targets": [{"target_id": "T001", "ground_truth_numeric": 100, "ground_truth_surface": "100",
        "unit_hint": "USD", "scoring": {"mode": "relative", "full_tolerance": .05, "half_tolerance": .10}}]}
    exploit = score(predictions_payload={"predictions": [{"target_id": "T001", "predicted_value": "0 or 100"}]}, benchmark_qa_payload=dummy)
    return {"revision": REVISION, "files_expected": len(metadata["siblings"]), "files_verified": len(inventory),
        "verified_bytes": sum(f["bytes"] for f in inventory), "instances": len(instances),
        "unique_companies": len({b["cik"] for b in bundles}), "targets": sum(b["targets"] for b in bundles),
        "visible_filing_rows": sum(b["filings"] for b in bundles),
        "visible_markdown_files": len(list(root.glob("runs/*/companies/*/filings/*.md"))),
        "scorer_sha256": source_hash, "model_scores": dict(model_stats), "score_replays": len(replay),
        "full_score_payload_matches": sum(r["full_payload_match"] for r in replay),
        "original_paths_work": sum(b["original_path_works"] for b in bundles),
        "missing_optional_stage_stats": sum(not b["stage_stats_present"] for b in bundles),
        "missing_codex_backend": not (root / "scripts/edgar_bench_codex.py").exists(),
        "synthetic_multiple_numeric_prediction_points": exploit["score_out_of_5"],
        "errors": errors, "bundles": bundles, "replays": replay, "file_inventory": inventory}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.dataset, read_json(args.metadata))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"bundles", "replays", "file_inventory"}}, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
