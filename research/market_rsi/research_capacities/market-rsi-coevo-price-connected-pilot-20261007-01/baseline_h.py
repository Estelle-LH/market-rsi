"""Supervisor bootstrap: supplied process evidence, not a learned tool."""


def apply(context):
    return {
        "role": "harness",
        "process_feedback": context.get("history", {}).get("process_feedback"),
        "scope": "Supplied evidence only; no scorer, permission or pool mutation",
        "capacity_gain_claimed": False,
    }
