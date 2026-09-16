"""Carry existing source-specific file coverage forward, not only allowed dates.

Reuses the completed metadata-only inventory; no remote access or raw row read.
Counts mean files observed then, not complete capture or present-day availability.
"""
from collections import Counter
from pathlib import Path
import re
from market_rsi import file_hash, load_json

ROOT=Path(__file__).resolve().parents[1]
INVENTORY=ROOT/"artifacts/capture-raw-inventory-20260911-01/report.json"
SHA="eff3f1a9ff2019874ffc92a6762075073890d25e4cbd1c095d7ae88b8ed2b89d"


def summarize(value, allowed_dates):
    if (value.get("schema")!="capture_raw_file_inventory_v1" or value.get("host")!="173.255.231.4"
            or value.get("source_root")!="/opt/d10/raw/data/polymarket"
            or value.get("source_admitted") is not False or value.get("complete_content_verified") is not False
            or value.get("raw_rows_read")!=0):
        raise ValueError("exact metadata-only D10 inventory required")
    days=value["days"]; files=value["files"]
    observed=[d["date"] for d in days]
    if observed!=sorted(set(observed)) or set(observed)!=set(allowed_dates):
        raise ValueError("inventory and opened planning scope differ")
    counts=Counter(); sizes=Counter(); names=set()
    for f in files:
        if f["date"] not in observed or type(f["compressed_bytes"]) is not int or f["compressed_bytes"]<=0:
            raise ValueError("invalid scoped file descriptor")
        pattern="polymarket-"+f["date"].replace("-","")+r"T([01][0-9]|2[0-3])\.jsonl\.zst"
        if not re.fullmatch(pattern,f["filename"]) or f["filename"] in names:
            raise ValueError("invalid or repeated hourly filename")
        names.add(f["filename"]);counts[f["date"]]+=1;sizes[f["date"]]+=f["compressed_bytes"]
    for d in days:
        if (type(d["files_present"]) is not int or type(d["compressed_bytes"]) is not int
                or d["files_present"]!=counts[d["date"]] or d["compressed_bytes"]!=sizes[d["date"]]):
            raise ValueError("inventory summary and file descriptors disagree")
    return {"days":days,"files_observed":len(files),"compressed_bytes_observed":sum(sizes.values()),
        "no_files_observed_dates":[d["date"] for d in days if d["files_present"]==0],
        "less_than24_hour_files_dates":[d["date"] for d in days if d["files_present"]<24],
        "raw_rows_read":0,"source_admitted":False,"complete_sessions_proven":False,
        "meaning":"Previously recorded file-name/byte inventory only. 24 files do not prove a complete day. "
            "Zero files in this directory is not proof of exchange outage, and does not prove no other archive exists. "
            "Do not invent missing dates or silently change your selected split; any acquisition is a separate authorized action. "
            "Choose your plan using this evidence and account for missingness. Selected objects still require current immutable manifests and content/clock checks."}


def finding(context):
    if context["source_id"]!="d10_polymarket_raw" or file_hash(INVENTORY)!=SHA:
        raise ValueError("source inventory changed or belongs to another source")
    return {"id":"existing-d10-file-coverage-not-just-date-permissions",
        "evidence_ref":{"path":str(INVENTORY),"sha256":SHA},
        "inventory":summarize(load_json(INVENTORY),context["opened_diagnostic_dates"]),
        "handoff_correction":"Earlier source-study inputs omitted this per-day inventory. That is a runner context omission, "
            "not evidence the controller knowingly ignored missing files. The old workspace remains unchanged."}
