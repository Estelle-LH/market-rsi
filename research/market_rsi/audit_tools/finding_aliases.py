"""Workspace-local short finding IDs; preserve every original finding and hash.

A short display key is not a content commitment. The existing findings hash,
manifest, exact response count, and runner-owned verification remain mandatory.
"""
from market_rsi import digest


def alias_findings(findings):
    if not findings or len({f["id"] for f in findings}) != len(findings):
        raise ValueError("unique nonempty source findings required")
    result=[]
    for index, original in enumerate(findings,1):
        if "source_finding" in original or "source_finding_sha256" in original:
            raise ValueError("do not silently re-alias an existing alias")
        # Original payload remains byte-equivalent under canonical JSON in this
        # explicit nested field; no review/budget/history text is discarded.
        result.append({"id":f"f{index:03d}","source_finding":original,
            "source_finding_sha256":digest(original),
            "id_scope":"This short ID applies only to the current frozen findings list. Respond with this id, not the nested original id."})
    return result
