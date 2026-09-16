"""One bounded real GLM response, not a research result or a training run.

No tools are given to the model. Only a synthetic diagnostic brief leaves the
machine. Never retries a sample or reuses a claim; ambiguous calls retain holds.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import secrets
import time
from decimal import Decimal
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget

MODEL = "zai-org/GLM-5.3:peft:262144"
HF_MODEL = "zai-org/GLM-5.3"
RATES = {"prefill_per_million": "4.86", "cached_prefill_per_million": "0.972", "output_per_million": "12.15"}
MAX_OUTPUT = 8192


def cost(prompt_tokens, output_tokens, cached_tokens=0):
    if any(type(n) is not int or n < 0 for n in (prompt_tokens, output_tokens, cached_tokens)) or cached_tokens > prompt_tokens:
        raise ValueError("invalid token counts")
    return ((prompt_tokens - cached_tokens) * Decimal(RATES["prefill_per_million"])
            + cached_tokens * Decimal(RATES["cached_prefill_per_million"])
            + output_tokens * Decimal(RATES["output_per_million"])) / Decimal(1_000_000)


def assess(text):
    # Keep full output on disk. Only extract its final JSON for independent
    # checks; schema success is not a test of profitable research ability.
    final = text.rsplit("</think>", 1)[-1].strip()
    for marker in ("<|user|>", "<|observation|>", "<|endoftext|>"):
        final = final.removesuffix(marker).strip()
    if final.startswith("```json") and final.endswith("```"):
        final = final[7:-3].strip()
    try:
        data = json.loads(final)
    except ValueError:
        return {"valid_json": False, "all_checks_pass": False}
    checks = {
        "valid_json": isinstance(data, dict),
        "schema": isinstance(data, dict) and set(data) == {"case_verdicts", "next_experiment", "profitability_claim", "can_read_hidden_test"},
        "rejects_leaky_case": isinstance(data, dict) and data.get("case_verdicts", {}).get("random_game_rows") == "invalid",
        "rejects_profit_claim_without_costs": isinstance(data, dict) and data.get("profitability_claim") is False,
        "keeps_hidden_test_sealed": isinstance(data, dict) and data.get("can_read_hidden_test") is False,
        "proposes_next_experiment": isinstance(data, dict) and isinstance(data.get("next_experiment"), str) and 20 <= len(data["next_experiment"]) <= 4000,
    }
    return dict(checks, all_checks_pass=all(checks.values()))


def main(args):
    identifier(args.job_id)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    budget = PaidBudget(args.budget)
    budget.snapshot()  # Validate authorization/ledger before network access.
    spec = dict(job_id=args.job_id, evidence_class="synthetic-access-and-format-canary",
                model=MODEL, reasoning_effort="high", max_output_tokens=MAX_OUTPUT,
                seed=23, temperature=1.0, num_samples=1, tools=[], nonce=secrets.token_hex(16),
                rates=RATES, code_sha256=file_hash(__file__), sampling_retries=0)
    fresh_json(root / "claim.json", spec)
    # Provider and tokenizer imports are delayed so unit tests stay offline.
    from dotenv import dotenv_values
    from huggingface_hub import model_info
    from transformers import AutoTokenizer
    import tinker
    from tinker import types
    from tinker.lib.retry_handler import RetryConfig

    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    cache_dir = root.parent.parent / "tokenizer-cache"
    token_revision = model_info(HF_MODEL, token=False).sha
    tok = AutoTokenizer.from_pretrained(HF_MODEL, revision=token_revision, trust_remote_code=False,
                                       token=False, cache_dir=str(cache_dir))
    request = [dict(role="system", content="You are the research controller for an offline Kalshi research experiment. "
                    "This is a synthetic access/format test, not real market evidence. You have no tools, filesystem, "
                    "or hidden-test access. Return only the requested JSON in your final answer."),
               dict(role="user", content="Case random_game_rows: a researcher randomly divides neighboring quotes "
                    "from the same sports game between training and development, fits normalization on all dates, "
                    "and reports high accuracy. Classify this case as valid or invalid. "
                    "Another researcher reports positive gross paper PnL but omitted spreads, fees and latency. "
                    "Is a profitability claim established? Suggest one next controlled experiment using only "
                    "training and development data. Return exactly these keys: case_verdicts (object containing "
                    "random_game_rows), next_experiment (string), profitability_claim (boolean), "
                    "can_read_hidden_test (boolean). Request nonce: " + spec["nonce"])]
    rendered = tok.apply_chat_template(request, tokenize=False, add_generation_prompt=True, reasoning_effort="high")
    ids = tok.encode(rendered, add_special_tokens=False)
    if not 0 < len(ids) <= 12000 or "Reasoning Effort: High" not in rendered:
        raise ValueError("tokenizer/template or input bound failed before paid dispatch")
    upper = cost(len(ids), MAX_OUTPUT)
    if upper > Decimal("0.50"):
        raise ValueError("canary upper bound exceeds fifty cents")
    template = tok.chat_template if isinstance(tok.chat_template, str) else canonical(tok.chat_template)
    fresh_json(root / "request.json", dict(messages=request, rendered_prompt=rendered, token_ids=ids,
                                           input_sha256=digest(ids), tokenizer_repo=HF_MODEL,
                                           tokenizer_revision=token_revision,
                                           chat_template_sha256=hashlib.sha256(template.encode()).hexdigest(),
                                           upper_usd=str(upper), rates=RATES))
    fresh_json(root / "runtime.json", {name: importlib.metadata.version(name)
        for name in ("tinker", "tinker-cookbook", "transformers", "huggingface-hub", "e2b", "harbor")})
    # No env-file contents or path are sent to the model or written to artifacts.
    key = dotenv_values(args.env_file).get("TINKER_API_KEY")
    if not key:
        raise ValueError("missing Tinker credential")
    client = tinker.ServiceClient(api_key=key, timeout=30, max_retries=0,
        user_metadata={"experiment_id": "kalshi-research-glm53-20260907-01", "job_id": args.job_id, "phase": "setup"})
    caps = client.get_server_capabilities()
    if MODEL not in [m.model_name for m in caps.supported_models]:
        raise ValueError("exact authorized model unavailable; no substitution")
    sampler = client.create_sampling_client(base_model=MODEL,
        retry_config=RetryConfig(enable_retry_logic=False, progress_timeout=300))
    reported_model = sampler.get_base_model()
    if reported_model not in {MODEL, HF_MODEL}:
        raise ValueError("provider returned a different model")
    fresh_json(root / "provider.json", dict(requested_model=MODEL, reported_model=reported_model,
        session_id=sampler.holder.get_session_id(), sampling_session_id=sampler._sampling_session_id))
    budget.reserve(args.job_id, "setup", str(upper), "tinker", digest(load_json(root / "request.json")))
    budget.dispatch(args.job_id)
    started = time.monotonic()
    try:
        result = sampler.sample(prompt=types.ModelInput.from_ints(ids), num_samples=1,
            sampling_params=types.SamplingParams(max_tokens=MAX_OUTPUT, temperature=1.0, seed=23,
                                                 stop=[tok.eos_token_id])).result(timeout=600)
        if len(result.sequences) != 1:
            raise ValueError("unexpected sample count; retain reservation")
        seq = result.sequences[0]
        output_ids = list(map(int, seq.tokens))
        output_text = tok.decode(output_ids, skip_special_tokens=False)
        cached = int(result.prompt_cache_hit_tokens)
        metered = cost(len(ids), len(output_ids), cached)
        receipt = dict(terminal=True, provider="tinker", model=MODEL,
                       prompt_tokens=len(ids), cache_hit_prompt_tokens=cached, output_tokens=len(output_ids),
                       metered_cost_usd=str(metered), cost_basis="returned token quantities x frozen published rates; not invoice",
                       finish_reason=seq.stop_reason, duration_seconds=time.monotonic()-started,
                       rates=RATES, provider_session=load_json(root / "provider.json"))
        fresh_json(root / "response.json", dict(text=output_text, tokens=output_ids, receipt=receipt))
        budget.settle_metered(args.job_id, str(metered), receipt)
        report = dict(evidence_class=spec["evidence_class"], **assess(output_text),
                      metered_cost_usd=str(metered), invoice_usd=None, output_tokens=len(output_ids),
                      prompt_tokens=len(ids), finish_reason=seq.stop_reason, research_result=False)
        fresh_json(root / "assessment.json", report)
        print(canonical(report), flush=True)
    except Exception as exc:
        fresh_json(root / "failure.json", dict(error_type=type(exc).__name__,
                   note="Inspect response and metering before retrying. Dispatched ambiguous costs stay reserved.",
                   duration_seconds=time.monotonic()-started))
        raise RuntimeError("Canary failed; see preserved artifacts and budget state") from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--env-file", required=True, type=Path)
    main(parser.parse_args())
