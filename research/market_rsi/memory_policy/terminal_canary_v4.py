"""One real GLM terminal-reserve canary with no market rows or scores.

The model receives a synthetic request and the actual v4 adapter is placed at
the frozen terminal trigger.  The only visible action is model-authored
``submit_candidate``.  No candidate is fit and no Dev or Final source exists.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_glm_provider import ControllerSession, TinkerGLMBackend
from controller_harness_contract import (
    MAX_CUMULATIVE_OUTPUT_TOKENS,
    TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
)
from glm_canary import MODEL
from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget


ALLOWED = ("inspect_experiment", "submit_candidate")


def tool(name, description, properties, required):
    return {
        "type": "function",
        "name": "mcp__controller_tools__" + name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def request():
    string = {"type": "string"}
    return {
        "model": MODEL,
        "stream": True,
        "store": False,
        "instructions": (
            "This is a synthetic controller terminal-capacity canary. There are "
            "no market rows, scores, experiments, files, or hidden data. The only "
            "valid decision is to retain the named synthetic baseline by calling "
            "submit_candidate. Never claim a fitted result."
        ),
        "tools": [
            tool("inspect_experiment", "Unavailable synthetic research action.", {}, []),
            tool(
                "submit_candidate",
                "Submit the already-supported synthetic baseline.",
                {"trial_id": string, "reason": string},
                ["trial_id", "reason"],
            ),
        ],
        "input": [{
            "type": "message",
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": (
                    "The research allowance is ending. Submit trial_id baseline "
                    "and state that this is only a terminal-protocol canary."
                ),
            }],
        }],
    }


def run(output, budget_path, env_file, tokenizer_cache):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh terminal canary ID required")
    output.mkdir(parents=True)
    from dotenv import dotenv_values

    key = dotenv_values(env_file).get("TINKER_API_KEY")
    if not key:
        raise ValueError("missing Tinker credential")
    backend = TinkerGLMBackend(key, Path(tokenizer_cache))
    budget = PaidBudget(Path(budget_path))
    session = ControllerSession(
        session_id=output.name,
        output=output / "session",
        backend=backend,
        budget=budget,
        budget_bucket="repair",
        submit_tool="submit_candidate",
        allowed_tools=ALLOWED,
        protocol_error_tool=None,
        max_protocol_feedback=0,
    )
    session.tokens.output_tokens = (
        MAX_CUMULATIVE_OUTPUT_TOKENS - TERMINAL_SUBMISSION_TRIGGER_OUTPUT
    )
    first_request = request()
    first = session.handle(first_request)
    calls = first[-1]["response"]["output"]
    if len(calls) != 1 or calls[0].get("type") != "function_call":
        raise ValueError("terminal canary did not produce one model-authored call")
    call = calls[0]
    if call.get("name") != "submit_candidate":
        raise ValueError("terminal canary used a non-submission tool")
    arguments = json.loads(call["arguments"])
    if arguments.get("trial_id") != "baseline":
        raise ValueError("terminal canary did not retain the synthetic baseline")

    second_request = request()
    second_request["input"] += [
        {
            "type": "function_call",
            "call_id": call["call_id"],
            "name": call["name"],
            "namespace": call["namespace"],
            "arguments": call["arguments"],
        },
        {
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": json.dumps({"submitted": True, "bytes": len(call["arguments"])}),
        },
    ]
    terminal = session.handle(second_request)
    text = terminal[-1]["response"]["output"][0]["content"][0]["text"]
    if text != "Controller decision submitted; session complete.":
        raise ValueError("terminal handshake failed")

    response = json.loads((output / "session/turn-001/response.json").read_text())
    result = {
        "schema": "memory_policy_terminal_canary_v4",
        "passed": True,
        "actual_provider_calls": 1,
        "market_rows": 0,
        "scores_opened": 0,
        "candidate_fits": 0,
        "model_authored_submission": True,
        "submission_inferred_or_repaired": False,
        "submitted_trial_id": arguments["trial_id"],
        "finish_reason": response["receipt"]["finish_reason"],
        "metered_usd": response["receipt"]["metered_cost_usd"],
        "prompt_tokens": response["receipt"]["prompt_tokens"],
        "output_tokens": response["receipt"]["output_tokens"],
        "provider_source_sha256": file_hash(Path(__file__).parents[1] / "codex_glm_provider.py"),
        "adapter_source_sha256": file_hash(Path(__file__).parents[1] / "codex_glm_responses_adapter.py"),
        "contract_source_sha256": file_hash(Path(__file__).parents[1] / "controller_harness_contract.py"),
        "terminal_handshake_sha256": file_hash(output / "session/terminal-handshake.json"),
    }
    result["result_sha256"] = digest(result)
    fresh_json(output / "canary.json", result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--tokenizer-cache", required=True, type=Path)
    args = parser.parse_args()
    run(args.output, args.budget, args.env_file, args.tokenizer_cache)
