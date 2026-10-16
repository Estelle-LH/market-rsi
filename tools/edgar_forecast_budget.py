"""Durable, serial EDGAR API pilot budget; amounts are integer nano-dollars."""
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3

TOTAL_CAP = 200_000_000_000
MODEL_CAP = 10_000_000_000


class BudgetStop(RuntimeError):
    pass


class PilotBudget:
    RECONCILIATION_MODEL_CAP = MODEL_CAP

    def __init__(self, path):
        path = Path(path)
        if path.is_symlink() or not path.parent.is_dir():
            raise ValueError("Unsafe or missing budget directory")
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        with self.transaction():
            self.db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, cap INTEGER, model_cap INTEGER, blocked INTEGER)")
            self.db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, model TEXT, reserved INTEGER, charged INTEGER, status TEXT)")
            self.db.execute("CREATE TABLE IF NOT EXISTS reconciliations (request_id TEXT PRIMARY KEY, evidence_sha256 TEXT NOT NULL, prior_status TEXT NOT NULL, prior_charge INTEGER NOT NULL, ceiling INTEGER NOT NULL, policy TEXT NOT NULL, recorded_utc TEXT DEFAULT CURRENT_TIMESTAMP)")
            self.db.execute("INSERT OR IGNORE INTO config VALUES (1, ?, ?, 0)", (TOTAL_CAP, MODEL_CAP))
            if self.db.execute("SELECT cap, model_cap FROM config WHERE id=1").fetchone() != (TOTAL_CAP, MODEL_CAP):
                raise BudgetStop("Existing budget limits differ")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def close(self):
        self.db.close()

    def active(self):
        blocked = self.db.execute("SELECT blocked FROM config WHERE id=1").fetchone()[0]
        pending = self.db.execute("SELECT COUNT(*) FROM requests WHERE status NOT IN ('settled', 'settled_upper_bound')").fetchone()[0]
        if blocked or pending:
            raise BudgetStop("Unresolved request or uncertain charge; no further dispatch")

    def reserve(self, request_id, model, amount):
        if not isinstance(request_id, str) or not request_id or not isinstance(model, str) or not model:
            raise ValueError("Missing request identity")
        if type(amount) is not int or amount <= 0:
            raise ValueError("Reservation must be positive integer nano-dollars")
        with self.transaction():
            self.active()
            if self.db.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone():
                raise BudgetStop("Request identity already used; retry prohibited")
            total, same_model = self.db.execute(
                "SELECT COALESCE(SUM(charged),0), COALESCE(SUM(CASE WHEN model=? THEN charged ELSE 0 END),0) FROM requests",
                (model,)).fetchone()
            if total + amount > TOTAL_CAP or same_model + amount > MODEL_CAP:
                raise BudgetStop("Next request would exceed the pilot or model ceiling")
            self.db.execute("INSERT INTO requests VALUES (?, ?, ?, 0, 'reserved')", (request_id, model, amount))

    def settle(self, request_id, charge):
        if type(charge) is not int or charge < 0:
            raise ValueError("Charge must be nonnegative integer nano-dollars")
        exceeded = False
        with self.transaction():
            row = self.db.execute("SELECT reserved, status FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None or row[1] != "reserved":
                raise BudgetStop("Reservation missing, uncertain or already settled")
            exceeded = charge > row[0]
            self.db.execute("UPDATE requests SET charged=?, status='settled' WHERE id=?", (charge, request_id))
            if exceeded:
                self.db.execute("UPDATE config SET blocked=1 WHERE id=1")
        if exceeded:
            raise BudgetStop("Observed charge exceeded reservation; budget blocked")

    def uncertain(self, request_id):
        with self.transaction():
            row = self.db.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None or row[0] != "reserved":
                raise BudgetStop("No pending reservation")
            self.db.execute("UPDATE requests SET status='uncertain' WHERE id=?", (request_id,))
            self.db.execute("UPDATE config SET blocked=1 WHERE id=1")

    def reconcile_uncertain_at_ceiling(self, request_id, evidence_sha256):
        """Explicit operator action, never an automatic retry or a refund.

        Count the entire reservation as liability. The actual invoice remains
        unknown; preserve its prior state and external evidence in an audit row.
        Only the sole uncertain request may be resolved, not another stop cause.
        """
        if not isinstance(evidence_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256):
            raise ValueError("Reconciliation requires a saved evidence SHA256")
        with self.transaction():
            row = self.db.execute("SELECT reserved, charged, status FROM requests WHERE id=?", (request_id,)).fetchone()
            config = self.db.execute("SELECT cap, model_cap, blocked FROM config WHERE id=1").fetchone()
            if row is None or row[2] != "uncertain" or row[1] != 0 or row[0] <= 0:
                raise BudgetStop("Not an untouched uncertain reservation")
            if config != (TOTAL_CAP, self.RECONCILIATION_MODEL_CAP, 1):
                raise BudgetStop("Budget configuration or stop cause differs")
            if self.db.execute("SELECT 1 FROM requests WHERE id != ? AND status NOT IN ('settled', 'settled_upper_bound')", (request_id,)).fetchone():
                raise BudgetStop("Other unresolved request remains")
            if self.db.execute("SELECT 1 FROM requests WHERE charged > reserved").fetchone():
                raise BudgetStop("Known overcharge cannot be reconciled away")
            total = self.db.execute("SELECT COALESCE(SUM(charged),0) FROM requests").fetchone()[0]
            model_total = self.db.execute("SELECT COALESCE(SUM(charged),0) FROM requests WHERE model=(SELECT model FROM requests WHERE id=?)", (request_id,)).fetchone()[0]
            if total + row[0] > TOTAL_CAP or model_total + row[0] > self.RECONCILIATION_MODEL_CAP:
                raise BudgetStop("Full liability exceeds frozen cap")
            self.db.execute("INSERT INTO reconciliations (request_id, evidence_sha256, prior_status, prior_charge, ceiling, policy) VALUES (?, ?, ?, ?, ?, ?)",
                            (request_id, evidence_sha256, row[2], row[1], row[0], "operator_full_ceiling_actual_charge_unknown"))
            self.db.execute("UPDATE requests SET charged=reserved, status='settled_upper_bound' WHERE id=?", (request_id,))
            self.db.execute("UPDATE config SET blocked=0 WHERE id=1")

    def summary(self):
        charged, reserved, calls = self.db.execute(
            "SELECT COALESCE(SUM(charged),0), COALESCE(SUM(CASE WHEN status NOT IN ('settled', 'settled_upper_bound') THEN reserved ELSE 0 END),0), COUNT(*) FROM requests").fetchone()
        return {"cap_usd": 200, "model_cap_usd": 10, "charged_upper_bound_usd": charged / 1e9,
                "unresolved_reserved_usd": reserved / 1e9, "generation_requests_reserved": calls,
                "blocked": bool(self.db.execute("SELECT blocked FROM config WHERE id=1").fetchone()[0]) or reserved > 0}
