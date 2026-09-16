"""Conservative cross-file replay of recorded Kalshi order-book messages.

Read-only source adapter, not a backtest. Missing anchors, invalid increments,
sequence gaps and long transport silence invalidate state until fresh snapshots.
Source clocks and session ownership still require collector provenance.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from market_rsi import canonical, file_hash, fresh_json


def scaled(value, places):
    if not isinstance(value, str):
        raise ValueError("fixed-point strings required")
    negative = value.startswith("-")
    text = value[1:] if negative else value
    parts = text.split(".")
    if len(parts) > 2 or not parts[0].isdigit():
        raise ValueError("invalid fixed-point value")
    fraction = parts[1] if len(parts) == 2 else ""
    if (fraction and not fraction.isdigit()) or len(fraction) > places:
        raise ValueError("unexpected precision")
    result = int(parts[0]) * 10**places + int(fraction.ljust(places, "0") or "0")
    return -result if negative else result


class Replay:
    def __init__(self, no_side_price_convention, max_transport_silence_ms=30000):
        if no_side_price_convention not in {"no_bids", "yes_asks"}:
            raise ValueError("explicit collector no-side price convention required")
        self.no_side_price_convention = no_side_price_convention
        if type(max_transport_silence_ms) is not int or max_transport_silence_ms <= 0:
            raise ValueError("positive transport silence bound required")
        self.silence = max_transport_silence_ms
        self.last_receive = None
        self.last_stream_receive = {}
        self.sequences = {}
        self.epochs = Counter()
        self.books = {}
        self.counts = Counter()
        self.market_counts = Counter()
        self.coverage = {}
        self.issues = []

    def issue(self, name, key, t=None, sid=None, market=None):
        self.counts[name] += 1
        if len(self.issues) < 100:
            self.issues.append(dict(issue=name, source_key=key, t=t, sid=sid, market=market))

    def invalidate(self, sid=None):
        if sid is None:
            for stream in self.epochs:
                self.epochs[stream] += 1
        else:
            self.epochs[sid] += 1

    @staticmethod
    def ladder(rows):
        if not isinstance(rows, list):
            raise ValueError("missing snapshot ladder")
        book = {}
        for level in rows:
            if not isinstance(level, list) or len(level) != 2:
                raise ValueError("bad ladder level")
            price, quantity = scaled(level[0], 4), scaled(level[1], 2)
            if not 0 < price < 10000 or quantity <= 0 or price in book:
                raise ValueError("invalid or repeated ladder level")
            book[price] = quantity
        return book

    def accept(self, record, source_key):
        self.counts["records"] += 1
        if not isinstance(record, dict) or type(record.get("t")) is not int or not isinstance(record.get("m"), dict):
            self.issue("bad_envelope", source_key)
            self.invalidate()
            return None
        t, message = record["t"], record["m"]
        if self.last_receive is not None and t < self.last_receive:
            self.issue("clock_reversal", source_key, t)
            self.invalidate()
            raise ValueError("receive clock reversed; reject source batch")
        self.last_receive = t
        kind, sid, seq = message.get("type"), message.get("sid"), message.get("seq")
        if sid is not None and (type(sid) is not int or sid < 0):
            self.issue("bad_sequence", source_key, t)
            self.invalidate()
            return None
        if seq is not None:
            if sid is None or type(seq) is not int or seq < 0:
                self.issue("bad_sequence", source_key, t)
                self.invalidate(sid)
                return None
            if sid in self.sequences and seq != self.sequences[sid] + 1:
                self.issue("sequence_gap_or_reset", source_key, t, sid)
                self.invalidate(sid)
            if sid in self.last_stream_receive and t - self.last_stream_receive[sid] > self.silence:
                self.issue("transport_silence", source_key, t, sid)
                self.invalidate(sid)
            self.sequences[sid] = seq
            self.last_stream_receive[sid] = t
            # Counter lookups don't insert absent keys; explicitly register the
            # stream so global invalidation reaches epoch-zero books as well.
            self.epochs.setdefault(sid, 0)
        if kind not in {"orderbook_delta", "orderbook_snapshot"}:
            self.counts["non_book"] += 1
            return None
        self.counts[kind] += 1
        if sid is None or seq is None:
            self.issue("book_without_sequence", source_key, t)
            self.invalidate()
            return None
        msg = message.get("msg")
        if not isinstance(msg, dict) or not isinstance(msg.get("market_ticker"), str) or not msg["market_ticker"]:
            self.issue("bad_book", source_key, t, sid)
            self.invalidate(sid)
            return None
        market = msg["market_ticker"]
        key = sid, market
        try:
            if kind == "orderbook_snapshot":
                # No guessing between dollars, cents, signed deltas or old ETL
                # `use_yes_price` conventions: explicitly support the raw schema.
                book = dict(yes=self.ladder(msg.get("yes_dollars_fp")),
                            no=self.ladder(msg.get("no_dollars_fp")), epoch=self.epochs[sid],
                            anchor_key=source_key, anchor_ms=t, quote_segment=0)
                self.books[key] = book
            else:
                book = self.books.get(key)
                if book is None or book["epoch"] != self.epochs[sid]:
                    self.issue("delta_without_valid_anchor", source_key, t, sid, market)
                    return None
                side = msg.get("side")
                if side not in {"yes", "no"}:
                    raise ValueError("unknown side")
                price, delta = scaled(msg.get("price_dollars"), 4), scaled(msg.get("delta_fp"), 2)
                if not 0 < price < 10000:
                    raise ValueError("invalid price")
                quantity = book[side].get(price, 0) + delta
                if quantity < 0:
                    raise ValueError("negative resulting quantity")
                if quantity == 0:
                    book[side].pop(price, None)
                else:
                    book[side][price] = quantity
            if not book["yes"] or not book["no"]:
                self.counts["one_sided_book"] += 1
                # The book can recover through valid deltas, but a later label
                # must never bridge this untradable interval. Stream epochs
                # alone do not capture loss of one side in just this market.
                book["quote_segment"] += 1
                return None
            bid = max(book["yes"])
            if self.no_side_price_convention == "yes_asks":
                no_touch = min(book["no"])
                ask = no_touch
            else:
                no_touch = max(book["no"])
                ask = 10000 - no_touch
            if bid > ask:
                raise ValueError("crossed binary book")
        except (ValueError, TypeError) as error:
            self.books.pop(key, None)
            self.issue("invalid_book_state", source_key, t, sid, market)
            return None
        self.counts["valid_two_sided_updates"] += 1
        self.market_counts[market] += 1
        span = self.coverage.setdefault(market, dict(first_ms=t, last_ms=t))
        span["last_ms"] = t
        return dict(source_key=source_key, receive_ms=t, sid=sid, seq=seq, stream_epoch=self.epochs[sid],
                    market_id=market, anchor_key=book["anchor_key"], anchor_ms=book["anchor_ms"],
                    quote_segment=book["quote_segment"],
                    bid_1e4=bid, ask_1e4=ask, bid_size_1e2=book["yes"][bid],
                    ask_size_1e2=book["no"][no_touch])

    def summary(self):
        return dict(counts=dict(self.counts), issues=self.issues,
                    markets_with_valid_updates=len(self.market_counts),
                    valid_updates_by_market=dict(self.market_counts), envelope_spans=self.coverage,
                    max_transport_silence_ms=self.silence,
                    no_side_price_convention=self.no_side_price_convention,
                    collector_clock_provenance_verified=False, scoring_ready=False,
                    evidence_class="diagnostic-replay-only",
                    note="Spans are NOT continuous eligibility intervals. Use per-row epochs and anchors, "
                         "then independently verify transport, clock, game splits, staleness and labels before scoring.")


def replay_files(sources, output, no_side_price_convention, max_transport_silence_ms=30000, emit_quotes=False):
    sources = [Path(p).resolve() for p in sources]
    if not sources or len(set(sources)) != len(sources) or sources != sorted(sources):
        raise ValueError("explicit distinct sorted source files required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = [dict(path=str(p), sha256=file_hash(p), size_bytes=p.stat().st_size) for p in sources]
    fresh_json(output / "claim.json", dict(sources=manifest, code_sha256=file_hash(__file__),
               no_side_price_convention=no_side_price_convention,
               max_transport_silence_ms=max_transport_silence_ms, emit_quotes=emit_quotes))
    replay, streams = Replay(no_side_price_convention, max_transport_silence_ms), []
    quotes = gzip.open(output / "quotes.jsonl.gz", "xt") if emit_quotes else None
    try:
        for source_index, source in enumerate(sources):
            process = None
            if source.suffix == ".zst":
                process = subprocess.Popen(["zstd", "-dc", str(source)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                handle = process.stdout
            else:
                handle = source.open("rb")
            sha, lines = hashlib.sha256(), 0
            try:
                for line_index, line in enumerate(handle):
                    sha.update(line)
                    lines += 1
                    source_key = [source_index, line_index]
                    try:
                        record = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        replay.issue("invalid_json", source_key)
                        replay.invalidate()
                        continue
                    row = replay.accept(record, source_key)
                    if row is not None and quotes is not None:
                        quotes.write(canonical(row) + "\n")
            finally:
                handle.close()
                if process:
                    err = process.stderr.read()
                    rc = process.wait()
                    if rc:
                        raise ValueError("source decompression failed")
            if file_hash(source) != manifest[source_index]["sha256"]:
                raise ValueError("source changed during replay")
            streams.append(dict(index=source_index, lines=lines, uncompressed_sha256=sha.hexdigest()))
    finally:
        if quotes:
            quotes.close()
    report = dict(**replay.summary(), sources=manifest, uncompressed_streams=streams,
                  quotes_sha256=file_hash(output / "quotes.jsonl.gz") if emit_quotes else None)
    fresh_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-side-price-convention", choices=["no_bids", "yes_asks"], required=True)
    parser.add_argument("--max-transport-silence-ms", type=int, default=30000)
    parser.add_argument("--emit-quotes", action="store_true")
    args = parser.parse_args()
    report = replay_files(args.sources, args.output, args.no_side_price_convention,
                          args.max_transport_silence_ms, args.emit_quotes)
    print(canonical({key: report[key] for key in ("counts", "markets_with_valid_updates", "scoring_ready")}))
