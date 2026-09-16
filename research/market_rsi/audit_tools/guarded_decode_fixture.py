"""Retain a synthetic success + injected failure canary for local decompression."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import zstandard

from canary_sqlite_fixture import build_fixture
from canary_sqlite_observations import canonical, inspect_archive
from guarded_sqlite_decode import decode


def run(output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    raw = output / "synthetic-source.sqlite"
    raw_hash, raw_size = build_fixture(raw)
    archive = output / "synthetic-source.sqlite.zst"
    archive.write_bytes(zstandard.ZstdCompressor(write_checksum=True).compress(raw.read_bytes()))
    archive.chmod(0o444)
    binary = Path(shutil.which("zstd")).resolve()
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    common = dict(expected_sha256=source_hash, expected_bytes=archive.stat().st_size,
                  decoder=binary, expected_decoder_sha256=binary_hash,
                  decoded_upper_bound_bytes=raw_size, reserve_bytes=5 * 1024**3, max_seconds=30)
    good = decode(archive, output / "valid", **common)
    assert good["decoded_sha256"] == raw_hash and good["decoded_bytes"] == raw_size
    activity = inspect_archive(Path(good["decoded_file"]), expected_sha256=raw_hash,
                               expected_bytes=raw_size, start_ms=0, end_ms=180_000,
                               recorder_scope="synthetic-only")
    try:
        decode(archive, output / "injected-no-space", **common, free_bytes_at=lambda _: 0)
        raise AssertionError("injected no-space should not decode")
    except ValueError as exc:
        assert "insufficient free space" in str(exc)
    fail = json.loads((output / "injected-no-space/failure.json").read_text())
    assert fail["process_reaped"] and fail["decoder_pid"] is None
    assert not (output / "injected-no-space/payload.sqlite").exists()
    damaged = output / "synthetic-corrupt.sqlite.zst"
    damaged.write_bytes(archive.read_bytes()[:-1])
    damaged.chmod(0o444)
    corrupt_args = dict(common, expected_sha256=hashlib.sha256(damaged.read_bytes()).hexdigest(),
                        expected_bytes=damaged.stat().st_size)
    try:
        decode(damaged, output / "injected-truncation", **corrupt_args)
        raise AssertionError("injected truncated frame should not publish")
    except ValueError as exc:
        assert "decoder failed" in str(exc)
    damaged_report = json.loads((output / "injected-truncation/failure.json").read_text())
    assert damaged_report["process_reaped"]
    assert not (output / "injected-truncation/payload.sqlite").exists()
    report = {
        "schema": "guarded_sqlite_decode_fixture_v1", "passed": True,
        "evidence_mode": "synthetic_software_canary_only", "real_market_rows_read": 0,
        "new_download_bytes": 0, "new_model_calls": 0, "provider_cost_usd": "0",
        "success": good, "read_only_activity": activity,
        "injected_failures": {"disk": fail, "truncated_frame": damaged_report},
        "failures_are_synthetic_not_live_incidents": True,
        "zstandard_fixture_writer_version": zstandard.__version__,
        "decoder_version": subprocess.run([str(binary), "--version"], capture_output=True,
                                           text=True, timeout=10, check=True).stdout.strip(),
        "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (raw, archive, damaged)},
        "code_hashes": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ("guarded_decode_fixture.py", "guarded_sqlite_decode.py",
                                     "canary_sqlite_fixture.py", "canary_sqlite_observations.py",
                                     "canary_activity_observations.py")},
        "acquisition_admitted": False, "clean_sessions_proven": False,
        "full_archive_throughput_tested": False,
    }
    report["result_sha256"] = hashlib.sha256(canonical(report).encode()).hexdigest()
    with (output / "canary.json").open("x") as stream:
        stream.write(canonical(report) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    r = run(parser.parse_args().output.resolve())
    print(json.dumps({k: r[k] for k in ("passed", "evidence_mode", "new_download_bytes",
                                       "new_model_calls", "provider_cost_usd", "result_sha256")}))
