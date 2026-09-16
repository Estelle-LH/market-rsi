"""Build owned completion records from completed jobs and independent Dev math.

No scoring-ready market data exists yet. The live path calls the still-closed
independent admission gate. Offline tests exercise fabricated component receipts,
never actual market results. This producer handles completed development jobs;
failed/incomplete provider jobs require a separate failure producer.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import development_harbor
from inspection_stream import permitted_artifact
from market_rsi import digest, file_hash
from market_scoring import numeric_metrics
from prediction_stream import finite
from sandbox_receipts import read_sandbox_receipts, sandbox_usage
from trial_inputs import prepare_development_trial
from worker_receipts import Receipts, read_research_job


def dev_metrics(train, dev, predictions, contract):
    """Runner math on the full common Dev mask; no candidate-supplied score.

    Baseline rule must be explicitly frozen in the original public task before
    researcher dispatch. Neither baseline is selected here by observed errors.
    This is not evidence that a cloud baseline trial has run or source admission.
    """
    target_name = contract.get("target")
    baseline_rule = contract.get("baseline_rule")
    if (contract.get("primary_metric") != "mse" or target_name not in {
            "future_midpoint", "mid_change", "buy_yes_gross_price_change",
            "buy_no_gross_price_change"}
            or baseline_rule not in {"persistence", "zero", "train_mean"}
            or (baseline_rule == "persistence" and target_name != "future_midpoint")):
        raise ValueError("explicit original numeric target and baseline rule required")
    if not train or not dev or set(predictions) != {r["row_id"] for r in dev}:
        raise ValueError("complete nonempty paired Dev mask required")
    train_targets = [finite(r["target"]) for r in train]
    target = [finite(r["target"]) for r in dev]
    predicted = [finite(predictions[r["row_id"]]) for r in dev]
    if baseline_rule == "persistence":
        baseline = [finite(r["features"].get("mid")) for r in dev]
    else:
        value = 0.0 if baseline_rule == "zero" else math.fsum(train_targets) / len(train_targets)
        baseline = [value] * len(dev)

    def paired(indices):
        candidate = numeric_metrics([predicted[i] for i in indices], [target[i] for i in indices])
        common = numeric_metrics([baseline[i] for i in indices], [target[i] for i in indices])
        return {"candidate": candidate, "baseline": common,
                "candidate_minus_baseline_mse": candidate["mse"] - common["mse"]}

    groups = {"day": {}, "game": {}}
    for i, row in enumerate(dev):
        day = datetime.fromtimestamp(row["decision_ms"] / 1000, timezone.utc).date().isoformat()
        groups["day"].setdefault(day, []).append(i)
        groups["game"].setdefault(row["game_id"], []).append(i)
    return {"primary_metric": "mse", "target": contract["target"], "baseline_rule": contract["baseline_rule"],
            "aggregate": paired(list(range(len(dev)))),
            "by_day": {k: paired(v) for k, v in sorted(groups["day"].items())},
            "by_game": {k: paired(v) for k, v in sorted(groups["game"].items())},
            "rows": [{"row_id": r["row_id"], "prediction": predicted[i], "target": target[i],
                      "baseline_prediction": baseline[i]} for i, r in enumerate(dev)],
            "uncertainty": None, "promotion": False, "source_admission": False,
            "net_pnl": None, "net_pnl_status": "requires separate frozen execution/fee/censoring contract"}


def build_completion(study, development_directory, **trial_arguments):
    """Read an active study claim; no caller-selected replacement request/score.

    Returned read sets must be revalidated immediately before study.complete().
    Full available own Train/Dev traces are retained; later context overflow must
    fail its declared bound, never silently summarize/truncate the Archive arm.
    """
    active = study.snapshot()["active"]
    if active is None or "prepared_research" in trial_arguments:
        raise ValueError("one actual active study claim required; no replacement request")
    prepared = active["prepared"]
    if type(trial_arguments.get("expected_live")) is not bool:
        raise ValueError("explicit expected worker identity required")
    if trial_arguments["expected_live"]:
        development_harbor.require_admission(development_directory)
    elif not prepared["audit"]["experiment_id"].startswith("fixture-"):
        raise ValueError("synthetic completion cannot be assigned to a real study")
    bundle = prepare_development_trial(prepared_research=prepared, **trial_arguments)
    root, reads = Path(development_directory).absolute(), Receipts()
    if (root / "failure.json").exists():
        raise ValueError("failed development jobs need failure accounting, not a success record")
    reads.absent(root / "failure.json")
    claim, packet, runtime, _ = development_harbor.verify_job(root)
    binding = reads.read(root / "binding.json")
    if binding != bundle["binding"] or packet != bundle["packet"] or runtime != bundle["runtime"]:
        raise ValueError("completed development job differs from this active step")
    results = development_harbor.verify_outputs(root)  # Recompute, do not read its assessment flag.
    budget = trial_arguments["budget"]
    job = read_sandbox_receipts(root, reads, claim, budget, prepared["audit"]["phase"],
                                expected_live=trial_arguments["expected_live"])
    task = json.loads(prepared["messages"][1]["content"])["task"]
    catalog = {x["artifact_id"]: x for x in task["data_catalog"]}
    train = permitted_artifact(trial_arguments["train_bytes"], catalog[trial_arguments["train_id"]], task,
                               runtime["feature_names"])["rows"]
    dev = permitted_artifact(trial_arguments["dev_bytes"], catalog[trial_arguments["dev_id"]], task,
                             runtime["feature_names"])["rows"]
    research = read_research_job(trial_arguments["research_directory"], prepared, budget,
                                 expected_live=trial_arguments["expected_live"])
    coder_directory = Path(trial_arguments["coding_directory"])
    coding = reads.read(coder_directory / "response.json")
    coder_usage = reads.read(coder_directory / "subscription-usage.json")
    protocol = reads.read(root / "collected/protocol.json")
    # Preserve complete available protocol and own permitted inputs, not a host
    # interpretation of success. Root evaluator traceback, keys, cross-arm data
    # and Test are excluded. Candidate stderr is separately marked untrusted.
    trace = {"research_response": research["raw_response"], "coding_events": coding["events"],
             "coding_notes": coding["body"]["notes"], "train": train, "dev": dev,
             "data_evidence": {
                 "train_artifact_id": trial_arguments["train_id"],
                 "train_sha256": catalog[trial_arguments["train_id"]]["sha256"],
                 "train_rows": len(train),
                 "dev_artifact_id": trial_arguments["dev_id"],
                 "dev_sha256": catalog[trial_arguments["dev_id"]]["sha256"],
                 "dev_rows": len(dev),
                 "feature_names": runtime["feature_names"],
             },
             "protocol": protocol, "candidate_stderr": results["candidate_stderr"]}
    feedback = {"execution_verified": True, "available_trace": trace,
                "inspection": results["diagnostic"], "numeric": None, "scientific_admission": False}
    eligible = claim["mode"] == "fit_predict"
    if eligible:
        feedback["numeric"] = dev_metrics(train, dev, results["predictions"], task["evaluation_contract"])
    outputs = development_harbor.OUTPUTS + (development_harbor.PREDICTIONS if eligible else ())
    for name in outputs:
        if name != "failure.json":
            if not name.endswith(".json"):
                # Retain bytes hash without treating a journal as one JSON object.
                from worker_receipts import read_regular
                raw = read_regular(root / "collected" / name)
                reads.files[str(root / "collected" / name)] = hashlib.sha256(raw).hexdigest()
            else:
                reads.read(root / "collected" / name)
    for name in ("claim.json", "packet.json", "declared-runtime.json", "sources.json", "command.json", "libraries.json", "collection.json"):
        reads.read(root / name)
    reads.absent(root / "collected/failure.json")
    usage = {"research_token_metered_estimate_usd": research["metered_usd"], "coding": coder_usage,
        "sandbox": sandbox_usage(job),
        "note": "Reservations are not spend; unknown invoice/subscription allocation is not zero."}
    evidence = {"research_receipts": research["receipts"].commitment()["sha256"],
                "coding_receipts": bundle["coding_receipts"].commitment()["sha256"],
                "development_receipts": reads.commitment()["sha256"], "execution_binding": digest(binding),
                "completion_producer_source": file_hash(__file__),
                "sandbox_receipt_source": file_hash(Path(__file__).with_name("sandbox_receipts.py"))}
    completed = {"trial_id": active["trial_id"], "research_packet_sha256": prepared["packet_sha256"],
        "raw_research_response": research["raw_response"], "eligible_submission": eligible,
        "evidence_commitments": evidence, "payload": {"proposal": research["proposal"],
            "candidate_code": bundle["candidate_source"], "train_dev_results": {"dev": feedback},
            "usage": usage, "failure": None}}
    read_sets = [reads, research["receipts"], bundle["research_receipts"], bundle["coding_receipts"]]
    for read_set in read_sets:
        read_set.revalidate()
    return {"completion": completed, "read_sets": read_sets, "scientific_admission": False}


def commit_completion(study, built):
    for read_set in built["read_sets"]:
        read_set.revalidate()
    # StudyState independently checks the exact active packet and duplicate ID.
    study.complete(copy.deepcopy(built["completion"]))
