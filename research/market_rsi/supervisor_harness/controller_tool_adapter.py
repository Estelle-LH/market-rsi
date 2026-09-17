"""Host-side, role-bound bridge to the existing literature research tools.

The transport must supply the observed E2B sandbox object; guest JSON cannot
declare its own role or sandbox ID. This is an offline-testable adapter, not a
live E2B or GLM attestation. The existing Data Scientist Broker remains the
authority for argument schemas, public-read budgets and durable receipts.
"""
from __future__ import annotations

from market_rsi import digest, identifier


LITERATURE_TOOLS = frozenset({
    "search_literature_live", "read_public_source", "record_research",
})


class ControllerToolAdapter:
    def __init__(self, broker, *, controller_sandbox_id: str,
                 researcher_sandbox_id: str, input_sha256: str):
        if (not isinstance(controller_sandbox_id, str) or not controller_sandbox_id
                or not isinstance(researcher_sandbox_id, str) or not researcher_sandbox_id
                or controller_sandbox_id == researcher_sandbox_id):
            raise ValueError("controller and researcher need distinct sandbox IDs")
        if (not isinstance(input_sha256, str) or len(input_sha256) != 64
                or any(c not in "0123456789abcdef" for c in input_sha256)):
            raise ValueError("exact frozen controller input hash required")
        self.broker = broker
        self.controller_sandbox_id = controller_sandbox_id
        self.researcher_sandbox_id = researcher_sandbox_id
        self.input_sha256 = input_sha256

    def call_from_sandbox(self, observed_sandbox, request: dict) -> dict:
        """The trusted host passes its E2B object, never a guest-supplied ID."""
        if getattr(observed_sandbox, "sandbox_id", None) != self.controller_sandbox_id:
            raise ValueError("literature tool call did not originate from controller sandbox")
        if not isinstance(request, dict) or set(request) != {
                "schema", "input_sha256", "call_id", "tool", "arguments"}:
            raise ValueError("exact controller tool-request schema required")
        if (request["schema"] != "controller_literature_tool_request_v1"
                or request["input_sha256"] != self.input_sha256):
            raise ValueError("tool request is not bound to frozen controller input")
        identifier(request["call_id"])
        if request["tool"] not in LITERATURE_TOOLS:
            raise ValueError("controller tool is outside the literature allowlist")
        if not isinstance(request["arguments"], dict):
            raise ValueError("controller tool arguments must be an object")
        # Broker.call validates exact arguments, applies its public-fetch budget,
        # and archives both success and failure. Do not implement a second,
        # weaker literature fetch path here.
        record = self.broker.call(request["tool"], request["arguments"])
        return {"schema": "controller_literature_tool_response_v1",
                "input_sha256": self.input_sha256, "call_id": request["call_id"],
                "tool": request["tool"], "broker_record_sha256": digest(record),
                "broker_record": record,
                "metadata_is_not_paper_read": request["tool"] == "search_literature_live"}
