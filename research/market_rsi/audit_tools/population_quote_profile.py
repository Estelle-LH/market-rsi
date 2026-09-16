"""Streaming all-entity diagnostics around the UNCHANGED quote source adapter.

No inference of outage, receipt-time semantics, continuous prices or independent
sample size. No row selection by subsequent movement. Standard library only.
"""
from collections import Counter
from decimal import Decimal
import hashlib
import json

PROFILE_VERSION = "pm-population-audit-v0.1.1"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


class EntityProfile:
    def __init__(self, asset, market, engine_class):
        self.engine = engine_class(asset, market)
        self.entity_hash = fingerprint([market, asset])
        self.market_hash = fingerprint(market)
        self.counts = Counter()
        self.status = Counter()
        self.depth_status = Counter()
        self.issues = Counter()
        self.snapshots = Counter()
        self.pairs = Counter()
        self.event_kinds = Counter()
        self.quote_minutes = set()
        self.candidate_minutes = set()
        self.first_ms = self.last_ms = None
        self.previous = None
        self.equal_run = 0
        self.equal_start = None
        self.max_equal_run = self.max_equal_span = self.max_gap = 0

    def observe(self, row):
        source, depth = row["source"], row["depth"]
        self.counts["quote_observations"] += 1
        self.status[source["status"]] += 1
        self.depth_status[depth["status"]] += 1
        self.pairs[depth["status"]+" -> "+source["status"]] += 1
        self.issues.update(row["issues"])
        self.counts["price_candidates"] += int(row["price_candidate"])
        self.counts["bbo_comparable"] += int(depth["bbo_matches_source"] is not None)
        self.counts["bbo_mismatch"] += int(depth["bbo_matches_source"] is False)
        if row["kind"] == "price_change":
            self.counts["delta_observations"] += 1
            self.counts["unanchored_delta_observations"] += int(depth["status"] == "unanchored")
        if source["origin"] == "complete_snapshot_levels":
            equality = depth["full_map_equals_next_snapshot"]
            self.snapshots["equal" if equality is True else "different" if equality is False else "no_prior_anchor"] += 1
        if source["origin"] == "same_message_best_bid_ask" and any(source[k] is not None for k in ("bid_size", "ask_size")):
            raise ValueError("source size invention")
        if row["source_admitted"] or row["clock_semantics_attested"] or depth["executable_certified"]:
            raise ValueError("unexpected admission")
        t = row["capture_ms"]
        if t is not None:
            self.quote_minutes.add(t // 60000)
            self.first_ms = t if self.first_ms is None else min(self.first_ms, t)
            self.last_ms = t if self.last_ms is None else max(self.last_ms, t)
        # Bad rows split chains; neither prices nor their validity are carried.
        if not row["price_candidate"] or t is None:
            self.previous = None; self.equal_run = 0; self.equal_start = None
            return
        self.candidate_minutes.add(t // 60000)
        mid = (Decimal(source["bid"]) + Decimal(source["ask"])) / 2
        if self.previous is not None:
            old_t, old_mid = self.previous
            dt = t-old_t
            if dt < 0:
                raise ValueError("candidate clock regressed")
            self.counts["adjacent_valid_mid_pairs"] += 1
            self.max_gap = max(self.max_gap, dt)
            bucket = "0ms" if dt == 0 else "1..1000ms" if dt <= 1000 else "1001..10000ms" if dt <= 10000 else "10001..60000ms" if dt <= 60000 else ">60000ms"
            self.counts["pair_gap_"+bucket] += 1
            if mid == old_mid:
                self.counts["equal_mid_pairs"] += 1
                if self.equal_run == 0: self.equal_start = old_t
                self.equal_run += 1
                self.max_equal_run = max(self.max_equal_run, self.equal_run)
                self.max_equal_span = max(self.max_equal_span, t-self.equal_start)
            else:
                self.counts["changed_mid_pairs"] += 1
                self.equal_run = 0; self.equal_start = None
        self.previous = (t, mid)

    def public(self):
        return {"entity_sha256": self.entity_hash, "market_sha256": self.market_hash,
            "counts": dict(self.counts), "source_status": dict(self.status),
            "depth_status": dict(self.depth_status), "depth_to_source_status": dict(self.pairs),
            "issues": dict(self.issues), "snapshots": dict(self.snapshots),
            "event_kinds": dict(self.event_kinds),
            "observed_quote_minutes": len(self.quote_minutes), "candidate_quote_minutes": len(self.candidate_minutes),
            "first_capture_ms": self.first_ms, "last_capture_ms": self.last_ms,
            "max_adjacent_valid_observation_gap_ms": self.max_gap,
            "max_equal_mid_run_pairs": self.max_equal_run,
            "max_equal_mid_observed_span_ms": self.max_equal_span}


class PopulationProfile:
    def __init__(self, engine_class, *, max_entities=5000, max_total_levels=1000000):
        self.engine_class = engine_class
        self.max_entities, self.max_total_levels = max_entities, max_total_levels
        self.entities = {}
        self.last_ordinal = 0
        self.counts = Counter()
        self.event_kinds = Counter()
        self.stream_hash = hashlib.sha256()
        self.case = []

    def process(self, record, ordinal, raw_hash, *, cases=None):
        if ordinal <= self.last_ordinal:
            raise ValueError("raw input out of order")
        self.last_ordinal = ordinal
        self.counts["raw_records"] += 1
        if not isinstance(record, dict): raise ValueError("record object required")
        messages = record.get("m")
        messages = messages if isinstance(messages, list) else [messages]
        selected = {}
        for m in messages:
            if not isinstance(m, dict): raise ValueError("unrecognized raw envelope")
            kind = m.get("event_type")
            if kind is None and record.get("src") == "rest": kind = "rest_snapshot"
            if not isinstance(kind, str): kind = "missing_event_type"
            self.event_kinds[kind] += 1
            if kind == "price_change":
                changes = m.get("price_changes")
                if not isinstance(changes, list) or any(not isinstance(c, dict) for c in changes):
                    raise ValueError("invalid price_changes envelope")
                identities = [c.get("asset_id") for c in changes]
            else:
                identities = [m.get("asset_id")]
            unique = set()
            for asset in identities:
                if not isinstance(asset, str) or not asset:
                    self.counts["unroutable_identity_entries"] += 1
                    continue
                market = m.get("market")
                if not isinstance(market, str) or not market:
                    raise ValueError("missing contemporaneous market identity")
                if asset in selected and selected[asset]["market"] != market:
                    raise ValueError("token identity conflict inside record")
                item = selected.setdefault(asset, {"market": market, "kinds": Counter()})
                # Per-token message kinds, not duplicated per price level.
                if asset not in unique:
                    item["kinds"][kind] += 1
                unique.add(asset)
            if not unique:
                self.counts["messages_without_routable_asset"] += 1
                # Keep these visible; never infer they came from RTDS or sports.
        if not selected:
            self.counts["records_without_routable_asset"] += 1
        compact_rows = []
        for asset, meta in selected.items():
            if asset not in self.entities:
                if len(self.entities) >= self.max_entities: raise ValueError("entity resource bound")
                self.entities[asset] = EntityProfile(asset, meta["market"], self.engine_class)
            profile = self.entities[asset]
            if profile.engine.market != meta["market"]:
                raise ValueError("historical token market changed")
            profile.counts["raw_records_with_entity"] += 1
            profile.event_kinds.update(meta["kinds"])
            for row in profile.engine.process(record, ordinal, raw_hash):
                profile.observe(row)
                self.counts["quote_observations"] += 1
                # Compact, deterministic content commitment; raw fields not exported.
                compact_rows.append([row["key"], profile.entity_hash, row["source"], row["depth"], row["issues"], row["price_candidate"]])
                if cases and tuple(row["key"]) in cases:
                    if raw_hash != cases[tuple(row["key"])]: raise ValueError("known raw case changed")
                    self.case.append({"key": row["key"], "entity_sha256": profile.entity_hash,
                        "raw_sha256": raw_hash, "source_status": row["source"]["status"],
                        "depth_status": row["depth"]["status"], "price_candidate": row["price_candidate"]})
        # Asset routing order must not replace original message/change order.
        compact_rows.sort(key=lambda r: r[0])
        self.stream_hash.update((json.dumps([ordinal, raw_hash, compact_rows], sort_keys=True, separators=(",", ":"))+"\n").encode())
        if ordinal % 10000 == 0:
            total_levels = sum(sum(len(s) for s in p.engine.book.values()) for p in self.entities.values() if p.engine.book is not None)
            if total_levels > self.max_total_levels: raise ValueError("global depth resource bound")

    def summary(self, *, include_entities=False):
        counters = {k: Counter() for k in ("counts", "source_status", "depth_status", "depth_to_source_status", "issues", "snapshots")}
        breadth = Counter(); minutes = Counter(); entities = []
        for profile in self.entities.values():
            item = profile.public()
            for key, accumulator in counters.items(): accumulator.update(item[key])
            count = item["counts"]
            breadth["entities"] += 1
            breadth["entities_with_quotes"] += int(count.get("quote_observations", 0) > 0)
            breadth["entities_with_price_candidates"] += int(count.get("price_candidates", 0) > 0)
            breadth["entities_with_snapshot_observations"] += int(sum(item["snapshots"].values()) > 0)
            breadth["entities_with_source_crossings"] += int(item["source_status"].get("crossed", 0) > 0)
            breadth["entities_with_bbo_mismatch"] += int(count.get("bbo_mismatch", 0) > 0)
            breadth["entities_with_changed_mid"] += int(count.get("changed_mid_pairs", 0) > 0)
            breadth["entities_with_no_mid_change_among_valid_pairs"] += int(count.get("adjacent_valid_mid_pairs", 0) > 0 and count.get("changed_mid_pairs", 0) == 0)
            minutes[str(item["candidate_quote_minutes"])] += 1
            if include_entities: entities.append(item)
        breadth["observed_market_ids"] = len({p.market_hash for p in self.entities.values()})
        if counters["counts"].get("quote_observations", 0) != self.counts.get("quote_observations", 0):
            raise ValueError("population denominator mismatch")
        result = {"schema": "population_quote_profile_v1", "profile_version": PROFILE_VERSION,
            "input_counts": dict(self.counts), "message_kinds": dict(self.event_kinds),
            "totals": {k: dict(v) for k, v in counters.items()}, "breadth": dict(breadth),
            "candidate_minute_histogram": dict(minutes), "derived_stream_sha256": self.stream_hash.hexdigest(),
            "case": list(self.case), "source_admitted": False, "clock_semantics_attested": False,
            "continuous_flat_price_proven": False, "outage_classified": False,
            "independent_sample_size_estimated": False, "raw_rows_exported": 0}
        if include_entities: result["entities"] = sorted(entities, key=lambda e: e["entity_sha256"])
        return result
