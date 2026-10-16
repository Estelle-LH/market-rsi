"""Reviewed two-round envelope and mechanical child bindings; no role dispatch."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

SOURCES = ("tools/earnings_loop_policy.py", "tools/earnings_controller.py", "tools/earnings_controller_archive.py", "tools/earnings_clock.py",
           "tools/earnings_feedback_loop.py", "tools/earnings_feedback.py",
           "research/market_rsi/supervisor_harness/feedback_linked_loop.py",
           "research/market_rsi/supervisor_harness/account_controller_feedback_consumer.py",
           "research/market_rsi/supervisor_harness/opened_train_discovery_worker.py",
           "research/market_rsi/supervisor_harness/continuous_discovery_batch.py")
LIMITS = {"max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600}
FIELDS = {"schema", "source_commit", "baseline_config", "root", "forecasts", "controllers",
          "max_rounds", "controller_limits", "review", "loop_policy_sha256"}
ADDITIONS = {"research_recipe", "parent_feedback_sha256", "feedback_packet",
             "controller_proposal", "loop_authorization"}
MUTABLE = {"output", "review", "launch_policy_sha256"}


def _entry():
    import earnings_entry
    return earnings_entry


def _path(value):
    if type(value) is not str:
        raise ValueError("Canonical absolute path required")
    path = Path(value)
    if not path.is_absolute() or str(path) != value or path.resolve() != path:
        raise ValueError("Canonical absolute path required")
    return path


def _read(binding, expected=None):
    if (type(binding) is not dict or set(binding) != {"path", "sha256"}
            or type(binding["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])):
        raise ValueError("Exact immutable artifact binding required")
    path = _path(binding["path"])
    if expected is not None and path != expected:
        raise ValueError("Artifact is outside its declared role slot")
    return _entry().strict_json(_entry().checked(binding).decode())


def policy_sha(envelope):
    value = {k: v for k, v in envelope.items() if k not in {"review", "loop_policy_sha256"}}
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_envelope(envelope):
    entry = _entry()
    if (type(envelope) is not dict or set(envelope) != FIELDS
            or envelope["schema"] != "earnings_feedback_envelope_v1"
            or type(envelope["source_commit"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", envelope["source_commit"])
            or type(envelope["max_rounds"]) is not int or envelope["max_rounds"] != 2
            or type(envelope["controller_limits"]) is not dict or envelope["controller_limits"] != LIMITS
            or any(type(v) is not int for v in envelope["controller_limits"].values())):
        raise ValueError("Exact two-round loop envelope required")
    base = envelope["baseline_config"]
    if (type(base) is not dict or ADDITIONS & set(base) or base.get("source_commit") != envelope["source_commit"]
            or type(base.get("task_id")) is not str or not base["task_id"]
            or type(base.get("cik")) is not str or not base["cik"]
            or base.get("deadline_utc") != entry.DEADLINE or base.get("new_request_cutoff_utc") != entry.CUTOFF):
        raise ValueError("Original baseline/task/window boundary required")
    if _path(envelope["root"]).parent != entry.ARCHIVE / "loops":
        raise ValueError("Exact reviewed canonical loop root required")
    if "archived_first_controller" in base and "inherited_clock" not in base:
        raise ValueError("Recovery must inherit the original sealed clock")
    for name, folder in (("forecasts", "attempts"), ("controllers", "controllers")):
        values = envelope[name]
        if (type(values) is not list or len(values) != 2 or any(type(v) is not str for v in values) or len(set(values)) != 2
                or any(_path(v).parent != entry.ARCHIVE / folder for v in values)):
            raise ValueError("Two unique canonical role slots required")
    if envelope["loop_policy_sha256"] != policy_sha(envelope):
        raise ValueError("Actual loop policy changed")
    review = _read(envelope["review"])
    if (type(review) is not dict or review.get("verdict") != "PASS_FOR_TWO_BOUNDED_FEEDBACK_ROUNDS"
            or review.get("source_commit") != envelope["source_commit"]
            or review.get("loop_policy_sha256") != envelope["loop_policy_sha256"]):
        raise ValueError("Exact independent loop review required")
    for name in SOURCES:
        path = _path(str(entry.REPO / name))
        try:
            committed = subprocess.run(["git", "show", envelope["source_commit"] + ":" + name],
                                       cwd=entry.REPO, check=True, capture_output=True).stdout
        except subprocess.CalledProcessError as error:
            raise ValueError("Loop source absent from reviewed commit") from error
        if not path.is_file() or path.read_bytes() != committed:
            raise ValueError("Loop source differs from reviewed commit")
    return entry.preflight(base, require_review=False)


def validate_child(config):
    if (type(config) is not dict or type(config.get("loop_authorization")) is not dict
            or set(config["loop_authorization"]) != {"envelope"}):
        raise ValueError("Reviewed parent envelope binding required")
    envelope = _read(config["loop_authorization"]["envelope"])
    original = validate_envelope(envelope)
    base = envelope["baseline_config"]
    if (set(config) - set(base) != ADDITIONS or set(base) - set(config)
            or any(_canonical(config[k]) != _canonical(value) for k, value in base.items() if k not in MUTABLE)):
        raise ValueError("Child changed protected baseline fields")
    output = _path(config["output"])
    if str(output) not in envelope["forecasts"]:
        raise ValueError("Undeclared forecast slot")
    index = envelope["forecasts"].index(str(output))
    packet = _read(config["feedback_packet"], _path(envelope["root"]) / f"packet-{index + 1:02d}.json")
    proposal = _read(config["controller_proposal"], _path(envelope["controllers"][index]) / "proposal.json")
    entry = _entry()
    recipe = entry.load_research_recipe(config)
    feedback = packet.get("feedback") if type(packet) is dict else None
    observation = feedback.get("observation") if type(feedback) is dict else None
    score = feedback.get("baseline_score_out_of_5") if type(feedback) is dict else None
    if (type(packet) is not dict or not {"schema", "task_id", "parent_feedback_sha256", "questions", "feedback", "prior_recipe"} <= set(packet)
            or packet["task_id"] != config["task_id"] or packet["parent_feedback_sha256"] != config["parent_feedback_sha256"]
            or packet["questions"] != entry.FilingTools(original[0]).files["questions.md"]
            or type(feedback) is not dict or set(feedback) - {"observation", "baseline_score_out_of_5"}
            or type(observation) is not dict or observation.get("schema") != "earnings_aggregate_feedback_v1"
            or observation.get("task_id") != config["task_id"] or observation.get("cik") != config["cik"]
            or ("baseline_score_out_of_5" in feedback and
                (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 5))):
        raise ValueError("Packet task/parent/questions/aggregate feedback differs")
    if (type(proposal) is not dict or set(proposal) != {"recipe", "input_packet", "source_commit"}
            or proposal["recipe"] != recipe or proposal["input_packet"] != config["feedback_packet"]
            or proposal["source_commit"] != config["source_commit"]):
        raise ValueError("Checked Controller proposal differs from child")
    return original


CAPACITY_FIELDS = {"schema", "id", "mode", "source_commit", "sources", "study", "root", "cik",
                   "max_rounds", "role_limits", "slots", "initial_state", "grant", "window", "evaluation_kernel"}


def capacity_sources():
    return sorted(set((*SOURCES, *_entry().SOURCES,
        "tools/earnings_research_state.py", "tools/earnings_capacity_adapter.py", "tools/earnings_capacity_worker.py",
        "tools/earnings_capacity_task.py", "tools/earnings_execution_receipt.py", "research/market_rsi/supervisor_harness/capacity_feedback_engine.py",
        "tools/earnings_capacity_runtime.py", "tools/earnings_capacity_assembly.py", "tools/earnings_assembly_readiness.py",
        "tools/earnings_round_plan.py",
        "tools/earnings_native_namespace.py", "tools/earnings_source_review.py", "tools/earnings_pending_evolution.py",
        "tools/earnings_capacity_checks.py", "tools/earnings_effect_review.py", "tools/earnings_shadow_trial.py",
        "tools/earnings_shadow_measurement.py", "tools/earnings_research_diagnostics.py", "tools/earnings_completed_replay.py",
        "configs/earnings_coevolution/researcher_v0.py", "configs/earnings_coevolution/harness_v0.py",
        "research/market_rsi/supervisor_harness/research_capacity_identity.py",
        "research/market_rsi/supervisor_harness/research_capacity_activation.py",
        "research/market_rsi/market_rsi.py",
        "research/market_rsi/supervisor_harness/learning_checkpoint_assessment.py",
        "research/market_rsi/data_scientist_harness/__init__.py",
        "research/market_rsi/data_scientist_harness/co_evolution_loop.py")))


def validate_capacity_episode(envelope):
    """Prospective offline scope, not permission or a paid-role implementation."""
    from earnings_round_plan import round_count
    if type(envelope) is dict and envelope.get('schema') == 'earnings_capacity_episode_v3':
        from earnings_live_capacity import admit
        admit(envelope)
        return _read(envelope['study'])
    entry = _entry()
    round_count(envelope)
    if (type(envelope) is not dict or set(envelope) != CAPACITY_FIELDS
            or envelope["schema"] not in {"earnings_capacity_episode_v1", "earnings_capacity_episode_v2"}
            or envelope["mode"] != "offline_replay"
            or envelope["grant"] is not None or envelope["window"] is not None
            or type(envelope["id"]) is not str or not re.fullmatch(r"earnings-coevolution-20261013-[a-z0-9-]{1,60}", envelope["id"])
            or type(envelope["source_commit"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", envelope["source_commit"])
            or envelope["role_limits"] != {"controller": LIMITS, "author": LIMITS, "review": LIMITS}
            or any(type(v) is not int for role in envelope["role_limits"].values() for v in role.values())):
        raise ValueError("Exact offline episode required; live roles/grants are not admitted here")
    root = _path(envelope["root"])
    if root != entry.PILOT.parent.parent / "earnings-coevolution-plan-20261013" / "episodes" / envelope["id"]:
        raise ValueError("New episode namespace required; expired roots/IDs stay closed")
    study = _read(envelope["study"])
    if (study.get("schema") != "earnings_coevolution_study_v1" or study.get("new_live_grant") is not None
            or study.get("new_episode_deadline") is not None or study.get("closed_episode", {}).get("reopen") is not False
            or study.get("closed_episode", {}).get("status") != "completed_bounded_overnight"):
        raise ValueError("Original closed history and no-live study required")
    _read(study["closed_episode"]["binding"])
    if envelope["cik"] not in {c["cik"] for c in study["cases"]}:
        raise ValueError("Undeclared company case")
    admitted = next(c for c in study['cases'] if c['cik'] == envelope['cik'])
    kernel = envelope['evaluation_kernel']
    if (type(kernel) is not dict or set(kernel) != {'scorer', 'qa'}
            or admitted.get('evaluation_kernel') != kernel or study.get('scorer') != kernel['scorer']):
        raise ValueError('Exact study-bound protected task scorer/QA kernel required')
    _read(kernel['qa'])
    _entry().checked(kernel['scorer'])
    slots = envelope["slots"]
    if (type(slots) is not list or len(slots) != envelope["max_rounds"]
            or any(type(slot) is not dict or set(slot) != {"controller", "author", "review", "forecast"} for slot in slots)):
        raise ValueError("Exact finite role slots required")
    locations = [v for slot in slots for v in slot.values()]
    if len(set(locations)) != len(locations) or any(not _path(p).is_relative_to(root / "roles") for p in locations):
        raise ValueError("Unique new bounded role slots required")
    sources = envelope["sources"]
    if type(sources) is not dict or set(sources) != set(capacity_sources()):
        raise ValueError("Complete actual source closure required")
    for name, token in sources.items():
        if not re.fullmatch(r"[0-9a-f]{64}", token):
            raise ValueError("Actual source hash required")
        committed = subprocess.run(["git", "show", envelope["source_commit"] + ":" + name],
                                   cwd=entry.REPO, check=True, capture_output=True).stdout
        if hashlib.sha256(committed).hexdigest() != token or (entry.REPO / name).read_bytes() != committed:
            raise ValueError("Actual episode source differs from its commit")
    return study
