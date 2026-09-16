"""Integrity and denominator audit; descriptive breadth, never source admission."""
import argparse
from collections import Counter
from pathlib import Path
import statistics
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, file_hash, fresh_json, load_json
from run_population_quote_profile import mode_spec, validate_terminal


def ratio(numerator, denominator):
    return numerator/denominator if denominator else None


def describe(profile):
    entities = profile["entities"]; totals = profile["totals"]["counts"]
    total_quotes = totals.get("quote_observations", 0)
    sorted_counts = sorted((e["counts"].get("quote_observations", 0) for e in entities), reverse=True)
    eligible = [e for e in entities if e["counts"].get("adjacent_valid_mid_pairs", 0) > 0]
    fractions = [e["counts"].get("equal_mid_pairs", 0)/e["counts"]["adjacent_valid_mid_pairs"] for e in eligible]
    # No future-label activity exclusion; zero-observation entities remain counted.
    return {"scope": "descriptive event-stream observations, not fixed-horizon labels or OOS results",
        "observed_entities": len(entities), "observed_market_ids": profile["breadth"]["observed_market_ids"],
        "quote_observations": total_quotes,
        "source_status_counts": profile["totals"]["source_status"],
        "unanchored_delta_fraction": ratio(totals.get("unanchored_delta_observations", 0), totals.get("delta_observations", 0)),
        "source_depth_mismatch_fraction_of_comparable": ratio(totals.get("bbo_mismatch", 0), totals.get("bbo_comparable", 0)),
        "equal_mid_fraction_event_weighted": ratio(totals.get("equal_mid_pairs", 0), totals.get("adjacent_valid_mid_pairs", 0)),
        "equal_mid_fraction_equal_entity_weighted": statistics.mean(fractions) if fractions else None,
        "equal_mid_fraction_entity_median": statistics.median(fractions) if fractions else None,
        "entities_with_valid_pair_denominator": len(eligible),
        "entities_without_valid_pairs": len(entities)-len(eligible),
        "zero_ms_fraction_of_valid_pairs": ratio(totals.get("pair_gap_0ms", 0), totals.get("adjacent_valid_mid_pairs", 0)),
        "top_one_entity_quote_share": ratio(sum(sorted_counts[:1]), total_quotes),
        "top_ten_entity_quote_share": ratio(sum(sorted_counts[:10]), total_quotes),
        "breadth": profile["breadth"], "candidate_minute_histogram": profile["candidate_minute_histogram"],
        "source_admitted": False, "predictive_improvement_proven": False,
        "outage_classified": False, "source_clock_attested": False,
        "warning": "Repeated depth updates can repeat unchanged BBO. Equal adjacent observations, including gaps, do not prove a continuously flat path; "
            "this is not the no-change fraction of a future target. Entity counts are not independent samples."}


def verify_population_sums(profile):
    fields = ("counts", "source_status", "depth_status", "depth_to_source_status", "issues", "snapshots")
    for key in fields:
        summed = Counter()
        for entity in profile["entities"]: summed.update(entity[key])
        if dict(summed) != profile["totals"][key]:
            raise ValueError("per-entity population sums differ: "+key)
    totals = profile["totals"]["counts"]
    if totals.get("equal_mid_pairs", 0)+totals.get("changed_mid_pairs", 0) != totals.get("adjacent_valid_mid_pairs", 0):
        raise ValueError("mid-change denominator mismatch")
    if sum(v for k, v in totals.items() if k.startswith("pair_gap_")) != totals.get("adjacent_valid_mid_pairs", 0):
        raise ValueError("gap denominator mismatch")


def audit(root):
    report = load_json(root/"report.json"); claim = load_json(root/"claim.json")
    if report.get("result_sha256") != digest({k: v for k, v in report.items() if k != "result_sha256"}):
        raise ValueError("report changed")
    if report.get("claim_sha256") != file_hash(root/"claim.json") or report.get("publication") != claim.get("publication"):
        raise ValueError("claim/publication mismatch")
    if report.get("adapter_sha256") != claim["publication"]["sources"]["quote_source/reconstruct.py"]:
        raise ValueError("adapter commitment mismatch")
    if report.get("ssh_reaped") is not True or report.get("exit_code") != 0:
        raise ValueError("transport not terminal")
    spec = mode_spec(report["mode"])
    if any(claim.get(k) != v for k, v in spec.items()): raise ValueError("scope mismatch")
    validate_terminal(report, spec); verify_population_sums(report["profile"])
    paths = sorted(root.glob("progress-*.json"))
    if [p.name for p in paths] != [f"progress-{i:03d}.json" for i in range(len(paths))]:
        raise ValueError("missing progress packet")
    packets = [load_json(p) for p in paths]
    stripped = {k: v for k, v in report.items() if k not in ("result_sha256", "publication", "claim_sha256", "ssh_reaped", "exit_code")}
    if [p["report"] for p in packets if p.get("stage") == "complete"] != [stripped]:
        raise ValueError("terminal packet differs")
    checkpoints = [p for p in packets if p.get("stage") == "checkpoint"]
    if report["mode"] == "hour" and [p["scanned"] for p in checkpoints] != list(range(500000, 4000001, 500000)):
        raise ValueError("missing expected durable checkpoints")
    for p in checkpoints:
        if p.get("partial_not_terminal") is not True or p["profile"]["input_counts"]["raw_records"] != p["scanned"]:
            raise ValueError("checkpoint accounting differs")
        if p["scanned"] % 1000000 == 0:
            verify_population_sums(p["profile"])
    result = {"schema": "population_quote_audit_v1", "report_sha256": file_hash(root/"report.json"),
        "claim_sha256": file_hash(root/"claim.json"), "publication": report["publication"],
        "integrity_passed": True, "mode": report["mode"], "elapsed_seconds": report["elapsed_seconds"],
        "peak_self_rss_kib_linux": report["peak_self_rss_kib_linux"],
        "progress_packets": len(packets), "durable_population_checkpoints": sum("entities" in p["profile"] for p in checkpoints),
        "summary": describe(report["profile"]), "fits": 0, "new_tinker_cost_usd": 0,
        "new_test_opened": False, "source_admitted": False}
    result["result_sha256"] = digest(result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); result = audit(a.run.resolve())
    a.output.parent.mkdir(parents=True, exist_ok=True); fresh_json(a.output, result)
    print({"output": str(a.output), "integrity_passed": True, "summary": result["summary"]})
