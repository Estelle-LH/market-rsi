"""Thin real-task adapter for the unchanged seven-stage feedback driver."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

import earnings_entry as e
import earnings_controller as controller
import earnings_loop_policy as policy
import earnings_clock as clock
from earnings_feedback import project_feedback
from earnings_night_budget import utc_epoch

sys.path.insert(0, str(e.REPO / "research" / "market_rsi"))
from supervisor_harness import feedback_linked_loop as driver

BASELINE_RESULT_SHA = "6ffc40babb42d6f72bbea42e4a4ea87656abebcb6810778e52bb282b6a23b0cb"
BASELINE_AUDIT_SHA = "8aa74231d19d8f63ffad1700c16e1e0c149b11b05324d71af58aab57c8ab23de"


def binding(path):
    return {"path": str(path), "sha256": e.digest(path.read_bytes())}


def save(path, value):
    e.durable_json(path, value)
    return binding(path)


def baseline_seed(config):
    result_binding = {"path": str(e.ARCHIVE / "attempts" / "alico-baseline-01" / "result.json"),
                      "sha256": BASELINE_RESULT_SHA}
    audit_binding = {"path": str(e.ARCHIVE / "diagnostics" / "alico-baseline-01-format-audit-v1" / "AUDIT.json"),
                     "sha256": BASELINE_AUDIT_SHA}
    result = e.strict_json(e.checked(result_binding).decode())
    audit = e.strict_json(e.checked(audit_binding).decode())
    if (result["status"] != "FAILED_NO_RETRY" or audit["original_entry_status"] != "FAILED_NO_RETRY"
            or audit["audit_status"] != "OFFLINE_UNCHANGED_FRESH_ARTIFACT_SCORE"
            or audit["target_count"] != 5 or audit["prediction_count"] != 5
            or audit["scorer_sha256"] != config["scorer"]["sha256"]
            or audit["qa_sha256"] != config["qa"]["sha256"]):
        raise ValueError("Original failure/audit provenance differs")
    observation = project_feedback(result, None, task_id=config["task_id"], cik=config["cik"])
    return {"feedback": {"observation": observation, "baseline_score_out_of_5": audit["points"]},
            "prior_recipe": None, "artifacts": [result_binding, audit_binding]}


def handlers(envelope, envelope_binding, *, controller_factory=None, forecast_factory=None):
    config, root = envelope["baseline_config"], Path(envelope["root"])

    def packet(context):
        company, _, _ = policy.validate_envelope(envelope)
        previous = context["previous_result"]
        value = {"schema": "earnings_controller_packet_v1", "task_id": config["task_id"],
            "parent_feedback_sha256": context["previous_feedback_sha256"],
            "questions": e.FilingTools(company).files["questions.md"],
            "feedback": previous["feedback"], "prior_recipe": previous["prior_recipe"]}
        controller.safe_input(value)
        bound = save(root / f"packet-{context['round_index']:02d}.json", value)
        return {"packet": bound, "artifacts": [bound]}

    def propose(context):
        if context["round_index"] == 1 and "archived_first_controller" in config:
            from earnings_controller_archive import archive_proposal
            bound = archive_proposal(envelope, context["outputs"]["input"]["packet"], context["round_index"])
            return {"proposal": bound, "artifacts": [bound], "origin": "ARCHIVAL_UNCHANGED_CANDIDATE_NEW_H_ADMISSION",
                    "new_provider_generations": 0}
        bound = controller.propose(envelope, context["outputs"]["input"]["packet"],
                                   context["round_index"], client_factory=controller_factory)
        return {"proposal": bound, "artifacts": [bound]}

    def implement(context):
        outputs, index = context["outputs"], context["round_index"]
        proposal_binding = outputs["controller"]["proposal"]
        proposal = e.strict_json(e.checked(proposal_binding).decode())
        recipe_binding = save(root / f"recipe-{index:02d}.json", proposal["recipe"])
        child = dict(config, output=envelope["forecasts"][index - 1], research_recipe=recipe_binding,
            parent_feedback_sha256=context["previous_feedback_sha256"], feedback_packet=outputs["input"]["packet"],
            controller_proposal=proposal_binding, loop_authorization={"envelope": envelope_binding})
        child["launch_policy_sha256"] = e.policy_sha(child)
        policy.validate_child(child)
        bound = save(root / f"child-{index:02d}.json", child)
        return {"child": bound, "recipe": recipe_binding, "artifacts": [bound, recipe_binding]}

    def source_review(context):
        child_binding = context["outputs"]["implement"]["child"]
        child = e.strict_json(e.checked(child_binding).decode())
        e.preflight(child)
        return {"status": "MECHANICAL_CHILD_ADMITTED_UNDER_REVIEWED_PARENT", "child": child_binding,
                "parent_review": envelope["review"]}

    def execute(context):
        child = e.strict_json(e.checked(context["outputs"]["implement"]["child"]).decode())
        result = e.run_one(child, client_factory=forecast_factory)
        output = Path(child["output"])
        artifacts = [binding(output / "result.json"), binding(output / "identity.json")]
        if (output / "effective-recipe.json").exists():
            artifacts.append(binding(output / "effective-recipe.json"))
        if result["status"] != "COMPLETED_SCORED":
            # Preserve paid failure and stop; a fresh retry needs a new diagnosis/authorization.
            raise RuntimeError("Forecast failed once; inspect original result/receipts before a new attempt")
        return {"result": artifacts[0], "artifacts": artifacts}

    def result_review(context):
        outputs = context["outputs"]
        result = e.strict_json(e.checked(outputs["execute"]["result"]).decode())
        child = e.strict_json(e.checked(outputs["implement"]["child"]).decode())
        score = e.strict_json((Path(child["output"]) / "score.json").read_text())
        observation = project_feedback(result, score, task_id=config["task_id"], cik=config["cik"])
        baseline = context["seed"]["feedback"]["baseline_score_out_of_5"]
        prior = context["previous_result"]["feedback"]["observation"]["prediction"]["score_out_of_5"]
        recipe = e.load_research_recipe(child)
        return {"feedback": {"observation": observation, "baseline_score_out_of_5": baseline},
            "prior_recipe": recipe, "delta_from_audited_baseline": observation["prediction"]["score_out_of_5"] - baseline,
            "delta_from_parent": None if prior is None else observation["prediction"]["score_out_of_5"] - prior,
            "recipe_changed": recipe["research_instructions"] != (context["previous_result"]["prior_recipe"] or {}).get("research_instructions"),
            "artifacts": outputs["execute"]["artifacts"] + [outputs["implement"]["recipe"]],
            "claims": {"feedback_delivered": True, "heldout_gain": False, "co_evolving_RH": False}}

    def reconcile(context):
        return context["outputs"]["result_review"]

    return dict(zip(driver.STAGES, (packet, propose, implement, source_review, execute, result_review, reconcile)))


def run(envelope_binding, *, controller_factory=None, forecast_factory=None,
        assembly_binding=None, client_factory=None, task=None):
    envelope = e.strict_json(e.checked(envelope_binding).decode())
    if envelope.get('schema') in {'earnings_capacity_episode_v1', 'earnings_capacity_episode_v2', 'earnings_capacity_episode_v3'}:
        if controller_factory is not None or forecast_factory is not None or assembly_binding is None:
            raise ValueError('Capacity requires its explicit assembly, not legacy role factories')
        from earnings_capacity_assembly import run_assembled_capacity
        return run_assembled_capacity(envelope_binding, assembly_binding, client_factory=client_factory, task=task)
    if assembly_binding is not None or client_factory is not None or task is not None:
        raise ValueError('Legacy run cannot consume capacity assembly or task overrides')
    policy.validate_envelope(envelope)
    config = envelope["baseline_config"]
    window, clock_binding = clock.capture_or_load(envelope["root"], config)
    seed = baseline_seed(config)
    def identity():
        sources = {name: binding(e.REPO / name) for name in (*e.SOURCES, *policy.SOURCES)}
        common = {"source_commit": envelope["source_commit"], "envelope": envelope_binding, "sources": sources,
                  "clock": clock_binding}
        return {stage: dict(common, handler=stage) for stage in driver.STAGES}
    def admit(context):
        policy.validate_envelope(envelope)
        if time.time() >= utc_epoch(config["deadline_utc"]) or time.monotonic() >= window["deadline_monotonic"]:
            return False
        if context["stage"] in ("controller", "execute") and (time.time() >= utc_epoch(config["new_request_cutoff_utc"])
                or time.monotonic() >= window["cutoff_monotonic"]):
            return False
        with sqlite3.connect(Path(config["ledger"]).as_uri() + "?mode=ro", uri=True) as db:
            charged = db.execute("SELECT COALESCE(SUM(charged),0) FROM requests").fetchone()[0]
        return charged < 200_000_000_000 and charged - config["baseline"]["charged_nano_usd"] < 20_000_000_000
    return driver.run(envelope["root"], handlers(envelope, envelope_binding,
        controller_factory=controller_factory, forecast_factory=forecast_factory), seed=seed,
        admit=admit, max_rounds=2, handler_identity=identity)


def run_capacity(envelope_binding, capacity, *, roles=None, task=None, pending_handler=None):
    """Compatibility entry for the common seven-stage capacity engine.

    Explicit offline services only. Live budget/clock/busy claims and original
    scorer verification need their exact adapters; no paid fallback.
    """
    from earnings_capacity_task import EarningsTask
    from supervisor_harness import capacity_feedback_engine as engine
    names = {"controller", "author", "review", "forecast"}
    if type(roles) is not dict or set(roles) != names or any(not callable(f) for f in roles.values()):
        raise ValueError("Explicit trusted offline role services required; no paid fallback")
    services = {name: roles[name] for name in ("controller", "author", "review")}
    services["execute"] = roles["forecast"]
    return engine.run(envelope_binding, capacity, EarningsTask() if task is None else task,
                      services=services, pending_handler=pending_handler)



def main(argv=None, *, client_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--assembly", type=Path)
    parser.add_argument("--completed-replay", type=Path)
    args = parser.parse_args(argv)
    bound = binding(args.envelope.absolute())
    envelope = e.strict_json(e.checked(bound).decode())
    if args.completed_replay is not None:
        if args.assembly is not None or args.preflight_only or client_factory is not None:
            raise ValueError('Completed replay is callback-free and separate from warm assembly')
        from earnings_completed_replay import replay_completed
        print(json.dumps(replay_completed(bound, binding(args.completed_replay.absolute())), sort_keys=True))
        return
    assembly = None if args.assembly is None else binding(args.assembly.absolute())
    if args.preflight_only:
        if envelope.get('schema') in {'earnings_capacity_episode_v1', 'earnings_capacity_episode_v2', 'earnings_capacity_episode_v3'}:
            from earnings_capacity_assembly import validate_assembly
            from earnings_live_capacity import live, provider_client
            if live(envelope) and client_factory is None: client_factory = provider_client
            validate_assembly(bound, assembly, client_factory=client_factory)
            print(json.dumps({'status': ('REAL_CAPACITY_ASSEMBLY_PREFLIGHT_PASS' if envelope.get('mode')=='real_provider'
                else 'OFFLINE_CAPACITY_ASSEMBLY_PREFLIGHT_PASS'), 'new_provider_calls': 0}))
            return
        if assembly is not None or client_factory is not None:
            raise ValueError('Legacy preflight cannot consume capacity transport/config')
        policy.validate_envelope(envelope)
        baseline_seed(envelope["baseline_config"])
        print(json.dumps({"status": "OFFLINE_LOOP_PREFLIGHT_PASS", "new_rounds": 2}))
    else:
        print(json.dumps(run(bound, assembly_binding=assembly, client_factory=client_factory), sort_keys=True))


if __name__ == "__main__":
    main()
