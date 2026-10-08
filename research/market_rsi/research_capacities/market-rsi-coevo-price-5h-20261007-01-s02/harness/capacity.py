"""Proposed pure delivery of supplied operational evidence; no action or gain."""


def apply(context):
    result = {
        "role": "harness",
        "process_feedback": context.get("history", {}).get("process_feedback"),
        "scope": "Supplied evidence only; no scorer, permission or pool mutation",
        "capacity_gain_claimed": False,
        "operational_failure_brief": None,
    }
    for section, key in (
        ("history", "last_operational_failure"),
        ("feedback", "last_operational_failure"),
        ("memory", "last_operational_failure"),
        ("history", "known_operational_failure"),
    ):
        record = context.get(section, {}).get(key)
        if record is not None:
            brief = {"context_origin": section + "." + key}
            for field in (
                "execution_outcome", "reason", "observation", "proposal",
                "attempts_entered", "fits_entered", "performance_evidence",
                "scientific_refutation", "next", "same_ID_retry",
            ):
                brief[field] = record.get(field)
            result["operational_failure_brief"] = brief
            break
    return result
