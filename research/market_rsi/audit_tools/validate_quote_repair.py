"""Validate one versioned quote adapter on the exact previously opened hour.

No raw rows/IDs leave Linode. No new data, source writes, fitting or provider call.
Ordinal/inner-message keys are taken from ORIGINAL messages, never filtered copies.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

HELPER_SHA = "97d9c13c5aa5d6f118b562f73a4ff3db2c93cffb3af18377199873fb9c4319f5"
WINDOW_SHA = "10e420f0fa1c429a573d16731052ee5fa3971577bc23a130b55e85e67b3cccaf"
CASE_T = 1787270630696
CASE_ORDINAL = 5311264
CASE_ROW_SHA = "f016a2ecde5dcf4811830ac436b7bcba95816f24c5b27a521ba2507461b3545c"
RAW_CASE_HASHES = {
    116007: "387e05f05d147553cf5ec427d249a01c0361ee79ce93a6d0fefffc47bdbddfd4",
    116008: "af00dd4f2bd1addc165bb82ac410cfdfc550eea812c7c9bb739a76f8f750c9d5",
    116009: "c4efa119b3561ecf1699275a355a5ef6fd91d561d3e3d6ff3c84bde9866d8e45",
}
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(records, engine, expected_cases=RAW_CASE_HASHES):
    counts = Counter(); statuses = Counter(); pairs = Counter(); issues = Counter()
    case = []; snapshot_matches = Counter(); stream_hash = hashlib.sha256(); prior_key = None
    for ordinal, record, record_hash in records:
        counts["target_raw_records"] += 1
        for row in engine.process(record, ordinal, record_hash):
            key = tuple(row["key"])
            if prior_key is not None and key <= prior_key:
                raise ValueError("adapter reordered or duplicated an observation")
            prior_key = key
            source, depth = row["source"], row["depth"]
            counts["observations"] += 1
            counts["price_candidates"] += int(row["price_candidate"])
            counts["source_bbo_observations"] += int(source["origin"] == "same_message_best_bid_ask")
            counts["snapshot_observations"] += int(source["origin"] == "complete_snapshot_levels")
            counts["candidates_with_depth_mismatch"] += int(row["price_candidate"] and depth["bbo_matches_source"] is False)
            counts["candidates_without_depth_anchor"] += int(row["price_candidate"] and depth["status"] == "unanchored")
            statuses[source["status"]] += 1
            pairs[depth["status"]+" -> "+source["status"]] += 1
            issues.update(row["issues"])
            if source["origin"] == "same_message_best_bid_ask" and any(source[k] is not None for k in ("bid_size", "ask_size")):
                raise ValueError("invented source quantity")
            if row["source_admitted"] or depth["executable_certified"] or row["clock_semantics_attested"]:
                raise ValueError("repair cannot certify admission or execution")
            equal = depth["full_map_equals_next_snapshot"]
            if source["origin"] == "complete_snapshot_levels":
                snapshot_matches["equal" if equal is True else "different" if equal is False else "no_prior_anchor"] += 1
            stream_hash.update((json.dumps(row, sort_keys=True, separators=(",", ":"))+"\n").encode())
            if ordinal in expected_cases:
                if record_hash != expected_cases[ordinal]:
                    raise ValueError("case changed")
                case.append({"key": row["key"], "record_sha256": record_hash,
                    "source_status": source["status"], "depth_status": depth["status"],
                    "depth_bbo_matches_source": depth["bbo_matches_source"],
                    "price_candidate": row["price_candidate"], "issues": row["issues"],
                    "source_size_present": source["bid_size"] is not None or source["ask_size"] is not None})
    case_pass = (len(case) == 3 and [c["key"][0] for c in case] == list(expected_cases)
        and [c["depth_status"] for c in case] == ["crossed", "locked", "uncrossed"]
        and all(c["source_status"] == "uncrossed" and c["price_candidate"] and not c["source_size_present"] for c in case))
    return {"counts": dict(counts), "source_status_counts": dict(statuses),
        "same_record_depth_to_source_status": dict(pairs), "issue_counts": dict(issues),
        "full_snapshot_comparisons": dict(snapshot_matches), "case": case,
        "known_cross_record_case_fixed": case_pass, "derived_stream_sha256": stream_hash.hexdigest(),
        "derived_rows_persisted": False,
        "comparison_scope": "same raw records, source-reported BBO vs snapshot-anchored local depth; not legacy CSV frequency"}


def remote():
    import resource
    f = FORENSIC
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    def progress(value):
        print(json.dumps(value, sort_keys=True), flush=True)
    target, locator = f["locate_csv"](f["CSV_PATH"])
    if target["ordinal"] != CASE_ORDINAL or f["digest"](target["row"]) != CASE_ROW_SHA:
        raise ValueError("fixed case changed")
    progress({"stage": "case_verified", "case_ordinal": target["ordinal"]})
    token, market = target["row"]["outcome"], target["row"]["market"]
    before = f["checked_file"](f["RAW_PATH"], f["RAW_HASH"])
    p = subprocess.Popen(["zstd", "-dc", "--", str(f["RAW_PATH"])], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    retained = []; raw_hash = hashlib.sha256(); n = 0; eof = False
    try:
        for n, line in enumerate(f["bounded_lines"](p.stdout, 8*1024**3), 1):
            if n > 12_000_000: raise ValueError("raw row bound")
            raw_hash.update(line); record = json.loads(line)
            if f["target_record"](record, token, market) is not None:
                if len(retained) >= 200_000: raise ValueError("retained row bound")
                retained.append((n, record, hashlib.sha256(line).hexdigest()))
            if n % 500_000 == 0:
                progress({"stage": "raw_progress", "scanned": n, "retained": len(retained)})
        eof = True
    finally:
        p.stdout.close()
        if not eof and p.poll() is None: p.terminate()
        try: code = p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill(); code = p.wait(timeout=5)
    if not eof or code: raise ValueError("full decoder did not complete")
    f["unchanged"](f["RAW_PATH"], before)
    if n != 4328805 or raw_hash.hexdigest() != "9dc75c1814796f226e55801cb0ecb662ad1727c05ae3de78f09b8a3ffef22c31":
        raise ValueError("previously frozen full hour differs")
    progress({"stage": "validating_adapter", "scanned": n, "retained": len(retained)})
    analysis = summarize(retained, ADAPTER["QuoteReconstructor"](token, market))
    result = {"schema": "quote_repair_validation_v1", "adapter_version": ADAPTER["VERSION"],
        "adapter_sha256": ADAPTER_SHA, "raw_sha256": f["RAW_HASH"], "raw_records": n,
        "decoded_sha256": raw_hash.hexdigest(), "csv_sha256": f["CSV_HASH"], "csv_case_sha256": CASE_ROW_SHA,
        "decoder_exit_code": code, "decoder_reaped": True, "analysis": analysis,
        "raw_frames_exported": 0, "identifiers_exported": 0, "fits": 0, "new_tinker_cost_usd": 0,
        "source_mutated": False, "source_admitted": False, "new_test_opened": False,
        "source_clock_attested": False, "coverage_admitted": False}
    progress({"stage": "complete", "report": result})


def local(output):
    sys.path.insert(0, str(ROOT))
    from market_rsi import digest, fresh_json
    helper = ROOT/"audit_tools/capture_cross_forensic.py"
    adapter = ROOT/"quote_source/reconstruct.py"
    parent = ROOT/"artifacts/capture-cross-window-20260911-01/report.json"
    if sha(helper) != HELPER_SHA or sha(parent) != WINDOW_SHA:
        raise ValueError("frozen forensic provenance changed")
    # Commit all validation and adapter source before touching real records.
    sources = [adapter, Path(__file__).resolve(), ROOT/"quote_source/test_reconstruct.py",
               ROOT/"audit_tools/test_validate_quote_repair.py"]
    repo = ROOT.parents[1]
    relative = [str(p.relative_to(repo)) for p in sources]
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], timeout=30).decode().strip()
    if git("status", "--porcelain", "--", *relative): raise ValueError("uncommitted repair source")
    commit = git("rev-parse", "HEAD")
    for path, name in zip(sources, relative):
        blob = subprocess.check_output(["git", "-C", str(repo), "show", commit+":"+name], timeout=30)
        if hashlib.sha256(blob).hexdigest() != sha(path):
            raise ValueError("committed repair bytes differ")
    origin = git("remote", "get-url", "origin")
    if origin != "https://github.com/Estelle-LH/RSIBench-Data.git": raise ValueError("wrong origin")
    tag = "pm-source-quotes-v0.1.0"
    if git("cat-file", "-t", "refs/tags/"+tag) != "tag": raise ValueError("annotated source tag required")
    if git("rev-parse", "refs/tags/"+tag+"^{commit}") != commit: raise ValueError("tag/HEAD differ")
    remote_refs = git("ls-remote", "origin", "refs/tags/"+tag, "refs/tags/"+tag+"^{}")
    refs = {line.split()[1]: line.split()[0] for line in remote_refs.splitlines()}
    if refs != {"refs/tags/"+tag: git("rev-parse", "refs/tags/"+tag), "refs/tags/"+tag+"^{}": commit}:
        raise ValueError("unpublished source tag")
    prefix = "FORENSIC = {}\nexec("+repr(helper.read_text().split("if __name__ == '__main__':")[0])+", FORENSIC)\n"
    prefix += "ADAPTER = {}\nexec("+repr(adapter.read_text())+", ADAPTER)\nADAPTER_SHA = "+repr(sha(adapter))+"\n"
    # __file__ is diagnostic only on the remote stdin program, not a source path.
    source = ("__file__ = '/tmp/quote_repair_stdin.py'\n"+prefix+Path(__file__).read_text()).encode()
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output/"claim.json", {"schema": "quote_repair_claim_v1", "source_commit": commit,
        "source_tag": tag, "source_origin": origin, "sources": {str(p.relative_to(ROOT)): sha(p) for p in sources},
        "program_sha256": hashlib.sha256(source).hexdigest(), "parent_sha256": sha(parent),
        "day": "2026-08-21", "hour": 0, "max_rows": 12000000, "max_decoded_bytes": 8*1024**3,
        "max_retained": 200000, "wall_seconds": 600, "fits": 0, "paid_calls": 0})
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "root@173.255.231.4",
        "nice -n 10 timeout --signal=TERM --kill-after=10s 600s python3 -u - --remote"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p.stdin.write(source); p.stdin.close()
    os.set_blocking(p.stdout.fileno(), False)
    selector = selectors.DefaultSelector(); selector.register(p.stdout, selectors.EVENT_READ)
    pending = b""; total = seq = 0; completed = None; deadline = time.monotonic()+630
    try:
        while True:
            if time.monotonic() > deadline: raise TimeoutError("transport deadline")
            if not selector.select(1): continue
            chunk = os.read(p.stdout.fileno(), 65536)
            if not chunk: break
            total += len(chunk); pending += chunk
            if total > 1024*1024: raise ValueError("response byte bound")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1); packet = json.loads(line)
                fresh_json(output/f"progress-{seq:03d}.json", packet); seq += 1
                print(json.dumps({"progress": seq, "stage": packet.get("stage"), "scanned": packet.get("scanned")}), flush=True)
                if packet.get("stage") == "complete": completed = packet["report"]
        code = p.wait(timeout=15)
        if pending or code or completed is None: raise ValueError("missing terminal validation receipt")
        completed.update(claim_sha256=sha(output/"claim.json"), ssh_reaped=True, exit_code=code)
        completed["result_sha256"] = digest(completed)
        fresh_json(output/"report.json", completed)
        print(json.dumps({"report": str(output/"report.json"), "known_case_fixed": completed["analysis"]["known_cross_record_case_fixed"]}))
    except BaseException as exc:
        fresh_json(output/"failure.json", {"failure_type": type(exc).__name__, "progress_receipts": seq,
            "automatic_retry": False, "remote_exit_unverified": p.poll() is None})
        if p.poll() is None: p.terminate()
        try: p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=5)
        raise
    finally:
        selector.close(); p.stdout.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--remote", action="store_true"); ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if args.remote:
        try: remote()
        except Exception as exc:
            print(json.dumps({"stage": "failure", "failure_type": type(exc).__name__}), flush=True)
            sys.exit(1)
    elif args.output: local(args.output.resolve())
    else: ap.error("--output required")
