"""Unactivated, stdlib-only MCP reader for Supervisor-approved UTF-8 evidence.

Policy v1: evidence[{id,path,sha256,kind,controller_payload_approved:true}],
limits{file_bytes,page_bytes,output_bytes,tool_calls}, audit_path, schema.
The Supervisor must vet every record; hashes cannot classify its contents.
The output budget covers serialized tool payloads, not JSON-RPC framing.
Receipts describe prepared responses, not confirmed delivery to a consumer.
Audit paths are fresh per process: restart cannot silently reset a used policy.
This component does not sandbox the Controller or enable its other tools.
"""
import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import threading


SCHEMA = "controller_research_evidence_policy_v1"
TOOLS = [
    {"name": "list_evidence", "description": "List approved evidence IDs, never paths.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "read_evidence", "description": "Read a UTF-8 page by approved ID; offset is characters.",
     "inputSchema": {"type": "object", "properties": {
         "evidence_id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0},
         "max_bytes": {"type": "integer", "minimum": 4}},
         "required": ["evidence_id"], "additionalProperties": False}},
]


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON value")
    def finite_float(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON value")
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)


def parent_fd(path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("absolute path required")
    parts = path.split("/")[1:]
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("noncanonical path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def read_file(path, cap):
    directory, leaf = parent_fd(path)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > cap:
                raise ValueError("file size or type denied")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(cap + 1)
            if len(raw) > cap:
                raise ValueError("file byte bound")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(directory)


class BudgetStop(RuntimeError):
    """Terminal: no further evidence reads or tool payloads may be emitted."""


class EvidenceBroker:
    def __init__(self, policy_path, policy_sha256):
        raw = read_file(policy_path, 1_048_576)
        if digest(raw) != policy_sha256:
            raise ValueError("policy hash mismatch")
        policy = strict_json(raw)
        if set(policy) != {"schema", "evidence", "limits", "audit_path"} or policy["schema"] != SCHEMA:
            raise ValueError("policy schema denied")
        ceilings = {"file_bytes": 16_777_216, "page_bytes": 65_536,
                    "output_bytes": 4_194_304, "tool_calls": 1000}
        limits = policy["limits"]
        if not isinstance(limits, dict) or set(limits) != set(ceilings):
            raise ValueError("limits required")
        for key, cap in ceilings.items():
            if type(limits[key]) is not int or not 1 <= limits[key] <= cap:
                raise ValueError("invalid limit")
        if limits["page_bytes"] < 4:
            raise ValueError("UTF-8 page bound")
        self.records = {}
        for record in policy["evidence"]:
            if set(record) != {"id", "path", "sha256", "kind", "controller_payload_approved"}:
                raise ValueError("record schema denied")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", record["id"]):
                raise ValueError("invalid evidence id")
            if record["id"] in self.records or record["kind"] not in {"source", "evidence", "memory"}:
                raise ValueError("duplicate or unapproved kind")
            if record["controller_payload_approved"] is not True or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
                raise ValueError("unapproved record")
            directory, _ = parent_fd(record["path"])
            os.close(directory)
            self.records[record["id"]] = record
        self.policy_path, self.policy_sha256, self.limits = policy_path, policy_sha256, limits
        self.lock, self.calls, self.bytes, self.stopped = threading.Lock(), 0, 0, False
        self.audit_dir, self.audit_leaf = parent_fd(policy["audit_path"])
        try:
            self.audit_fd = os.open(self.audit_leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                    0o600, dir_fd=self.audit_dir)
            os.fsync(self.audit_fd)
            os.fsync(self.audit_dir)
        except BaseException:
            if hasattr(self, "audit_fd"):
                os.close(self.audit_fd)
            os.close(self.audit_dir)
            raise

    def close(self):
        os.close(self.audit_fd)
        os.close(self.audit_dir)

    def _audit(self, receipt):
        try:
            data = encode(receipt) + b"\n"
            while data:
                written = os.write(self.audit_fd, data)
                if written <= 0:
                    raise OSError("audit write failed")
                data = data[written:]
            os.fsync(self.audit_fd)
            named = os.stat(self.audit_leaf, dir_fd=self.audit_dir, follow_symlinks=False)
            opened = os.fstat(self.audit_fd)
            if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                raise OSError("audit path drift")
        except BaseException:
            self.stopped = True
            raise BudgetStop("audit persistence failed") from None

    def call(self, name, arguments):
        with self.lock:
            if self.stopped:
                raise BudgetStop("session stopped")
            self.calls += 1
            result, reason, request_sha256 = None, "", None
            try:
                if self.calls > self.limits["tool_calls"]:
                    raise ValueError("call budget exhausted")
                if self.bytes >= self.limits["output_bytes"]:
                    raise ValueError("output budget exhausted")
                request_sha256 = digest(encode({"name": name, "arguments": arguments}))
                if digest(read_file(self.policy_path, 1_048_576)) != self.policy_sha256:
                    raise ValueError("policy drift")
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")
                if not isinstance(name, str):
                    raise ValueError("tool name must be a string")
                if name == "list_evidence" and not arguments:
                    result = {"ok": True, "evidence": [{k: r[k] for k in ("id", "kind", "sha256")}
                              for r in self.records.values()]}
                elif name == "read_evidence":
                    if set(arguments) - {"evidence_id", "offset", "max_bytes"}:
                        raise ValueError("unexpected arguments")
                    record = self.records.get(arguments.get("evidence_id"))
                    if record is None:
                        raise ValueError("unlisted evidence id")
                    offset, size = arguments.get("offset", 0), arguments.get("max_bytes", self.limits["page_bytes"])
                    if type(offset) is not int or offset < 0 or type(size) is not int or not 4 <= size <= self.limits["page_bytes"]:
                        raise ValueError("invalid page bounds")
                    raw = read_file(record["path"], self.limits["file_bytes"])
                    if digest(raw) != record["sha256"]:
                        raise ValueError("source drift")
                    text = raw.decode("utf-8")
                    if offset > len(text):
                        raise ValueError("offset beyond evidence")
                    page = text[offset:offset + size].encode("utf-8")[:size].decode("utf-8", errors="ignore")
                    result = {"ok": True, "evidence_id": record["id"], "sha256": record["sha256"],
                              "text": page, "next_offset": offset + len(page), "eof": offset + len(page) == len(text)}
                else:
                    raise ValueError("unsupported tool or arguments")
            except Exception as error:
                reason = str(error) if type(error) is ValueError else "evidence access denied"
                result = {"ok": False, "error": reason[:100]}
            payload = encode(result)
            terminal = self.calls > self.limits["tool_calls"] or self.bytes + len(payload) > self.limits["output_bytes"]
            emitted = b"" if terminal else payload
            self._audit({"sequence": self.calls, "policy_sha256": self.policy_sha256,
                         "pid": os.getpid(), "request_sha256": request_sha256,
                         "delivery": "not_confirmed",
                         "tool": name if isinstance(name, str) and name in {"list_evidence", "read_evidence"} else "unsupported",
                         "evidence_id": arguments.get("evidence_id") if isinstance(arguments, dict)
                         and isinstance(arguments.get("evidence_id"), str) and arguments["evidence_id"] in self.records else None,
                         "status": "denied" if terminal or not result["ok"] else "success",
                         "reason": "output/call budget exhausted" if terminal else reason,
                         "payload_bytes": len(emitted), "payload_sha256": digest(emitted)})
            if terminal:
                self.stopped = True
                raise BudgetStop("output/call budget exhausted")
            self.bytes += len(payload)
            return result


def serve(broker, source=sys.stdin, sink=sys.stdout):
    while True:
        line = source.readline(100_001)
        if not line:
            return
        request, rpc_id = {}, None
        bad_frame = len(line.encode("utf-8")) > 100_000 or not line.endswith("\n")
        try:
            if bad_frame:
                raise ValueError("RPC byte bound or incomplete line")
            request = strict_json(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                raise ValueError("invalid RPC request")
            if "id" in request and request["id"] is not None and type(request["id"]) not in (str, int):
                raise ValueError("unsupported RPC id")
            rpc_id = request.get("id")
            if "id" not in request:
                continue
            method = request["method"]
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "controller-research-evidence", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "ping":
                result = {}
            elif method == "tools/call":
                params = request.get("params", {})
                value = broker.call(params.get("name") if isinstance(params, dict) else None,
                                    params.get("arguments", {}) if isinstance(params, dict) else None)
                result = {"isError": not value["ok"], "content": [{"type": "text", "text": encode(value).decode()}]}
            else:
                raise ValueError("unknown method")
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except BudgetStop:
            return
        except Exception:
            response = {"jsonrpc": "2.0", "id": rpc_id,
                        "error": {"code": -32600, "message": "invalid RPC request"}}
        sink.write(encode(response).decode() + "\n")
        sink.flush()
        if bad_frame:
            return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--policy-sha256", required=True)
    args = parser.parse_args()
    broker = EvidenceBroker(args.policy, args.policy_sha256)
    try:
        serve(broker)
    finally:
        broker.close()
