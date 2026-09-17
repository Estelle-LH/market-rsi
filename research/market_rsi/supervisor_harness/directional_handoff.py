"""Zero-paid A -> local broker -> one persistent B transport fixture.

This records host-observed transport boundaries only. It neither starts E2B nor
proves GLM authorship, sandbox isolation, guest event timing, or cleanup.
The caller owns the active supervisor cycle and the eventual live adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from market_rsi import canonical, digest, file_hash, fresh_json, identifier


EXPECTED_HANDOFFS = 20
MAX_MESSAGE_BYTES = 64 * 1024
P95_LIMIT_NS = 2_000_000_000
SINGLE_LEG_LIMIT_NS = 5_000_000_000
B_ORDER_DIR = "/tmp/market-researcher/directional/orders"
B_ACK_DIR = "/tmp/market-researcher/directional/acks"
B_EVENT_DIR = "/tmp/market-researcher/directional/events"


def _sha(value: object) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("lowercase SHA256 required")
    return value


def _raw_json(raw: object) -> tuple[dict, str]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("missing or oversized researcher message")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("researcher message must be an object")
    return value, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _p95_nearest_rank(values: list[int]) -> int | None:
    return sorted(values)[math.ceil(.95 * len(values)) - 1] if values else None


class DirectionalHandoff:
    """Sequence- and hash-bound synthetic transport over one observed B object.

    A is a brokered model session, not another sandbox. Each method is one
    explicit broker boundary; no guest code is executed by this class.
    """

    def __init__(self, *, researcher_sandbox, state, cycle_id: str,
                 input_sha256: str, receipt_root: Path,
                 clock_ns: Callable[[], int] = time.monotonic_ns):
        identifier(cycle_id)
        _sha(input_sha256)
        sandbox_id = getattr(researcher_sandbox, "sandbox_id", None)
        if not isinstance(sandbox_id, str) or not sandbox_id:
            raise ValueError("one observed B sandbox ID required")
        self.researcher = researcher_sandbox
        self.sandbox_id = sandbox_id
        self.state = state
        self.cycle_id = cycle_id
        self.input_sha256 = input_sha256
        self.root = Path(receipt_root)
        self.clock_ns = clock_ns
        self.source_sha256 = file_hash(__file__)
        self._last_ns = -1
        self.next_sequence = 0
        self.stage = "ready"
        self.failure: str | None = None
        self.duplicate_count = 0
        self.timeout_count = 0
        self.current: dict | None = None
        self.samples: list[dict] = []
        self.sent_task_ids: set[str] = set()
        self.receipt_hashes: dict[str, str] = {}
        if self.root.exists() or self.root.is_symlink():
            raise FileExistsError("fresh directional receipt root required")
        self._guard()
        anchor_ns = self._tick()
        self.root.mkdir(mode=0o700)
        self._record("manifest.json", {
            "schema": "market_directional_handoff_manifest_v1",
            "cycle_id": cycle_id, "input_sha256": input_sha256,
            "researcher_sandbox_id": sandbox_id,
            "source_sha256": self.source_sha256,
            "python_runtime": sys.version, "expected_handoffs": EXPECTED_HANDOFFS,
            "host_monotonic_anchor_ns": anchor_ns,
            "host_utc_anchor": datetime.now(timezone.utc).isoformat(),
            "synthetic_only": True, "live_e2b_proven": False,
            "glm_authorship_proven": False, "cleanup_verified": False})

    def _record(self, name: str, value: dict) -> None:
        fresh_json(self.root / name, value)
        self.receipt_hashes[name] = digest(value)

    def _verify_receipts(self) -> None:
        for name, expected_sha in self.receipt_hashes.items():
            path = self.root / name
            if (path.is_symlink() or not path.is_file()
                    or path.stat().st_size > MAX_MESSAGE_BYTES):
                raise ValueError("host handoff receipt missing or unsafe")
            record = json.loads(path.read_bytes())
            if not isinstance(record, dict) or digest(record) != expected_sha:
                raise ValueError("host handoff receipt changed")

    def _tick(self) -> int:
        value = self.clock_ns()
        if type(value) is not int or value < self._last_ns:
            raise ValueError("host monotonic clock regressed or is invalid")
        self._last_ns = value
        return value

    def _guard(self) -> None:
        if self.state.snapshot()["active_cycle"] != self.cycle_id:
            raise ValueError("supervisor cycle is not active")
        if self.researcher.sandbox_id != self.sandbox_id:
            raise ValueError("researcher sandbox identity changed")
        if file_hash(__file__) != self.source_sha256:
            raise ValueError("directional handoff source changed during cycle")
        self._verify_receipts()

    def _require(self, stage: str, sequence: int) -> None:
        if (self.failure is not None or self.stage != stage
                or type(sequence) is not int or sequence != self.next_sequence
                or sequence >= EXPECTED_HANDOFFS):
            reason = ("duplicate_message" if type(sequence) is int
                      and sequence < self.next_sequence else "sequence_or_stage")
            self._fail(reason)
            raise ValueError("directional handoff is duplicate or out of order")
        self._guard()

    def _fail(self, reason: str) -> None:
        if self.failure is None:
            self.failure = reason
            self.duplicate_count += int(reason == "duplicate_message")
            self.timeout_count += int(reason == "TimeoutError")
            self.stage = "failed"
            self._record("failure.json", {
                "schema": "market_directional_handoff_failure_v1",
                "cycle_id": self.cycle_id, "sequence": self.next_sequence,
                "reason": reason, "host_monotonic_ns": self._tick()})

    def send_task(self, sequence: int, task: dict) -> dict:
        """Accept an A-authored synthetic tool argument and deliver it to B."""
        self._require("ready", sequence)
        try:
            if (not isinstance(task, dict)
                    or set(task) != {"schema", "cycle_id", "input_sha256",
                                     "sequence", "task_id", "public_text"}
                    or task["schema"] != "market_directional_task_v1"
                    or task["cycle_id"] != self.cycle_id
                    or task["input_sha256"] != self.input_sha256
                    or type(task["sequence"]) is not int
                    or task["sequence"] != sequence):
                raise ValueError("task is not bound to the current A input and sequence")
            identifier(task["task_id"])
            if task["task_id"] in self.sent_task_ids:
                self._fail("duplicate_message")
                raise ValueError("duplicate A task ID")
            if (not isinstance(task["public_text"], str) or not task["public_text"]
                    or len(task["public_text"].encode()) > 4096):
                raise ValueError("synthetic public text must be bounded and nonempty")
            encoded = canonical(task)
            if len(encoded.encode()) > MAX_MESSAGE_BYTES:
                raise ValueError("oversized task")
            start_ns = self._tick()
            order = {"schema": "market_directional_order_v1",
                     "cycle_id": self.cycle_id, "input_sha256": self.input_sha256,
                     "sequence": sequence, "task_id": task["task_id"],
                     "task_sha256": digest(task), "public_text": task["public_text"]}
            path = f"{B_ORDER_DIR}/{sequence:03d}.json"
            self._record(f"{sequence:03d}-task.json", task)
            self._record(f"{sequence:03d}-order.json", order)
            self._record(f"{sequence:03d}-task-attempt.json", {
                "schema": "market_directional_task_attempt_v1",
                "sequence": sequence, "task_sha256": digest(task),
                "order_sha256": digest(order), "host_start_ns": start_ns,
                "destination_sandbox_id": self.sandbox_id, "guest_path": path})
            self.researcher.files.write(path, canonical(order))
            write_done_ns = self._tick()
            self._record(f"{sequence:03d}-order-delivery.json", {
                "schema": "market_directional_order_delivery_v1",
                "sequence": sequence, "order_sha256": digest(order),
                "destination_sandbox_id": self.sandbox_id,
                "host_write_done_ns": write_done_ns, "guest_path": path})
            self.current = {"sequence": sequence, "task": task, "order": order,
                            "task_start_ns": start_ns, "write_done_ns": write_done_ns}
            self.sent_task_ids.add(task["task_id"])
            self.stage = "await_ack"
            return order
        except Exception as exc:
            self._fail(type(exc).__name__)
            raise

    def receive_ack(self, sequence: int) -> dict:
        """Read B's order-hash acknowledgement, marking the end of handoff."""
        self._require("await_ack", sequence)
        try:
            assert self.current is not None
            read_start_ns = self._tick()
            path = f"{B_ACK_DIR}/{sequence:03d}.json"
            ack, raw_sha = _raw_json(self.researcher.files.read(path))
            read_done_ns = self._tick()
            order = self.current["order"]
            if (set(ack) != {"schema", "cycle_id", "sequence", "order_sha256"}
                    or ack["schema"] != "market_directional_ack_v1"
                    or ack["cycle_id"] != self.cycle_id
                    or type(ack["sequence"]) is not int or ack["sequence"] != sequence
                    or ack["order_sha256"] != digest(order)):
                raise ValueError("B acknowledgement does not bind exact order")
            latency_ns = read_done_ns - self.current["task_start_ns"]
            self._record(f"{sequence:03d}-ack.json", {
                "schema": "market_directional_ack_receipt_v1",
                "sequence": sequence, "ack": ack, "ack_sha256": digest(ack),
                "raw_bytes_sha256": raw_sha, "source_sandbox_id": self.sandbox_id,
                "host_read_start_ns": read_start_ns,
                "host_read_done_ns": read_done_ns,
                "handoff_latency_ns": latency_ns})
            self.current["handoff_latency_ns"] = latency_ns
            self.stage = "await_event"
            return ack
        except Exception as exc:
            self._fail(type(exc).__name__)
            raise

    def receive_event(self, sequence: int) -> dict:
        """Read one B synthetic tool event; B computation precedes this call."""
        self._require("await_event", sequence)
        try:
            assert self.current is not None
            read_start_ns = self._tick()
            path = f"{B_EVENT_DIR}/{sequence:03d}.json"
            event, raw_sha = _raw_json(self.researcher.files.read(path))
            arrival_ns = self._tick()
            order = self.current["order"]
            expected_text_sha = hashlib.sha256(order["public_text"].encode()).hexdigest()
            if (set(event) != {"schema", "cycle_id", "sequence", "task_id",
                              "order_sha256", "tool_name", "input_sha256",
                              "output_sha256", "status"}
                    or event["schema"] != "market_directional_tool_event_v1"
                    or event["cycle_id"] != self.cycle_id
                    or type(event["sequence"]) is not int or event["sequence"] != sequence
                    or event["task_id"] != order["task_id"]
                    or event["order_sha256"] != digest(order)
                    or event["tool_name"] != "hash_public_text"
                    or event["input_sha256"] != expected_text_sha
                    or event["output_sha256"] != expected_text_sha
                    or event["status"] != "ok"):
                raise ValueError("B event does not bind the exact public task")
            self._record(f"{sequence:03d}-event.json", event)
            publish_ns = self._tick()
            self._record(f"{sequence:03d}-event-publication.json", {
                "schema": "market_directional_event_publication_v1",
                "sequence": sequence, "event_sha256": digest(event),
                "raw_bytes_sha256": raw_sha, "source_sandbox_id": self.sandbox_id,
                "host_read_start_ns": read_start_ns,
                "host_arrival_ns": arrival_ns,
                "host_publish_ns": publish_ns})
            self.current.update(event=event, event_read_start_ns=read_start_ns,
                                event_arrival_ns=arrival_ns,
                                event_publish_ns=publish_ns)
            self.stage = "await_a_read"
            return event
        except Exception as exc:
            self._fail(type(exc).__name__)
            raise

    def read_event_for_a(self, sequence: int) -> dict:
        """Return the broker-published B event as A-visible tool data."""
        self._require("await_a_read", sequence)
        try:
            assert self.current is not None
            read_start_ns = self._tick()
            event = self.current["event"]
            if json.loads((self.root / f"{sequence:03d}-event.json").read_text()) != event:
                raise ValueError("broker event changed before A read")
            view = {"schema": "market_directional_a_event_view_v1",
                    "cycle_id": self.cycle_id, "sequence": sequence,
                    "task_sha256": digest(self.current["task"]),
                    "order_sha256": digest(self.current["order"]),
                    "event_sha256": digest(event), "event": event}
            read_done_ns = self._tick()
            # Includes the broker's bounded B-file read and publication; B
            # computation before the host read is deliberately not charged.
            visibility_ns = read_done_ns - self.current["event_read_start_ns"]
            self._record(f"{sequence:03d}-a-read.json", {
                "schema": "market_directional_a_read_receipt_v1",
                "sequence": sequence, "view_sha256": digest(view),
                "event_sha256": digest(event),
                "host_read_start_ns": read_start_ns,
                "host_read_done_ns": read_done_ns,
                "event_visibility_latency_ns": visibility_ns})
            self.samples.append({"sequence": sequence,
                                 "task_id": self.current["task"]["task_id"],
                                 "order_sha256": digest(self.current["order"]),
                                 "event_sha256": digest(event),
                                 "handoff_latency_ns": self.current["handoff_latency_ns"],
                                 "event_visibility_latency_ns": visibility_ns})
            self.current = None
            self.next_sequence += 1
            self.stage = "ready"
            return view
        except Exception as exc:
            self._fail(type(exc).__name__)
            raise

    def finish(self) -> dict:
        """Evaluate the predeclared 20-sample friction criterion, fail closed."""
        if self.stage == "complete":
            raise ValueError("summary already finalized")
        self._guard()
        handoff = [s["handoff_latency_ns"] for s in self.samples]
        visibility = [s["event_visibility_latency_ns"] for s in self.samples]
        complete = (self.failure is None and self.stage == "ready"
                    and self.next_sequence == EXPECTED_HANDOFFS
                    and len(self.samples) == EXPECTED_HANDOFFS
                    and len({s["task_id"] for s in self.samples}) == EXPECTED_HANDOFFS
                    and self.duplicate_count == 0 and self.timeout_count == 0)
        passed = (complete and max(handoff) <= SINGLE_LEG_LIMIT_NS
                  and max(visibility) <= SINGLE_LEG_LIMIT_NS
                  and _p95_nearest_rank(handoff) <= P95_LIMIT_NS
                  and _p95_nearest_rank(visibility) <= P95_LIMIT_NS)
        summary = {"schema": "market_directional_friction_summary_v1",
                   "cycle_id": self.cycle_id, "source_sha256": self.source_sha256,
                   "researcher_sandbox_id": self.sandbox_id,
                   "sample_count": len(self.samples),
                   "expected_count": EXPECTED_HANDOFFS,
                   "missing_count": EXPECTED_HANDOFFS - len(self.samples),
                   "duplicate_count": self.duplicate_count,
                   "timeout_count": self.timeout_count,
                   "failure": self.failure,
                   "handoff_latency_ns": handoff,
                   "event_visibility_latency_ns": visibility,
                   "handoff_p95_ns": _p95_nearest_rank(handoff),
                   "event_visibility_p95_ns": _p95_nearest_rank(visibility),
                   "handoff_max_ns": max(handoff) if handoff else None,
                   "event_visibility_max_ns": max(visibility) if visibility else None,
                   "p95_limit_ns": P95_LIMIT_NS,
                   "single_leg_limit_ns": SINGLE_LEG_LIMIT_NS,
                   "friction_criterion_passed": passed,
                   "synthetic_only": True, "live_e2b_proven": False,
                   "glm_authorship_proven": False, "cleanup_verified": False}
        self._record("summary.json", summary)
        self.stage = "complete"
        return summary
