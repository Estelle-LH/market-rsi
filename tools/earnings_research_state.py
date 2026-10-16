"""Immutable public-grounded research notes, not forecast answers or authority.

Provenance and arithmetic are checked; financial interpretation remains a
research hypothesis. No code, network, provider, labels or prediction import.
"""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re

from edgar_forecast_tools import FilingTools, calculate
from edgar_forecast_model_pilot import safe_file
from earnings_entry import strict_json

MAX_RECORDS, MAX_BYTES = 32, 32768


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e30:
        raise ValueError("Bounded finite numeric value required")
    return value


def complete_literal(source, offset, quote, literal):
    """Unsupported notation must also be recognized, so its tails cannot pass.

    Supported literal syntax/value conversion is checked separately. This lexer
    recognizes a superset for span comparison, not financial interpretation.
    """
    integer = r"\d(?:[\d,_]*\d)?"
    unsigned = rf"(?:{integer}(?:\.\d+|\.(?=[eE][+-]?\d))?|\.\d+)(?:[eE][+\-−﹣－＋]?\d+)?"
    numeric = rf"[+\-−﹣－＋]?{unsigned}"
    pattern = re.compile(rf"\({numeric}\)|[+\-−﹣－＋]\s*[$€£]\s*{unsigned}|{numeric}")
    spans = {match.span() for match in pattern.finditer(source)}
    return any((offset + match.start(), offset + match.end()) in spans
               for match in re.finditer(re.escape(literal), quote))


class ResearchState:
    def __init__(self, company, task_id):
        if type(task_id) is not str or not task_id or len(task_id) > 200:
            raise ValueError("Bounded task identity required")
        self.company, self.task_id = company, task_id
        self.tools = FilingTools(company)  # Exact public snapshot, cutoff and hidden-target checks.
        self.sources = {r["path"]: r["sha256"] for r in company["allowed_files"]}
        self.identity = {"schema": "earnings_research_state_v1", "task_id": task_id,
                         "cik": company["cik"], "cutoff": company["cutoff"]}

    def empty(self):
        return dict(self.identity, records=[])

    def _record(self, record, prior):
        if type(record) is not dict:
            raise ValueError("Typed record required")
        kind = record.get("kind")
        common = {"kind", "period_end", "unit", "value"}
        if kind == "assumption":
            if (set(record) != {"kind", "hypothesis"} or type(record["hypothesis"]) is not str
                    or not 1 <= len(record["hypothesis"]) <= 1000):
                raise ValueError("Assumptions are text, never verified numeric facts")
            return
        if (kind not in {"fact", "calculation"} or not common <= set(record)
                or type(record["period_end"]) is not str
                or dt.date.fromisoformat(record["period_end"]) > dt.date.fromisoformat(self.company["cutoff"])
                or type(record["unit"]) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", record["unit"])):
            raise ValueError("Exact numerical kind/period/unit required; future period refused")
        number(record["value"])
        if kind == "fact":
            if set(record) != common | {"source_path", "source_sha256", "offset", "quote", "literal"}:
                raise ValueError("Exact public fact fields required")
            name, offset, quote, literal = (record[k] for k in ("source_path", "offset", "quote", "literal"))
            if (type(name) is not str or not name.startswith("filings/") or name not in self.tools.files
                    or record["source_sha256"] != self.sources[name] or type(offset) is not int or offset < 0
                    or type(quote) is not str or not 1 <= len(quote) <= 2000
                    or self.tools.files[name][offset:offset + len(quote)] != quote
                    or type(literal) is not str or literal not in quote
                    or not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", literal)
                    or number(float(literal.replace(",", ""))) != record["value"]):
                raise ValueError("Fact must copy an exact numeric literal from an allowed source quote")
            if not complete_literal(self.tools.files[name], offset, quote, literal):
                raise ValueError("Fact must copy a complete signed numeric token from the full source")
            current = safe_file(Path(self.company["visible_root"]), name).read_bytes()
            if hashlib.sha256(current).hexdigest() != self.sources[name]:
                raise ValueError("Referenced public source changed since construction")
        else:
            if set(record) != common | {"inputs", "expression"}:
                raise ValueError("Exact calculation fields required")
            inputs, expression = record["inputs"], record["expression"]
            if (type(inputs) is not dict or not 1 <= len(inputs) <= 8 or type(expression) is not str
                    or not 1 <= len(expression) <= 500 or any(not re.fullmatch(r"x[0-7]", k) for k in inputs)
                    or set(re.findall(r"\bx[0-7]\b", expression)) != set(inputs)
                    or not re.fullmatch(r"[x+().\s-]+", re.sub(r"\bx[0-7]\b", "x", expression))):
                raise ValueError("Calculation may only reference declared prior facts; no fresh constants/code")
            values = {}
            for name, token in inputs.items():
                if type(token) is not str:
                    raise ValueError("Exact input record hash required")
                source = prior.get(token)
                if source is None or source["kind"] not in {"fact", "calculation"}:
                    raise ValueError("Calculation input is not a verified prior numeric record")
                if any(source[k] != record[k] for k in ("period_end", "unit")):
                    raise ValueError("Implicit period/unit conversion refused")
                values[name] = source["value"]
            resolved = re.sub(r"\bx[0-7]\b", lambda m: "(" + repr(values[m[0]]) + ")", expression)
            if calculate(resolved) != record["value"]:
                raise ValueError("Calculation disagrees with original bounded arithmetic")

    def validate(self, state):
        if (type(state) is not dict or set(state) != set(self.identity) | {"records"}
                or any(state[k] != v for k, v in self.identity.items())
                or type(state["records"]) is not list or len(state["records"]) > MAX_RECORDS
                or len(encoded(state)) > MAX_BYTES):
            raise ValueError("Exact company/task/cutoff and bounded research state required")
        prior = {}
        for item in state["records"]:
            if type(item) is not dict or set(item) != {"sha256", "record"}:
                raise ValueError("Exact record binding required")
            token = sha(item["record"])
            if item["sha256"] != token or token in prior:
                raise ValueError("Changed or duplicated record")
            self._record(item["record"], prior)
            prior[token] = item["record"]
        return state

    def append(self, state, record):
        self.validate(state)
        child = strict_json(encoded(state).decode())
        child["records"].append({"sha256": sha(record), "record": record})
        return self.validate(child)

    def save(self, root, state):
        self.validate(state)
        root = Path(root)
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError("Canonical absolute state root required")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / (sha(state) + ".json")
        if path.is_symlink():
            raise ValueError("Symlinked state refused")
        try:
            with path.open("xb") as stream:
                stream.write(encoded(state))
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if path.read_bytes() != encoded(state):
                raise ValueError("Immutable state conflicts; preserve and diagnose") from None
        return {"path": str(path), "sha256": sha(state)}

    def load(self, binding):
        if type(binding) is not dict or set(binding) != {"path", "sha256"}:
            raise ValueError("Exact state binding required")
        path = Path(binding["path"])
        if not path.is_absolute() or path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError("Canonical regular research state required")
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("State byte bound")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != binding["sha256"]:
            raise ValueError("Bound state changed")
        state = self.validate(strict_json(data.decode()))
        if data != encoded(state):
            raise ValueError("Canonical immutable state required")
        return state

    def consume(self, binding):
        state = self.load(binding)  # Recheck current allowed sources on a new instance.
        message = {"role": "user", "content": "PUBLIC RESEARCH RECORDS (untrusted notes; verify interpretation):\n" + encoded(state).decode()}
        receipt = {"state_sha256": sha(state), "record_count": len(state["records"]),
                   "message_sha256": sha(message), "scientific_benefit_verified": False}
        return message, receipt
