"""Trusted optional worker bridge; same filing/state facility for all arms."""
from copy import deepcopy
import json

from edgar_forecast_tools import FilingTools, TOOLS, function
from earnings_research_state import ResearchState
from earnings_capacity_adapter import EarningsCapacity
from earnings_entry import strict_json, durable_json
from market_rsi import digest

SAVE_TOOL = function("save_research_record", "Save a public-source grounded numerical fact or additive calculation; assumptions must be separate text notes. No forecast answers.",
                     {"record_json": {"type": "string"}})


class CapacityWorker:
    def __init__(self, company, task_id, capacity, pair_sha256, state_root, state_binding=None,
                 *, shadow_proposal_sha256=None):
        if not isinstance(capacity, EarningsCapacity):
            raise ValueError("Reviewed native earnings capacity required")
        self.capacity, self.pair = capacity, pair_sha256
        self.shadow_proposal_sha256 = shadow_proposal_sha256
        self.tools = FilingTools(company)
        self.state_api = ResearchState(company, task_id)
        self.company_sha256 = digest(company)
        self.state_root = state_root
        self.state = self.state_api.empty() if state_binding is None else self.state_api.load(state_binding)
        self.state_binding = self.state_api.save(state_root, self.state)
        message, self.state_receipt = self.state_api.consume(self.state_binding)
        self.context = capacity.prepare(expected_pair_sha256=pair_sha256,
            questions=self.tools.files["questions.md"], state_message=message,
            shadow_proposal_sha256=shadow_proposal_sha256)
        self.tested_pair = self.context["receipts"][0]["selected_pair_sha256"]
        self._selection = (self.pair, self.tested_pair, shadow_proposal_sha256)
        self.definitions = deepcopy(TOOLS) + [deepcopy(SAVE_TOOL)]

    @property
    def files(self): return self.tools.files

    @property
    def calls(self): return self.tools.calls

    def start(self, output):
        self._check()
        value = {"context": self.context,
            "initial_state": self.state_binding, "state_receipt": self.state_receipt,
            "scope": "Exact profiles/notes in next payload; no benefit or learning claim"}
        if self.shadow_proposal_sha256 is not None:
            value["shadow"] = {"active_pair_sha256": self.pair,
                "tested_pair_sha256": self.tested_pair,
                "pending_proposal_sha256": self.shadow_proposal_sha256}
        durable_json(output / "effective-capacity.json", value)
        return deepcopy(self.context["messages"])

    def _check(self):
        self.verify_company(self.state_api.company)
        if self._selection != (self.pair, self.tested_pair, self.shadow_proposal_sha256):
            raise ValueError("Worker selection commitment drift")
        if self.shadow_proposal_sha256 is not None:
            snapshot = self.capacity.batch.snapshot()
            if digest(snapshot["micro_evolution"]["active_pair"]) != self.pair:
                raise ValueError("Stale shadow active parent")
            self.capacity._selected(snapshot)
        for axis in ("R", "H"):
            actual = self.capacity.resolve(axis, expected_pair_sha256=self.pair,
                shadow_proposal_sha256=self.shadow_proposal_sha256)
            expected = next(r for r in self.context["receipts"] if r["axis"] == axis)
            if actual["receipt"] != expected:
                raise ValueError("Selected source drift before tool/send")

    def verify_company(self, company):
        if digest(company) != self.company_sha256:
            raise ValueError("Capacity company/cutoff/source manifest drift")

    def dispatch(self, name, arguments):
        self._check()
        args = deepcopy(arguments)
        if name == "save_research_record":
            self.tools.calls += 1
            if self.tools.calls > 80 or type(args) is not dict or set(args) != {"record_json"}:
                raise ValueError("State tool count/fields exceeded")
            if type(args["record_json"]) is not str or len(args["record_json"].encode()) > 8192:
                raise ValueError("Bounded literal record JSON required")
            state = self.state_api.append(self.state, strict_json(args["record_json"]))
            binding = self.state_api.save(self.state_root, state)
            result = {"state_sha256": binding["sha256"], "record_sha256": state["records"][-1]["sha256"],
                      "records": len(state["records"]), "interpretation_verified": False}
            self.tools.returned += len(json.dumps(result))
            if self.tools.returned > 2_000_000:
                raise ValueError("Original tool return budget exhausted")
            self.state, self.state_binding = state, binding
            return result
        if name == "read_file" and type(args) is dict and type(args.get("characters")) is int and 0 < args["characters"] <= 20000:
            args["characters"] = min(args["characters"], self.context["tool_bounds"]["read_chunk_limit"])
        if name == "search_files" and type(args) is dict and type(args.get("max_hits")) is int and 0 < args["max_hits"] <= 50:
            args["max_hits"] = min(args["max_hits"], self.context["tool_bounds"]["search_hit_limit"])
        return self.tools.dispatch(name, args)

    def finish(self, output):
        self._check()
        durable_json(output / "research-state-output.json", {"state": self.state_binding,
            "records": len(self.state["records"]), "tool_calls": self.calls,
            "model_authorship": "Inspect original function-call receipts; count alone is not learning"})
