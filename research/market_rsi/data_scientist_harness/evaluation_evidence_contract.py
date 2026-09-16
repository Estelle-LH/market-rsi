"""Open research types with a frozen, type-specific evidence output."""
from __future__ import annotations

from data_scientist_harness.paired_evidence import validate_paired_evidence_spec


SCALAR_FIELDS = {
    "kind", "metric", "persist_terminal_record_runner_private", "public_visibility",
}


def validate_evaluation_evidence_output(spec: dict) -> None:
    if not isinstance(spec, dict):
        raise ValueError("evaluation evidence output must be an explicit object")
    if spec.get("kind") == "paired_grouped_loss_v1":
        validate_paired_evidence_spec(spec)
        return
    if spec.get("kind") == "scalar_terminal_v1":
        if set(spec) != SCALAR_FIELDS or not isinstance(spec["metric"], str) or not spec["metric"]:
            raise ValueError("exact scalar-terminal evidence schema required")
        if spec["persist_terminal_record_runner_private"] is not True:
            raise ValueError("runner-private terminal evidence is required")
        if spec["public_visibility"] != "aggregate_only":
            raise ValueError("terminal evidence must be aggregate-only")
        return
    raise ValueError("known evaluation evidence output kind required")

