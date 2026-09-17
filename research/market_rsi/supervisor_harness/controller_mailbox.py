"""Host-owned A-side mailbox for bounded literature calls.

This connects the existing research broker to a *host-observed* controller
sandbox object. It is deliberately transport-only: it does not launch E2B,
call GLM, grant network access, or certify a live controller-led cycle. The
trusted host must claim a cycle in SupervisorGlobalState before serving calls.
"""
from __future__ import annotations

import json
from pathlib import Path

from market_rsi import canonical, digest, fresh_json, identifier


MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_CALLS = 32
GUEST_OUTBOX = "/tmp/market-controller/outbox"
GUEST_INBOX = "/tmp/market-controller/inbox"


class ControllerMailbox:
    def __init__(self, *, controller_sandbox, adapter, state, cycle_id: str,
                 receipt_root: Path, max_calls: int = MAX_CALLS):
        identifier(cycle_id)
        if (controller_sandbox.sandbox_id != adapter.controller_sandbox_id
                or type(max_calls) is not int or not 1 <= max_calls <= MAX_CALLS):
            raise ValueError("host controller identity or call bound is invalid")
        self.sandbox = controller_sandbox
        self.adapter = adapter
        self.state = state
        self.cycle_id = cycle_id
        self.receipt_root = Path(receipt_root)
        if self.receipt_root.exists() or self.receipt_root.is_symlink():
            raise FileExistsError("fresh controller mailbox receipt root required")
        self._require_active_cycle()
        self.receipt_root.mkdir(mode=0o700)
        self.next_index = 0
        self.max_calls = max_calls
        self.terminal = False

    def _require_active_cycle(self) -> None:
        # snapshot also rejects an unjournaled RESEARCH_STATE.md edit.
        if self.state.snapshot()["active_cycle"] != self.cycle_id:
            raise ValueError("supervisor global cycle is not active")

    def serve_next(self, index: int) -> dict:
        """Serve exactly one guest-authored call; only A receives the answer.

        Guest filenames are fixed by the host sequence number. A durable claim
        is written before the broker is invoked. A failed or oversized call is
        terminal for this mailbox, not a license to resample or replay it.
        """
        if self.terminal or type(index) is not int or index != self.next_index \
                or index >= self.max_calls:
            raise ValueError("mailbox stopped or out-of-order call")
        self._require_active_cycle()
        self.terminal = True  # failures cannot be retried in this session
        filename = f"{index:03d}.json"
        raw = self.sandbox.files.read(f"{GUEST_OUTBOX}/{filename}")
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise ValueError("missing or oversized guest tool request")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("guest tool request must be an object")
        if request.get("input_sha256") != self.adapter.input_sha256:
            raise ValueError("guest tool request belongs to another frozen input")
        claim = {"schema": "controller_tool_mailbox_claim_v1", "cycle_id": self.cycle_id,
                 "controller_sandbox_id": self.sandbox.sandbox_id,
                 "input_sha256": self.adapter.input_sha256,
                 "index": index, "request_sha256": digest(request)}
        fresh_json(self.receipt_root / f"{index:03d}-claim.json", claim)
        try:
            response = self.adapter.call_from_sandbox(self.sandbox, request)
            encoded = canonical(response)
            if len(encoded.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise ValueError("broker response exceeds mailbox bound")
            self._require_active_cycle()
            fresh_json(self.receipt_root / f"{index:03d}-response.json", response)
            self.sandbox.files.write(f"{GUEST_INBOX}/{filename}", encoded)
            fresh_json(self.receipt_root / f"{index:03d}-delivery.json", {
                "schema": "controller_tool_mailbox_delivery_v1",
                "claim_sha256": digest(claim), "response_sha256": digest(response),
                "destination_sandbox_id": self.sandbox.sandbox_id,
                "guest_path": f"{GUEST_INBOX}/{filename}"})
        except Exception as exc:
            fresh_json(self.receipt_root / f"{index:03d}-failure.json", {
                "schema": "controller_tool_mailbox_failure_v1",
                "claim_sha256": digest(claim), "error_type": type(exc).__name__})
            raise
        self.next_index += 1
        self.terminal = False
        return response
