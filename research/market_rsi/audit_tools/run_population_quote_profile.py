"""One committed, bounded all-token quote-source diagnostic on an opened file."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TAG = "pm-population-audit-v0.1.1"
ADAPTER_SHA = "211ac84f7dca210c649f32e69f42a6c35867f591c618bd3197cee4ff8bbc7e09"
HELPER_SHA = "97d9c13c5aa5d6f118b562f73a4ff3db2c93cffb3af18377199873fb9c4319f5"
RAW_SHA = "27621845de8cc31ca2055235b2a4b69e11a0c6116f3d316f3eda84e647bb4255"
PREFIX_SHA = "81a51236351e142851130aa37d2cb56a90ce00aca24f1219c7eb4d8a048d1ded"
FULL_SHA = "9dc75c1814796f226e55801cb0ecb662ad1727c05ae3de78f09b8a3ffef22c31"
CASES = {
    (116007, 0, 0): "387e05f05d147553cf5ec427d249a01c0361ee79ce93a6d0fefffc47bdbddfd4",
    (116008, 0, 1): "af00dd4f2bd1addc165bb82ac410cfdfc550eea812c7c9bb739a76f8f750c9d5",
    (116009, 0, 1): "c4efa119b3561ecf1699275a355a5ef6fd91d561d3e3d6ff3c84bde9866d8e45",
}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mode_spec(mode):
    if mode not in {"pilot", "hour"}: raise ValueError("fixed pilot/hour mode required")
    return {"mode": mode, "max_records": 50000 if mode == "pilot" else 4328805,
            "max_decoded_bytes": 64*1024**2 if mode == "pilot" else 8*1024**3,
            "wall_seconds": 120 if mode == "pilot" else 1800,
            "max_address_space_bytes": 1024**3, "max_entities": 5000,
            "max_total_levels": 1000000, "source_sha256": RAW_SHA,
            "expected_decoded_sha256": PREFIX_SHA if mode == "pilot" else FULL_SHA}


def validate_terminal(report, spec):
    if (report.get("source_sha256") != RAW_SHA or report.get("mode") != spec["mode"]
            or report.get("raw_records") != spec["max_records"]
            or report.get("decoded_sha256") != spec["expected_decoded_sha256"]
            or report.get("decoder_reaped") is not True):
        raise ValueError("source/terminal scope mismatch")
    if spec["mode"] == "hour":
        if not report.get("full_hour_decoded") or report.get("decoder_exit_code") != 0:
            raise ValueError("full source not decoded")
        cases = report["profile"]["case"]
        if ([tuple(c["key"]) for c in cases] != list(CASES)
                or len({c["entity_sha256"] for c in cases}) != 1
                or [c["raw_sha256"] for c in cases] != list(CASES.values())
                or [c["depth_status"] for c in cases] != ["crossed", "locked", "uncrossed"]
                or any(c["source_status"] != "uncrossed" or c["price_candidate"] is not True for c in cases)):
            raise ValueError("frozen one-token case no longer agrees")
    elif (report.get("full_hour_decoded") is not False or report.get("stop_reason") != "fixed_prefix"
          or report.get("decoder_exit_code") not in (0, -13, -15)):
        raise ValueError("pilot masquerades as full hour")
    p = report["profile"]
    entities = p["entities"]; n = p["totals"]["counts"].get("quote_observations", 0)
    if (len(entities) != p["breadth"]["entities"] or len({e["entity_sha256"] for e in entities}) != len(entities)
            or sum(e["counts"].get("quote_observations", 0) for e in entities) != n
            or sum(p["totals"]["source_status"].values()) != n
            or sum(p["totals"]["depth_status"].values()) != n
            or sum(p["totals"]["depth_to_source_status"].values()) != n
            or p["input_counts"]["raw_records"] != spec["max_records"]):
        raise ValueError("population denominators differ")
    if any(report.get(k) is not False for k in ("source_mutated", "new_test_opened", "source_admitted")):
        raise ValueError("diagnostic cannot admit source")
    if any(report.get(k) != 0 for k in ("fits", "paid_calls", "raw_rows_exported")):
        raise ValueError("scope expanded")


def remote(mode):
    import resource
    spec = mode_spec(mode); started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS, (spec["max_address_space_bytes"], spec["max_address_space_bytes"]))
    def terminated(signum, frame): raise TimeoutError("remote wall limit")
    signal.signal(signal.SIGTERM, terminated)
    def progress(value): print(json.dumps(value, sort_keys=True), flush=True)
    f = FORENSIC
    source = f["RAW_PATH"]
    before = f["checked_file"](source, RAW_SHA)
    model = PROFILE["PopulationProfile"](ADAPTER["QuoteReconstructor"],
        max_entities=spec["max_entities"], max_total_levels=spec["max_total_levels"])
    decoder = subprocess.Popen(["zstd", "-dc", "--", str(source)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    progress({"stage": "started", "mode": mode, "pid": os.getpid(), "decoder_pid": decoder.pid,
              "source_sha256": RAW_SHA, "source_bytes": before.st_size})
    digest = hashlib.sha256(); n = total_bytes = 0; eof = False
    first_t = last_t = None
    try:
        for n, line in enumerate(f["bounded_lines"](decoder.stdout, spec["max_decoded_bytes"]), 1):
            if n > spec["max_records"]: raise ValueError("more rows than frozen source")
            digest.update(line); total_bytes += len(line)
            record = json.loads(line)
            t = ADAPTER["timestamp"](record.get("t"))
            # Exact previously opened date, not a guess that file mtime is receipt time.
            if not 1787270400000 <= t < 1787356800000:
                raise ValueError("record outside allowed diagnostic date")
            first_t = t if first_t is None else min(first_t, t)
            last_t = t if last_t is None else max(last_t, t)
            model.process(record, n, hashlib.sha256(line).hexdigest(), cases=CASES)
            if n % 500000 == 0:
                packet = {"stage": "checkpoint", "scanned": n, "elapsed_seconds": time.monotonic()-started,
                    "prefix_sha256": digest.hexdigest(), "partial_not_terminal": True,
                    "profile": model.summary(include_entities=n % 1000000 == 0)}
                progress(packet)
            if mode == "pilot" and n == spec["max_records"]: break
        else:
            eof = True
    except BaseException as exc:
        progress({"stage": "failure_partial", "failure_type": type(exc).__name__, "scanned": n,
                  "prefix_sha256": digest.hexdigest(), "partial_not_terminal": True,
                  "profile": model.summary(include_entities=True)})
        raise
    finally:
        decoder.stdout.close()
        if not eof and decoder.poll() is None: decoder.terminate()
        try: code = decoder.wait(timeout=5)
        except subprocess.TimeoutExpired: decoder.kill(); code = decoder.wait(timeout=5)
    f["unchanged"](source, before)
    result = {"schema": "population_quote_run_v1", "mode": mode, "source_sha256": RAW_SHA,
        "adapter_sha256": ADAPTER_SHA, "source_bytes": before.st_size, "raw_records": n,
        "decoded_bytes": total_bytes, "decoded_sha256": digest.hexdigest(),
        "full_hour_decoded": eof, "stop_reason": "eof" if eof else "fixed_prefix",
        "decoder_exit_code": code, "decoder_reaped": True, "elapsed_seconds": time.monotonic()-started,
        "peak_self_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "min_observed_capture_ms": first_t, "max_observed_capture_ms": last_t,
        "profile": model.summary(include_entities=True), "source_mutated": False,
        "source_admitted": False, "new_test_opened": False, "fits": 0, "paid_calls": 0,
        "raw_rows_exported": 0, "raw_identifiers_exported": 0, "derived_rows_persisted": False}
    validate_terminal(result, spec)
    progress({"stage": "complete", "report": result})


def publication(sources):
    repo = ROOT.parents[1]
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], timeout=30).decode().strip()
    names = [str(p.relative_to(repo)) for p in sources]
    if git("status", "--porcelain", "--", *names): raise ValueError("uncommitted source")
    commit = git("rev-parse", "HEAD")
    for path, name in zip(sources, names):
        blob = subprocess.check_output(["git", "-C", str(repo), "show", commit+":"+name], timeout=30)
        if hashlib.sha256(blob).hexdigest() != file_hash(path): raise ValueError("committed bytes differ")
    if git("remote", "get-url", "origin") != "https://github.com/Estelle-LH/RSIBench-Data.git":
        raise ValueError("wrong origin")
    ref = "refs/tags/"+TAG
    if git("cat-file", "-t", ref) != "tag" or git("rev-parse", ref+"^{commit}") != commit:
        raise ValueError("wrong annotated source version")
    tag_object = git("rev-parse", ref)
    remote_refs = {line.split()[1]: line.split()[0] for line in git("ls-remote", "origin", ref, ref+"^{}").splitlines()}
    if remote_refs != {ref: tag_object, ref+"^{}": commit}: raise ValueError("source version not published")
    return {"commit": commit, "tag": TAG, "tag_object": tag_object,
            "sources": {str(p.relative_to(ROOT)): file_hash(p) for p in sources}}


def local(output, mode, pilot=None):
    sys.path.insert(0, str(ROOT))
    from market_rsi import fresh_json, digest, load_json
    spec = mode_spec(mode)
    adapter = ROOT/"quote_source/reconstruct.py"
    helper = ROOT/"audit_tools/capture_cross_forensic.py"
    profile = Path(__file__).with_name("population_quote_profile.py")
    if file_hash(adapter) != ADAPTER_SHA or file_hash(helper) != HELPER_SHA:
        raise ValueError("frozen adapter/helper changed")
    published = publication([adapter, helper, profile, Path(__file__).resolve(),
        Path(__file__).with_name("test_population_quote_profile.py"), Path(__file__).with_name("test_run_population_quote_profile.py")])
    if mode == "hour":
        if not pilot: raise ValueError("same-source successful pilot required")
        tested = load_json(pilot/"report.json")
        if tested.get("result_sha256") != digest({k: v for k, v in tested.items() if k != "result_sha256"}):
            raise ValueError("pilot integrity mismatch")
        validate_terminal(tested, mode_spec("pilot"))
        projected = tested["elapsed_seconds"] / tested["raw_records"] * spec["max_records"]
        if (tested.get("publication") != published or not tested.get("ssh_reaped") or tested.get("exit_code") != 0
                or tested["elapsed_seconds"] > 90 or projected > spec["wall_seconds"] * 0.8):
            raise ValueError("pilot runtime/cleanup/source differs; no blind scale-up")
    source = "__file__ = '/tmp/population_quote_stdin.py'\n"
    for name, path in (("FORENSIC", helper), ("ADAPTER", adapter), ("PROFILE", profile)):
        content = path.read_text().split("if __name__ == '__main__':")[0] if name == "FORENSIC" else path.read_text()
        source += name+" = {}\nexec("+repr(content)+", "+name+")\n"
    source = (source+Path(__file__).read_text()).encode()
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output/"claim.json", {"schema": "population_quote_claim_v1", **spec,
        "publication": published, "program_sha256": hashlib.sha256(source).hexdigest(),
        "pilot_report_sha256": file_hash(pilot/"report.json") if pilot else None,
        "new_test_opened": False, "paid_calls": 0})
    command = ("flock -n /tmp/market-rsi-population-quote.lock nice -n 10 timeout --signal=TERM --kill-after=10s "
        +str(spec["wall_seconds"])+"s python3 -u - --remote --mode "+mode)
    process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "root@173.255.231.4", command],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    process.stdin.write(source); process.stdin.close()
    os.set_blocking(process.stdout.fileno(), False)
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    pending = b""; received = seq = 0; completed = None; deadline = time.monotonic()+spec["wall_seconds"]+30
    try:
        while True:
            if time.monotonic() > deadline: raise TimeoutError("transport deadline")
            if not selector.select(1): continue
            data = os.read(process.stdout.fileno(), 65536)
            if not data: break
            pending += data; received += len(data)
            if received > 64*1024**2: raise ValueError("aggregate output bound")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1); packet = json.loads(line)
                fresh_json(output/f"progress-{seq:03d}.json", packet); seq += 1
                print(json.dumps({"progress": seq, "stage": packet.get("stage"), "scanned": packet.get("scanned"),
                                  "elapsed_seconds": packet.get("elapsed_seconds")}), flush=True)
                if packet.get("stage") == "complete": completed = packet["report"]
        code = process.wait(timeout=15)
        if pending or code or completed is None: raise ValueError("missing successful terminal receipt")
        validate_terminal(completed, spec)
        completed.update(publication=published, claim_sha256=file_hash(output/"claim.json"), ssh_reaped=True, exit_code=code)
        completed["result_sha256"] = digest(completed)
        fresh_json(output/"report.json", completed)
        print(json.dumps({"report": str(output/"report.json"), "raw_records": completed["raw_records"],
                          "breadth": completed["profile"]["breadth"]}))
    except BaseException as exc:
        fresh_json(output/"failure.json", {"failure_type": type(exc).__name__, "progress_receipts": seq,
            "automatic_retry": False, "remote_exit_unverified": process.poll() is None})
        if process.poll() is None: process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        raise
    finally:
        selector.close(); process.stdout.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--remote", action="store_true"); ap.add_argument("--mode", choices=("pilot", "hour"), required=True)
    ap.add_argument("--output", type=Path); ap.add_argument("--pilot", type=Path)
    args = ap.parse_args()
    if args.remote:
        try: remote(args.mode)
        except BaseException as exc:
            print(json.dumps({"stage": "failure", "failure_type": type(exc).__name__}), flush=True)
            sys.exit(1)
    elif args.output: local(args.output.resolve(), args.mode, args.pilot.resolve() if args.pilot else None)
    else: ap.error("--output required")
