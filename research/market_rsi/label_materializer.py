"""Streaming, runner-only labels from explicitly segmented replay quotes.

This module constructs actual numeric labels, but cannot attest to collector
clocks, game identity or a completed market experiment. Its file entry point is
diagnostic-only until independent source provenance and worker gates exist.
Never mount its output directory in an agent: future prices and source indexes
belong to the runner. A separate split/worker projection controls exposure.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from split_manifest import integer, sha


@dataclass(frozen=True)
class LabelPolicy:
    horizon_ms: int
    latency_ms: int
    max_entry_lateness_ms: int
    max_label_lateness_ms: int
    max_quote_gap_ms: int
    decision_interval_ms: int

    def __post_init__(self):
        for key, value in asdict(self).items():
            integer(value, 1 if key in {"horizon_ms", "max_quote_gap_ms", "decision_interval_ms"} else 0)
        if self.max_entry_lateness_ms >= self.horizon_ms:
            raise ValueError("entry lateness must be shorter than label horizon")


def ordinal(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("two-part immutable replay source key required")
    return tuple(integer(x) for x in value)


def checked_quote(row, sources):
    if not isinstance(row, dict):
        raise ValueError("quote object required")
    required = {"source_key", "receive_ms", "sid", "seq", "stream_epoch", "market_id",
                "anchor_key", "anchor_ms", "quote_segment", "bid_1e4", "ask_1e4",
                "bid_size_1e2", "ask_size_1e2"}
    if set(row) != required:
        raise ValueError("segmented replay schema required; old quotes must not be silently reused")
    identifier(row["market_id"])
    for key in required - {"source_key", "anchor_key", "market_id"}:
        integer(row[key])
    key, anchor = ordinal(row["source_key"]), ordinal(row["anchor_key"])
    if key[0] >= len(sources) or anchor[0] >= len(sources) or anchor > key:
        raise ValueError("invalid source/anchor order")
    if row["anchor_ms"] > row["receive_ms"]:
        raise ValueError("snapshot anchor from the future")
    if not 0 < row["bid_1e4"] <= row["ask_1e4"] < 10000:
        raise ValueError("invalid two-sided price")
    if min(row["bid_size_1e2"], row["ask_size_1e2"]) <= 0:
        raise ValueError("positive displayed size required")
    return key


def continuity(row):
    return (row["sid"], row["stream_epoch"], tuple(row["anchor_key"]), row["quote_segment"])


class LabelBuilder:
    """Emit immutable decision features and first-observed forward endpoints.

    Sampling is by a predeclared interval, independent of future outcomes. We do
    not forward-fill missing endpoints or choose the most profitable later mark.
    Endpoint lateness, quote gaps and continuity changes censor examples with
    explicit counters. Labels are price diagnostics, not net PnL or fill evidence.
    """
    def __init__(self, policy, market_games, source_sha256):
        if not isinstance(policy, LabelPolicy) or not market_games or not source_sha256:
            raise ValueError("policy, nonempty game mapping and source hashes required")
        for market, game in market_games.items():
            identifier(market)
            identifier(game)
        if len(set(source_sha256)) != len(source_sha256):
            raise ValueError("duplicate source hash")
        self.sources = tuple(sha(value) for value in source_sha256)
        self.games, self.policy = dict(market_games), policy
        self.pending, self.previous, self.last_decision = {}, {}, {}
        self.last_key, self.last_ms = None, None
        self.counts = Counter()
        self.closed = False

    def source(self, quote):
        index, line = quote["source_key"]
        return {"sha256": self.sources[index], "ordinal": line}

    def labeled(self, decision, entry, future):
        d, e, f = decision, entry, future
        bid, ask = d["bid_1e4"] / 10000, d["ask_1e4"] / 10000
        bsize, asize = d["bid_size_1e2"] / 100, d["ask_size_1e2"] / 100
        mid = (bid + ask) / 2
        return {
            "row_id": digest({"market": d["market_id"], "source": self.source(d)}),
            "game_id": self.games[d["market_id"]], "market_id": d["market_id"],
            "decision_ms": d["receive_ms"], "feature_available_ms": d["receive_ms"],
            "entry_ms": e["receive_ms"], "label_end_ms": f["receive_ms"],
            "label_available_ms": f["receive_ms"],
            "input_source": self.source(d), "entry_source": self.source(e),
            "label_source": self.source(f),
            "features": {"bid": bid, "ask": ask, "mid": mid, "spread": ask - bid,
                         "bid_size": bsize, "ask_size": asize,
                         "imbalance": (bsize - asize) / (bsize + asize)},
            "labels": {
                "mid_change": (f["bid_1e4"] + f["ask_1e4"]) / 20000 - mid,
                "buy_yes_gross_price_change": (f["bid_1e4"] - e["ask_1e4"]) / 10000,
                "buy_no_gross_price_change": (e["bid_1e4"] - f["ask_1e4"]) / 10000,
            },
            "runner_endpoints": {"entry_bid_1e4": e["bid_1e4"], "entry_ask_1e4": e["ask_1e4"],
                "exit_bid_1e4": f["bid_1e4"], "exit_ask_1e4": f["ask_1e4"],
                "entry_bid_size_1e2": e["bid_size_1e2"], "entry_ask_size_1e2": e["ask_size_1e2"],
                "exit_bid_size_1e2": f["bid_size_1e2"], "exit_ask_size_1e2": f["ask_size_1e2"]},
        }

    def accept(self, quote):
        if self.closed:
            raise ValueError("cannot append after materializer completion")
        key = checked_quote(quote, self.sources)
        t = quote["receive_ms"]
        if self.last_key is not None and (key <= self.last_key or t < self.last_ms):
            raise ValueError("duplicate/reordered source key or reversed clock")
        self.last_key, self.last_ms = key, t
        self.counts["input_quotes"] += 1
        market = quote["market_id"]
        if market not in self.games:
            self.counts["outside_frozen_market_map"] += 1
            return []
        p, prior = self.policy, self.previous.get(market)
        pending = self.pending.setdefault(market, [])
        if prior is not None:
            reason = None
            if continuity(prior) != continuity(quote):
                reason = "continuity_break"
            elif t - prior["receive_ms"] > p.max_quote_gap_ms:
                reason = "quote_gap"
            if reason:
                self.counts[reason] += len(pending)
                pending.clear()
        self.previous[market] = quote
        ready, waiting = [], []
        for item in pending:
            decision = item["decision"]
            entry_target = decision["receive_ms"] + p.latency_ms
            label_target = entry_target + p.horizon_ms
            if item["entry"] is None and t >= entry_target:
                if t > entry_target + p.max_entry_lateness_ms:
                    self.counts["entry_endpoint_late"] += 1
                    continue
                item["entry"] = quote
            if t >= label_target:
                if t > label_target + p.max_label_lateness_ms:
                    self.counts["label_endpoint_late"] += 1
                elif item["entry"] is None or item["entry"]["receive_ms"] >= t:
                    self.counts["missing_distinct_entry"] += 1
                else:
                    ready.append(self.labeled(decision, item["entry"], quote))
                    self.counts["labeled_rows"] += 1
            else:
                waiting.append(item)
        self.pending[market] = waiting
        if market not in self.last_decision or t - self.last_decision[market] >= p.decision_interval_ms:
            self.last_decision[market] = t
            waiting.append({"decision": quote, "entry": quote if p.latency_ms == 0 else None})
            self.counts["scheduled_decisions"] += 1
        return ready

    def finish(self):
        if not self.closed:
            self.counts["capture_tail_censored"] += sum(len(v) for v in self.pending.values())
            self.pending.clear()
            self.closed = True
        return dict(self.counts)


def materialize_diagnostic(replay_dir, spec_path, output):
    """Exclusive local artifact; NEVER a scoring authorization or public dataset."""
    replay_dir, spec_path, output = Path(replay_dir), Path(spec_path), Path(output)
    report_path, quotes_path = replay_dir / "report.json", replay_dir / "quotes.jsonl.gz"
    report_hash, spec_hash = file_hash(report_path), file_hash(spec_path)
    report, spec = load_json(report_path), load_json(spec_path)
    if set(spec) != {"schema", "evidence_class", "policy", "market_games"}:
        raise ValueError("explicit materialization spec required")
    if spec["schema"] != "market_labels_v1" or spec["evidence_class"] not in {"fixture", "diagnostic"}:
        raise ValueError("live scoring provenance is not implemented")
    quotes_hash = file_hash(quotes_path)
    if report.get("quotes_sha256") != quotes_hash:
        raise ValueError("replay quotes no longer match their receipt")
    builder = LabelBuilder(LabelPolicy(**spec["policy"]), spec["market_games"],
                           [row["sha256"] for row in report["sources"]])
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    claim = {"spec_sha256": spec_hash, "replay_report_sha256": report_hash,
             "quotes_sha256": quotes_hash, "code_sha256": file_hash(__file__),
             "evidence_class": spec["evidence_class"], "scoring_ready": False}
    fresh_json(output / "claim.json", claim)
    fresh_json(output / "spec.json", spec)
    rows_path = output / "runner-labels.jsonl.gz"
    try:
        with gzip.open(quotes_path, "rt") as source, gzip.open(rows_path, "xt") as target:
            for line in source:
                for row in builder.accept(json.loads(line)):
                    target.write(canonical(row) + "\n")
        counts = builder.finish()
        if (file_hash(report_path) != report_hash or file_hash(spec_path) != spec_hash
                or file_hash(quotes_path) != quotes_hash):
            raise ValueError("source changed during materialization")
        result = {**claim, "counts": counts, "labels_sha256": file_hash(rows_path),
                  "research_result": False, "net_pnl_computed": False,
                  "remaining_gates": ["collector_clock_and_session_provenance", "audited_game_mapping",
                    "whole_game_split_and_visibility", "frozen_external_scorer", "isolated_worker"],
                  "limitations": "Gross price changes omit fees, slippage, position limits and fill uncertainty."}
        fresh_json(output / "complete.json", result)
        return result
    except Exception as error:
        fresh_json(output / "failure.json", {"type": type(error).__name__, "scoring_ready": False})
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("replay_dir", type=Path)
    p.add_argument("spec_path", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    print(canonical(materialize_diagnostic(a.replay_dir, a.spec_path, a.output)))
