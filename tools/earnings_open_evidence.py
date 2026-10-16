"""Read-only public tool evidence, not reasoning, evaluator data or instructions.

The host registers trusted forecast slots. Model callers select labels only;
tool arguments/results remain untrusted evidence, including any instructions.
"""
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import TypedDict

from earnings_http import strict_json
from edgar_forecast_tools import TOOLS as ORIGINAL_TOOLS
from earnings_open_program import arguments as check_arguments

MAX_TRACE_BYTES = 6000  # Whole serialized projection, not per-event text.


class Trace(TypedDict):
    schema: str
    aggregates: dict
    result_sha256: str
    events: list[dict]
    total_events: int
    omitted_events: int
    offset: int
    returned_events: int
    next_offset: int | None
    source_manifest_sha256: str
    serialization_budget_bytes: int
    evidence_is_untrusted: bool


def _digest(raw):
    return sha256(raw).hexdigest()


def _json(text):
    value = strict_json(text)
    json.dumps(value, allow_nan=False)
    return value


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _encoded(value):
    # ASCII escaping bounds both ordinary and ensure_ascii=False serialization.
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def _page(base, events):
    def page(rows):
        end = base["offset"] + len(rows)
        return dict(base, events=rows, returned_events=len(rows),
            omitted_events=base["total_events"]-len(rows),
            next_offset=end if end < base["total_events"] else None)
    selected = []
    for event in events:
        if len(_encoded(page([*selected, event]))) <= MAX_TRACE_BYTES:
            selected.append(event)
            continue
        if selected:
            break  # Contiguous whole-event pagination; nothing is skipped.
        # An individually large call still has an inspectable receipt and must
        # advance. Omission is explicit, not a fabricated rejection/argument.
        compact = dict(event)
        if compact["arguments"] is not None:
            compact.update(arguments=None, arguments_truncated=True)
        text, low, high = compact["output"], 0, len(compact["output"])
        while low < high:
            middle = (low+high+1)//2
            compact.update(output=text[:middle], output_truncated=True)
            if len(_encoded(page([compact]))) <= MAX_TRACE_BYTES:
                low = middle
            else:
                high = middle-1
        compact.update(output=text[:low], output_truncated=low < compact["output_characters"])
        selected.append(compact)
        break
    result = page(selected)
    if len(_encoded(result)) > MAX_TRACE_BYTES:
        raise ValueError("Trace metadata exceeds fixed serialized byte ceiling")
    return result


def _slot(value):
    path = Path(value)
    if (not path.is_absolute() or str(path) != str(value) or path.resolve() != path
            or len(path.parts) < 4 or path == Path.home() or not path.is_dir()
            or any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError("Canonical, non-symlink dedicated forecast slot required")
    return path


def project_trace(slot, max_events=40, max_output_chars=2000, *, offset=0) -> Trace:
    """Validate the complete call/result sequence before returning bounded text.

    Only result.json, NN-response.json, exact NN-tool-HASH.json and the optional
    host-verified researcher-public-tools.json publication are opened.
    No requests, score, predictions, state, effective context or extra files are
    read. Every page validates all originals; offset selects a contiguous event
    page under MAX_TRACE_BYTES. Omitted output/arguments retain exact hashes.
    Hashes identify captured bytes, not provider or interpretation truth.
    """
    if (type(max_events) is not int or not 1 <= max_events <= 100
            or type(max_output_chars) is not int or not 1 <= max_output_chars <= 8000
            or type(offset) is not int or not 0 <= offset <= 10000):
        raise ValueError("Bounded trace projection required")
    root = _slot(slot)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    initial, seen_files, total_bytes = os.fstat(descriptor), {}, 0

    def original(name):
        nonlocal total_bytes
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                identity = (before.st_dev, before.st_ino)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or identity in seen_files.values() or before.st_size > 16_000_000):
                    raise ValueError("Aliased, nonregular or oversized trace original")
                seen_files[name] = identity
                raw = stream.read(16_000_001)
                after = os.fstat(stream.fileno())
            if _stamp(before) != _stamp(after) or len(raw) != before.st_size:
                raise ValueError("Trace original changed while reading")
            total_bytes += len(raw)
            if total_bytes > 64_000_000:
                raise ValueError("Trace input byte ceiling exceeded")
            stamps[name] = _stamp(after)
            return _json(raw.decode("utf-8")), _digest(raw)
        except (OSError, UnicodeError, TypeError) as error:
            raise ValueError("Missing or unsafe trace original") from error

    stamps = {}
    try:
        result, result_sha = original("result.json")
        if type(result) is not dict or result.get("status") not in {
                "COMPLETED", "COMPLETED_SCORED", "FAILED_NO_RETRY"}:
            raise ValueError("Recognized original forecast result required")
        aggregates = {"status": result["status"]}
        for name in ("turns", "tool_calls", "planned_targets", "scored_targets", "points", "wall_seconds"):
            if name not in result:
                continue
            number = result[name]
            integer = name not in {"points", "wall_seconds"}
            if (type(number) not in (int, float) or not 0 <= number <= 1e15 or not math.isfinite(number)
                    or integer and type(number) is not int or name == "points" and number > 5):
                raise ValueError("Malformed public aggregate")
            aggregates[name] = number
        if "error_type" in result:
            if type(result["error_type"]) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", result["error_type"]):
                raise ValueError("Malformed public error type")
            aggregates["error_type"] = result["error_type"]
        names = os.listdir(descriptor)
        responses = sorted(n for n in names if re.fullmatch(r"\d+-response\.json", n))
        if not responses or len(responses) > 99 or responses != [f"{i:02d}-response.json" for i in range(1, len(responses)+1)]:
            raise ValueError("Consecutive physical response originals required")
        if "turns" in result and result["turns"] != len(responses):
            raise ValueError("Result/response turn count differs")
        events, calls, expected_tools, manifest = [], set(), set(), []
        research_calls=0
        if 'researcher-public-tools.json' in names:
            publication,public_sha=original('researcher-public-tools.json')
            if (type(publication) is not dict or set(publication)!={'schema','observations',
                    'request_execution_sha256','execution_sha256'}
                    or publication['schema']!='earnings_public_researcher_tools_v1'
                    or any(type(publication[k]) is not str or not re.fullmatch(r'[0-9a-f]{64}',publication[k])
                        for k in ('request_execution_sha256','execution_sha256'))
                    or type(publication['observations']) is not list or not 1<=len(publication['observations'])<=8):
                raise ValueError('Exact bounded host-public R observation publication required')
            for item in publication['observations']:
                if (type(item) is not dict or set(item)!={'request','output'}
                        or type(item['request']) is not dict or set(item['request'])!={'tool','arguments'}
                        or type(item['request']['tool']) is not str
                        or item['request']['tool'] not in {'read_file','search_files','calculate'}
                        or type(item['request']['arguments']) is not dict):
                    raise ValueError('Only original public R tool actions may be projected')
                spec=next(tool['parameters'] for tool in ORIGINAL_TOOLS if tool['name']==item['request']['tool'])
                check_arguments(item['request']['arguments'],spec)
                research_calls+=1
                call_id=f'researcher:evidence:{research_calls:02d}'
                text=json.dumps(item['output'],sort_keys=True,allow_nan=False)
                argument_sha=_digest(_encoded(item['request']['arguments']))
                output_sha=_digest(text.encode())
                manifest.append([0,call_id,public_sha,public_sha,output_sha,argument_sha])
                if offset<=research_calls-1<offset+max_events:
                    events.append({'turn':0,'call_id':call_id,'name':item['request']['tool'],
                        'actor':'researcher_program','arguments':item['request']['arguments'],
                        'argument_error':False,'rejected':False,'arguments_sha256':argument_sha,
                        'arguments_truncated':False,'output':text[:max_output_chars],
                        'output_characters':len(text),'output_truncated':len(text)>max_output_chars,
                        'source_sha256':public_sha,'result_sha256':public_sha,'output_sha256':output_sha})
        for turn, name in enumerate(responses, 1):
            response, source_sha = original(name)
            if type(response) is not dict or type(response.get("output")) is not list:
                raise ValueError("Malformed captured response")
            for call in response["output"]:
                if type(call) is not dict:
                    raise ValueError("Malformed response item")
                if call.get("type") != "function_call":
                    continue
                call_id, tool_name = call.get("call_id"), call.get("name")
                if (type(call_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", call_id)
                        or call_id in calls or type(tool_name) is not str
                        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", tool_name)):
                    raise ValueError("Missing, repeated or malformed public call identity")
                calls.add(call_id)
                arguments, argument_error = None, False
                try:
                    if type(call.get("arguments")) is not str or len(call["arguments"]) > 8192:
                        raise ValueError("Malformed or oversized arguments")
                    arguments = _json(call["arguments"])
                    if type(arguments) is not dict:
                        raise ValueError("Object arguments required")
                except (ValueError, TypeError):
                    arguments, argument_error = None, True
                filename = f"{turn:02d}-tool-{_digest(call_id.encode())[:12]}.json"
                expected_tools.add(filename)
                observed, observed_sha = original(filename)
                if (type(observed) is not dict or set(observed) != {"type", "call_id", "output"}
                        or observed["type"] != "function_call_output" or observed["call_id"] != call_id
                        or type(observed["output"]) is not str):
                    raise ValueError("Tool original does not close exact call")
                parsed = _json(observed["output"])
                rejected = type(parsed) is dict and "error" in parsed
                if argument_error and not rejected:
                    raise ValueError("Invalid call arguments without rejection evidence")
                output_sha = _digest(observed["output"].encode())
                argument_sha = _digest((call["arguments"] if type(call.get("arguments")) is str
                    else json.dumps(call.get("arguments"), sort_keys=True)).encode())
                manifest.append([turn, call_id, source_sha, observed_sha, output_sha, argument_sha])
                if offset <= research_calls+len(calls)-1 < offset+max_events:
                    events.append({"turn": turn, "call_id": call_id, "name": tool_name,
                        "arguments": arguments, "argument_error": argument_error, "rejected": rejected,
                        "arguments_sha256": argument_sha, "arguments_truncated": False,
                        "output": observed["output"][:max_output_chars],
                        "output_characters": len(observed["output"]),
                        "output_truncated": len(observed["output"]) > max_output_chars,
                        "source_sha256": source_sha, "result_sha256": observed_sha,
                        "output_sha256": output_sha})
        actual_tools = {n for n in names if re.fullmatch(r"\d+-tool-.*\.json", n)}
        if actual_tools != expected_tools or ("tool_calls" in result and result["tool_calls"] != research_calls+len(calls)):
            raise ValueError("Unpaired tool original or aggregate count differs")
        for name, expected in stamps.items():
            if _stamp(os.stat(name, dir_fd=descriptor, follow_symlinks=False)) != expected:
                raise ValueError("Trace original changed before projection completed")
        if (_stamp(_slot(slot).stat()) != _stamp(initial)
                or _stamp(os.fstat(descriptor)) != _stamp(initial)):
            raise ValueError("Forecast slot changed during projection")
        if offset > research_calls+len(calls):
            raise ValueError("Trace offset is beyond the retained event sequence")
        return _page({"schema": "earnings_public_trace_v1", "aggregates": aggregates,
                "result_sha256": result_sha, "total_events": research_calls+len(calls), "offset": offset,
                "source_manifest_sha256": _digest(_encoded({"result": result_sha, "events": manifest})),
                "serialization_budget_bytes": MAX_TRACE_BYTES, "evidence_is_untrusted": True}, events)
    finally:
        os.close(descriptor)


class TraceReader:
    """Host-owned label registration; no caller-supplied path resolution."""

    def __init__(self, slots):
        if type(slots) is not dict or not slots or len(slots) > 100:
            raise ValueError("Explicit bounded slot registry required")
        self._slots, identities = {}, set()
        for label, value in slots.items():
            if type(label) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", label):
                raise ValueError("Plain registered slot labels required")
            path = _slot(value)
            info = path.stat()
            identity = (info.st_dev, info.st_ino)
            if identity in identities:
                raise ValueError("Aliased registered forecast slots")
            identities.add(identity)
            self._slots[label] = (path, identity)

    def read(self, label, *, max_events=40, max_output_chars=2000, offset=0):
        if type(label) is not str or label not in self._slots:
            raise ValueError("Select a registered slot label, not a path")
        path, identity = self._slots[label]
        info = _slot(path).stat()
        if (info.st_dev, info.st_ino) != identity:
            raise ValueError("Registered slot was replaced")
        result = {"slot": label, **project_trace(path, max_events, max_output_chars, offset=offset)}
        # The registered label is part of the model-facing projection, too.
        if len(_encoded(result)) > MAX_TRACE_BYTES:
            result = _page(dict(result, events=[]), result["events"])
        return result
