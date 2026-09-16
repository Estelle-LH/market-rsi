"""Bound the existing worker components to the recorded study schedule.

Live admission requires a separately reviewed immutable receipt. This is
orchestration code, not a source-provenance certificate or a final scorer.
Fixture transports/executors are accepted only for fixture-named studies.
One invocation advances one action; pending jobs are never redispatched.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time

import development_harbor
from coder_worker import REAP_SECONDS as CODER_REAP_SECONDS, _limits, dispatch_code_once
from dev_evidence import build_completion, commit_completion
from failure_evidence import build_worker_failure
from failure_review import build_failure_review, commit_failure_review
from glm_canary import cost
from harbor_process import WALL_SECONDS as HARBOR_WALL_SECONDS, REAP_SECONDS as HARBOR_REAP_SECONDS, run_bounded_development
from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget, money
from provider_timeout_evidence import (build_uncertain_timeout, commit_uncertain_timeout,
                                       settle_uncertain_timeout_budget)
from researcher_worker import dispatch_once
from sandbox_failure_evidence import build_sandbox_failure
from selection_worker import dispatch_selection, build_selection_completion, commit_selection
from step_deadline import LOCAL_OVERHEAD_SECONDS, PROFILE as STEP_DEADLINE_PROFILE, StepDeadline
from study_state import StudyState
from trial_inputs import execution_profile, prepare_development_trial
from worker_receipts import code_request_from_job, read_regular, read_research_terminal, read_code_terminal


SOURCES = ("study_runner.py", "study_state.py", "researcher_worker.py", "coder_worker.py",
    "selection_protocol.py", "selection_worker.py", "worker_receipts.py", "trial_inputs.py",
    "development_harbor.py", "dev_evidence.py", "failure_evidence.py", "sandbox_failure_evidence.py",
    "sandbox_receipts.py", "failure_review.py", "final_stage.py", "final_failure.py", "paid_budget.py", "research_context.py", "market_scoring.py",
    "market_rsi.py", "market_harbor.py", "glm_canary.py", "coder_probe.py",
    "bounded_process.py", "glm_process_worker.py", "glm_process_receipts.py",
    "provider_timeout_evidence.py",
    "harbor_process.py", "harbor_process_worker.py", "scientific_admission.py",
    "step_deadline.py",
    "prediction_stream.py", "prediction_candidate_server.py", "inspection_stream.py",
    "inspection_candidate_server.py", "sandbox_development_runner.py", "diagnostic_channel.py",
    "fixtures/harbor-stream-01/isolation_probe.py", "tasks/development-worker/task.toml",
    "tasks/development-worker/instruction.md", "tasks/development-worker/environment/Dockerfile")


class StudyRunner:
    def __init__(self, root):
        self.root = Path(root).absolute()

    @classmethod
    def create(cls, root, study, budget, *, runtime, coder_limits, coder_identity, task_data, live):
        execution_profile(runtime)
        _limits(coder_limits)
        with study.journal.locked():
            manifest, _ = study._load()
        if (type(live) is not bool or (not live and not manifest["experiment_id"].startswith("fixture-"))
                or budget.snapshot()["experiment_id"] != manifest["experiment_id"]):
            raise ValueError("explicit matching study/budget/worker identity required")
        # Conservatively include the entire configured general Harbor timeout,
        # even when a candidate's own declared execution cap is much shorter.
        maximum = (manifest["tasks"][0]["resource_limits"]["max_wall_seconds"]
                   + coder_limits["wall_seconds"] + CODER_REAP_SECONDS
                   + HARBOR_WALL_SECONDS + HARBOR_REAP_SECONDS
                   + LOCAL_OVERHEAD_SECONDS)
        if maximum > manifest["worst_case_step_seconds"]:
            raise ValueError("study step bound does not cover all worker stages")
        if set(task_data) != {t["task_id"] for t in manifest["tasks"]}:
            raise ValueError("exact public task data mapping required")
        mapped = {}
        for task in manifest["tasks"]:
            entry = task_data[task["task_id"]]
            if set(entry) != {"train_id", "train_path", "dev_id", "dev_path"}:
                raise ValueError("only Train/Dev paths are accepted")
            by_id = {x["artifact_id"]: x for x in task["data_catalog"]}
            mapped[task["task_id"]] = copy.deepcopy(entry)
            for split in ("train", "dev"):
                declared = by_id[entry[split + "_id"]]
                path = Path(entry[split + "_path"]).absolute()
                data = read_regular(path)
                if declared["split"] != split or hashlib.sha256(data).hexdigest() != declared["sha256"]:
                    raise ValueError("input bytes do not match the original public task catalog")
                mapped[task["task_id"]][split + "_path"] = str(path)
        config = {"schema": "market_study_runner_v1", "study_path": str(study.root),
            "study_manifest_sha256": digest(manifest), "budget_path": str(budget.root),
            "experiment_id": manifest["experiment_id"], "runtime": copy.deepcopy(runtime),
            "coder_limits": copy.deepcopy(coder_limits), "coder_identity": copy.deepcopy(coder_identity),
            "task_data": mapped, "live": live, "worst_case_step_seconds": maximum,
            "source_hashes": {name: file_hash(Path(__file__).parent / name) for name in SOURCES},
            "scientific_admission": False, "end_to_end_wall_enforcement_verified": True,
            "end_to_end_wall_enforcement_profile": STEP_DEADLINE_PROFILE,
            "local_overhead_seconds": LOCAL_OVERHEAD_SECONDS}
        root = Path(root).absolute()
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        (root / "step-deadlines").mkdir(mode=0o700)
        fresh_json(root / "config.json", config)
        fresh_json(root / "config-commitment.json", {"sha256": digest(config)})
        return cls(root)

    def _load(self):
        config = json.loads(read_regular(self.root / "config.json"))
        commitment = json.loads(read_regular(self.root / "config-commitment.json"))
        if commitment != {"sha256": digest(config)} or config["source_hashes"] != {
                name: file_hash(Path(__file__).parent / name) for name in SOURCES}:
            raise ValueError("runner configuration/source changed")
        study, budget = StudyState(config["study_path"]), PaidBudget(config["budget_path"])
        with study.journal.locked():
            manifest, state = study._load()
        if (digest(manifest) != config["study_manifest_sha256"]
                or budget.snapshot()["experiment_id"] != config["experiment_id"]):
            raise ValueError("study/budget identity changed")
        return config, study, budget, manifest, state

    def install_admission(self, reviewed_receipt):
        """Bind one trusted review before any live provider or study claim."""
        from scientific_admission import install_admission
        config, study, budget, _, state = self._load()
        if not config["live"] or state["active"] is not None or any(state["claimed"]):
            raise ValueError("admission must precede every live study claim")
        if budget.snapshot()["experiment_id"] != config["experiment_id"]:
            raise ValueError("admission budget identity changed")
        return install_admission(self.root, reviewed_receipt)

    def next_action(self):
        """Runner-only scheduler. Never pass this all-arm view to a model."""
        config, study, _, manifest, state = self._load()
        if state["active"] is not None:
            return {"action": "reconcile_pending", "trial_id": state["active"]["trial_id"]}
        if study._causal_review_ids(state):
            return {"action": "causal_review_required", "trial_ids": study._causal_review_ids(state)}
        if state["transfer_frozen"] is not None:
            return {"action": "research_closed", "hidden_scoring_authorized": False}
        counts = {a: len(v) for a, v in state["submissions"].items()}
        learning_count = sum(t["phase"] == "learning" for t in manifest["tasks"])
        if min(counts.values()) == len(manifest["tasks"]):
            return {"action": "freeze_transfer"}
        if min(counts.values()) == learning_count and state["learning_frozen"] is None:
            return {"action": "freeze_learning"}
        if time.time() + config["worst_case_step_seconds"] > datetime.fromisoformat(manifest["deadline_utc"]).timestamp():
            return {"action": "window_closed", "deadline_utc": manifest["deadline_utc"]}
        # Task-major, then round-robin step-major; no sorting by score or cost.
        index = min(counts.values())
        candidates = []
        for arm in sorted(manifest["arms"]):
            if counts[arm] != index:
                continue
            current = [r for r in state["records"][arm] if r["task_index"] == index]
            attempts = study._attempt_counts(current, state["eligible"])
            complete = study._research_complete(manifest, attempts)
            candidates.append((complete, attempts["scoreable_candidates"], len(current), arm))
        complete, scoreable_candidates, step, arm = min(candidates)
        kind = "selection" if complete else "experiment"
        if (scoreable_candidates > manifest["max_steps_per_task"]
                or step > manifest["max_research_calls_per_task"]):
            raise ValueError("research allowances exceeded without task advancement")
        return {"action": kind, "arm": arm, "task_index": index,
            "trial_id": f"task-{index:03d}-{arm}-{'select' if kind == 'selection' else f'step-{step:02d}'}"}

    def _paths(self, trial_id):
        base = self.root / "jobs" / trial_id
        return {"research_directory": base / (trial_id + "-research"),
            "coding_directory": base / (trial_id + "-coder"),
            "development_directory": base / (trial_id + "-sandbox")}

    def _window_stop(self, manifest, stage, required_seconds, *, active_trial_id=None):
        """Check unchanged phase allowances again after potentially slow setup.

        This is dispatch admission, NOT a whole-step operating-system watchdog.
        Never shorten scientific limits to squeeze a late phase into the window.
        A partially completed attempt stays permanently claimed and is not retried.
        """
        checked = time.time()
        deadline = datetime.fromisoformat(manifest["deadline_utc"]).timestamp()
        if checked + required_seconds <= deadline:
            return None
        result = {"action": "window_closed", "stage": stage,
            "deadline_utc": manifest["deadline_utc"], "checked_at_unix": checked,
            "required_seconds": required_seconds, "active_trial_id": active_trial_id,
            "limits_shortened": False, "automatic_retry": False}
        if active_trial_id is not None:
            path = self.root / "jobs" / active_trial_id
            path.mkdir(parents=True, mode=0o700, exist_ok=True)
            fresh_json(path / ("window-closed-" + stage + ".json"), result)
        return result

    def _arguments(self, config, budget, prepared, paths):
        task = json.loads(prepared["messages"][1]["content"])["task"]
        entry = config["task_data"][task["task_id"]]
        args = {k: paths[k] for k in ("research_directory", "coding_directory")}
        args.update(budget=budget, frozen_runtime=config["runtime"], frozen_coder_limits=config["coder_limits"],
            expected_live=config["live"], expected_coder_identity=config["coder_identity"])
        catalog = {x["artifact_id"]: x for x in task["data_catalog"]}
        for split in ("train", "dev"):
            args[split + "_id"] = entry[split + "_id"]
            data = read_regular(entry[split + "_path"])
            if hashlib.sha256(data).hexdigest() != catalog[entry[split + "_id"]]["sha256"]:
                raise ValueError("public data changed before dispatch")
            args[split + "_bytes"] = data
        return args

    def _build_existing(self, config, study, budget, active):
        if active.get("kind") == "selection":
            return build_selection_completion(study, self.root / "selection-jobs" / active["trial_id"],
                                               budget, expected_live=config["live"])
        paths = self._paths(active["trial_id"])
        prepared = active["prepared"]
        research_failure = paths["research_directory"] / "failure.json"
        research_response = paths["research_directory"] / "response.json"
        if (research_failure.exists() and not research_response.exists()
                and (paths["research_directory"] / "sample-process/receipt.json").exists()):
            return build_uncertain_timeout(study, paths["research_directory"], budget,
                                           expected_live=config["live"])
        research = read_research_terminal(paths["research_directory"], prepared, budget, expected_live=config["live"])
        common = {"research_directory": paths["research_directory"], "budget": budget, "expected_live": config["live"]}
        if not research["valid"]:
            return build_worker_failure(study, **common)
        args = self._arguments(config, budget, prepared, paths)
        _, coding_request = code_request_from_job(paths["research_directory"], prepared, budget,
            config["runtime"], config["coder_limits"], expected_live=config["live"])
        coding = read_code_terminal(paths["coding_directory"], research, coding_request,
            expected_live=config["live"], expected_identity=config["coder_identity"])
        if not coding["valid"]:
            return build_worker_failure(study, **common, coding_directory=paths["coding_directory"],
                frozen_runtime=config["runtime"], frozen_coder_limits=config["coder_limits"],
                expected_coder_identity=config["coder_identity"])
        producer = build_sandbox_failure if (paths["development_directory"] / "failure.json").exists() else build_completion
        return producer(study, paths["development_directory"], **args)

    def reconcile_pending(self):
        """Read/commit only: never create a provider or resume missing execution."""
        config, study, budget, _, state = self._load()
        active = state["active"]
        if active is None:
            raise ValueError("no pending study action")
        built = self._build_existing(config, study, budget, active)
        selection = active.get("kind") == "selection"
        path = study.root / ("selections" if selection else "steps") / active["trial_id"] / "completion.json"
        if path.exists():
            if json.loads(read_regular(path)) != built["completion"]:
                raise ValueError("interrupted completion differs from verified receipts")
            if "budget_accounting" in built:
                settle_uncertain_timeout_budget(
                    self._paths(active["trial_id"])["research_directory"], budget, built)
            for reads in built["read_sets"]:
                reads.revalidate()
            (study.recover_selection if selection else study.recover_completion)(active["trial_id"])
        else:
            if "budget_accounting" in built:
                commit_uncertain_timeout(study,
                    self._paths(active["trial_id"])["research_directory"], budget, built)
            else:
                (commit_selection if selection else commit_completion)(study, built)
        return {"completed_trial_id": active["trial_id"], "scored_market_experiment": False,
                "scientific_admission": False, "failure": built["completion"].get("payload", {}).get("failure")}

    def review_closed_failure(self, trial_id, *, review_id, rationale, evidence_paths):
        """Trusted reviewer only. No automatic classification or source repair."""
        config, study, budget, _, state = self._load()
        if state["active"] is not None or trial_id not in study._causal_review_ids(state):
            raise ValueError("only a closed unresolved failure can be reviewed")
        prepared = json.loads(read_regular(study.root / "steps" / trial_id / "request.json"))
        paths = self._paths(trial_id)
        args = self._arguments(config, budget, prepared, paths)
        built = build_failure_review(study, paths["development_directory"], trial_id=trial_id,
            review_id=review_id, rationale=rationale, evidence_paths=evidence_paths, **args)
        commit_failure_review(study, built)
        return {"reviewed_trial_id": trial_id, "automatic_retry": False, "automatic_causal_diagnosis": False}

    def tick(self, research_transport=None, coder_transport=None, *, env_file=None, fixture_execute=None):
        """Advance one predeclared action. Never retry an exception or pending job."""
        action = self.next_action()
        config, study, budget, manifest, state = self._load()
        if action["action"] == "reconcile_pending":
            return action  # Separate explicit read-only reconciliation, not another paid call.
        if action["action"] in {"research_closed", "causal_review_required", "window_closed"}:
            return action
        if action["action"] in {"freeze_learning", "freeze_transfer"}:
            getattr(study, action["action"])()
            return action
        if config["live"]:
            development_harbor.require_admission(self.root)  # No callback or boolean bypass.
            if fixture_execute is not None:
                raise ValueError("fixture executor cannot run a real study")
        for transport in ((research_transport,) if action["action"] == "selection" else (research_transport, coder_transport)):
            if transport is None or getattr(transport, "live", True) is not config["live"]:
                raise ValueError("exact declared transport mode required")
        task = manifest["tasks"][action["task_index"]]
        # Availability precheck, not a charge or substitute for each worker's
        # atomic ledger reservation. One global study claim prevents overlap.
        limits = task["resource_limits"]
        upper = cost(limits["max_input_tokens"], limits["max_output_tokens"])
        if action["action"] == "experiment":
            upper += money("0.10")
        available = budget.snapshot()["buckets"]["final" if task["phase"] == "transfer" else "learning"]["available_usd"]
        if upper > money(available):
            return {"action": "budget_blocked", "upper_usd": str(upper), "available_usd": available}
        trial_id = action["trial_id"]
        if action["action"] == "selection":
            stopped = self._window_stop(manifest, "selection", limits["max_wall_seconds"])
            if stopped:
                return stopped
            study.claim_selection(action["arm"], trial_id)
            stopped = self._window_stop(manifest, "selection", limits["max_wall_seconds"], active_trial_id=trial_id)
            if stopped:
                return stopped
            step_deadline = StepDeadline.start(self.root / "step-deadlines" / (trial_id + ".json"),
                study_deadline_utc=manifest["deadline_utc"], cap_seconds=config["worst_case_step_seconds"])
            dispatch_selection(study, research_transport, budget, self.root / "selection-jobs" / trial_id,
                               deadline_monotonic=step_deadline.deadline_monotonic)
            return self.reconcile_pending()
        paths = self._paths(trial_id)
        # Inspect catalog bytes before making a permanent claim or model call.
        prospective = study.next_request(action["arm"])
        self._arguments(config, budget, prospective, paths)
        stopped = self._window_stop(manifest, "research", config["worst_case_step_seconds"])
        if stopped:
            return stopped
        prepared = study.claim(action["arm"], trial_id)
        stopped = self._window_stop(manifest, "research", config["worst_case_step_seconds"], active_trial_id=trial_id)
        if stopped:
            return stopped
        step_deadline = StepDeadline.start(self.root / "step-deadlines" / (trial_id + ".json"),
            study_deadline_utc=manifest["deadline_utc"], cap_seconds=config["worst_case_step_seconds"])

        def admission(audit):
            development_harbor.require_admission(self.root)
            if study.snapshot()["active"]["trial_id"] != trial_id:
                raise ValueError("active study claim changed")
            return True

        step_deadline.require(limits["max_wall_seconds"], "research")
        result = dispatch_once(prepared, research_transport, budget, paths["research_directory"],
                               admission_check=admission,
                               deadline_monotonic=step_deadline.deadline_monotonic)
        if not result["valid"]:
            return self.reconcile_pending()
        _, coding = code_request_from_job(paths["research_directory"], prepared, budget,
            config["runtime"], config["coder_limits"], expected_live=config["live"])
        stopped = self._window_stop(manifest, "coding",
            config["coder_limits"]["wall_seconds"] + CODER_REAP_SECONDS
            + HARBOR_WALL_SECONDS + HARBOR_REAP_SECONDS, active_trial_id=trial_id)
        if stopped:
            return stopped
        step_deadline.require(config["coder_limits"]["wall_seconds"] + CODER_REAP_SECONDS,
                              "coding")
        coded = dispatch_code_once(coding, coder_transport, paths["coding_directory"],
                                   admission_check=admission,
                                   deadline_monotonic=step_deadline.deadline_monotonic)
        if not coded["valid"]:
            return self.reconcile_pending()
        args = self._arguments(config, budget, prepared, paths)
        bundle = prepare_development_trial(prepared_research=prepared, **args)
        development_harbor.prepare_job(bundle, paths["development_directory"])
        stopped = self._window_stop(manifest, "sandbox", HARBOR_WALL_SECONDS + HARBOR_REAP_SECONDS,
            active_trial_id=trial_id)
        if stopped:
            return stopped
        if config["live"]:
            if env_file is None:
                raise ValueError("runner-owned provider environment required")
            step_deadline.require(HARBOR_WALL_SECONDS + HARBOR_REAP_SECONDS, "sandbox")
            run_bounded_development(paths["development_directory"], budget.root, env_file,
                                    deadline_utc=step_deadline.deadline_utc)
        else:
            if fixture_execute is None:
                raise ValueError("offline executor required; never execute candidate code on this host")
            fixture_execute(bundle, paths["development_directory"], budget)
        return self.reconcile_pending()
