"""Real zero-provider canary for exact remote derived-cache cleanup."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.study_v3 import cleanup_remote_cache


RUN_ID = "memory-policy-v3-20990101-01"
SESSION = "2099-01-01T00"


def source_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = ("memory_policy/study_v3.py",
             "memory_policy/remote_cleanup_canary_v3.py")
    return {path: file_hash(root / path) for path in paths}


def run(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh remote cleanup canary ID required")
    output.mkdir()
    target = "/opt/d10/derived/" + RUN_ID + "/" + SESSION
    program = (
        "import json,pathlib,sys;"
        "target=pathlib.Path(sys.argv[1]);"
        "target.mkdir(parents=True,exist_ok=False);"
        "(target/'canary.bin').write_bytes(b'canary');"
        "print(json.dumps({'created':target.is_dir(),'bytes':6}))"
    )
    command = "python3 -c " + shlex.quote(program) + " " + shlex.quote(target)
    created = subprocess.run([
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "root@173.255.231.4", command,
    ], capture_output=True, text=True, timeout=60)
    try:
        creation_receipt = json.loads(created.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("remote cleanup canary creation failed") from error
    if created.returncode != 0 or creation_receipt != {"created": True, "bytes": 6}:
        raise RuntimeError("remote cleanup canary creation failed")
    fresh_json(output / "claim.json", {
        "schema": "memory_policy_remote_cleanup_canary_claim_v3",
        "source_hashes": source_hashes(),
        "target_sha256": digest(target),
        "provider_calls_allowed": 0,
        "raw_source_in_scope": False,
    })
    cleanup_remote_cache(Path(RUN_ID), SESSION, output)
    cleanup = load_json(output / "remote-cleanup.json")
    value = {
        "schema": "memory_policy_remote_cleanup_canary_v3",
        "passed": cleanup["complete"],
        "source_hashes": source_hashes(),
        "cleanup_sha256": file_hash(output / "remote-cleanup.json"),
        "provider_calls": 0,
        "raw_source_deleted": False,
    }
    value["result_sha256"] = digest(value)
    fresh_json(output / "canary.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.output)
    print({"passed": value["passed"], "provider_calls": 0,
           "raw_source_deleted": False})
