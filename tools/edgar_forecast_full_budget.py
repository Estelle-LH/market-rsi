"""Explicit full-batch allocation on the existing pilot ledger, never a new cap."""
from pathlib import Path
import re
import sqlite3

from edgar_forecast_budget import PilotBudget, BudgetStop, TOTAL_CAP, MODEL_CAP

FULL_MODEL_CAP = 100_000_000_000
MODELS = ("gpt-5.4-2026-03-05", "gpt-5.5-2026-04-23", "gpt-6.1-sol")


def connect_existing(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Only an existing regular sole budget ledger is allowed")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=5, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


class FullBudget(PilotBudget):
    RECONCILIATION_MODEL_CAP = FULL_MODEL_CAP

    def __init__(self, path):
        self.db = connect_existing(path)
        try:
            self.active()
        except BaseException:
            self.db.close()
            raise

    def active(self):
        super().active()
        if self.db.execute("SELECT cap,model_cap FROM config WHERE id=1").fetchone() != (TOTAL_CAP, FULL_MODEL_CAP):
            raise BudgetStop("Full-batch allocation not activated or changed")

    def reserve(self, request_id, model, amount):
        if model not in MODELS or not isinstance(request_id, str) or not request_id or type(amount) is not int or amount <= 0:
            raise ValueError("Invalid full-batch model/request/reservation")
        with self.transaction():
            self.active()
            if self.db.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone():
                raise BudgetStop("Request already used; retry prohibited")
            total, same = self.db.execute("SELECT COALESCE(SUM(charged),0),COALESCE(SUM(CASE WHEN model=? THEN charged ELSE 0 END),0) FROM requests", (model,)).fetchone()
            if total + amount > TOTAL_CAP or same + amount > FULL_MODEL_CAP:
                raise BudgetStop("Cumulative full-batch budget ceiling")
            self.db.execute("INSERT INTO requests VALUES (?,?,?,0,'reserved')", (request_id, model, amount))

    def summary(self):
        result = super().summary()
        result["model_cap_usd"] = FULL_MODEL_CAP / 1e9
        result["allocation"] = "explicit_full_openai_batch_prior_charges_included"
        return result

    def reconcile_uncertain_at_ceiling(self, request_id, evidence_sha256):
        # Research runtime subclasses (including NightBudget) must never
        # acquire operator reconciliation authority through inheritance.
        if type(self) is not FullBudget:
            raise BudgetStop("Runtime budget cannot perform operator reconciliation")
        return super().reconcile_uncertain_at_ceiling(request_id, evidence_sha256)


def reconcile_at_ceiling(path, request_id, evidence_sha256):
    """Explicit operator-only full-allocation reconciliation; no retry/refund.

    The blocked constructor intentionally cannot admit research. This wrapper
    opens only the existing ledger, then applies all inherited transactional
    checks before booking the whole sole uncertain reservation. Caller owns
    operator authorization, saved evidence and the shared execution lock.
    """
    budget = FullBudget.__new__(FullBudget)
    budget.db = connect_existing(path)
    try:
        budget.reconcile_uncertain_at_ceiling(request_id, evidence_sha256)
        return budget.summary()
    finally:
        budget.close()


def activate(path, batch_sha256, source_commit):
    """One operator activation AFTER old uncertainty is conservatively resolved."""
    if not re.fullmatch(r"[0-9a-f]{64}", batch_sha256) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Exact batch and committed source identities required")
    budget = PilotBudget.__new__(PilotBudget)
    budget.db = connect_existing(path)  # Never initialize a second ledger.
    try:
        with budget.transaction():
            budget.active()
            if budget.db.execute("SELECT cap,model_cap,blocked FROM config WHERE id=1").fetchone() != (TOTAL_CAP, MODEL_CAP, 0):
                raise BudgetStop("Only the unchanged idle pilot allocation can migrate")
            if budget.db.execute("SELECT COALESCE(SUM(charged),0) FROM requests").fetchone()[0] > TOTAL_CAP:
                raise BudgetStop("Prior liability already exceeds global cap")
            if budget.db.execute("SELECT 1 FROM requests GROUP BY model HAVING SUM(charged)>?", (FULL_MODEL_CAP,)).fetchone():
                raise BudgetStop("Prior model liability exceeds new allocation")
            budget.db.execute("CREATE TABLE IF NOT EXISTS full_batch_allocations (batch_sha256 TEXT PRIMARY KEY, source_commit TEXT NOT NULL, old_model_cap INTEGER NOT NULL, new_model_cap INTEGER NOT NULL, total_cap INTEGER NOT NULL)")
            budget.db.execute("INSERT INTO full_batch_allocations VALUES (?,?,?,?,?)", (batch_sha256, source_commit, MODEL_CAP, FULL_MODEL_CAP, TOTAL_CAP))
            budget.db.execute("UPDATE config SET model_cap=? WHERE id=1", (FULL_MODEL_CAP,))
        return {"total_cap_usd":200,"old_model_cap_usd":10,"model_cap_usd":100,"batch_sha256":batch_sha256,"source_commit":source_commit,"prior_charges_preserved":True}
    finally:
        budget.close()
