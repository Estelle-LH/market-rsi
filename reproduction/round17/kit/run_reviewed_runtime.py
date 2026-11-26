#!/usr/bin/env python3
"""Preflight and optionally execute one exact reviewed runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


HERE = Path(__file__).resolve().parent
KNOWN_CLOSED_RUN_IDS = {
    "edgar-population-20261016-242",
    "edgar-population-20261016-243",
    "edgar-population-20261016-244",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(source, python, runtime, preflight):
    cmd = [str(python), "-B", "tools/earnings_population_run.py", "--runtime", str(runtime)]
    if preflight:
        cmd.append("--preflight-only")
    env = dict(os.environ)
    env["PYTHONPATH"] = ":".join(str(source / part) for part in ("tools", "tests", "research/market_rsi"))
    return subprocess.run(cmd, cwd=source, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--python-bin", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-source-commit", default="217b13e28cceaba628a5fe057f6860b56ecbd978")
    parser.add_argument("--local-manifest", type=Path,
                        help="Required for paid execution; verified with zero pending requests")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-fees", action="store_true")
    args = parser.parse_args()

    source, python, runtime = (x.resolve() for x in (args.source_root, args.python_bin, args.runtime))
    if not all(x.is_absolute() for x in (source, python, runtime)):
        raise ValueError("Absolute paths required")
    if sha256(runtime) != args.expected_runtime_sha256:
        raise ValueError("Runtime hash mismatch")
    payload = json.loads(runtime.read_text())
    run_id = payload.get("id", "")
    if not re.fullmatch(r"edgar-population-20261016-[0-9]+", run_id):
        raise ValueError("Fresh canonical run ID required")
    if run_id in KNOWN_CLOSED_RUN_IDS:
        raise ValueError("Historical reproduction IDs are closed and cannot be relaunched")
    if payload.get("source_commit") != args.expected_source_commit or payload.get("review") is None:
        raise ValueError("Reviewed runtime/source binding required")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, check=True,
                          capture_output=True, text=True).stdout.strip()
    if head != args.expected_source_commit:
        raise ValueError("Source checkout mismatch")
    if command(source, python, runtime, True).returncode != 0:
        raise SystemExit("Preflight failed; live execution not started")
    if sha256(runtime) != args.expected_runtime_sha256:
        raise ValueError("Runtime changed during preflight")
    if not args.execute:
        print(json.dumps({"preflight": "PASS", "executed": False}, sort_keys=True))
        return
    if not args.acknowledge_fees:
        parser.error("--execute requires --acknowledge-fees")
    if args.local_manifest is None:
        parser.error("--execute requires --local-manifest")
    manifest_check = subprocess.run(
        [str(python), str(HERE / "verify_local_manifest.py"),
         str(args.local_manifest.resolve()), "--require-idle"]
    )
    if manifest_check.returncode != 0:
        raise SystemExit("Local manifest/ledger verification failed; live execution not started")
    if sha256(runtime) != args.expected_runtime_sha256:
        raise ValueError("Runtime changed after local verification")
    code = command(source, python, runtime, False).returncode
    print(json.dumps({"preflight": "PASS", "executed": True, "owner_exit": code}, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
