"""A stricter overnight envelope on the original ledger; no new allowance."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import time

from edgar_forecast_budget import BudgetStop, TOTAL_CAP
from edgar_forecast_full_budget import FullBudget, FULL_MODEL_CAP, MODELS


def history_snapshot(db, max_rowid=None):
    if max_rowid is None:
        max_rowid = db.execute("SELECT COALESCE(MAX(rowid),0) FROM requests").fetchone()[0]
    rows = db.execute("SELECT rowid,id,model,reserved,charged,status FROM requests "
                      "WHERE rowid<=? ORDER BY rowid", (max_rowid,)).fetchall()
    return {"max_rowid": max_rowid, "request_count": len(rows),
            "charged_nano_usd": sum(row[4] for row in rows),
            "rows_sha256": hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()}


def utc_epoch(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Exact UTC deadline required")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class NightBudget(FullBudget):
    def __init__(self, path, *, baseline, deadline_utc, clock=time.time, monotonic=time.monotonic,
                 captured_deadline=None, additional_cap_nano_usd=20_000_000_000, runtime_binding=None):
        if type(additional_cap_nano_usd) is not int or additional_cap_nano_usd < 1:
            raise ValueError("Explicit additional ceiling may only narrow existing USD20 limit")
        if additional_cap_nano_usd > 20_000_000_000:
            if type(runtime_binding) is not dict:
                raise ValueError("Source-bound approved24/25 runtime required above legacy USD20")
            # Validate before opening a ledger. Preflight is read-only and never
            # constructs a NightBudget, so this does not create an owner cycle.
            from earnings_capacity_runtime import preflight_runtime
            from earnings_open_fresh_grant import authorized_cumulative_cap
            runtime = preflight_runtime(runtime_binding)
            if (authorized_cumulative_cap(runtime) != additional_cap_nano_usd
                    or runtime["additional_cap_nano_usd"] != additional_cap_nano_usd
                    or str(path) != runtime["ledger"] or Path(path).resolve() != Path(path)
                    or runtime["baseline"] != baseline or runtime["cutoff_utc"] != deadline_utc):
                raise ValueError("Approved runtime ledger/history/cutoff/cumulative allowance drift")
        self.additional_cap_nano_usd = additional_cap_nano_usd
        if (set(baseline) != {"max_rowid", "request_count", "charged_nano_usd", "rows_sha256"}
                or any(type(baseline[k]) is not int or baseline[k] < 0
                       for k in ("max_rowid", "request_count", "charged_nano_usd"))
                or not isinstance(baseline["rows_sha256"], str)
                or len(baseline["rows_sha256"]) != 64):
            raise ValueError("Frozen prior-history identity required")
        self.baseline = dict(baseline)
        self.deadline = utc_epoch(deadline_utc)
        self.clock = clock
        self.monotonic = monotonic
        self.monotonic_deadline = monotonic() + max(0, self.deadline - clock())
        if captured_deadline is not None:
            if type(captured_deadline) not in (int, float) or not math.isfinite(captured_deadline) or captured_deadline < 0:
                raise ValueError("Finite original monotonic deadline required")
            self.monotonic_deadline = min(self.monotonic_deadline, captured_deadline)
        super().__init__(path)

    def active(self):
        super().active()
        self._boundary()

    def _boundary(self):
        if history_snapshot(self.db, self.baseline["max_rowid"]) != self.baseline:
            raise BudgetStop("Prior history changed; no refund or reset")
        if self.clock() >= self.deadline or self.monotonic() >= self.monotonic_deadline:
            raise BudgetStop("Overnight deadline reached")

    def check_reserved(self, request_id, model, amount):
        """Read-only check of this sole in-flight loan; never new dispatch credit."""
        if (type(request_id) is not str or not request_id or type(model) is not str or model not in MODELS
                or type(amount) is not int or amount <= 0):
            raise ValueError("Exact own in-flight reservation required")
        with self.transaction():
            if self.db.execute("SELECT cap,model_cap,blocked FROM config WHERE id=1").fetchone() != (
                    TOTAL_CAP, FULL_MODEL_CAP, 0):
                raise BudgetStop("In-flight accounting configuration changed")
            pending = self.db.execute("SELECT id,model,reserved,charged,status FROM requests "
                "WHERE status NOT IN ('settled','settled_upper_bound')").fetchall()
            if pending != [(request_id, model, amount, 0, "reserved")]:
                raise BudgetStop("Only this exact sole reserved request may dispatch")
            self._boundary()
            total, same = self.db.execute("SELECT COALESCE(SUM(charged),0),"
                "COALESCE(SUM(CASE WHEN model=? THEN charged ELSE 0 END),0) FROM requests", (model,)).fetchone()
            if (total + amount > TOTAL_CAP or same + amount > FULL_MODEL_CAP
                    or total - self.baseline["charged_nano_usd"] + amount > self.additional_cap_nano_usd):
                raise BudgetStop("In-flight original budget ceiling changed")

    def reserve(self, request_id, model, amount):
        if (model not in MODELS or not isinstance(request_id, str) or not request_id
                or type(amount) is not int or amount <= 0):
            raise ValueError("Invalid full-batch model/request/reservation")
        # One transaction owns ALL checks and the insertion. Do not nest reserve().
        with self.transaction():
            self.active()
            if self.db.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone():
                raise BudgetStop("Request already used; retry prohibited")
            total, same = self.db.execute("SELECT COALESCE(SUM(charged),0),"
                "COALESCE(SUM(CASE WHEN model=? THEN charged ELSE 0 END),0) FROM requests", (model,)).fetchone()
            if total + amount > TOTAL_CAP or same + amount > FULL_MODEL_CAP:
                raise BudgetStop("Cumulative full-batch budget ceiling")
            if total - self.baseline["charged_nano_usd"] + amount > self.additional_cap_nano_usd:
                raise BudgetStop("Additional overnight USD20 ceiling" if self.additional_cap_nano_usd == 20_000_000_000
                                 else "Additional runtime allowance ceiling")
            self.db.execute("INSERT INTO requests VALUES (?,?,?,0,'reserved')", (request_id, model, amount))

    def summary(self):
        result = super().summary()
        result.update(night_cap_usd=20 if self.additional_cap_nano_usd == 20_000_000_000
                      else self.additional_cap_nano_usd / 1e9,
            night_charged_upper_bound_usd=result["charged_upper_bound_usd"] - self.baseline["charged_nano_usd"] / 1e9,
            prior_history_sha256=self.baseline["rows_sha256"], deadline_epoch=self.deadline)
        return result


class DeadlineHTTP:
    """Clip each original, retry-free HTTP call to the actual remaining window."""
    def __init__(self, client, *, deadline_utc, rollout_seconds, clock=time.time, monotonic=time.monotonic,
                 captured_deadline=None):
        if type(rollout_seconds) not in (int, float) or rollout_seconds <= 0:
            raise ValueError("Positive rollout time required")
        self.client, self.clock, self.monotonic = client, clock, monotonic
        self.deadline = utc_epoch(deadline_utc)
        self.global_monotonic_deadline = monotonic() + max(0, self.deadline - clock())
        if captured_deadline is not None:
            self.global_monotonic_deadline = min(self.global_monotonic_deadline, captured_deadline)
        self.rollout_deadline = monotonic() + rollout_seconds
        self.original_timeout = client.timeout

    def post(self, path, payload):
        now = self.monotonic()
        remaining = min(self.deadline - self.clock(), self.global_monotonic_deadline - now,
                        self.rollout_deadline - now)
        if remaining <= 0:
            raise BudgetStop("Actual dispatch time boundary reached")
        self.client.timeout = min(self.original_timeout, remaining)
        return self.client.post(path, payload)
