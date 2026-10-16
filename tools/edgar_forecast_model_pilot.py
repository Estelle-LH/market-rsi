#!/usr/bin/env python3
"""Offline EDGAR pilot preparation and score replay; never calls a provider."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

from edgar_forecast_audit import REVISION, audit, load_scorer, read_json, remap

MATRIX = Path(__file__).resolve().parents[1] / "benchmarks/edgar_forecast/model_matrix.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_file(root, relative):
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts or "\\" in str(relative):
        raise ValueError("Unsafe relative path")
    root = root.resolve()
    path = root / value
    path.resolve().relative_to(root)
    if any(part.is_symlink() for part in [path, *path.parents] if part != root):
        raise ValueError("Symlinked input")
    if not path.is_file():
        raise ValueError("Missing input")
    return path


def eligible(rows, target, cutoff):
    accessions, names = set(), set()
    for row in rows:
        name = Path(row["relative_path"])
        if len(name.parts) != 2 or name.parts[0] != "filings" or name.suffix != ".md" or ".." in name.parts:
            raise ValueError("Unsafe filing name")
        if row["accession"] == target or dt.date.fromisoformat(row["date_filed"]) > cutoff:
            raise ValueError("Hidden target or post-cutoff filing")
        if row["accession"] in accessions or str(name) in names:
            raise ValueError("Duplicate filing")
        accessions.add(row["accession"])
        names.add(str(name))
    return rows


def select_instances(instances, count):
    ordered = sorted(instances, key=lambda item: item["cik"])
    if len({item["cik"] for item in ordered}) != len(ordered) or count != 3:
        raise ValueError("Pilot requires three unique companies in a unique universe")
    if len(ordered) < count:
        raise ValueError("Incomplete company universe")
    return ordered[:count]


def matrix_rows(matrix):
    models = matrix["models"]
    if len({m["id"] for m in models}) != len(models):
        raise ValueError("Duplicate models")
    if len(models) != 21 or sum(m["group"] == "paper" for m in models) != 4:
        raise ValueError("Unreviewed model matrix")
    for model in models:
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", model["id"]):
            raise ValueError("Unsafe model id")
        if model["provider"] not in {"openai", "anthropic", "google"}:
            raise ValueError("Unknown provider")
        if model["group"] not in {"paper", "later"}:
            raise ValueError("Unknown model group")
        if model.get("release_date") and model["group"] == "later":
            if not matrix["paper_v1"] < model["release_date"] <= matrix["observed_date_new_york"]:
                raise ValueError("Not a post-paper model release")
    return models


def pending_scoreboard(models, targets):
    return [{"model": m["id"], "provider": m["provider"], "group": m["group"],
             "fresh_status": "NOT_RUN", "fresh_points": None, "fresh_score_percent": None,
             "planned_targets": targets, "attempted_companies": 0, "completed_companies": 0,
             "account_access": "NOT_VERIFIED", "inference_adapter": "NOT_IMPLEMENTED"}
            for m in models]


def strict_single_number(payload, target_ids):
    """Additional schema diagnostic, not a replacement for the paper scorer."""
    errors, seen = [], set()
    predictions = payload.get("predictions") if isinstance(payload, dict) else None
    if not isinstance(predictions, list):
        return ["predictions_not_list"]
    for item in predictions:
        if not isinstance(item, dict) or not isinstance(item.get("target_id"), str):
            errors.append("invalid_prediction")
            continue
        name = item["target_id"]
        if name not in target_ids or name in seen:
            errors.append("unknown_or_duplicate_target")
        seen.add(name)
        value = item.get("predicted_value")
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        if isinstance(value, str):
            valid = bool(re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value))
        if not valid or not math.isfinite(float(value)):
            errors.append("not_single_finite_number")
    if seen != set(target_ids):
        errors.append("missing_target")
    return errors


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def stage_file(source, destination, expected_hash):
    data = source.read_bytes()
    if digest(data) != expected_hash:
        raise ValueError("Input changed since package audit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(data)
    return {"path": str(destination), "bytes": len(data), "sha256": digest(data)}


def prepare(dataset, metadata, output, source_commit):
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Full source commit required")
    models = matrix_rows(read_json(MATRIX))
    dataset = dataset.resolve()
    result = audit(dataset, read_json(metadata))
    if result["errors"] or (result["unique_companies"], result["targets"], result["full_score_payload_matches"]) != (50, 250, 200):
        raise ValueError("Package or published score audit failed")
    selected = select_instances(read_json(dataset / "benchmark_manifest.json")["instances"], 3)
    inventory = {f["path"]: f["sha256"] for f in result["file_inventory"]}
    score, scorer_hash = load_scorer(dataset / "scripts/edgar_forecast_bench.py")
    plan = {"dataset_revision": REVISION, "source_commit": source_commit,
            "source_sha256": digest(Path(__file__).read_bytes()), "scorer_sha256": scorer_hash,
            "model_matrix_sha256": digest(MATRIX.read_bytes()), "api_calls": 0, "api_spend_usd": 0,
            "status": "OFFLINE_PREPARED_NO_INFERENCE", "selection": "first_three_original_CIKs",
            "target_count": 15, "total_pilot_cap_usd": 200, "companies": [],
            "fresh_scoreboard": pending_scoreboard(models, 15), "published_replay": []}
    output = output.resolve()
    if output == dataset or dataset in output.parents:
        raise ValueError("Output must be outside original data")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "package-audit.json", result)
    for item in selected:
        bundle = safe_file(dataset, item["staged_bundle_path"] + "/bundle_manifest.json").parent
        bm = read_json(bundle / "bundle_manifest.json")
        cutoff = min(dt.date(2026, 2, 1), dt.datetime.strptime(bm["target_date_filed"], "%Y%m%d").date() - dt.timedelta(days=1))
        company = bundle.parents[1]
        rows = [json.loads(line) for line in (company / "filing_list.jsonl").read_text().splitlines() if line]
        eligible(rows, item["target_accession"], cutoff)
        staged = output / "visible" / item["cik"]
        prompt = bundle / "forecast_benchmark_doc.md"
        receipts = [stage_file(prompt, staged / "questions.md", inventory[str(prompt.relative_to(dataset))])]
        for row in rows:
            source_name = str(remap(row["source_path"]))
            source = safe_file(dataset, source_name)
            receipts.append(stage_file(source, staged / row["relative_path"], inventory[source_name]))
        index = "date_filed\tform_type\taccession\tpath\n" + "".join(
            "\t".join(row[k] for k in ["date_filed", "form_type", "accession", "relative_path"]) + "\n" for row in rows)
        index_path = staged / "filing_index.tsv"
        with index_path.open("x", encoding="utf-8") as handle:
            handle.write(index)
        receipts.append({"path": str(index_path), "bytes": len(index.encode()), "sha256": digest(index.encode())})
        for receipt in receipts:
            receipt["path"] = str(Path(receipt["path"]).relative_to(staged))
        plan["companies"].append({"cik": item["cik"], "company_name": item["company_name"],
                                  "cutoff": cutoff.isoformat(), "target_accession": item["target_accession"],
                                  "visible_root": str(staged), "filing_count": len(rows), "allowed_files": receipts})
        qa = read_json(bundle / "forecast_benchmark_qa.json")
        for model in models:
            if model["group"] != "paper":
                continue
            original = bundle / ("forecast_benchmark_doc_" + model["published_artifact"] + "_predictions.json")
            payload = read_json(original)
            scored = score(predictions_payload=payload, benchmark_qa_payload=qa)
            plan["published_replay"].append({"model": model["id"], "cik": item["cik"],
                "points": scored["score_out_of_5"], "targets": len(qa["targets"]),
                "strict_single_number_errors": strict_single_number(payload, [t["target_id"] for t in qa["targets"]]),
                "evidence_type": "PUBLISHED_OUTPUT_REPLAY_NOT_FRESH_INFERENCE"})
    for model in models:
        if model["group"] != "paper":
            continue
        points = sum(r["points"] for r in plan["published_replay"] if r["model"] == model["id"])
        plan["published_replay"].append({"model": model["id"], "cik": "PILOT_TOTAL",
                                       "points": points, "targets": 15, "score_percent": points / 15 * 100,
                                       "evidence_type": "PUBLISHED_OUTPUT_REPLAY_NOT_FRESH_INFERENCE"})
    write_json(output / "pilot-plan.json", plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    plan = prepare(args.dataset, args.metadata, args.output, args.source_commit)
    print(json.dumps({"status": plan["status"], "model_count": len(plan["fresh_scoreboard"]),
                     "companies": [c["cik"] for c in plan["companies"]], "targets": plan["target_count"],
                     "api_calls": 0, "api_spend_usd": 0, "plan_sha256": digest((args.output / "pilot-plan.json").read_bytes()),
                     "paper_pilot_replays": [r for r in plan["published_replay"] if r["cik"] == "PILOT_TOTAL"]}, indent=2))


if __name__ == "__main__":
    main()
