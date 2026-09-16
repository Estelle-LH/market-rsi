"""Auditable experiment control plane; no networking, credentials, or trading."""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import inspect
import copy
import shutil
from decimal import Decimal
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fresh_json(path, value):
    with Path(path).open("x") as f:
        f.write(canonical(value) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_json(path):
    return json.loads(Path(path).read_text())


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}", value):
        raise ValueError("unsafe identifier")
    return value


def probability(p):
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("probability must be finite and in [0,1]")
    return float(p)


def evaluator_hash(evaluator):
    return file_hash(inspect.getsourcefile(evaluator))


class Journal:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "journal.jsonl"

    @contextmanager
    def locked(self):
        with (self.root / ".lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read(self):
        records, previous = [], "0" * 64
        if not self.path.exists():
            return records
        for line in self.path.read_text().splitlines():
            record = json.loads(line)
            body = {k: v for k, v in record.items() if k != "hash"}
            if body["previous"] != previous or record["hash"] != digest(body) or body["seq"] != len(records):
                raise ValueError("journal integrity failure")
            previous = record["hash"]
            records.append(record)
        return records

    def append(self, event, payload):
        # Caller owns the process lock throughout a state transition.
        records = self.read()
        body = dict(seq=len(records), previous=records[-1]["hash"] if records else "0" * 64,
                    time=datetime.now(timezone.utc).isoformat(), event=event, payload=payload)
        with self.path.open("a") as f:
            f.write(canonical(dict(body, hash=digest(body))) + "\n")
            f.flush()
            os.fsync(f.fileno())


def audit_rows(rows, features, horizon_ms):
    """Validate canonical rows. Timestamp declarations also need upstream audit."""
    ids, previous, groups, splits = set(), {}, {}, {}
    for r in rows:
        rid, group, split = r["row_id"], r["game_id"], r["split"]
        if rid in ids:
            raise ValueError("duplicate row_id")
        ids.add(rid)
        if split not in {"train", "dev", "final"}:
            raise ValueError("unknown split")
        if group in groups and groups[group] != split:
            raise ValueError("same game appears in multiple splits")
        groups[group] = split
        t, available, end = r["decision_ms"], r["feature_available_ms"], r["label_end_ms"]
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (t, available, end)):
            raise ValueError("timestamps must be integer milliseconds")
        if available > t or end < t + horizon_ms:
            raise ValueError("future information or incorrect label horizon")
        # The ordering key is game/market/side, never just game.
        stream = (group, r["market_id"], r["side"])
        if stream in previous and t < previous[stream]:
            raise ValueError("out-of-order stream")
        previous[stream] = t
        if r["side"] not in {"bid", "ask"} or r["label"] not in (0, 1):
            raise ValueError("invalid side or binary label")
        if set(r["features"]) != set(features):
            raise ValueError("feature schema mismatch")
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
               for x in r["features"].values()):
            raise ValueError("missing or nonfinite feature")
        # UTC date is derived, not trusted as a caller-controlled grouping key.
        date = datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat()
        if r["date"] != date:
            raise ValueError("date does not match timestamp")
        splits.setdefault(split, []).append((t, end, date))
    if not rows or not {"train", "dev"} <= set(splits):
        raise ValueError("train and dev must both be nonempty")
    ordered = [s for s in ("train", "dev", "final") if s in splits]
    for earlier, later in zip(ordered, ordered[1:]):
        if max(x[1] for x in splits[earlier]) >= min(x[0] for x in splits[later]):
            raise ValueError("label overlap across chronological boundary")
        if max(x[2] for x in splits[earlier]) >= min(x[2] for x in splits[later]):
            raise ValueError("training/calibration must use earlier UTC dates")
    return {s: {"rows": len(v), "games": sum(x == s for x in groups.values()),
                "dates": sorted({x[2] for x in v})} for s, v in splits.items()}


def metrics(rows, predictions, alert_fraction=0.1):
    if not 0 < alert_fraction <= 1 or not rows:
        raise ValueError("invalid metric inputs")
    if set(predictions) != {r["row_id"] for r in rows}:
        raise ValueError("predictions must cover exactly the frozen evaluation rows")
    pairs = [(probability(predictions[r["row_id"]]), r["label"], r["row_id"]) for r in rows]
    n, positive = len(pairs), sum(y for _, y, _ in pairs)
    brier = sum((p - y) ** 2 for p, y, _ in pairs) / n
    # Average ranks for ties; no random tie-related AUC inflation.
    ordered = sorted(pairs)
    rank_sum, i = 0.0, 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][0] == ordered[i][0]:
            j += 1
        rank_sum += (i + 1 + j) / 2 * sum(x[1] for x in ordered[i:j])
        i = j
    auc = ((rank_sum - positive * (positive + 1) / 2) / (positive * (n - positive))
           if 0 < positive < n else None)
    k = max(1, math.ceil(n * alert_fraction))
    top = sorted(pairs, key=lambda x: (-x[0], x[2]))[:k]
    caught = sum(x[1] for x in top)
    return dict(rows=n, positives=positive, brier=brier, auc=auc, alerts=k,
                precision=caught / k, recall=caught / positive if positive else None)


class Market:
    """Binary LMSR markets with fixed identities, cash, no borrowing, no sells.

    Virtual shares only. Price is an aggregation mechanism, not a calibrated
    probability guarantee. Unresolved markets are not settled as failures.
    """
    def __init__(self, candidates, actors, liquidity=10.0, cash=10.0):
        if not math.isfinite(liquidity) or liquidity <= 0 or not math.isfinite(cash) or cash <= 0:
            raise ValueError("invalid market configuration")
        self.b = liquidity
        self.q = {c: [0.0, 0.0] for c in candidates}
        self.cash = {a: cash for a in actors}
        self.trades = []

    def cost(self, q):
        m = max(q)
        return m + self.b * math.log(sum(math.exp((x - m) / self.b) for x in q))

    def price(self, candidate):
        q = self.q[candidate]
        z = (q[0] - q[1]) / self.b
        return 1 / (1 + math.exp(-max(-700, min(700, z))))

    def buy(self, actor, candidate, side, shares):
        if actor not in self.cash or candidate not in self.q or side not in {"yes", "no"}:
            raise ValueError("unknown identity, candidate, or side")
        if isinstance(shares, bool) or not isinstance(shares, (int, float)) or not math.isfinite(shares) or shares <= 0:
            raise ValueError("shares must be positive and finite")
        old = self.q[candidate]
        new = old.copy()
        new[side == "no"] += shares
        cost = self.cost(new) - self.cost(old)
        if cost > self.cash[actor] + 1e-10:
            raise ValueError("virtual cash limit")
        self.q[candidate] = new
        self.cash[actor] -= cost
        self.trades.append(dict(actor=actor, candidate=candidate, side=side, shares=shares, cost=cost))

    def settle(self, outcomes):
        pnl, unresolved = {a: 0.0 for a in self.cash}, []
        for t in self.trades:
            y = outcomes[t["candidate"]]
            if y is None:
                unresolved.append(t)
                continue
            pnl[t["actor"]] += t["shares"] * (y == (t["side"] == "yes")) - t["cost"]
        return dict(realized_virtual_pnl=pnl, unresolved_trades=unresolved)


def choose(scores):
    if not scores or max(scores.values()) <= 0.5:
        return "parent"
    return sorted(scores, key=lambda c: (-scores[c], c))[0]


class Round:
    def __init__(self, root):
        self.root = Path(root)
        self.journal = Journal(root)

    @classmethod
    def create(cls, root, protocol, plans, data_path):
        actors = protocol["actors"]
        if len(set(actors)) != len(actors) or len(actors) < 2:
            raise ValueError("fixed distinct forecasters required")
        for a in actors:
            identifier(a)
        if protocol["primary_metric"] != "brier" or protocol["success_delta"] != 0:
            raise ValueError("pilot scoring contract is lower paired Brier")
        if protocol["evidence_class"] not in {"fixture", "diagnostic", "fresh_pilot"}:
            raise ValueError("unsupported evidence class; not a promotion run")
        if protocol.get("final_test_access", False):
            raise ValueError("this runner does not open final holdouts")
        if not plans or len({p["id"] for p in plans}) != len(plans):
            raise ValueError("unique candidate IDs required")
        for p in plans:
            identifier(p["id"])
            if p["id"] == "parent" or p["parent_id"] != protocol["parent_id"]:
                raise ValueError("all candidates must share one parent")
            if p["changed_stage"] not in {"raw_indicator_signal", "prediction"}:
                raise ValueError("adapter supports only signal or training changes")
            changes = [s for s in p["baseline_components"]
                       if p["baseline_components"][s] != p["candidate_components"].get(s)]
            expected = {"raw_data", "raw_indicator_signal", "prediction", "objective", "pnl"}
            if set(p["baseline_components"]) != expected or set(p["candidate_components"]) != expected or changes != [p["changed_stage"]]:
                raise ValueError("one declared causal-stage change required")
            if p["baseline_components"] != plans[0]["baseline_components"]:
                raise ValueError("baseline component hashes differ across candidates")
        if not re.fullmatch(r"[0-9a-f]{64}", protocol["evaluator_sha256"]):
            raise ValueError("trusted evaluator code hash required")
        evaluator_source = Path(protocol["evaluator_source_path"])
        if file_hash(evaluator_source) != protocol["evaluator_sha256"]:
            raise ValueError("evaluator source does not match its commitment")
        root = Path(root)
        root.mkdir(parents=True, exist_ok=False)  # Permanent, non-reusable claim.
        r = cls(root)
        with r.journal.locked():
            frozen = dict(protocol=protocol, plans=plans, data_sha256=file_hash(data_path),
                          data_path=str(Path(data_path).resolve()), runner_sha256=file_hash(__file__))
            (root / "source").mkdir()
            shutil.copyfile(__file__, root / "source/market_rsi.py")
            shutil.copyfile(evaluator_source, root / "source/learner.py")
            fresh_json(root / "contract.json", frozen)
            r.journal.append("created", {"contract_hash": digest(frozen)})
        return r

    def verify(self, data_path):
        records = self.journal.read()
        contract = load_json(self.root / "contract.json")
        if not records or records[0]["payload"]["contract_hash"] != digest(contract):
            raise ValueError("contract changed")
        if file_hash(data_path) != contract["data_sha256"] or file_hash(__file__) != contract["runner_sha256"]:
            raise ValueError("reserved input or runner mutated")
        return contract

    def commit_forecasts(self, data_path, forecasts, trades, single_actor):
        with self.journal.locked():
            c = self.verify(data_path)
            actors, candidates = c["protocol"]["actors"], [p["id"] for p in c["plans"]]
            if set(forecasts) != set(actors) or single_actor not in actors:
                raise ValueError("forecaster identity mismatch")
            for predictions in forecasts.values():
                if set(predictions) != set(candidates):
                    raise ValueError("every forecaster must forecast every candidate")
                for p in predictions.values():
                    probability(p)
            market = Market(candidates, actors)
            for t in trades:
                market.buy(**t)
            prices = {p: market.price(p) for p in candidates}
            averages = {p: sum(forecasts[a][p] for a in actors) / len(actors) for p in candidates}
            frozen = dict(forecasts=forecasts, trades=trades, market_prices=prices,
                          single_actor=single_actor, choices=dict(single=choose(forecasts[single_actor]),
                          average=choose(averages), market=choose(prices)))
            fresh_json(self.root / "forecasts.json", frozen)
            self.journal.append("forecasts_committed", {"hash": digest(frozen)})
            return frozen

    def evaluate(self, data_path, evaluator):
        """Trusted callable fits models and returns row probabilities + metadata.

        It runs only after forecast commitment. Arbitrary agent Python is NOT
        supported here: an external sandbox adapter remains a separate gate.
        """
        with self.journal.locked():
            c = self.verify(data_path)
            if evaluator_hash(evaluator) != c["protocol"]["evaluator_sha256"]:
                raise ValueError("evaluator source changed after commitment")
            f = load_json(self.root / "forecasts.json")
            records = self.journal.read()
            commits = [r for r in records if r["event"] == "forecasts_committed"]
            if len(commits) != 1 or commits[0]["payload"]["hash"] != digest(f):
                raise ValueError("forecast commitment invalid")
            if any(r["event"] == "evaluation_started" for r in records):
                raise ValueError("round already started; never retry for score")
            self.journal.append("evaluation_started", {})
            rows = load_json(data_path)
            audit = audit_rows(rows, c["protocol"]["features"], c["protocol"]["horizon_ms"])
            if any(r["split"] == "final" for r in rows):
                raise ValueError("final rows cannot enter a development round")
            train = [r for r in rows if r["split"] == "train"]
            dev = [r for r in rows if r["split"] == "dev"]
            visible = [{k: v for k, v in r.items() if k not in {"label", "label_end_ms"}} for r in dev]
            result, outcomes = {}, {}
            candidates = [{"id": "parent", "config": c["protocol"]["parent_config"]}] + c["plans"]
            for plan in candidates:
                try:
                    predictions, metadata = evaluator(copy.deepcopy(plan["config"]), copy.deepcopy(train), copy.deepcopy(visible))
                    score = metrics(dev, predictions, c["protocol"]["alert_fraction"])
                    by_game = {g: metrics([r for r in dev if r["game_id"] == g],
                                         {r["row_id"]: predictions[r["row_id"]] for r in dev if r["game_id"] == g},
                                         c["protocol"]["alert_fraction"])
                               for g in sorted({r["game_id"] for r in dev})}
                    by_date = {d: metrics([r for r in dev if r["date"] == d],
                                         {r["row_id"]: predictions[r["row_id"]] for r in dev if r["date"] == d},
                                         c["protocol"]["alert_fraction"])
                               for d in sorted({r["date"] for r in dev})}
                    result[plan["id"]] = dict(status="completed", metrics=score, by_game=by_game,
                                              by_date=by_date, metadata=metadata)
                    fresh_json(self.root / (plan["id"] + "-predictions.json"), predictions)
                except Exception as exc:
                    result[plan["id"]] = dict(status="failed", error_type=type(exc).__name__,
                                              error=str(exc)[:400])
                # Integrity failures stop the round, not just the candidate.
                self.verify(data_path)
                if digest(load_json(self.root / "forecasts.json")) != commits[0]["payload"]["hash"]:
                    raise ValueError("forecasts mutated during evaluation")
                if evaluator_hash(evaluator) != c["protocol"]["evaluator_sha256"]:
                    raise ValueError("evaluator source changed during evaluation")
            # Every candidate is evaluated even if the market does not choose it.
            parent = result["parent"]
            for p in c["plans"]:
                child = result[p["id"]]
                outcomes[p["id"]] = (int(child["metrics"]["brier"] < parent["metrics"]["brier"])
                                     if parent["status"] == child["status"] == "completed" else None)
            forecast_scores = {a: {p: ((probability(v) - outcomes[p]) ** 2 if outcomes[p] is not None else None)
                                   for p, v in fs.items()} for a, fs in f["forecasts"].items()}
            market = Market([p["id"] for p in c["plans"]], c["protocol"]["actors"])
            for t in f["trades"]:
                market.buy(**t)
            complete = {p: x["metrics"]["brier"] for p, x in result.items() if x["status"] == "completed"}
            # Unknown best if any admitted candidate failed; don't erase failures.
            regret = {name: complete[choice] - min(complete.values())
                      if len(complete) == len(result) else None for name, choice in f["choices"].items()}
            summary = dict(evidence_class=c["protocol"]["evidence_class"], audit=audit, candidates=result,
                           outcomes=outcomes, choices=f["choices"], selection_regret_brier=regret,
                           forecast_brier=forecast_scores, virtual_settlement=market.settle(outcomes),
                           pnl_claim=False, promotion_eligible=False)
            fresh_json(self.root / "results.json", summary)
            self.journal.append("evaluation_completed", {"results_hash": digest(summary)})
            return summary


class Budget:
    """New external spend only; reservations != charges; unknown jobs stay held."""
    def __init__(self, cap):
        self.cap = Decimal(str(cap))
        if not self.cap.is_finite() or self.cap < 0:
            raise ValueError("invalid cap")
        self.jobs = {}

    def reserve(self, job, upper):
        identifier(job)
        amount = Decimal(str(upper))
        if job in self.jobs or not amount.is_finite() or amount < 0:
            raise ValueError("invalid or reused budget claim")
        snapshot = self.snapshot()
        if amount > Decimal(snapshot["available"]):
            raise ValueError("hard cap would be exceeded")
        self.jobs[job] = dict(reserved=amount, actual=None, estimate=None, status="reserved")

    def reconcile(self, job, actual=None, estimate=None):
        record = self.jobs[job]
        if record["status"] == "reconciled":
            raise ValueError("duplicate reconciliation")
        if estimate is not None:
            value = Decimal(str(estimate))
            if not value.is_finite() or value < 0:
                raise ValueError("invalid estimate")
            record["estimate"] = value
        if actual is not None:
            value = Decimal(str(actual))
            if not value.is_finite() or value < 0 or value > record["reserved"]:
                raise ValueError("charge exceeds its reservation or is invalid")
            record.update(actual=value, reserved=Decimal(0), status="reconciled")

    def snapshot(self):
        actual = sum((r["actual"] or Decimal(0) for r in self.jobs.values()), Decimal(0))
        reserved = sum((r["reserved"] for r in self.jobs.values()), Decimal(0))
        estimates = sum((r["estimate"] or Decimal(0) for r in self.jobs.values()), Decimal(0))
        return dict(actual=str(actual), reserved=str(reserved), estimated=str(estimates),
                    available=str(self.cap - actual - reserved))
