"""Original-trace arithmetic, not proof of learning or provider authenticity."""
from copy import deepcopy
import json
import math
from pathlib import Path

import earnings_entry as e
from edgar_forecast_openai import digest
from supervisor_harness import capacity_feedback_engine as engine

METRICS = {"turns", "tool_calls", "input_tokens", "output_tokens", "tool_return_characters",
           "repeated_reads", "rejected_tools", "records_added"}
FAMILIES = {
    "research_policy": METRICS - {"tool_return_characters"},
    "memory_policy": METRICS - {"tool_return_characters"},
    "tool_interface": METRICS - {"records_added"},
}
SCORE_METRIC = 'score_out_of_5'


def validate_criterion(value):
    """Keep operational v1 intact; v2 names the unchanged original score."""
    fields = {'schema', 'component', 'metric', 'direction', 'min_delta'}
    if (type(value) is not dict or set(value) != fields
            or type(value['schema']) is not str
            or value['schema'] not in {'earnings_shadow_criterion_v1', 'earnings_shadow_criterion_v2'}
            or type(value['component']) is not str or value['component'] not in FAMILIES
            or type(value['metric']) is not str or type(value['direction']) is not str
            or type(value['min_delta']) not in (int, float)
            or not math.isfinite(value['min_delta']) or value['min_delta'] <= 0):
        raise ValueError('Exact predeclared finite matched criterion required')
    if value['schema'] == 'earnings_shadow_criterion_v1':
        if value['metric'] not in FAMILIES[value['component']] or value['direction'] not in {'lower', 'higher'}:
            raise ValueError('Original operational criterion required')
    elif (value['metric'] != SCORE_METRIC or value['direction'] != 'higher'
            or value['min_delta'] > 5 or value['min_delta'] * 2 != int(value['min_delta'] * 2)):
        raise ValueError('Prediction criterion requires original-score gain in half-point steps')
    return deepcopy(value)


def observe(output):
    """Return ten numeric aggregates; never return labels, paths or tool text.

    The caller must first use Task.execution/shadow_execution for the exact
    worker/kernel. This rechecks retained bindings and diagnostic arithmetic.
    Duplicate reads mean identical requested signatures, not overlap or quality.
    """
    engine.driver._artifacts(output)
    root = Path(output["result"]["path"]).parent
    if any(output[key]["path"] != str(root / (key + ".json")) for key in ("result", "score")):
        raise ValueError("Exact original forecast slot required")
    bindings = {}
    for binding in output["artifacts"]:
        if binding["path"] in bindings:
            raise ValueError("Duplicate original artifact bindings")
        bindings[binding["path"]] = binding
    def original(name):
        binding = bindings.get(str(root / name))
        if binding is None:
            raise ValueError("Missing original diagnostic artifact")
        return engine.read(binding)
    result, score = engine.read(output["result"]), engine.read(output["score"])
    turns = result.get("turns")
    points = score.get("score_out_of_5")
    if (result.get("status") != "COMPLETED_SCORED" or result.get("scored_targets") != 5
            or result.get("planned_targets") != 5 or type(turns) is not int or not 1 <= turns <= 24
            or type(points) not in (int, float) or not math.isfinite(points) or not 0 <= points <= 5
            or result.get("points") != points or score.get("target_count") != 5
            or score.get("prediction_count") != 5):
        raise ValueError("Original complete five-target score required")
    effective = original("effective-capacity.json")
    first = engine.read(effective["initial_state"])
    final = engine.read(output["state"])
    added = len(final["records"]) - len(first["records"])
    if added < 0 or final["records"][:len(first["records"])] != first["records"]:
        raise ValueError("Research record history was not preserved")
    values = dict.fromkeys(METRICS, 0)
    values.update(turns=turns, records_added=added, initial_records=len(first["records"]), score_out_of_5=points)
    signatures, ids = set(), set()
    if str(root/'program-executions.json') in bindings:
        from earnings_open_researcher import evidence_rows
        for item in evidence_rows(original('program-executions.json')['R']):
            name,args=item['request']['tool'],item['request']['arguments']
            values['tool_calls']+=1
            values['tool_return_characters']+=len(json.dumps(item['output']))
            if name=='read_file':
                signature=(args['path'],args['offset'],args['characters'])
                values['repeated_reads']+=int(signature in signatures)
                signatures.add(signature)
    for turn in range(1, turns + 1):
        count = original(f"{turn:02d}-count.json")
        request = original(f"{turn:02d}-request.json")
        response = original(f"{turn:02d}-response.json")
        usage = response["usage"]
        numbers = [count["input_tokens"], usage["input_tokens"], usage["output_tokens"],
                   usage["total_tokens"], usage["input_tokens_details"]["cached_tokens"]]
        if (any(type(n) is not int or n < 0 for n in numbers) or numbers[1] > numbers[0]
                or numbers[3] != numbers[1] + numbers[2] or numbers[4] > numbers[1]
                or request["request_id"] in ids or request["payload"]["model"] != response["model"]
                or response.get("status") != "completed" or response.get("error") is not None):
            raise ValueError("Original request/count/usage mismatch")
        ids.add(request["request_id"])
        values["input_tokens"] += numbers[1]
        values["output_tokens"] += numbers[2]
        for call in response["output"]:
            if call.get("type") != "function_call":
                continue
            value = original(f"{turn:02d}-tool-{digest(call['call_id'].encode())[:12]}.json")
            if value.get("call_id") != call["call_id"] or type(value.get("output")) is not str:
                raise ValueError("Original function output differs")
            observed = e.strict_json(value["output"])
            values["tool_calls"] += 1
            values["tool_return_characters"] += len(value["output"])
            values["rejected_tools"] += int(type(observed) is dict and "error" in observed)
            try:
                args = e.strict_json(call["arguments"])
            except (TypeError, ValueError):
                args = None  # A malformed request can have a valid rejection original.
            if (call.get("name") == "read_file" and type(args) is dict
                    and set(args) == {"path", "offset", "characters"} and type(args["path"]) is str
                    and type(args["offset"]) is int and type(args["characters"]) is int):
                signature = (args["path"], args["offset"], args["characters"])
                values["repeated_reads"] += int(signature in signatures)
                signatures.add(signature)
    if type(result.get("tool_calls")) is not int or result["tool_calls"] != values["tool_calls"]:
        raise ValueError("Original tool count mismatch")
    return values


def compare(parent, child, *, declaration):
    """One prospective operational or original-score Discovery comparison."""
    declaration = validate_criterion(declaration)
    expected = {"active_pair_sha256", "tested_pair_sha256", "pending_proposal_sha256", "state_sha256"}
    p, c = parent["consumed"], child["consumed"]
    if (type(p) is not dict or type(c) is not dict or set(p) != expected or set(c) != expected
            or any(p[k] != c[k] for k in expected - {"tested_pair_sha256"})
            or p["tested_pair_sha256"] != p["active_pair_sha256"]
            or c["tested_pair_sha256"] == c["active_pair_sha256"]):
        raise ValueError("Matched active/pending/initial-state and distinct tested child required")
    for consumed in (p, c):
        for token in consumed.values(): engine.identity.sha(token)
    before, after = observe(parent), observe(child)
    delta = {metric: after[metric] - before[metric] for metric in METRICS}
    score_delta = after["score_out_of_5"] - before["score_out_of_5"]
    if declaration['schema'] == 'earnings_shadow_criterion_v2':
        delta[SCORE_METRIC] = score_delta
    named = delta[declaration["metric"]]
    improved = named <= -declaration["min_delta"] if declaration["direction"] == "lower" else named >= declaration["min_delta"]
    return {"schema": "earnings_matched_shadow_v1", "parent": before, "child": after,
        "declaration": deepcopy(declaration), "delta": delta, "score_delta": score_delta,
        "benefit_observed": improved and score_delta >= 0,
        "originals": {"parent": deepcopy(parent), "child": deepcopy(child)},
        "claims": {"learning": False, "model_authorship": False, "predictive_gain": False}}
