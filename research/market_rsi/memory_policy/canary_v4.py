"""Bind deterministic mechanics, trainer, cleanup, and real terminal canaries."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json
import memory_policy.canary as engine
import memory_policy.controller as controller
from memory_policy.broker_v3 import Broker, refit_worker
from memory_policy.remote_cleanup_canary_v4 import (
    source_hashes as remote_cleanup_source_hashes,
)
from memory_policy.study_v4 import configure_engine, hashes
from memory_policy.trainer_canary_v3 import source_hashes as trainer_source_hashes


def validate_terminal(path):
    root = Path(__file__).resolve().parents[1]
    terminal = load_json(path)
    if (terminal.get("schema") != "memory_policy_terminal_canary_v4"
            or terminal.get("passed") is not True
            or terminal.get("actual_provider_calls") != 1
            or terminal.get("market_rows") != 0
            or terminal.get("scores_opened") != 0
            or terminal.get("candidate_fits") != 0
            or terminal.get("model_authored_submission") is not True
            or terminal.get("submission_inferred_or_repaired") is not False
            or terminal.get("submitted_trial_id") != "baseline"
            or terminal.get("provider_source_sha256") !=
                file_hash(root / "codex_glm_provider.py")
            or terminal.get("adapter_source_sha256") !=
                file_hash(root / "codex_glm_responses_adapter.py")
            or terminal.get("contract_source_sha256") !=
                file_hash(root / "controller_harness_contract.py")):
        raise ValueError("same-source real zero-score terminal canary required")
    signed = dict(terminal)
    result_sha256 = signed.pop("result_sha256", None)
    if result_sha256 != digest(signed):
        raise ValueError("terminal canary signature differs")
    return terminal


def run(output, spec, trainer_canary, remote_cleanup_canary, terminal_canary):
    output = Path(output).resolve()
    trainer_canary = Path(trainer_canary).resolve()
    remote_cleanup_canary = Path(remote_cleanup_canary).resolve()
    terminal_canary = Path(terminal_canary).resolve()
    if output.exists():
        raise ValueError("fresh v4 full canary ID required")
    trainer = load_json(trainer_canary)
    if (trainer.get("passed") is not True
            or trainer.get("source_hashes") != trainer_source_hashes()
            or trainer.get("positive_canary", {}).get("provider_calls") != 0
            or trainer.get("positive_canary", {}).get("scores_opened") != 0
            or trainer.get("model_may_be_reused_for_training") is not False):
        raise ValueError("same-source positive trainer canary required")
    cleanup = load_json(remote_cleanup_canary)
    if (cleanup.get("passed") is not True
            or cleanup.get("source_hashes") != remote_cleanup_source_hashes()
            or cleanup.get("provider_calls") != 0
            or cleanup.get("raw_source_deleted") is not False):
        raise ValueError("same-source v4 remote cleanup canary required")
    terminal = validate_terminal(terminal_canary)

    output.mkdir()
    configure_engine()
    engine.hashes = hashes
    engine.Broker = Broker
    engine.run_worker = refit_worker
    engine.run_session = controller.run_session
    engine.run(output / "controller", Path(spec).resolve())
    result = load_json(output / "controller/canary.json")
    result.update({
        "schema": "memory_policy_full_canary_v4",
        "trainer_canary_sha256": file_hash(trainer_canary),
        "trainer_canary_result_sha256": trainer["result_sha256"],
        "trainer_source_hashes": trainer["source_hashes"],
        "trainer_positive_canary": trainer["positive_canary"],
        "trainer_model_reused": False,
        "remote_cleanup_canary_sha256": file_hash(remote_cleanup_canary),
        "remote_cleanup_source_hashes": cleanup["source_hashes"],
        "remote_cleanup_passed": True,
        "terminal_canary_sha256": file_hash(terminal_canary),
        "terminal_canary": terminal,
    })
    result["sha256"] = digest({key: value for key, value in result.items()
                               if key != "sha256"})
    fresh_json(output / "canary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--trainer-canary", type=Path, required=True)
    parser.add_argument("--remote-cleanup-canary", type=Path, required=True)
    parser.add_argument("--terminal-canary", type=Path, required=True)
    args = parser.parse_args()
    run(args.output, args.spec, args.trainer_canary,
        args.remote_cleanup_canary, args.terminal_canary)
