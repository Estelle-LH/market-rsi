"""Durable new-experiment accounting. A reservation is never a charge.

Provider-metered quantities priced at frozen rates are distinct from invoices.
Their unused reservation can be released only after a terminal usage receipt.
No networking or credential access in this module.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from market_rsi import Journal, canonical, digest, fresh_json, identifier, load_json


def money(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not money")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("invalid nonnegative dollar amount")
    return amount


class PaidBudget:
    def __init__(self, root):
        self.root = Path(root)
        self.journal = Journal(root)

    @classmethod
    def create(cls, root, authorization):
        if set(authorization) != {"experiment_id", "cap_usd", "target_usd", "buckets_usd", "authority"}:
            raise ValueError("invalid authorization fields")
        identifier(authorization["experiment_id"])
        cap = money(authorization["cap_usd"])
        if money(authorization["target_usd"]) > cap or not authorization["authority"]:
            raise ValueError("invalid spending target or missing authority")
        if not authorization["buckets_usd"] or sum(map(money, authorization["buckets_usd"].values())) != cap:
            raise ValueError("allocations must add to the combined hard cap")
        for key in authorization["buckets_usd"]:
            identifier(key)
        root = Path(root)
        root.mkdir(parents=True, exist_ok=False)
        budget = cls(root)
        with budget.journal.locked():
            fresh_json(root / "authorization.json", authorization)
            budget.journal.append("authorized", {"authorization_sha256": digest(authorization)})
        return budget

    def _state(self):
        auth = load_json(self.root / "authorization.json")
        records = self.journal.read()
        if not records or records[0]["event"] != "authorized" or records[0]["payload"] != {"authorization_sha256": digest(auth)}:
            raise ValueError("authorization integrity failure")
        jobs = {}
        allocations = {key: money(value) for key, value in auth["buckets_usd"].items()}
        for record in records[1:]:
            kind, payload = record["event"], record["payload"]
            if kind == "allocation_transfer":
                if set(payload) != {"from_bucket", "to_bucket", "usd", "authority"}:
                    raise ValueError("invalid allocation transfer")
                source, target, amount = payload["from_bucket"], payload["to_bucket"], money(payload["usd"])
                if (source == target or source not in allocations or target not in allocations
                        or amount <= 0 or not isinstance(payload["authority"], str)
                        or not payload["authority"].strip() or len(payload["authority"]) > 1000):
                    raise ValueError("invalid allocation transfer")
                occupied = Decimal(0)
                for job in jobs.values():
                    if job["bucket"] != source:
                        continue
                    if job["state"] in {"reserved", "dispatched"}:
                        occupied += money(job["upper_usd"])
                    elif job["invoice_usd"] is not None:
                        occupied += money(job["invoice_usd"])
                    elif job["state"] == "metered_terminal":
                        occupied += money(job["metered_usd"])
                    elif job["state"] == "uncertain_terminal":
                        occupied += money(job["uncertain_upper_usd"])
                if amount > allocations[source] - occupied:
                    raise ValueError("allocation transfer exceeds source availability")
                allocations[source] -= amount
                allocations[target] += amount
                continue
            job = payload["job_id"]
            if kind == "reserved":
                if job in jobs:
                    raise ValueError("reused job claim")
                jobs[job] = dict(payload, state="reserved", metered_usd=None,
                                 uncertain_upper_usd=None, invoice_usd=None)
            elif kind == "dispatched":
                if jobs[job]["state"] != "reserved":
                    raise ValueError("duplicate dispatch")
                jobs[job]["state"] = "dispatched"
            elif kind == "metered_terminal":
                if jobs[job]["state"] != "dispatched":
                    raise ValueError("terminal receipt without one dispatch")
                if digest(load_json(self.root / f"{job}.metering.json")) != payload["receipt_sha256"]:
                    raise ValueError("metering receipt integrity failure")
                jobs[job].update(state="metered_terminal", metered_usd=payload["metered_usd"],
                                 receipt_sha256=payload["receipt_sha256"])
            elif kind == "uncertain_terminal_upper_bound":
                if jobs[job]["state"] != "dispatched":
                    raise ValueError("uncertain terminal accounting requires one dispatch")
                receipt = load_json(self.root / f"{job}.uncertain.json")
                if (digest(receipt) != payload["receipt_sha256"]
                        or payload["upper_usd"] != jobs[job]["upper_usd"]):
                    raise ValueError("uncertain terminal receipt integrity failure")
                jobs[job].update(state="uncertain_terminal",
                                 uncertain_upper_usd=payload["upper_usd"],
                                 receipt_sha256=payload["receipt_sha256"])
            elif kind == "cancelled_before_dispatch":
                if jobs[job]["state"] != "reserved":
                    raise ValueError("cannot cancel a possibly paid request")
                jobs[job].update(state="cancelled_before_dispatch", metered_usd="0")
            elif kind == "invoice":
                if (jobs[job]["state"] not in {"metered_terminal", "uncertain_terminal"}
                        or jobs[job]["invoice_usd"] is not None):
                    raise ValueError("invalid or duplicate invoice")
                jobs[job]["invoice_usd"] = payload["invoice_usd"]
            else:
                raise ValueError("unknown budget event")
        if sum(allocations.values()) != money(auth["cap_usd"]):
            raise ValueError("allocation integrity failure")
        return auth, jobs, allocations

    def _snapshot(self):
        auth, jobs, allocations = self._state()
        meter = invoice = effective = reserved = Decimal(0)
        buckets = {key: {"effective_usd": Decimal(0), "reserved_usd": Decimal(0)}
                   for key in allocations}
        for job in jobs.values():
            metered = money(job["metered_usd"]) if job["metered_usd"] is not None else Decimal(0)
            uncertain = (money(job["uncertain_upper_usd"])
                         if job["uncertain_upper_usd"] is not None else Decimal(0))
            invoiced = money(job["invoice_usd"]) if job["invoice_usd"] is not None else None
            charge = (metered if job["state"] == "metered_terminal" else uncertain) if invoiced is None else invoiced
            hold = money(job["upper_usd"]) if job["state"] in {"reserved", "dispatched"} else Decimal(0)
            meter += metered
            invoice += invoiced or Decimal(0)
            effective += charge
            reserved += hold
            buckets[job["bucket"]]["effective_usd"] += charge
            buckets[job["bucket"]]["reserved_usd"] += hold
        for key, values in buckets.items():
            values["available_usd"] = allocations[key] - sum(values.values())
            values["allocation_usd"] = allocations[key]
        return dict(experiment_id=auth["experiment_id"], cap_usd=str(money(auth["cap_usd"])),
                    metered_usd=str(meter), invoiced_usd=str(invoice),
                    effective_cost_usd=str(effective), reserved_usd=str(reserved),
                    available_usd=str(money(auth["cap_usd"]) - effective - reserved),
                    # An unmetered dispatch must not disappear from this check.
                    # Unsent holds also remain pending until explicitly cancelled.
                    invoice_reconciliation_complete=all(
                        j["state"] == "cancelled_before_dispatch" or
                        (j["state"] in {"metered_terminal", "uncertain_terminal"}
                         and j["invoice_usd"] is not None)
                        for j in jobs.values()),
                    jobs=jobs, buckets={k: {n: str(v) for n, v in values.items()}
                                        for k, values in buckets.items()})

    def snapshot(self):
        with self.journal.locked():
            return self._snapshot()

    def transfer_allocation(self, from_bucket, to_bucket, usd, authority):
        """Append one explicitly authorized bucket transfer; never change the cap."""
        amount = money(usd)
        if (amount <= 0 or not isinstance(authority, str)
                or not authority.strip() or len(authority) > 1000):
            raise ValueError("positive transfer and explicit authority required")
        with self.journal.locked():
            state = self._snapshot()
            if (from_bucket == to_bucket or from_bucket not in state["buckets"]
                    or to_bucket not in state["buckets"]
                    or amount > money(state["buckets"][from_bucket]["available_usd"])):
                raise ValueError("transfer exceeds available source allocation")
            self.journal.append("allocation_transfer", {
                "from_bucket": from_bucket, "to_bucket": to_bucket,
                "usd": str(amount), "authority": authority})

    def reserve(self, job_id, bucket, upper_usd, provider, input_sha256):
        identifier(job_id)
        upper = money(upper_usd)
        if not provider or len(input_sha256) != 64 or any(c not in "0123456789abcdef" for c in input_sha256):
            raise ValueError("provider and input hash required")
        with self.journal.locked():
            state = self._snapshot()
            if job_id in state["jobs"] or bucket not in state["buckets"]:
                raise ValueError("reused job ID or unknown bucket")
            if upper > Decimal(state["available_usd"]) or upper > Decimal(state["buckets"][bucket]["available_usd"]):
                raise ValueError("protected allocation or global hard cap would be exceeded")
            self.journal.append("reserved", dict(job_id=job_id, bucket=bucket, upper_usd=str(upper),
                                                  provider=provider, input_sha256=input_sha256))

    def dispatch(self, job_id):
        with self.journal.locked():
            _, jobs, _ = self._state()
            if jobs[job_id]["state"] != "reserved":
                raise ValueError("not dispatchable; never retry this job ID")
            self.journal.append("dispatched", {"job_id": job_id})

    def cancel_before_dispatch(self, job_id):
        with self.journal.locked():
            _, jobs, _ = self._state()
            if jobs[job_id]["state"] != "reserved":
                raise ValueError("a dispatched request must be reconciled, not cancelled as free")
            self.journal.append("cancelled_before_dispatch", {"job_id": job_id})

    def settle_metered(self, job_id, metered_usd, terminal_receipt):
        value = money(metered_usd)
        if not terminal_receipt or terminal_receipt.get("terminal") is not True:
            raise ValueError("terminal usage evidence required")
        with self.journal.locked():
            _, jobs, _ = self._state()
            job = jobs[job_id]
            if job["state"] != "dispatched" or value > money(job["upper_usd"]):
                raise ValueError("invalid terminal state or metered cost above bound; audit before continuing")
            fresh_json(self.root / f"{job_id}.metering.json", terminal_receipt)
            self.journal.append("metered_terminal", dict(job_id=job_id, metered_usd=str(value),
                                                         receipt_sha256=digest(terminal_receipt)))

    def settle_uncertain_at_upper(self, job_id, terminal_local_receipt):
        """Close a reaped local timeout without pretending remote usage is known.

        The entire reserved upper bound becomes effective cost until an invoice
        replaces it.  The same job ID remains terminal and can never be retried.
        """
        expected = {"terminal_local", "process_reaped", "remote_usage_unknown",
                    "automatic_retry", "evidence_sha256", "note"}
        if (not isinstance(terminal_local_receipt, dict)
                or set(terminal_local_receipt) != expected
                or terminal_local_receipt["terminal_local"] is not True
                or terminal_local_receipt["process_reaped"] is not True
                or terminal_local_receipt["remote_usage_unknown"] is not True
                or terminal_local_receipt["automatic_retry"] is not False
                or not isinstance(terminal_local_receipt["note"], str)
                or not terminal_local_receipt["note"].strip()
                or not isinstance(terminal_local_receipt["evidence_sha256"], str)
                or len(terminal_local_receipt["evidence_sha256"]) != 64
                or any(c not in "0123456789abcdef"
                       for c in terminal_local_receipt["evidence_sha256"])):
            raise ValueError("verified local termination and unknown remote usage required")
        with self.journal.locked():
            _, jobs, _ = self._state()
            job = jobs[job_id]
            if job["state"] != "dispatched":
                raise ValueError("only one unresolved dispatched job may be conservatively closed")
            fresh_json(self.root / f"{job_id}.uncertain.json", terminal_local_receipt)
            self.journal.append("uncertain_terminal_upper_bound", {
                "job_id": job_id, "upper_usd": job["upper_usd"],
                "receipt_sha256": digest(terminal_local_receipt)})

    def record_invoice(self, job_id, invoice_usd, evidence_sha256):
        value = money(invoice_usd)
        if len(evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in evidence_sha256):
            raise ValueError("invoice evidence hash required")
        with self.journal.locked():
            _, jobs, _ = self._state()
            job = jobs[job_id]
            if (job["state"] not in {"metered_terminal", "uncertain_terminal"}
                    or job["invoice_usd"] is not None):
                raise ValueError("invalid invoice state")
            # Record even an unexpectedly high invoice; negative availability
            # then blocks every new reservation rather than hiding the overrun.
            self.journal.append("invoice", dict(job_id=job_id, invoice_usd=str(value),
                                                evidence_sha256=evidence_sha256))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args()
    if args.initialize:
        budget = PaidBudget.create(args.root, {
            "experiment_id": "kalshi-research-glm53-20260907-01", "cap_usd": "200", "target_usd": "100",
            "buckets_usd": {"setup": "10", "learning": "120", "final": "50", "repair": "20"},
            "authority": "User authorized $100-200 for the whole new experiment on 2026-09-07; active PILOT_PROTOCOL_2026-09-07.md",
        })
    else:
        budget = PaidBudget(args.root)
    print(canonical(budget.snapshot()))
