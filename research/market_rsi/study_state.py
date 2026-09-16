"""Durable study ordering and owned memory; no providers or scientific admission.

The trusted completion producer must verify worker/source/scorer receipts BEFORE
calling complete(). This store validates ownership, sequencing and commitments,
not the truth of arbitrary payload contents. It does not choose a predictor,
certify a data source, execute code or expose hidden data. Do not mistake a
caller-supplied completion or selection for a verified autonomous result.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from market_rsi import Journal, digest, file_hash, fresh_json, identifier
from research_context import ARMS
from researcher_worker import (PAYLOAD_KEYS, assess_proposal, hash_string, prepare_request,
                               scored_experiment_record)
from worker_receipts import read_regular


class StudyState:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.journal = Journal(self.root)

    @classmethod
    def create(cls, root, *, common_manifest, tasks, baseline_source_hashes,
               max_steps_per_task, deadline_utc, worst_case_step_seconds,
               max_diagnostics_per_task=0, max_research_calls_per_task=None):
        if max_research_calls_per_task is None:
            max_research_calls_per_task = max_steps_per_task + max_diagnostics_per_task
        if (type(max_steps_per_task) is not int or not 1 <= max_steps_per_task <= 3
                or type(max_diagnostics_per_task) is not int
                or not 0 <= max_diagnostics_per_task <= 2
                or type(max_research_calls_per_task) is not int
                or not max_steps_per_task <= max_research_calls_per_task <= 6
                or type(worst_case_step_seconds) is not int or not 1 <= worst_case_step_seconds <= 3600
                or not isinstance(tasks, list) or len(tasks) < 2):
            raise ValueError("explicit bounded study schedule required")
        deadline = datetime.fromisoformat(deadline_utc)
        if deadline.tzinfo is None or deadline.utcoffset().total_seconds() != 0:
            raise ValueError("explicit UTC report deadline required")
        tasks = copy.deepcopy(tasks)
        experiment, seen, transfer_seen = tasks[0]["experiment_id"], set(), False
        if not isinstance(baseline_source_hashes, dict):
            raise ValueError("one common baseline source commitment per task required")
        for index, task in enumerate(tasks):
            if task["task_index"] != index or task["experiment_id"] != experiment or task["task_id"] in seen:
                raise ValueError("task identity/order differs across study")
            seen.add(task["task_id"])
            if task["phase"] == "transfer":
                transfer_seen = True
            elif transfer_seen:
                raise ValueError("learning cannot follow transfer")
            if task["resource_limits"] != tasks[0]["resource_limits"]:
                raise ValueError("research request allowances must be common")
            # Same actual initialization and public task for every arm. This is
            # schema validation, not chronological market/source certification.
            for arm in sorted(ARMS):
                prepare_request(common_manifest, arm=arm, task=task, step_index=0, records=[])
        if (tasks[0]["phase"] != "learning" or not transfer_seen
                or set(baseline_source_hashes) != seen):
            raise ValueError("learning then transfer with common baselines required")
        for sha in baseline_source_hashes.values():
            hash_string(sha)
        root = Path(root).absolute()
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        (root / "steps").mkdir(mode=0o700)
        common_manifest = Path(common_manifest).absolute()
        manifest = {"schema": "market_study_state_v1", "experiment_id": experiment,
            "common_manifest": str(common_manifest), "common_manifest_sha256": file_hash(common_manifest),
            "tasks": tasks, "baseline_source_hashes": copy.deepcopy(baseline_source_hashes),
            "arms": sorted(ARMS), "max_steps_per_task": max_steps_per_task,
            "max_diagnostics_per_task": max_diagnostics_per_task,
            "max_research_calls_per_task": max_research_calls_per_task,
            "deadline_utc": deadline_utc, "worst_case_step_seconds": worst_case_step_seconds,
            "state_code_sha256": file_hash(__file__), "scientific_admission": False,
            "selection_protocol_sha256": file_hash(Path(__file__).with_name("selection_protocol.py")),
            "failure_review_source_sha256": file_hash(Path(__file__).with_name("failure_review.py")),
            "final_stage_source_sha256": file_hash(Path(__file__).with_name("final_stage.py")),
            "selection_policy": {"after_scoreable_candidates": max_steps_per_task,
                                 "max_diagnostic_attempts": max_diagnostics_per_task,
                                 "max_research_calls": max_research_calls_per_task,
                                 "selection_trigger": "target_scoreable_candidates_or_call_cap",
                                 "calls_per_task": 1, "invalid_output": "common_baseline",
                                 "guide_update": False},
            "completion_authority": "trusted external producer must independently verify evidence"}
        obj = cls(root)
        with obj.journal.locked():
            fresh_json(root / "manifest.json", manifest)
            obj.journal.append("created", {"manifest_sha256": digest(manifest)})
        return obj

    def _json(self, path):
        return json.loads(read_regular(path))

    def _load(self):
        manifest = self._json(self.root / "manifest.json")
        events = self.journal.read()
        if (not events or events[0]["event"] != "created"
                or events[0]["payload"] != {"manifest_sha256": digest(manifest)}
                or manifest["state_code_sha256"] != file_hash(__file__)
                or manifest["selection_protocol_sha256"] != file_hash(Path(__file__).with_name("selection_protocol.py"))
                or manifest["failure_review_source_sha256"] != file_hash(Path(__file__).with_name("failure_review.py"))
                or manifest["final_stage_source_sha256"] != file_hash(Path(__file__).with_name("final_stage.py"))
                or file_hash(manifest["common_manifest"]) != manifest["common_manifest_sha256"]):
            raise ValueError("study manifest/source/common initialization changed")
        state = {"records": {arm: [] for arm in ARMS}, "guides": {arm: None for arm in ARMS},
                 "submissions": {arm: [] for arm in ARMS}, "active": None, "claimed": set(),
                 "eligible": {}, "learning_frozen": None, "transfer_frozen": None,
                 "failure_reviews": {}, "review_ids": set()}
        for event in events[1:]:
            kind, payload = event["event"], event["payload"]
            if kind == "step_claimed":
                trial_id = identifier(payload["trial_id"])
                prepared = self._json(self.root / "steps" / trial_id / "request.json")
                if (state["active"] is not None or trial_id in state["claimed"]
                        or digest(prepared) != payload["request_sha256"]
                        or prepared != self._request(manifest, state, payload["arm"])):
                    raise ValueError("duplicate, unordered or changed step claim")
                state["claimed"].add(trial_id)
                state["active"] = {"trial_id": trial_id, "arm": payload["arm"], "prepared": prepared}
            elif kind == "step_completed":
                if state["active"] is None or payload["trial_id"] != state["active"]["trial_id"]:
                    raise ValueError("completion without exact active step")
                completed = self._json(self.root / "steps" / payload["trial_id"] / "completion.json")
                if digest(completed) != payload["completion_sha256"]:
                    raise ValueError("completion evidence changed")
                self._apply_completion(manifest, state, completed)
            elif kind == "task_submitted":
                self._apply_submission(manifest, state, payload)
            elif kind == "failure_reviewed":
                review = self._json(self.root / "failure-reviews" / payload["review_id"] / "review.json")
                if payload != {"review_id": review["review_id"], "sha256": digest(review)}:
                    raise ValueError("recorded failure review changed")
                self._apply_failure_review(manifest, state, review)
            elif kind == "selection_claimed":
                trial_id = identifier(payload["trial_id"])
                prepared = self._json(self.root / "selections" / trial_id / "request.json")
                if (state["active"] is not None or trial_id in state["claimed"]
                        or digest(prepared) != payload["request_sha256"]
                        or prepared != self._selection_request(manifest, state, payload["arm"])):
                    raise ValueError("duplicate, unordered or changed selection claim")
                state["claimed"].add(trial_id)
                state["active"] = {"kind": "selection", "trial_id": trial_id,
                                   "arm": payload["arm"], "prepared": prepared}
            elif kind == "selection_completed":
                completed = self._json(self.root / "selections" / payload["trial_id"] / "completion.json")
                if digest(completed) != payload["completion_sha256"]:
                    raise ValueError("selection completion evidence changed")
                self._apply_selection(manifest, state, completed)
            elif kind == "learning_frozen":
                self._require_learning_complete(manifest, state)
                frozen = self._json(self.root / "learning-freeze.json")
                if payload != {"sha256": digest(frozen)} or frozen != self._learning_snapshot(manifest, state):
                    raise ValueError("last learning state changed")
                state["learning_frozen"] = frozen
            elif kind == "transfer_frozen":
                self._require_transfer_complete(manifest, state)
                frozen = self._json(self.root / "transfer-freeze.json")
                if payload != {"sha256": digest(frozen)} or frozen != self._transfer_snapshot(manifest, state):
                    raise ValueError("transfer submissions changed")
                state["transfer_frozen"] = frozen
            else:
                raise ValueError("unknown study transition; hidden results cannot enter memory")
        return manifest, state

    @staticmethod
    def _attempt_counts(records, eligible=None):
        eligible = eligible or {}
        diagnostics = sum(isinstance(r["payload"].get("proposal"), dict)
            and r["payload"]["proposal"].get("action") in {"inspect", "reject_measurement"}
            for r in records)
        scoreable = sum(eligible.get(r["trial_id"]) is True for r in records)
        return {"diagnostics": diagnostics, "scoreable_candidates": scoreable,
                "failed_or_unscored": len(records) - diagnostics - scoreable,
                "research_calls": len(records)}

    @staticmethod
    def _research_complete(manifest, counts):
        return (counts["scoreable_candidates"] >= manifest["max_steps_per_task"]
                or counts["research_calls"] >= manifest["max_research_calls_per_task"])

    def _request(self, manifest, state, arm):
        self._require_no_causal_review(state)
        if arm not in ARMS or state["transfer_frozen"] is not None:
            raise ValueError("research arm unavailable or all submissions sealed")
        index = len(state["submissions"][arm])
        if index >= len(manifest["tasks"]):
            raise ValueError("this arm has finished its task schedule")
        task = manifest["tasks"][index]
        if task["phase"] == "transfer" and state["learning_frozen"] is None:
            raise ValueError("all last learning states must freeze before any transfer")
        owned = state["records"][arm]
        current = [r for r in owned if r["task_index"] == index]
        counts = self._attempt_counts(current, state["eligible"])
        max_candidates = manifest["max_steps_per_task"]
        max_diagnostics = manifest.get("max_diagnostics_per_task", 0)
        max_calls = manifest.get("max_research_calls_per_task", max_candidates + max_diagnostics)
        if self._research_complete(manifest, counts):
            raise ValueError("task research allowance complete; selection is next")
        if counts["diagnostics"] > max_diagnostics:
            raise ValueError("task diagnostic allowance exceeded")
        history = [r for r in owned if r["task_index"] == index
                   or (arm != "reset" and r["phase"] == "learning")]
        return prepare_request(manifest["common_manifest"], arm=arm, task=task, step_index=len(current),
                               records=history, guide=state["guides"][arm], slot_policy={
                                   "scoreable_candidates_remaining": max_candidates - counts["scoreable_candidates"],
                                   "diagnostic_attempts_remaining": max_diagnostics - counts["diagnostics"],
                                   "research_calls_remaining": max_calls - counts["research_calls"]})

    def next_request(self, arm):
        """Read-only prospective request. A dispatch still needs an exact claim."""
        with self.journal.locked():
            manifest, state = self._load()
            if state["active"] is not None:
                raise ValueError("unfinished step must be inspected, never duplicated")
            return self._request(manifest, state, arm)

    def claim(self, arm, trial_id):
        identifier(trial_id)
        with self.journal.locked():
            manifest, state = self._load()
            if state["active"] is not None or trial_id in state["claimed"]:
                raise ValueError("active or reused step; no duplicate dispatch")
            deadline = datetime.fromisoformat(manifest["deadline_utc"]).timestamp()
            if time.time() + manifest["worst_case_step_seconds"] > deadline:
                raise TimeoutError("new step cannot finish within the authorized deadline")
            prepared = self._request(manifest, state, arm)
            directory = self.root / "steps" / trial_id
            directory.mkdir(mode=0o700, exist_ok=False)
            fresh_json(directory / "request.json", prepared)
            self.journal.append("step_claimed", {"trial_id": trial_id, "arm": arm, "request_sha256": digest(prepared)})
            return prepared

    def _apply_completion(self, manifest, state, completed):
        active = state["active"]
        if (not isinstance(completed, dict) or set(completed) != {"trial_id", "research_packet_sha256",
                "raw_research_response", "payload", "eligible_submission", "evidence_commitments"}
                or active is None or active.get("kind") == "selection" or completed["trial_id"] != active["trial_id"]
                or completed["research_packet_sha256"] != active["prepared"]["packet_sha256"]
                or type(completed["eligible_submission"]) is not bool):
            raise ValueError("completion is not bound to the exact active research step")
        evidence = completed["evidence_commitments"]
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError("external producer evidence commitments required")
        for name, sha in evidence.items():
            identifier(name)
            hash_string(sha)
        payload = completed["payload"]
        if (not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS
                or not isinstance(payload["train_dev_results"], dict)
                or not set(payload["train_dev_results"]) <= {"train", "dev"}):
            raise ValueError("only permitted Train/Dev completion fields may enter memory")
        audit = active["prepared"]["audit"]
        assessment = assess_proposal(completed["raw_research_response"], audit)
        if assessment["valid"]:
            proposal = assessment["proposal"]
            if payload["proposal"] != proposal:
                raise ValueError("record does not preserve the researcher's proposal")
        else:
            proposal = None
            if payload["proposal"] is not None or payload["failure"] is None or completed["eligible_submission"]:
                raise ValueError("invalid response must remain a failed, ineligible step")
        if completed["eligible_submission"] and (proposal["action"] != "experiment" or payload["failure"] is not None
                or not isinstance(payload["candidate_code"], str) or not payload["candidate_code"].strip()):
            raise ValueError("only an independently admitted experiment may be submitted")
        record = {"schema": "market_research_record_v1", "experiment_id": manifest["experiment_id"],
            "arm": active["arm"], "task_id": audit["task_id"], "task_index": audit["task_index"],
            "step_index": audit["step_index"], "phase": audit["phase"], "trial_id": active["trial_id"],
            "visibility": "train_dev", "origin": "runner_recorded_train_dev", "payload": copy.deepcopy(payload)}
        state["records"][active["arm"]].append(record)
        state["eligible"][active["trial_id"]] = completed["eligible_submission"]
        if proposal is not None and proposal["guide_update"] is not None:
            update = proposal["guide_update"]
            scored = {r["trial_id"] for r in state["records"][active["arm"]]
                      if scored_experiment_record(r)}
            if not set(update["evidence_trial_ids"]) <= scored:
                raise ValueError("guide revision cites an unscored or diagnostic record")
            state["guides"][active["arm"]] = {"schema": "market_research_guide_v1",
                "experiment_id": manifest["experiment_id"], "arm": active["arm"],
                "revision_id": "guide-" + digest(completed)[0:24], "origin": "agent_generated",
                "text": update["text"], "evidence_trial_ids": update["evidence_trial_ids"]}
        state["active"] = None

    def complete(self, completed):
        """Only trusted, independently verified completion producers may call.

        Evidence hashes commit to that producer's inputs; this class does NOT
        establish their authenticity. Production admission remains closed.
        """
        completed = copy.deepcopy(completed)
        completion_sha256 = digest(completed)  # Validate finite JSON before creating a permanent file.
        with self.journal.locked():
            manifest, state = self._load()
            self._apply_completion(manifest, state, completed)
            trial_id = completed["trial_id"]
            fresh_json(self.root / "steps" / trial_id / "completion.json", completed)
            self.journal.append("step_completed", {"trial_id": trial_id, "completion_sha256": completion_sha256})

    def recover_completion(self, trial_id):
        """Commit an already durable terminal file after a crash before journal append.

        No new response or payload is accepted. The trusted producer must still
        verify upstream receipts; this only repairs the local transaction edge.
        """
        identifier(trial_id)
        with self.journal.locked():
            manifest, state = self._load()
            if state["active"] is None or state["active"]["trial_id"] != trial_id:
                raise ValueError("no matching interrupted completion transaction")
            completed = self._json(self.root / "steps" / trial_id / "completion.json")
            self._apply_completion(manifest, state, completed)
            self.journal.append("step_completed", {"trial_id": trial_id, "completion_sha256": digest(completed)})

    def _apply_submission(self, manifest, state, submitted):
        self._require_no_causal_review(state)
        if (state["active"] is not None or state["transfer_frozen"] is not None
                or not isinstance(submitted, dict) or set(submitted) != {"arm", "task_id", "trial_id", "source_sha256", "selection_evidence_sha256"}
                or submitted["arm"] not in ARMS):
            raise ValueError("invalid or premature submission")
        arm = submitted["arm"]
        index = len(state["submissions"][arm])
        if index >= len(manifest["tasks"]) or submitted["task_id"] != manifest["tasks"][index]["task_id"]:
            raise ValueError("submission is outside this arm's next task")
        task = manifest["tasks"][index]
        if task["phase"] == "transfer" and state["learning_frozen"] is None:
            raise ValueError("learning not frozen")
        own = [r for r in state["records"][arm] if r["task_index"] == index]
        if not own:
            raise ValueError("a task cannot be silently skipped")
        hash_string(submitted["source_sha256"])
        hash_string(submitted["selection_evidence_sha256"])
        if submitted["trial_id"] is None:
            if submitted["source_sha256"] != manifest["baseline_source_hashes"][task["task_id"]]:
                raise ValueError("fallback must be this task's frozen common baseline")
        else:
            matches = [r for r in own if r["trial_id"] == submitted["trial_id"]]
            import hashlib
            if (len(matches) != 1 or not state["eligible"][submitted["trial_id"]]
                    or hashlib.sha256(matches[0]["payload"]["candidate_code"].encode()).hexdigest() != submitted["source_sha256"]):
                raise ValueError("submission must be an eligible candidate from this arm/task")
        state["submissions"][arm].append(copy.deepcopy(submitted))

    def submit_task(self, submitted):
        """Commit a separately recorded selection; this method makes no choice."""
        with self.journal.locked():
            manifest, state = self._load()
            if not manifest["experiment_id"].startswith("fixture-"):
                raise ValueError("real submissions must use a claimed researcher selection receipt")
            self._apply_submission(manifest, state, submitted)
            self.journal.append("task_submitted", copy.deepcopy(submitted))

    def _selection_request(self, manifest, state, arm):
        self._require_no_causal_review(state)
        from selection_protocol import prepare_selection
        if arm not in ARMS or state["transfer_frozen"] is not None:
            raise ValueError("selection arm unavailable")
        index = len(state["submissions"][arm])
        if index >= len(manifest["tasks"]):
            raise ValueError("task schedule already complete")
        task = manifest["tasks"][index]
        if task["phase"] == "transfer" and state["learning_frozen"] is None:
            raise ValueError("all learning must freeze before transfer selection")
        owned = state["records"][arm]
        current = [r for r in owned if r["task_index"] == index]
        counts = self._attempt_counts(current, state["eligible"])
        if (not self._research_complete(manifest, counts)
                or counts["diagnostics"] > manifest["selection_policy"]["max_diagnostic_attempts"]):
            raise ValueError("selection requires scoreable target or the predeclared call cap")
        history = [r for r in owned if r["task_index"] == index
                   or (arm != "reset" and r["phase"] == "learning")]
        candidates = [{"candidate_id": "baseline", "trial_id": None,
                       "source_sha256": manifest["baseline_source_hashes"][task["task_id"]]}]
        import hashlib
        for record in current:
            if state["eligible"][record["trial_id"]]:
                candidates.append({"candidate_id": "candidate-" + record["trial_id"], "trial_id": record["trial_id"],
                    "source_sha256": hashlib.sha256(record["payload"]["candidate_code"].encode()).hexdigest()})
        return prepare_selection(manifest["common_manifest"], arm=arm, task=task,
                                 records=history, guide=state["guides"][arm], candidates=candidates)

    def claim_selection(self, arm, trial_id):
        """One global pending choice; a token-metered worker still needs admission."""
        identifier(trial_id)
        with self.journal.locked():
            manifest, state = self._load()
            if state["active"] is not None or trial_id in state["claimed"]:
                raise ValueError("unfinished/reused work blocks selection")
            if time.time() + manifest["worst_case_step_seconds"] > datetime.fromisoformat(manifest["deadline_utc"]).timestamp():
                raise TimeoutError("selection cannot fit within authorized deadline")
            prepared = self._selection_request(manifest, state, arm)
            directory = self.root / "selections" / trial_id
            directory.mkdir(parents=True, mode=0o700, exist_ok=False)
            fresh_json(directory / "request.json", prepared)
            self.journal.append("selection_claimed", {"trial_id": trial_id, "arm": arm, "request_sha256": digest(prepared)})
            return prepared

    def _apply_selection(self, manifest, state, completed):
        from selection_protocol import assess_selection
        active = state["active"]
        if (active is None or active.get("kind") != "selection" or not isinstance(completed, dict)
                or set(completed) != {"trial_id", "packet_sha256", "raw_response", "terminal_worker_valid",
                                      "usage", "evidence_commitments"}
                or completed["trial_id"] != active["trial_id"]
                or completed["packet_sha256"] != active["prepared"]["packet_sha256"]
                or type(completed["terminal_worker_valid"]) is not bool):
            raise ValueError("selection result does not match the exact active claim")
        evidence = completed["evidence_commitments"]
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError("selection needs independently verified terminal receipts")
        for name, sha in evidence.items():
            identifier(name)
            hash_string(sha)
        audit = active["prepared"]["audit"]
        result = assess_selection(completed["raw_response"], audit)
        valid = result["valid"] and completed["terminal_worker_valid"]
        choice = result["selection"]["selected_candidate_id"] if valid else "baseline"
        selected = next(x for x in audit["selection_candidates"] if x["candidate_id"] == choice)
        submitted = {"arm": active["arm"], "task_id": audit["task_id"], "trial_id": selected["trial_id"],
            "source_sha256": selected["source_sha256"], "selection_evidence_sha256": digest(completed)}
        state["active"] = None
        self._apply_submission(manifest, state, submitted)
        state["records"][active["arm"]].append({"schema": "market_research_record_v1",
            "experiment_id": manifest["experiment_id"], "arm": active["arm"],
            "task_id": audit["task_id"], "task_index": audit["task_index"], "step_index": audit["step_index"],
            "phase": audit["phase"], "trial_id": active["trial_id"], "visibility": "train_dev",
            "origin": "runner_recorded_train_dev", "payload": {
                "proposal": {"kind": "task_selection", "raw_response": completed["raw_response"],
                             "decision": result.get("selection"), "accepted_candidate_id": choice,
                             "fallback": not valid},
                "candidate_code": None, "train_dev_results": {}, "usage": copy.deepcopy(completed["usage"]),
                "failure": None if valid else {"stage": "selection", "kind": "invalid_or_late_selection",
                                               "automatic_retry": False}}})
        state["eligible"][active["trial_id"]] = False

    def complete_selection(self, completed):
        """Trusted terminal receipt producer only; no model/host-provided score."""
        completed = copy.deepcopy(completed)
        sha = digest(completed)
        with self.journal.locked():
            manifest, state = self._load()
            self._apply_selection(manifest, state, completed)
            fresh_json(self.root / "selections" / completed["trial_id"] / "completion.json", completed)
            self.journal.append("selection_completed", {"trial_id": completed["trial_id"], "completion_sha256": sha})

    def recover_selection(self, trial_id):
        identifier(trial_id)
        with self.journal.locked():
            manifest, state = self._load()
            completed = self._json(self.root / "selections" / trial_id / "completion.json")
            self._apply_selection(manifest, state, completed)
            self.journal.append("selection_completed", {"trial_id": trial_id, "completion_sha256": digest(completed)})

    def _require_learning_complete(self, manifest, state):
        self._require_no_causal_review(state)
        count = sum(t["phase"] == "learning" for t in manifest["tasks"])
        if (state["active"] is not None or state["learning_frozen"] is not None
                or any(len(s) != count for s in state["submissions"].values())):
            raise ValueError("all arms must finish learning before one shared freeze")

    def _learning_snapshot(self, manifest, state):
        return {"manifest_sha256": digest(manifest), "guides": copy.deepcopy(state["guides"]),
                "record_hashes": {a: [digest(r) for r in state["records"][a]] for a in sorted(ARMS)},
                "submissions": copy.deepcopy(state["submissions"]), "scientific_admission": False}

    def freeze_learning(self):
        with self.journal.locked():
            manifest, state = self._load()
            self._require_learning_complete(manifest, state)
            frozen = self._learning_snapshot(manifest, state)
            fresh_json(self.root / "learning-freeze.json", frozen)
            self.journal.append("learning_frozen", {"sha256": digest(frozen)})
            return frozen

    def _require_transfer_complete(self, manifest, state):
        self._require_no_causal_review(state)
        if (state["active"] is not None or state["learning_frozen"] is None or state["transfer_frozen"] is not None
                or any(len(s) != len(manifest["tasks"]) for s in state["submissions"].values())):
            raise ValueError("all transfer submissions must exist before opening any hidden score")

    def _transfer_snapshot(self, manifest, state):
        return {"manifest_sha256": digest(manifest), "learning_freeze_sha256": digest(state["learning_frozen"]),
                "submissions": copy.deepcopy(state["submissions"]), "research_closed": True,
                "ordering_ready": True, "scientific_admission": False}

    def freeze_transfer(self):
        with self.journal.locked():
            manifest, state = self._load()
            self._require_transfer_complete(manifest, state)
            frozen = self._transfer_snapshot(manifest, state)
            fresh_json(self.root / "transfer-freeze.json", frozen)
            self.journal.append("transfer_frozen", {"sha256": digest(frozen)})
            return frozen

    def _causal_review_ids(self, state):
        return [record["trial_id"] for records in state["records"].values() for record in records
                if isinstance(record["payload"]["failure"], dict)
                and record["payload"]["failure"].get("continuation_requires_causal_review") is True
                and record["trial_id"] not in state["failure_reviews"]]

    def _apply_failure_review(self, manifest, state, review):
        from failure_review import validate_review
        validate_review(review)
        if (state["active"] is not None or state["transfer_frozen"] is not None
                or review["trial_id"] not in self._causal_review_ids(state)
                or review["review_id"] in state["review_ids"]
                or review["study_manifest_sha256"] != digest(manifest)
                or review["review_source_sha256"] != manifest["failure_review_source_sha256"]):
            raise ValueError("review must close one unresolved completed failure under unchanged source")
        completed = self._json(self.root / "steps" / review["trial_id"] / "completion.json")
        if (digest(completed) != review["completion_sha256"] or completed["eligible_submission"] is not False
                or completed["payload"]["failure"].get("stage") != "sandbox_execution"):
            raise ValueError("review cannot replace an outcome, score or eligibility")
        # The human/runner reviewer owns the causal judgment. This transition
        # commits that judgment; it does not prove it from a schema or stderr.
        # Original records/guides/budget/attempt counts are deliberately untouched.
        state["failure_reviews"][review["trial_id"]] = copy.deepcopy(review)
        state["review_ids"].add(review["review_id"])

    def complete_failure_review(self, review):
        """Trusted independently reviewed producer only; never a researcher tool."""
        review = copy.deepcopy(review)
        sha = digest(review)
        with self.journal.locked():
            manifest, state = self._load()
            self._apply_failure_review(manifest, state, review)
            path = self.root / "failure-reviews" / review["review_id"]
            path.mkdir(parents=True, mode=0o700, exist_ok=False)
            fresh_json(path / "review.json", review)
            self.journal.append("failure_reviewed", {"review_id": review["review_id"], "sha256": sha})

    def recover_failure_review(self, review_id):
        """Recover only an already durable reviewed transaction; no new judgment."""
        identifier(review_id)
        with self.journal.locked():
            manifest, state = self._load()
            review = self._json(self.root / "failure-reviews" / review_id / "review.json")
            if review["review_id"] != review_id:
                raise ValueError("different interrupted review")
            self._apply_failure_review(manifest, state, review)
            self.journal.append("failure_reviewed", {"review_id": review_id, "sha256": digest(review)})

    def _require_no_causal_review(self, state):
        if self._causal_review_ids(state):
            raise ValueError("causal review required before further research or selection")

    def snapshot(self):
        with self.journal.locked():
            manifest, state = self._load()
            # Runner-only status. Never send this all-arm view to a researcher.
            return {"experiment_id": manifest["experiment_id"], "active": copy.deepcopy(state["active"]),
                "records_by_arm": {a: len(v) for a, v in state["records"].items()},
                "submitted_by_arm": {a: len(v) for a, v in state["submissions"].items()},
                "learning_frozen": state["learning_frozen"] is not None,
                "transfer_frozen": state["transfer_frozen"] is not None,
                "causal_review_trial_ids": self._causal_review_ids(state),
                "reviewed_failure_trial_ids": sorted(state["failure_reviews"]),
                "scientific_admission": False}
