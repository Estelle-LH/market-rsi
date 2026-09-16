"""Fabricated lifecycle check: no real LLM calls, no real research scores."""
import argparse
from pathlib import Path

from agent_study import ARMS, Study
from market_rsi import digest, fresh_json


def fixture_manifest():
    tasks = []
    for i, phase in enumerate(("learning", "learning", "transfer", "transfer")):
        tasks.append(dict(id=f"task-{i}", phase=phase, group_ids=[f"game-{i}"],
                          start_ms=i * 10000, end_ms=i * 10000 + 1000,
                          data_sha256=digest(["fixture-data", i]),
                          scorer_sha256=digest("fixture-scorer"),
                          baseline=dict(model="fixture-logistic", steps=10, seed=23),
                          public_brief="Fabricated task; verify lifecycle rules only."))
    return dict(study_id="fixture-study", evidence_class="fixture", tasks=tasks,
                agent=dict(model_id="fixture-no-llm", backend="scripted-test", version="1",
                           base_instructions="Fixture instructions, not an actual researcher.",
                           tools_sha256=digest("fixture-tools")),
                limits=dict(calls_per_task=12, tokens_per_task=20000, experiments_per_task=3,
                            tool_seconds_per_task=120, memory_max_chars=4000, new_external_usd="0"))


def fixture_usage():
    return dict(calls=0, tokens=0, experiments=0, tool_seconds=0, actual_new_external_usd="0")


def learn(study, manifest):
    for task in manifest["tasks"]:
        if task["phase"] != "learning":
            continue
        for arm in ARMS:
            request = study.begin_episode(task["id"], arm)
            study.record_learning_feedback(task["id"], arm,
                dict(scope="train_dev_only", evidence_class="fixture", note="Fabricated execution feedback."),
                fixture_usage(), digest("fixture-executor-receipt"))
            if ARMS[arm]["carry_memory"]:
                study.update_memory(arm, "Fixture memory from " + task["id"],
                                    [request["episode_id"]], digest("fixture-scripted-response"))


def submit_all(study, manifest):
    for task in manifest["tasks"]:
        if task["phase"] == "transfer":
            for arm in ARMS:
                request = study.begin_episode(task["id"], arm)
                study.commit_submission(task["id"], arm,
                    dict(initial_baseline_sha256=request["baseline_sha256"],
                         predictor_sha256=digest(["fixture-predictor", arm, task["id"]]),
                         executor_receipt_sha256=digest("fixture-executor-receipt"), status="valid"),
                    fixture_usage())


def fixture_scores(manifest):
    return {task["id"]: dict(baseline_brier=.25, arms={arm: .25 for arm in ARMS},
                            scorer_sha256=task["scorer_sha256"], data_sha256=task["data_sha256"])
            for task in manifest["tasks"] if task["phase"] == "transfer"}


def run(root):
    manifest = fixture_manifest()
    study = Study.create(root, manifest)
    learn(study, manifest)
    study.freeze_researchers()
    submit_all(study, manifest)
    study.begin_scoring()
    result = study.record_scores(fixture_scores(manifest), digest("fixture-scorer-receipt"))
    study.verify()
    summary = dict(evidence_class="fixture", actual_agent_calls=0, actual_model_fits=0,
                   scores_are_fabricated=True, learning_result_claim=False,
                   learning_tasks=2, transfer_tasks=2, arms=list(ARMS),
                   lifecycle_complete=True, results_file="transfer-results.json")
    fresh_json(Path(root) / "smoke-summary.json", summary)
    print(Path(root) / "smoke-summary.json")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    run(parser.parse_args().output)
