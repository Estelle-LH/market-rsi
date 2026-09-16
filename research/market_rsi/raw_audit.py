"""Read-only Kalshi envelope validation. No price labels or model selection."""
import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from market_rsi import file_hash, fresh_json


class RawAudit:
    def __init__(self):
        self.counts = Counter()
        self.last_sequence = {}
        self.initialized = {}
        self.first_ms = self.last_ms = None
        self.exchange_time_pairs = 0
        self.arrival_minus_exchange_sum = 0
        self.examples = []

    def issue(self, name, ordinal):
        self.counts[name] += 1
        if len(self.examples) < 20:
            self.examples.append(dict(issue=name, source_ordinal=ordinal))

    def accept(self, record, ordinal):
        self.counts["records"] += 1
        if not isinstance(record, dict):
            self.issue("invalid_envelope", ordinal)
            return
        t, message = record.get("t"), record.get("m")
        if isinstance(t, bool) or not isinstance(t, int) or not isinstance(message, dict):
            self.issue("invalid_envelope", ordinal)
            return
        if self.last_ms is not None and t < self.last_ms:
            self.issue("receive_clock_reversal", ordinal)
        self.first_ms = t if self.first_ms is None else min(self.first_ms, t)
        self.last_ms = t
        kind, sid, seq = message.get("type"), message.get("sid"), message.get("seq")
        if seq is not None:
            if sid is None or isinstance(seq, bool) or not isinstance(seq, int):
                self.issue("invalid_sequence", ordinal)
                return
            if sid in self.last_sequence and seq != self.last_sequence[sid] + 1:
                self.issue("sequence_discontinuity", ordinal)
                # A seq reset cannot be confidently classified as reconnect
                # without capture metadata. Invalidate this subscription.
                self.initialized[sid] = set()
            self.last_sequence[sid] = seq
        if kind not in {"orderbook_snapshot", "orderbook_delta"}:
            self.counts["non_book_messages"] += 1
            return
        self.counts[kind] += 1
        msg = message.get("msg")
        if not isinstance(msg, dict) or not isinstance(msg.get("market_ticker"), str):
            self.issue("invalid_book_message", ordinal)
            return
        if sid is None or seq is None:
            self.issue("book_without_sequence", ordinal)
            return
        market = msg["market_ticker"]
        state = self.initialized.setdefault(sid, set())
        if kind == "orderbook_snapshot":
            state.add(market)
        elif market not in state:
            self.issue("delta_without_snapshot", ordinal)
        else:
            self.counts["deltas_with_initialized_snapshot"] += 1
        exchange_time = msg.get("ts_ms")
        if isinstance(exchange_time, int) and not isinstance(exchange_time, bool):
            self.exchange_time_pairs += 1
            self.arrival_minus_exchange_sum += t - exchange_time
            if exchange_time > t:
                self.issue("exchange_clock_after_envelope", ordinal)

    def summary(self):
        errors = sum(self.counts[k] for k in ("invalid_json", "invalid_envelope", "invalid_sequence",
                     "invalid_book_message", "book_without_sequence", "receive_clock_reversal"))
        complete_clock_proof = False  # Requires collector provenance, not inferred.
        return dict(counts=dict(self.counts), first_envelope_ms=self.first_ms,
                    last_envelope_ms=self.last_ms, example_issues=self.examples,
                    paired_clock_records=self.exchange_time_pairs,
                    mean_envelope_minus_exchange_ms=(self.arrival_minus_exchange_sum / self.exchange_time_pairs
                                                    if self.exchange_time_pairs else None),
                    parsing_pass=errors == 0 and self.counts["records"] > 0,
                    standalone_replay_pass=(errors == 0 and self.counts["records"] > 0
                                           and self.counts["sequence_discontinuity"] == 0
                                           and self.counts["delta_without_snapshot"] == 0),
                    collector_receive_semantics_verified=complete_clock_proof,
                    subsecond_evaluation_ready=False,
                    note="Clock differences are observations, not an independently measured latency. "
                         "An hourly slice may require the previous file's snapshot state; "
                         "missing state is not evidence that the original capture failed.")


def audit_file(path):
    path = Path(path)
    before = file_hash(path)
    process = None
    if path.suffix == ".zst":
        process = subprocess.Popen(["zstd", "-dc", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stream = process.stdout
    else:
        stream = path.open("rb")
    audit, uncompressed = RawAudit(), hashlib.sha256()
    try:
        for i, raw in enumerate(stream):
            uncompressed.update(raw)
            try:
                record = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                audit.issue("invalid_json", i)
                continue
            audit.accept(record, i)
    finally:
        stream.close()
    if process:
        error = process.stderr.read().decode(errors="replace")
        if process.wait() != 0:
            raise ValueError("decompression failed: " + error[:200])
    if file_hash(path) != before:
        raise ValueError("source changed during audit")
    return dict(source_path=str(path.resolve()), source_sha256=before,
                uncompressed_sha256=uncompressed.hexdigest(), audit_code_sha256=file_hash(__file__),
                **audit.summary())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = audit_file(args.source)
    fresh_json(args.output, report)
    print(json.dumps(report, indent=2))
