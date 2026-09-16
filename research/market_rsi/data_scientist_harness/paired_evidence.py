"""Predeclared paired evidence for one-shot grouped evaluation.

Detailed unit losses remain runner-private.  The controller receives aggregate
paired evidence without game identities, so it can learn whether an idea was
stable without turning a viewed Dev game into a new hand-tuned training case.
"""
from __future__ import annotations

import math
import random
import statistics

from market_rsi import digest


SPEC_FIELDS = {
    "kind", "unit", "block", "loss", "delta", "reward_direction",
    "persist_unit_records_runner_private", "public_visibility",
    "bootstrap_draws", "bootstrap_seed", "top_k_units",
}


def validate_paired_evidence_spec(spec: dict) -> None:
    if not isinstance(spec, dict) or set(spec) != SPEC_FIELDS:
        raise ValueError("exact paired-evidence output schema required")
    if spec["kind"] != "paired_grouped_loss_v1":
        raise ValueError("paired evidence kind required")
    for key in ("unit", "block", "loss", "delta"):
        if not isinstance(spec[key], str) or not spec[key]:
            raise ValueError("paired-evidence unit, block, loss and delta names are required")
    if spec["delta"] != "candidate_minus_baseline":
        raise ValueError(
            "paired loss uses the canonical candidate_minus_baseline delta; "
            "negative means the candidate has lower loss"
        )
    if spec["reward_direction"] != "minimize":
        raise ValueError("paired loss difference must be minimized")
    if spec["persist_unit_records_runner_private"] is not True:
        raise ValueError("runner-private paired unit records are required")
    if spec["public_visibility"] != "aggregate_only":
        raise ValueError("Dev unit identities cannot be controller-visible")
    if (type(spec["bootstrap_draws"]) is not int or spec["bootstrap_draws"] < 1000
            or type(spec["bootstrap_seed"]) is not int):
        raise ValueError("fixed paired block-bootstrap draws and seed required")
    if spec["top_k_units"] != [1, 5]:
        raise ValueError("paired concentration must report top-1 and top-5 shares")


def _finite_loss(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite nonnegative loss")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite nonnegative loss")
    return value


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_paired_evidence(records: list[dict], spec: dict) -> tuple[dict, dict]:
    """Return runner-private unit evidence and an identity-free public summary."""
    validate_paired_evidence_spec(spec)
    if not isinstance(records, list) or len(records) < 2:
        raise ValueError("at least two paired evaluation units required")
    expected = {"unit_id", "block_id", "rows", "baseline_loss", "candidate_loss"}
    units = []
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != expected:
            raise ValueError("exact paired unit record required")
        unit = record["unit_id"]
        block = record["block_id"]
        if (not isinstance(unit, str) or not unit or unit in seen
                or not isinstance(block, str) or not block):
            raise ValueError("paired units need unique ids and nonempty blocks")
        if type(record["rows"]) is not int or record["rows"] <= 0:
            raise ValueError("paired unit row count must be positive")
        seen.add(unit)
        baseline = _finite_loss(record["baseline_loss"], "baseline_loss")
        candidate = _finite_loss(record["candidate_loss"], "candidate_loss")
        units.append({
            "unit_id": unit,
            "block_id": block,
            "rows": record["rows"],
            "baseline_loss": baseline,
            "candidate_loss": candidate,
            "candidate_minus_baseline_loss": candidate - baseline,
        })
    units.sort(key=lambda row: row["unit_id"])
    deltas = [row["candidate_minus_baseline_loss"] for row in units]
    blocks: dict[str, list[float]] = {}
    for row in units:
        blocks.setdefault(row["block_id"], []).append(row["candidate_minus_baseline_loss"])
    if len(blocks) < 2:
        raise ValueError("paired evidence requires at least two time blocks")
    block_means = [statistics.fmean(blocks[key]) for key in sorted(blocks)]
    rng = random.Random(spec["bootstrap_seed"])
    draws = [statistics.fmean(rng.choices(block_means, k=len(block_means)))
             for _ in range(spec["bootstrap_draws"])]
    absolute = sorted((abs(value) for value in deltas), reverse=True)
    absolute_total = sum(absolute)
    top_share = lambda count: (sum(absolute[:count]) / absolute_total if absolute_total else 0.0)
    leave_one_out = [statistics.fmean(deltas[:index] + deltas[index + 1:])
                     for index in range(len(deltas))]
    private = {
        "schema": "runner_private_paired_evidence_v1",
        "spec_sha256": digest(spec),
        "units": units,
    }
    public = {
        "schema": "aggregate_paired_evidence_v1",
        "spec_sha256": digest(spec),
        "private_evidence_sha256": digest(private),
        "unit_count": len(units),
        "block_count": len(blocks),
        "rows": sum(row["rows"] for row in units),
        "equal_unit_baseline_loss": statistics.fmean(row["baseline_loss"] for row in units),
        "equal_unit_candidate_loss": statistics.fmean(row["candidate_loss"] for row in units),
        "equal_unit_mean_delta": statistics.fmean(deltas),
        "median_unit_delta": statistics.median(deltas),
        "candidate_better_unit_fraction": statistics.fmean(value < 0 for value in deltas),
        "candidate_better_block_fraction": statistics.fmean(value < 0 for value in block_means),
        "top_1_absolute_delta_share": top_share(1),
        "top_5_absolute_delta_share": top_share(5),
        "leave_one_unit_out_mean_delta": {
            "min": min(leave_one_out),
            "max": max(leave_one_out),
        },
        "equal_block_bootstrap_interval": {
            "lower": _quantile(draws, 0.025),
            "upper": _quantile(draws, 0.975),
            "draws": spec["bootstrap_draws"],
            "seed": spec["bootstrap_seed"],
        },
        "unit_ids_exposed": False,
    }
    return private, public
