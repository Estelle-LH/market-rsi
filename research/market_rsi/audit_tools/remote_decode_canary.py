"""Native-zstd/stdlib-only synthetic decode canary; no network or market data.

Run in a fresh Python process under an independent outer process deadline. The
driver creates its permanent output claim before reading dependencies or starting
children. All synthetic originals, compressed files and failed partials survive.
This tests software compatibility, not publisher coverage or acquisition authority.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import sqlite3
import stat
import subprocess
import sys
import time
import types


MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
CODE_FILES = (
    "canary_activity_observations.py", "canary_sqlite_observations.py",
    "canary_sqlite_fixture.py", "guarded_sqlite_decode.py", "remote_decode_canary.py",
)


def _json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


def _read_regular(path, max_bytes=MAX_SOURCE_BYTES):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError("canonical absolute resident regular input required")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 \
            or getattr(before, "st_flags", 0) & 0x40000000 \
            or not 0 < before.st_size <= max_bytes:
        raise ValueError("input is dataless, nonregular, linked, empty, or oversized")
    contents = path.read_bytes()
    after = path.lstat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ValueError("input changed during read")
    return contents, hashlib.sha256(contents).hexdigest()


def _remaining(end):
    left = end - time.monotonic()
    if left <= 0:
        raise TimeoutError("native decode canary wall deadline reached")
    return left


def _stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    return process.returncode


def _native(argv, output, name, *, end, stdout_limit):
    """Drain bounded pipes, preserve bytes/receipts, and reap only this child."""
    process = None
    selector = selectors.DefaultSelector()
    payload = output / (name + ".stdout")
    stderr_bytes, stdout_bytes = 0, 0
    stderr_hash = hashlib.sha256()
    try:
        with payload.open("xb", buffering=0) as target:
            process = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env={"LANG": "C", "LC_ALL": "C"})
            _json(output / (name + "-process.json"), {
                "pid": process.pid, "argv": argv, "synthetic_only": True,
                "stdout_max_bytes": stdout_limit, "stderr_max_bytes": 8192,
            })
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                for key, _ in selector.select(timeout=min(0.2, _remaining(end))):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if key.data == "stderr":
                        stderr_bytes += len(chunk)
                        stderr_hash.update(chunk)
                        if stderr_bytes > 8192:
                            raise ValueError("native canary stderr bound exceeded")
                        continue
                    if stdout_bytes + len(chunk) > stdout_limit:
                        raise ValueError("native canary stdout bound exceeded")
                    offset = 0
                    while offset < len(chunk):
                        count = target.write(chunk[offset:])
                        if not count:
                            raise OSError("short native canary output write")
                        stdout_bytes += count
                        offset += count
            status = process.wait(timeout=_remaining(end))
            if status != 0:
                raise ValueError("native canary command returned nonzero exit status")
            target.flush()
            os.fsync(target.fileno())
        result = {
            "passed": True, "pid": process.pid, "exit_code": status,
            "process_reaped": process.poll() is not None, "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes, "stderr_sha256": stderr_hash.hexdigest(),
        }
        _json(output / (name + "-result.json"), result)
        return payload, result
    except BaseException as exc:
        code = _stop(process) if process is not None else None
        _json(output / (name + "-failure.json"), {
            "passed": False, "error_type": type(exc).__name__, "reason": str(exc),
            "pid": process.pid if process else None, "exit_code": code,
            "process_reaped": process is None or process.poll() is not None,
            "stdout_bytes": stdout_bytes, "stderr_bytes": stderr_bytes,
            "automatic_retry": False,
        })
        raise
    finally:
        selector.close()
        if process is not None:
            _stop(process)
            for pipe in (process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        if payload.exists():
            payload.chmod(0o444)


def run(output, *, decoder, expected_decoder_sha256, expected_decoder_version,
        code_manifest=None, expected_code_manifest_sha256=None, max_seconds=60):
    output, decoder = Path(output), Path(decoder)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_decoder_sha256) \
            or not isinstance(expected_decoder_version, str) or not expected_decoder_version \
            or len(expected_decoder_version) > 4096:
        raise ValueError("exact native decoder hash and complete version string required")
    if type(max_seconds) is not int or not 1 <= max_seconds <= 120:
        raise ValueError("integer canary deadline between 1 and 120 seconds required")
    if (code_manifest is None) != (expected_code_manifest_sha256 is None):
        raise ValueError("optional code manifest requires its expected SHA256")
    if not output.is_absolute() or output.parent != output.parent.resolve(strict=True):
        raise ValueError("canonical absolute output with existing parent required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("permanent native canary output ID already used")
    output.mkdir(mode=0o700, exist_ok=False)
    _json(output / "claim.json", {
        "schema": "native_decode_canary_claim_v1", "synthetic_only": True,
        "decoder": str(decoder), "expected_decoder_sha256": expected_decoder_sha256,
        "expected_decoder_version": expected_decoder_version,
        "expected_code_manifest_sha256": expected_code_manifest_sha256,
        "max_seconds": max_seconds, "max_synthetic_payload_bytes": MAX_PAYLOAD_BYTES,
        "new_download_bytes": 0, "new_model_calls": 0, "real_market_rows_read": 0,
        "automatic_retry": False, "originals_and_failed_partials_preserved": True,
    })
    end = time.monotonic() + max_seconds
    previous_modules = {}
    try:
        source_root = Path(__file__).resolve().parent
        source_bytes, hashes = {}, {}
        for name in CODE_FILES:
            _remaining(end)
            source_bytes[name], hashes[name] = _read_regular(source_root / name)
        manifest_sha = None
        if code_manifest is not None:
            manifest_bytes, manifest_sha = _read_regular(Path(code_manifest))
            if manifest_sha != expected_code_manifest_sha256:
                raise ValueError("code manifest hash mismatch")
            if json.loads(manifest_bytes) != hashes:
                raise ValueError("code manifest must exactly match the five source file hashes")
        _json(output / "code-hashes.json", hashes)
        decoder_bytes, decoder_sha = _read_regular(decoder, max_bytes=32 * 1024 * 1024)
        del decoder_bytes
        if decoder_sha != expected_decoder_sha256:
            raise ValueError("native decoder hash mismatch")
        if not os.access(decoder, os.X_OK):
            raise ValueError("pinned native decoder is not executable")
        version_file, version_process = _native(
            [str(decoder), "--version"], output, "version", end=end, stdout_limit=8192)
        version = _read_regular(version_file, max_bytes=8192)[0].decode("utf-8").strip()
        if version != expected_decoder_version:
            raise ValueError("native decoder version mismatch")
        if not hasattr(sqlite3.Connection, "setlimit"):
            raise ValueError("stdlib SQLite Connection.setlimit is required")
        # Load exactly the resident bytes hashed above, with no source search,
        # pyc dependency, third-party package, or import of the market project.
        loaded = {}
        for name in CODE_FILES[:-1]:
            module_name = Path(name).stem
            previous_modules[module_name] = sys.modules.get(module_name)
            module = types.ModuleType(module_name)
            module.__file__ = str(source_root / name)
            sys.modules[module_name] = module
            exec(compile(source_bytes[name], module.__file__, "exec"), module.__dict__)
            loaded[module_name] = module
        _remaining(end)
        raw = output / "synthetic-source.sqlite"
        raw_sha, raw_size = loaded["canary_sqlite_fixture"].build_fixture(raw)
        if raw_size > MAX_PAYLOAD_BYTES // 8:
            raise ValueError("synthetic fixture exceeds conservative total-payload allowance")
        compressed, compression_process = _native(
            [str(decoder), "-1", "-c", "-q", "--no-progress", "--", str(raw)],
            output, "synthetic-compressed", end=end, stdout_limit=MAX_PAYLOAD_BYTES // 8)
        compressed_bytes, compressed_sha = _read_regular(compressed, max_bytes=MAX_PAYLOAD_BYTES // 8)
        if len(compressed_bytes) < 2:
            raise ValueError("synthetic compressed fixture unexpectedly short")
        decode = loaded["guarded_sqlite_decode"].decode
        common = {
            "expected_sha256": compressed_sha, "expected_bytes": len(compressed_bytes),
            "decoder": decoder, "expected_decoder_sha256": expected_decoder_sha256,
            "decoded_upper_bound_bytes": raw_size, "reserve_bytes": 5 * 1024**3,
        }
        good = decode(compressed, output / "valid", max_seconds=_remaining(end), **common)
        if good["decoded_sha256"] != raw_sha or good["decoded_bytes"] != raw_size \
                or not good["process_reaped"]:
            raise ValueError("synthetic full-hash roundtrip failed")
        activity = loaded["canary_sqlite_observations"].inspect_archive(
            good["decoded_file"], expected_sha256=raw_sha, expected_bytes=raw_size,
            start_ms=0, end_ms=180_000, recorder_scope="synthetic-native-canary-only",
            max_seconds=_remaining(end))
        if not activity["all_window_queries_complete"] or activity["fresh_validation_admitted"]:
            raise ValueError("synthetic read-only activity check failed")
        try:
            decode(compressed, output / "injected-no-space", max_seconds=_remaining(end),
                   free_bytes_at=lambda _path: 0, **common)
        except ValueError as exc:
            if "insufficient free space" not in str(exc):
                raise
        else:
            raise ValueError("injected no-space case unexpectedly succeeded")
        no_space = json.loads(_read_regular(output / "injected-no-space/failure.json")[0])
        if no_space["decoder_pid"] is not None or not no_space["process_reaped"]:
            raise ValueError("no-space guard started a decoder or did not reap it")
        damaged = output / "synthetic-truncated.zst"
        with damaged.open("xb") as stream:
            stream.write(compressed_bytes[:-1])
            stream.flush()
            os.fsync(stream.fileno())
        damaged.chmod(0o444)
        damaged_sha = hashlib.sha256(compressed_bytes[:-1]).hexdigest()
        truncated_options = dict(common, expected_sha256=damaged_sha,
                                 expected_bytes=len(compressed_bytes) - 1)
        try:
            decode(damaged, output / "injected-truncation", max_seconds=_remaining(end),
                   **truncated_options)
        except ValueError as exc:
            if "decoder failed" not in str(exc):
                raise
        else:
            raise ValueError("injected truncated-frame case unexpectedly succeeded")
        truncation = json.loads(_read_regular(output / "injected-truncation/failure.json")[0])
        if not truncation["process_reaped"] or truncation["decoder_exit_code"] in (None, 0) \
                or not (output / "injected-truncation/payload.partial").is_file() \
                or (output / "injected-truncation/payload.sqlite").exists():
            raise ValueError("truncated frame did not fail closed with preserved partial")
        # Include successful and failed decoded payloads in the total-size proof.
        payloads = (raw, compressed, damaged, Path(good["decoded_file"]),
                    output / "injected-truncation/payload.partial")
        payload_total = sum(path.stat().st_size for path in payloads)
        if payload_total > MAX_PAYLOAD_BYTES:
            raise ValueError("synthetic total payload exceeds 1 MiB")
        for name, expected in hashes.items():
            if _read_regular(source_root / name)[1] != expected:
                raise ValueError("canary source changed during execution")
        if _read_regular(decoder, max_bytes=32 * 1024 * 1024)[1] != expected_decoder_sha256 \
                or _read_regular(raw)[1] != raw_sha \
                or _read_regular(compressed)[1] != compressed_sha \
                or _read_regular(damaged)[1] != damaged_sha:
            raise ValueError("native decoder or retained synthetic originals changed")
        _remaining(end)
        result = {
            "schema": "native_decode_canary_result_v1", "passed": True,
            "evidence_mode": "synthetic_software_compatibility_canary_only",
            "python_executable": sys.executable, "python_version": sys.version,
            "sqlite_version": sqlite3.sqlite_version,
            "sqlite_setconfig_available": hasattr(sqlite3.Connection, "setconfig"),
            "decoder": str(decoder), "decoder_sha256": expected_decoder_sha256,
            "decoder_version": version, "code_sha256": hashes,
            "input_code_manifest_sha256": manifest_sha,
            "version_process": version_process, "compression_process": compression_process,
            "success": good, "activity": activity,
            "injected_failures": {"no_space": no_space, "truncated_frame": truncation},
            "synthetic_payload_total_bytes": payload_total,
            "synthetic_original_sha256": raw_sha,
            "synthetic_compressed_sha256": compressed_sha,
            "synthetic_truncated_sha256": damaged_sha,
            "originals_and_failed_partials_preserved": True,
            "new_download_bytes": 0, "new_model_calls": 0, "real_market_rows_read": 0,
            "provider_cost_usd": "0", "automatic_retry": False,
            "full_archive_throughput_tested": False, "publisher_schema_verified": False,
            "coverage_proven": False, "acquisition_admitted": False,
            "fresh_validation_admitted": False,
        }
        _json(output / "result.json", result)
        return result
    except BaseException as exc:
        _json(output / "failure.json", {
            "passed": False, "error_type": type(exc).__name__, "reason": str(exc),
            "automatic_retry": False, "new_download_bytes": 0, "new_model_calls": 0,
            "synthetic_only": True, "all_existing_outputs_preserved": True,
        })
        raise
    finally:
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decoder", required=True, type=Path)
    parser.add_argument("--expected-decoder-sha256", required=True)
    parser.add_argument("--expected-decoder-version", required=True)
    parser.add_argument("--code-manifest", type=Path)
    parser.add_argument("--expected-code-manifest-sha256")
    parser.add_argument("--max-seconds", type=int, default=60)
    report = run(**vars(parser.parse_args()))
    print(json.dumps({key: report[key] for key in (
        "passed", "evidence_mode", "decoder_version", "synthetic_payload_total_bytes",
        "new_download_bytes", "new_model_calls", "real_market_rows_read")}))
