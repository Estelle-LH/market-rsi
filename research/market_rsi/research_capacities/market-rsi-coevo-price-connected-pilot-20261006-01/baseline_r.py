"""Supervisor bootstrap: direct factual feedback, no autonomous lesson yet."""


def apply(context):
    return {
        "role": "researcher",
        "last_experiment": context.get("history", {}).get("last_experiment"),
        "stopped_exact_recipes": context.get("memory", {}).get("stopped_exact_recipes"),
        "prediction_decision": context.get("feedback", {}).get("decision"),
        "capacity_gain_claimed": False,
    }
