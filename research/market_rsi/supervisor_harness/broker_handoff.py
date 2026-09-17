"""Host-mediated A -> B -> reviewed-feedback canary handoff.

This is a transport/provenance component, not a GLM authorship or E2B
isolation attestation. It intentionally admits only a zero-cost synthetic
public task until a separately versioned scientific order policy exists.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier


A_DECISION = "/tmp/market-controller/decision.json"
B_ORDER = "/tmp/market-researcher/order.json"
B_RESULT = "/tmp/market-researcher/result.json"
A_FEEDBACK = "/tmp/market-controller/feedback.json"
MAX_MESSAGE_BYTES = 64 * 1024


def _sha(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("lowercase SHA256 required")
    return value


def _owned_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MESSAGE_BYTES:
        raise ValueError("missing, symlinked or oversized host receipt")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("host receipt must be an object")
    return value


class BrokerHandoff:
    def __init__(self, *, controller_sandbox, researcher_sandbox, state,
                 cycle_id: str, input_sha256: str, receipt_root: Path):
        identifier(cycle_id)
        _sha(input_sha256)
        if (not isinstance(controller_sandbox.sandbox_id, str)
                or not isinstance(researcher_sandbox.sandbox_id, str)
                or not controller_sandbox.sandbox_id
                or not researcher_sandbox.sandbox_id
                or controller_sandbox.sandbox_id == researcher_sandbox.sandbox_id):
            raise ValueError("observed A and B sandbox IDs must be distinct")
        self.controller = controller_sandbox
        self.researcher = researcher_sandbox
        self.state = state
        self.cycle_id = cycle_id
        self.input_sha256 = input_sha256
        self.root = Path(receipt_root)
        if self.root.exists() or self.root.is_symlink():
            raise FileExistsError("fresh handoff receipt root required")
        self._require_active()
        self.root.mkdir(mode=0o700)
        self.source_sha256 = file_hash(__file__)
        self.stage = "await_decision"

    def _require_active(self) -> None:
        if self.state.snapshot()["active_cycle"] != self.cycle_id:
            raise ValueError("supervisor cycle is not active")

    def _require_source(self) -> None:
        if file_hash(__file__) != self.source_sha256:
            raise ValueError("handoff source changed during cycle")

    def _verified_order(self) -> dict:
        attempt = _owned_json(self.root / "decision-attempt.json")
        claim = _owned_json(self.root / "decision-claim.json")
        raw_record = _owned_json(self.root / "raw-decision.json")
        raw = raw_record.get("raw_utf8")
        if (not isinstance(raw, str)
                or claim.get("attempt_sha256") != digest(attempt)
                or claim.get("raw_bytes_sha256") != hashlib.sha256(raw.encode()).hexdigest()):
            raise ValueError("host raw controller decision changed")
        decision = json.loads(raw)
        if claim.get("decision_sha256") != digest(decision):
            raise ValueError("host parsed controller decision changed")
        order = _owned_json(self.root / "order.json")
        delivery = _owned_json(self.root / "order-delivery.json")
        if (order.get("decision_sha256") != claim["decision_sha256"]
                or delivery.get("order_sha256") != digest(order)
                or delivery.get("destination_sandbox_id") != self.researcher.sandbox_id
                or delivery.get("guest_path") != B_ORDER):
            raise ValueError("host order or delivery receipt changed")
        return order

    def freeze_and_deliver(self) -> dict:
        """Accept the first A-authored synthetic order, unchanged, and send to B."""
        if self.stage != "await_decision":
            raise ValueError("decision already attempted")
        self._require_source()
        self._require_active()
        self.stage = "failed"  # even a malformed first order cannot be retried
        attempt = {"schema": "market_broker_handoff_attempt_v1",
                   "cycle_id": self.cycle_id, "input_sha256": self.input_sha256,
                   "controller_sandbox_id": self.controller.sandbox_id,
                   "researcher_sandbox_id": self.researcher.sandbox_id,
                   "source_sha256": self.source_sha256,
                   "decision_path": A_DECISION}
        fresh_json(self.root / "decision-attempt.json", attempt)
        try:
            raw = self.controller.files.read(A_DECISION)
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                raise ValueError("missing or oversized controller decision")
            fresh_json(self.root / "raw-decision.json", {"raw_utf8": raw})
            decision = json.loads(raw)
            if not isinstance(decision, dict):
                raise ValueError("controller decision must be an object")
            required = {"schema", "cycle_id", "input_sha256", "task_id",
                        "task_type", "data_role", "question", "hypothesis",
                        "expected_evidence", "stop_rule", "max_seconds",
                        "cost_bound_usd", "public_text"}
            if set(decision) != required or decision["schema"] != "market_research_decision_v1":
                raise ValueError("exact synthetic decision schema required")
            if (decision["cycle_id"] != self.cycle_id
                    or decision["input_sha256"] != self.input_sha256
                    or decision["task_type"] != "code_canary"
                    or decision["data_role"] != "synthetic_fixture"
                    or decision["cost_bound_usd"] != "0"
                    or type(decision["max_seconds"]) is not int
                    or not 1 <= decision["max_seconds"] <= 30):
                raise ValueError("decision is outside the zero-cost synthetic lane")
            identifier(decision["task_id"])
            if not all(isinstance(decision[name], str) and decision[name].strip()
                       and len(decision[name]) <= 4096 for name in
                       ("question", "hypothesis", "expected_evidence", "stop_rule",
                        "public_text")):
                raise ValueError("decision text must be bounded and nonempty")
            claim = {"schema": "market_broker_decision_claim_v1",
                     "attempt_sha256": digest(attempt),
                     "raw_bytes_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                     "decision_sha256": digest(decision)}
            fresh_json(self.root / "decision-claim.json", claim)
            order = {"schema": "market_broker_researcher_order_v1",
                     "cycle_id": self.cycle_id,
                     "input_sha256": self.input_sha256,
                     "decision_sha256": digest(decision),
                     "task_id": decision["task_id"],
                     "task_type": "code_canary",
                     "data_role": "synthetic_fixture",
                     "public_text": decision["public_text"]}
            self._require_active()
            fresh_json(self.root / "order.json", order)
            self.researcher.files.write(B_ORDER, canonical(order))
            fresh_json(self.root / "order-delivery.json", {
                "schema": "market_broker_order_delivery_v1",
                "order_sha256": digest(order),
                "destination_sandbox_id": self.researcher.sandbox_id,
                "guest_path": B_ORDER})
        except Exception as exc:
            fresh_json(self.root / "decision-failure.json", {
                "schema": "market_broker_decision_failure_v1",
                "attempt_sha256": digest(attempt), "error_type": type(exc).__name__})
            raise
        self.stage = "await_result"
        return order

    def receive_result(self) -> dict:
        """Archive B's untrusted result; independent review is still required."""
        if self.stage != "await_result":
            raise ValueError("researcher result is out of order")
        self._require_source()
        self._require_active()
        self.stage = "failed"
        order = None
        try:
            order = self._verified_order()
            raw = self.researcher.files.read(B_RESULT)
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                raise ValueError("missing or oversized researcher result")
            fresh_json(self.root / "raw-result.json", {"raw_utf8": raw})
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("researcher result must be an object")
            if (set(result) != {"schema", "cycle_id", "order_sha256",
                                "decision_sha256", "task_id", "text_sha256"}
                    or result["schema"] != "market_broker_researcher_result_v1"
                    or result["cycle_id"] != self.cycle_id
                    or result["order_sha256"] != digest(order)
                    or result["decision_sha256"] != order["decision_sha256"]
                    or result["task_id"] != order["task_id"]
                    or result["text_sha256"] != hashlib.sha256(
                        order["public_text"].encode()).hexdigest()):
                raise ValueError("researcher result is not bound to exact order")
            self._require_active()
            fresh_json(self.root / "result.json", result)
            fresh_json(self.root / "result-receipt.json", {
                "schema": "market_broker_result_receipt_v1",
                "raw_bytes_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "result_sha256": digest(result),
                "source_sandbox_id": self.researcher.sandbox_id,
                "independently_verified": False})
        except Exception as exc:
            fresh_json(self.root / "result-failure.json", {
                "schema": "market_broker_result_failure_v1",
                "order_sha256": digest(order) if order is not None else None,
                "error_type": type(exc).__name__})
            raise
        self.stage = "await_review"
        return result

    def deliver_reviewed_feedback(self, review: dict) -> dict:
        """Only a host-owned exact review, never B's self-score, goes back to A."""
        if self.stage != "await_review":
            raise ValueError("feedback before a bound researcher result")
        self._require_source()
        self._require_active()
        self.stage = "failed"  # do not choose a different review after one attempt
        attempt = {"schema": "market_broker_feedback_attempt_v1",
                   "cycle_id": self.cycle_id,
                   "review_sha256": digest(review),
                   "controller_sandbox_id": self.controller.sandbox_id}
        fresh_json(self.root / "feedback-attempt.json", attempt)
        try:
            order = self._verified_order()
            result = _owned_json(self.root / "result.json")
            receipt = _owned_json(self.root / "result-receipt.json")
            raw_result = _owned_json(self.root / "raw-result.json").get("raw_utf8")
            if (receipt.get("result_sha256") != digest(result)
                    or not isinstance(raw_result, str)
                    or receipt.get("raw_bytes_sha256") != hashlib.sha256(
                        raw_result.encode()).hexdigest()
                    or json.loads(raw_result) != result
                    or receipt.get("source_sandbox_id") != self.researcher.sandbox_id):
                raise ValueError("host researcher result or receipt changed")
            if (not isinstance(review, dict)
                    or set(review) != {"schema", "cycle_id", "result_sha256",
                                       "verdict", "reason", "protected_data_opened"}
                    or review["schema"] != "market_broker_independent_review_v1"
                    or review["cycle_id"] != self.cycle_id
                    or review["result_sha256"] != digest(result)
                    or review["verdict"] not in {"accept", "reject"}
                    or not isinstance(review["reason"], str)
                    or not review["reason"].strip()
                    or len(review["reason"]) > 4096
                    or review["protected_data_opened"] is not False):
                raise ValueError("feedback requires exact independent review")
            feedback = {"schema": "market_broker_feedback_v1",
                        "cycle_id": self.cycle_id,
                        "decision_sha256": order["decision_sha256"],
                        "result_sha256": digest(result), "review_sha256": digest(review),
                        "verdict": review["verdict"], "reason": review["reason"]}
            fresh_json(self.root / "review.json", review)
            fresh_json(self.root / "feedback.json", feedback)
            self.controller.files.write(A_FEEDBACK, canonical(feedback))
            fresh_json(self.root / "feedback-delivery.json", {
                "schema": "market_broker_feedback_delivery_v1",
                "feedback_sha256": digest(feedback),
                "destination_sandbox_id": self.controller.sandbox_id,
                "guest_path": A_FEEDBACK})
        except Exception as exc:
            fresh_json(self.root / "feedback-failure.json", {
                "schema": "market_broker_feedback_failure_v1",
                "attempt_sha256": digest(attempt),
                "error_type": type(exc).__name__})
            raise
        self.stage = "complete"
        return feedback
