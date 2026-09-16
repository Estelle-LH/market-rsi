"""Trusted sequential prediction protocol, with a bounded subprocess transport.

Only the trusted runner holds the full evaluation feature sequence. A candidate
receives training examples, then one feature row at a time. A prediction must be
validated and durably committed before the next row is sent. This is not a
scorer, market-data provenance gate or cloud launcher. No labels belong in the
evaluation payload. The Linux launcher must run inside a fresh E2B sandbox;
model-generated code must never be launched on the Mac.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path


PUBLIC_FIELDS = {"row_id", "game_id", "market_id", "decision_ms", "feature_available_ms", "features"}
TRAIN_FIELDS = PUBLIC_FIELDS | {"target", "label_available_ms"}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def finite(value):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("finite numeric value required")
    return value


def validate_rows(train, evaluation, feature_names):
    """Runner-only validation; never serialize the full evaluation into a request."""
    if not isinstance(train, list) or not train or not isinstance(evaluation, list) or not evaluation:
        raise ValueError("nonempty Train and evaluation required")
    if (not isinstance(feature_names, list) or not feature_names
            or any(not isinstance(x, str) or not x for x in feature_names)
            or len(set(feature_names)) != len(feature_names)):
        raise ValueError("frozen feature schema required")
    seen_ids, train_games, eval_games, last, market_games = set(), set(), set(), {}, {}
    for kind, rows in (("train", train), ("evaluation", evaluation)):
        for r in rows:
            if not isinstance(r, dict) or set(r) != (TRAIN_FIELDS if kind == "train" else PUBLIC_FIELDS):
                raise ValueError("unexpected payload fields; evaluation labels/endpoints are forbidden")
            for key in ("row_id", "game_id", "market_id"):
                if not isinstance(r[key], str) or not r[key] or len(r[key]) > 100:
                    raise ValueError("bounded opaque row/game/market ID required")
            if r["row_id"] in seen_ids:
                raise ValueError("duplicate row identity")
            seen_ids.add(r["row_id"])
            if market_games.setdefault(r["market_id"], r["game_id"]) != r["game_id"]:
                raise ValueError("market relabeled as a different game")
            for key in ("decision_ms", "feature_available_ms"):
                if type(r[key]) is not int or r[key] < 0:
                    raise ValueError("integer nonnegative timestamp required")
            if r["feature_available_ms"] > r["decision_ms"]:
                raise ValueError("future feature")
            if r["decision_ms"] < last.get(kind, 0):
                raise ValueError("nonchronological input stream")
            last[kind] = r["decision_ms"]
            if not isinstance(r["features"], dict) or set(r["features"]) != set(feature_names):
                raise ValueError("feature schema changed")
            for value in r["features"].values():
                finite(value)
            if kind == "train":
                finite(r["target"])
                if type(r["label_available_ms"]) is not int or r["label_available_ms"] < r["decision_ms"]:
                    raise ValueError("invalid training-label availability")
                train_games.add(r["game_id"])
            else:
                eval_games.add(r["game_id"])
    if train_games & eval_games:
        raise ValueError("a game cannot be split across training/evaluation")
    latest_label = max(r["label_available_ms"] for r in train)
    first_decision = evaluation[0]["decision_ms"]
    if latest_label >= first_decision or latest_label // 86400000 >= first_decision // 86400000:
        raise ValueError("training labels must be available on a strictly earlier UTC date")


def predict_stream(exchange, commit, train, evaluation, feature_names, *, prediction_min,
                   prediction_max, fit_timeout_seconds, predict_timeout_seconds,
                   wall_seconds, max_request_bytes):
    """Use only an already-isolated transport. Commit is trusted and must fsync.

    Exceptions propagate: partial predictions do not become a completed trial.
    Prediction labels never enter this function. Trial scoring and admission,
    including common researcher context and provider budget, remain outside it.
    """
    validate_rows(train, evaluation, feature_names)
    if finite(prediction_min) >= finite(prediction_max):
        raise ValueError("prediction bounds required")
    for duration in (fit_timeout_seconds, predict_timeout_seconds, wall_seconds):
        if finite(duration) <= 0:
            raise ValueError("positive enforced timeout required")
    if type(max_request_bytes) is not int or max_request_bytes <= 0:
        raise ValueError("request byte limit required")
    began, chain = time.monotonic(), "0" * 64

    def request(body, timeout):
        body = dict(body, request_id=secrets.token_hex(16))
        if len(encoded(body)) > max_request_bytes:
            raise ValueError("input exceeds frozen byte bound; do not truncate or sample silently")
        remaining = wall_seconds - (time.monotonic() - began)
        if remaining <= 0:
            raise TimeoutError("trial wall cap reached")
        answer = exchange(body, min(timeout, remaining))
        if time.monotonic() - began >= wall_seconds:
            raise TimeoutError("trial wall cap reached")
        if not isinstance(answer, dict) or answer.get("request_id") != body["request_id"]:
            raise ValueError("response request identity mismatch")
        return answer

    result = request({"type": "fit", "features": feature_names, "train": train}, fit_timeout_seconds)
    if set(result) != {"type", "request_id"} or result["type"] != "fitted":
        raise ValueError("candidate did not acknowledge one fit")
    for seq, row in enumerate(evaluation):
        result = request({"type": "predict", "row": row}, predict_timeout_seconds)
        if (set(result) != {"type", "request_id", "row_id", "prediction"}
                or result["type"] != "prediction" or result["row_id"] != row["row_id"]):
            raise ValueError("unexpected candidate output")
        value = finite(result["prediction"])
        if not prediction_min <= value <= prediction_max:
            raise ValueError("prediction outside frozen range")
        record = {"sequence": seq, "row_id": row["row_id"], "prediction": value,
                  "feature_row_sha256": fingerprint(row), "previous": chain}
        chain = fingerprint(record)
        # The next observation is not released until this callback succeeds.
        commit(dict(record, hash=chain))
    return {"predictions": len(evaluation), "last_prediction_hash": chain,
            "elapsed_seconds": time.monotonic() - began, "scored": False}


class PredictionJournal:
    """Exclusive runner-owned prediction log. Append/fsync before release of data.

    This is an output receipt, NOT permission to create a sandbox or score a
    market dataset. The future outer worker must bind its verified input,
    common-initialization, candidate and budget claims before using the log.
    """
    def __init__(self, directory, *, train_sha256, evaluation_sha256, candidate_sha256,
                 expected_predictions):
        for value in (train_sha256, evaluation_sha256, candidate_sha256):
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("input/code hashes required")
        if type(expected_predictions) is not int or expected_predictions <= 0:
            raise ValueError("positive expected prediction count required")
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.expected, self.count, self.chain, self.finished = expected_predictions, 0, "0" * 64, False
        self.write_once("claim.json", {"train_sha256": train_sha256, "evaluation_sha256": evaluation_sha256,
            "candidate_sha256": candidate_sha256, "expected_predictions": expected_predictions,
            "scoring_authorized": False})
        self.path = self.directory / "predictions.jsonl"
        with self.path.open("xb"):
            pass

    def write_once(self, name, value):
        with (self.directory / name).open("xb") as f:
            f.write(encoded(value) + b"\n")
            f.flush()
            os.fsync(f.fileno())

    def commit(self, row):
        if self.finished or self.count >= self.expected:
            raise ValueError("prediction journal closed or full")
        keys = {"sequence", "row_id", "prediction", "feature_row_sha256", "previous", "hash"}
        if not isinstance(row, dict) or set(row) != keys:
            raise ValueError("unexpected prediction record")
        body = {k: v for k, v in row.items() if k != "hash"}
        if (type(row["sequence"]) is not int or row["sequence"] != self.count
                or row["previous"] != self.chain or row["hash"] != fingerprint(body)):
            raise ValueError("prediction sequence/hash mismatch")
        finite(row["prediction"])
        with self.path.open("ab") as f:
            f.write(encoded(row) + b"\n")
            f.flush()
            os.fsync(f.fileno())
        self.count += 1
        self.chain = row["hash"]

    def finish(self):
        if self.finished or self.count != self.expected:
            raise ValueError("incomplete or already completed prediction log")
        # Read back the entire modest prediction log before a completion receipt.
        previous, count, h = "0" * 64, 0, hashlib.sha256()
        with self.path.open("rb") as f:
            for line in f:
                h.update(line)
                row = json.loads(line)
                body = {k: v for k, v in row.items() if k != "hash"}
                if row["sequence"] != count or row["previous"] != previous or row["hash"] != fingerprint(body):
                    raise ValueError("prediction log read-back integrity failure")
                previous, count = row["hash"], count + 1
        if count != self.count or previous != self.chain:
            raise ValueError("prediction log truncated or extended")
        result = {"predictions": count, "last_prediction_hash": previous,
                  "predictions_sha256": h.hexdigest(), "scored": False}
        self.write_once("complete.json", result)
        self.finished = True
        return result


class LineChannel:
    """Bounded one-request/one-line-response protocol; no shell invocation.

    This transport alone is NOT an isolation boundary. Production must use
    linux_candidate_command inside a fresh E2B instance, with private runner
    files inaccessible to UID 65534. Local tests use only human-written fixtures.
    """
    def __init__(self, command, cwd, max_response_bytes=16384):
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ValueError("positive response byte bound required")
        self.limit = max_response_bytes
        self.events = []  # Trusted owner persists this bounded protocol trace.
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            start_new_session=True, bufsize=0)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.closed = False

    def exchange(self, payload, timeout):
        if self.closed:
            raise ValueError("transport closed")
        remaining = memoryview(encoded(payload) + b"\n")
        self.events.append({"type": "request", "request_sha256": fingerprint(payload),
                            "request_bytes": len(remaining)})
        output, deadline = bytearray(), time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE, "send")
            selector.register(self.process.stdout, selectors.EVENT_READ, "receive")
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    self.events.append({"type": "timeout", "partial_response": bytes(output).decode("utf-8", "replace")})
                    raise TimeoutError("candidate response timeout")
                for selected, _ in selector.select(left):
                    if selected.data == "send":
                        try:
                            sent = os.write(self.process.stdin.fileno(), remaining)
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            raise ValueError("candidate exited before reading its request") from None
                        remaining = remaining[sent:]
                        if not remaining:
                            selector.unregister(self.process.stdin)
                    else:
                        try:
                            data = os.read(self.process.stdout.fileno(), 65536)
                        except BlockingIOError:
                            continue
                        if not data:
                            self.events.append({"type": "eof", "partial_response": bytes(output).decode("utf-8", "replace")})
                            raise ValueError("candidate exited without a complete response")
                        output.extend(data)
                        if len(output) > self.limit:
                            self.events.append({"type": "oversized_response", "observed_bytes": len(output),
                                "response_prefix": bytes(output[:self.limit]).decode("utf-8", "replace"), "truncated": True})
                            raise ValueError("candidate output exceeds byte bound")
                        if b"\n" in output:
                            self.events.append({"type": "response", "raw": bytes(output).decode("utf-8", "replace")})
                            first, extra = bytes(output).split(b"\n", 1)
                            if remaining or extra:
                                raise ValueError("unsolicited or multiple candidate responses")
                            return json.loads(first)

    def close(self):
        if not self.closed:
            self.closed = True
            # Exact process group created by this transport, never a name match.
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    # macOS may return EPERM for a process group that exited
                    # between poll and killpg. Never ignore a live kill failure.
                    if self.process.poll() is None:
                        raise
            self.process.wait(timeout=5)
            self.process.stdin.close()
            self.process.stdout.close()
            # An untrusted descendant could create a different process group.
            # The outer E2B owner MUST kill the entire sandbox in its finally.

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()


def linux_candidate_command(server_path, candidate_path):
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("candidate execution requires the trusted root runner INSIDE E2B, never the Mac")
    for path in (server_path, candidate_path):
        path = Path(path)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("explicit non-symlink sandbox paths required")
        stat = path.stat()
        if stat.st_uid != 0 or stat.st_mode & 0o022:
            raise ValueError("runner-owned, non-world-writable code required")
    return ["unshare", "--net", "--", "setpriv", "--reuid=65534", "--regid=65534",
            "--clear-groups", "--no-new-privs", "--", "python3", "-I", str(server_path), str(candidate_path)]
