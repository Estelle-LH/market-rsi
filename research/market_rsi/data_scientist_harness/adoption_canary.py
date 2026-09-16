"""Offline consumer parity: frozen legacy vs current core, synthetic data only.

Two fresh subprocesses execute the same broker workflow and four real CPU fits.
Public-source replies are fixtures, not literature searches. No LLM, provider,
market data, Dev/Test, dependency installation or other project is accessed.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROFILE_SHA = "77e4efe4ce8184a7999c2e1a41d21ce1b40b33dea482fb356467b38e761ba70d"


def child(source, root):
    sys.path.insert(0, str(source))
    from data_scientist_harness import fixtures, profiles
    from data_scientist_harness.broker import Broker, TOOLS
    from market_rsi import fresh_json

    if Path(profiles.__file__).resolve() != source / "data_scientist_harness/profiles.py":
        raise ValueError("comparison child imported the wrong consumer")
    manifest = fixtures.workspace(root, network=True)
    broker = Broker(root, manifest, transport=fixtures.fake_transport)
    status = broker.call("inspect_harness", {})
    read = broker.call("read_public_source", {"url": "https://example.org/research", "offset": 0})
    broker.call("search_literature_live", {"query": "synthetic mechanics fixture only"})
    notes = {"question": "same fixture", "read_records": [read["record_id"]],
             "applicability": "mechanics only", "limitations": "not market evidence",
             "alternatives": "unchanged baseline", "proposed_test": "exact consumer parity"}
    feature = broker.call("record_research", dict(notes, layer="feature_engineering"))
    trainer = broker.call("record_research", dict(notes, layer="trainer_engineering"))
    raw = broker.call("profile_raw_series", {})
    derived = broker.call("profile_candidate_feature", {
        "spec": fixtures.plan()["features"][0], "research_record": feature["record_id"]})
    review = broker.call("review_feature_set", {"profile_records": [derived["record_id"]],
        "dispositions": [{"profile_record": derived["record_id"], "reason": "fixture", "risk": "synthetic"}]})
    broker.call("acknowledge_current_findings", {"finding_sha256": status["finding_sha256"],
        "responses": [{"id": "fixture-only", "handling": "fixture", "next_evidence": "real QA"}]})
    reports = {}
    extended = any(t['name']=='reflect_candidate' for t in TOOLS)
    for i, algorithm in enumerate(fixtures.MODELS):
        args = {"trial_id": f"t{i}", "parent_trial_id": "t0" if i else "",
            "plan": fixtures.plan(algorithm), "feature_review": review["record_id"],
            "trainer_research": trainer["record_id"]}
        if extended: args['experiment']=fixtures.experiment('t0' if i else '')
        result = broker.call("train_candidate", args)
        if result["process_reaped"] is not True or result["provider_cost_usd"] != "0":
            raise ValueError("worker did not complete cleanly")
        # Elapsed time is the ONLY report field excluded from exact comparison.
        reports[algorithm] = {k: v for k, v in result["report"].items() if k != "elapsed_seconds"}
        if extended: broker.call('reflect_candidate',fixtures.reflection(root,f't{i}'))
    broker.call("submit_research_decision", {"action": "select", "trial_id": "t0",
        "reason": "fixed fixture choice, not selecting a research winner"})
    broker.store.verify()
    expected_steps=18 if extended else 14
    if len(broker.store.events()) != expected_steps or any(r["status"] != "ok" for r in broker.store.records()):
        raise ValueError("all version-specific broker steps must succeed")
    clean = lambda r: {k: v for k, v in r.items() if k not in {"record_id", "record_sha256"}}
    fresh_json(root / "comparison.json", {"raw_profile": clean(raw), "feature_profile": clean(derived),
        "reports": reports, "broker_steps": expected_steps, "cpu_fits": 4, "provider_calls": 0,
        "market_data_read": False, "new_dev_test_access": False, "all_workers_reaped": True})


def run_child(source, root):
    command = [sys.executable, str(Path(__file__).resolve()), "--child", "--source-root", str(source),
               "--output", str(root)]
    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1",
           "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    with (root.parent / (root.name + ".stdout.log")).open("x") as out, \
         (root.parent / (root.name + ".stderr.log")).open("x") as err:
        proc = subprocess.Popen(command, env=env, stdout=out, stderr=err, start_new_session=True)
        try:
            code = proc.wait(timeout=55)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
            raise TimeoutError("owned synthetic parity child timed out; no automatic retry")
        if code:
            raise RuntimeError(f"{root.name} comparison failed; preserved stderr, no automatic retry")


def run(output, baseline):
    sys.path.insert(0, str(ROOT))
    from data_scientist_harness.core_dependency import dependency_identity
    from market_rsi import digest, file_hash, fresh_json, load_json

    if output.exists():
        raise ValueError("fresh parity output ID required")
    output.mkdir(parents=True)
    try:
        proof = load_json(baseline / "canary.json")
        unhashed = {k: v for k, v in proof.items() if k != "result_sha256"}
        if (digest(unhashed) != proof["result_sha256"] or proof.get("passed") is not True
                or proof.get("actual_tinker_calls") != 0 or proof.get("model_authorship_proven") is not False
                or proof["source_hashes"].get("data_scientist_harness/profiles.py") != LEGACY_PROFILE_SHA):
            raise ValueError("expected successful legacy synthetic canary commitment")
        legacy = baseline / "code"
        def verify_legacy():
            for relative, sha in proof["source_hashes"].items():
                path = (legacy / relative).resolve()
                if not path.is_relative_to(legacy) or file_hash(path) != sha:
                    raise ValueError("frozen baseline code changed")
        verify_legacy()
        fresh_json(output / "plan.json", {"changed_component": "human_authored_sanity_gates_and_research_records",
            "candidate_dependency": dependency_identity(), "baseline_canary_sha256": file_hash(baseline / "canary.json"),
            "baseline_source_hashes": proof["source_hashes"], "synthetic_rows_per_arm": 12,
            "target_features_trainer_split_seed_unchanged": True, "new_dev_test_access": False,
            "comparison": "exact", "report_exclusions": ["elapsed_seconds"], "automatic_retry": False})
        run_child(legacy, output / "baseline")
        run_child(ROOT, output / "candidate")
        before = load_json(output / "baseline/comparison.json")
        after = load_json(output / "candidate/comparison.json")
        if {k:v for k,v in before.items() if k!='broker_steps'} != {k:v for k,v in after.items() if k!='broker_steps'}:
            raise AssertionError("raw/feature profiles or trainer reports differ")
        array_pairs = 0
        for i in range(4):
            with np.load(output / f"baseline/trials/t{i}/predictions.npz", allow_pickle=False) as a, \
                 np.load(output / f"candidate/trials/t{i}/predictions.npz", allow_pickle=False) as b:
                if set(a.files) != set(b.files):
                    raise AssertionError("prediction archive fields differ")
                for key in a.files:
                    if a[key].dtype != b[key].dtype or a[key].shape != b[key].shape or a[key].tobytes() != b[key].tobytes():
                        raise AssertionError(f"prediction/row/mask differs: t{i}/{key}")
                    array_pairs += 1
        for arm in ("baseline", "candidate"):
            config = load_json(output / arm / "workspace.json")
            for path, sha in config["files"].items():
                if file_hash(path) != sha:
                    raise ValueError("comparison workspace changed")
        verify_legacy()
        result = {"passed": True, "synthetic_only": True, "actual_cpu_fits": 8,
            "profiles_exact": 2, "trainer_reports_exact": 4, "prediction_array_pairs_byte_exact": array_pairs,
            "all_workers_reaped": True, "provider_calls": 0, "provider_cost_usd": "0",
            "live_web_calls": 0, "new_dev_test_access": False, "other_project_source_required": False,
            "python_environment": sys.prefix, "consumer_local_python_environment": Path(sys.prefix).is_relative_to(ROOT),
            "baseline_unchanged": True, "dependency": dependency_identity(),
            "broker_steps_by_arm":{"baseline":before['broker_steps'],'candidate':after['broker_steps']},
            "excluded_report_fields": ["elapsed_seconds"], "full_feature_batch_adoption": False,
            "plan_sha256": file_hash(output / "plan.json"),
            "candidate_manifest_sha256": file_hash(output / "candidate/workspace.json")}
        fresh_json(output / "result.json", result)
        return result
    except Exception as error:
        fresh_json(output / "failure.json", {"error_type": type(error).__name__, "error": str(error),
            "automatic_retry": False, "provider_calls": 0})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-canary", type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args.source_root.resolve(), args.output.resolve())
    elif args.baseline_canary is None:
        parser.error("--baseline-canary is required")
    else:
        print(json.dumps(run(args.output.resolve(), args.baseline_canary.resolve()), indent=2))
