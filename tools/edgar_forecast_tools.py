"""Hash-pinned public filing snapshots and bounded non-executing local tools."""
import ast
import json
import math
import operator
from pathlib import Path

from edgar_forecast_model_pilot import digest, safe_file, eligible
import datetime as dt


def function(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(properties), "additionalProperties": False}}


TOOLS = [
    function("read_file", "Read a character chunk from an allowed local filing or index; offsets are zero-based.",
             {"path": {"type": "string"}, "offset": {"type": "integer"}, "characters": {"type": "integer"}}),
    function("search_files", "Literal case-insensitive search over allowed files. Returns file, line and nearby text.",
             {"query": {"type": "string"}, "path_prefix": {"type": "string"}, "max_hits": {"type": "integer"}}),
    function("calculate", "Evaluate bounded numeric arithmetic only: + - * / and powers. No code or functions.",
             {"expression": {"type": "string"}}),
]


def calculate(expression):
    if type(expression) is not str or not 1 <= len(expression) <= 500:
        raise ValueError("Arithmetic expression length")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 50:
        raise ValueError("Arithmetic expression too large")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow}

    def value(node):
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            result = node.value
        elif isinstance(node, ast.UnaryOp) and type(node.op) in {ast.UAdd, ast.USub}:
            result = value(node.operand) * (1 if isinstance(node.op, ast.UAdd) else -1)
        elif isinstance(node, ast.BinOp) and type(node.op) in ops:
            left, right = value(node.left), value(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent limit")
            result = ops[type(node.op)](left, right)
        else:
            raise ValueError("Only numeric arithmetic is available")
        if type(result) not in {int, float} or not math.isfinite(result) or abs(result) > 1e30:
            raise ValueError("Arithmetic result limit")
        return result

    return value(tree.body)


class FilingTools:
    def __init__(self, company):
        self.files, self.calls, self.returned = {}, 0, 0
        root = Path(company["visible_root"])
        for receipt in company["allowed_files"]:
            name = receipt["path"]
            if name not in {"questions.md", "filing_index.tsv"} and not (name.startswith("filings/") and name.endswith(".md")):
                raise ValueError("Non-filing allowlist entry")
            if name in self.files or company["target_accession"] in name:
                raise ValueError("Duplicate or hidden target entry")
            data = safe_file(root, name).read_bytes()
            if len(data) != receipt["bytes"] or digest(data) != receipt["sha256"]:
                raise ValueError("Filing snapshot differs from prepared manifest")
            self.files[name] = data.decode("utf-8")
        if not {"questions.md", "filing_index.tsv"} <= set(self.files):
            raise ValueError("Missing questions or index")
        rows = []
        for line in self.files["filing_index.tsv"].splitlines()[1:]:
            date, form, accession, name = line.split("\t")
            rows.append({"date_filed": date, "accession": accession, "relative_path": name})
        eligible(rows, company["target_accession"], dt.date.fromisoformat(company["cutoff"]))
        if {r["relative_path"] for r in rows} != set(self.files) - {"questions.md", "filing_index.tsv"}:
            raise ValueError("Index and allowlist differ")

    def dispatch(self, name, arguments):
        self.calls += 1
        if self.calls > 80:
            raise ValueError("Tool call limit")
        specs = {t["name"]: t["parameters"]["properties"] for t in TOOLS}
        if name not in specs or type(arguments) is not dict or set(arguments) != set(specs[name]):
            raise ValueError("Unknown tool or parameters")
        for key, spec in specs[name].items():
            if type(arguments[key]) is not ({"integer": int, "string": str}[spec["type"]]):
                raise ValueError("Invalid argument type")
        if name == "calculate":
            result = {"value": calculate(arguments["expression"])}
        elif name == "read_file":
            path, offset, size = (arguments[k] for k in ["path", "offset", "characters"])
            if path not in self.files or offset < 0 or not 1 <= size <= 20000:
                raise ValueError("Read is outside allowed files or bounds")
            content = self.files[path]
            result = {"path": path, "offset": offset, "total_characters": len(content),
                      "text": content[offset:offset + size], "next_offset": min(offset + size, len(content))}
        else:
            query, prefix, limit = (arguments[k] for k in ["query", "path_prefix", "max_hits"])
            if not 1 <= len(query) <= 200 or not 1 <= limit <= 50:
                raise ValueError("Search bounds")
            if prefix not in {"", "filings/"} and prefix not in self.files:
                raise ValueError("Unknown path prefix")
            hits, total = [], 0
            for path, content in self.files.items():
                if not path.startswith(prefix):
                    continue
                for number, line in enumerate(content.splitlines(), 1):
                    pos = line.casefold().find(query.casefold())
                    if pos >= 0:
                        total += 1
                        if len(hits) < limit:
                            hits.append({"path": path, "line": number,
                                         "text": line[max(0, pos - 100):pos + len(query) + 200]})
            result = {"hits": hits, "total_matching_lines": total}
        self.returned += len(json.dumps(result))
        if self.returned > 2_000_000:
            raise ValueError("Tool return budget exhausted")
        return result
