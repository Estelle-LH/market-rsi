"""LLM-research study lifecycle. No model calls, arbitrary code, or trading.

The caller is a trusted runner. Hashes/allowlists are audit controls, NOT a
sandbox. A real executor must enforce access, budgets and baseline reset and
produce the receipts that this library binds together.
"""
from __future__ import annotations

import copy
import re
import shutil
from pathlib import Path

from market_rsi import Journal, digest, file_hash, fresh_json, identifier, load_json, probability

ARMS = {
    "reset": {"carry_memory": False, "selector": "average"},
    "memory": {"carry_memory": True, "selector": "average"},
    "memory_market": {"carry_memory": True, "selector": "market"},
}


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("expected SHA-256 commitment")
    return value


def validate_manifest(manifest):
    required = {"study_id", "evidence_class", "agent", "limits", "tasks"}
    if set(manifest) != required:
        raise ValueError("unexpected or missing study fields")
    identifier(manifest["study_id"])
    # Real prospective claims require a future independently audited executor.
    if manifest["evidence_class"] not in {"fixture", "diagnostic"}:
        raise ValueError("live prospective evidence gate is not implemented")
    agent = manifest["agent"]
    if set(agent) != {"model_id", "backend", "version", "base_instructions", "tools_sha256"}:
        raise ValueError("exact common agent specification required")
    if any(not isinstance(agent[k], str) or not agent[k].strip() for k in agent):
        raise ValueError("empty common agent specification")
    sha(agent["tools_sha256"])
    limits = manifest["limits"]
    if set(limits) != {"calls_per_task", "tokens_per_task", "experiments_per_task",
                       "tool_seconds_per_task", "memory_max_chars", "new_external_usd"}:
        raise ValueError("common resource limits required")
    for key, value in limits.items():
        if key == "new_external_usd":
            if value != "0":
                raise ValueError("no new paid model budget authorized")
        elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("positive integer resource bounds required")
    tasks = manifest["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("task suite required")
    fields = {"id", "phase", "group_ids", "start_ms", "end_ms", "data_sha256",
              "scorer_sha256", "baseline", "public_brief"}
    task_ids, groups, phases = set(), set(), {"learning": [], "transfer": []}
    for task in tasks:
        if set(task) != fields:
            raise ValueError("unexpected or missing task fields")
        identifier(task["id"])
        if task["id"] in task_ids or task["phase"] not in phases:
            raise ValueError("duplicate task or invalid phase")
        task_ids.add(task["id"])
        ids = task["group_ids"]
        if not isinstance(ids, list) or not ids or not all(isinstance(g, str) and g for g in ids):
            raise ValueError("canonical game/source group IDs required")
        if len(set(ids)) != len(ids) or groups.intersection(ids):
            raise ValueError("source group reused across research tasks")
        groups.update(ids)
        start, end = task["start_ms"], task["end_ms"]
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (start, end)) or end <= start:
            raise ValueError("invalid task time interval")
        sha(task["data_sha256"])
        sha(task["scorer_sha256"])
        if not isinstance(task["baseline"], dict) or not task["baseline"]:
            raise ValueError("common per-task baseline required")
        if not isinstance(task["public_brief"], str) or not task["public_brief"].strip():
            raise ValueError("public task brief required")
        phases[task["phase"]].append(task)
    if not all(phases.values()):
        raise ValueError("learning and transfer tasks required")
    if max(t["end_ms"] for t in phases["learning"]) >= min(t["start_ms"] for t in phases["transfer"]):
        raise ValueError("learning evidence must predate transfer tasks")
    # Validate JSON finiteness before making a permanent claim.
    digest(manifest)


class Study:
    def __init__(self, root):
        self.root = Path(root)
        self.journal = Journal(self.root)

    @classmethod
    def create(cls, root, manifest):
        validate_manifest(manifest)
        root = Path(root)
        root.mkdir(parents=True, exist_ok=False)
        study = cls(root)
        with study.journal.locked():
            (root / "source").mkdir()
            source_hashes = {}
            for name in ("agent_study.py", "market_rsi.py"):
                source = Path(__file__).with_name(name)
                shutil.copyfile(source, root / "source" / name)
                source_hashes[name] = file_hash(source)
            study._put("manifest.json", dict(spec=manifest, sources=source_hashes))
            for arm in ARMS:
                study._put(f"memory-{arm}-000.json", dict(
                    arm=arm, generation=0, core_sha256=digest(manifest["agent"]),
                    previous_sha256=None, text="", evidence=[]))
        return study

    def _put(self, name, value):
        fresh_json(self.root / name, value)
        self.journal.append("artifact", {"name": name, "sha256": digest(value)})

    def _read(self, name):
        records = [r for r in self.journal.read()
                   if r["event"] == "artifact" and r["payload"]["name"] == name]
        if len(records) != 1:
            raise ValueError("missing or duplicate artifact commitment: " + name)
        value = load_json(self.root / name)
        if digest(value) != records[0]["payload"]["sha256"]:
            raise ValueError("committed artifact changed: " + name)
        return value

    def verify(self):
        # Small pilot: verify the entire journal and all artifacts each transition.
        for r in self.journal.read():
            if r["event"] == "artifact":
                self._read(r["payload"]["name"])
        frozen = self._read("manifest.json")
        for name, expected in frozen["sources"].items():
            if file_hash(Path(__file__).with_name(name)) != expected or file_hash(self.root / "source" / name) != expected:
                raise ValueError("study source changed after claim")
        return copy.deepcopy(frozen["spec"])

    def _task(self, manifest, task_id):
        identifier(task_id)
        matches = [t for t in manifest["tasks"] if t["id"] == task_id]
        if len(matches) != 1:
            raise ValueError("task not in frozen suite")
        return matches[0]

    def _latest_memory(self, arm):
        if arm not in ARMS:
            raise ValueError("unknown study arm")
        names = [r["payload"]["name"] for r in self.journal.read()
                 if r["event"] == "artifact" and r["payload"]["name"].startswith(f"memory-{arm}-")]
        return self._read(names[-1])

    def _episode(self, task_id, arm):
        identifier(task_id)
        if arm not in ARMS:
            raise ValueError("unknown study arm")
        return f"episode-{task_id}-{arm}"

    def begin_episode(self, task_id, arm):
        """Return an allowlisted request, never internal task/test metadata."""
        with self.journal.locked():
            manifest = self.verify()
            task = self._task(manifest, task_id)
            episode = self._episode(task_id, arm)
            if task["phase"] == "learning":
                if (self.root / "frozen-researchers.json").exists():
                    raise ValueError("learning is closed")
                prior = [t for t in manifest["tasks"] if t["phase"] == "learning"]
                for t in prior[:prior.index(task)]:
                    self._read(self._episode(t["id"], arm) + "-feedback.json")
                memory = self._latest_memory(arm)
            else:
                frozen = self._read("frozen-researchers.json")
                memory = frozen[arm]
            request = dict(
                episode_id=episode, task_id=task_id, phase=task["phase"], arm=arm,
                agent=manifest["agent"], researcher_memory=memory,
                selector=ARMS[arm]["selector"], limits=manifest["limits"],
                task_brief=task["public_brief"], baseline=task["baseline"],
                baseline_sha256=digest(task["baseline"]), reset_downstream=True,
                hidden_test_access=False, cross_arm_access=False)
            self._put(episode + "-request.json", request)
            return copy.deepcopy(request)

    def _usage(self, usage, limits):
        expected = {"calls", "tokens", "experiments", "tool_seconds", "actual_new_external_usd"}
        if set(usage) != expected or usage["actual_new_external_usd"] != "0":
            raise ValueError("invalid usage or unauthorized external charge")
        for key in expected - {"actual_new_external_usd"}:
            value = usage[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("nonnegative metered usage required")
            if value > limits[key + "_per_task"]:
                raise ValueError("episode exceeded a resource cap; audit before continuing")

    def record_learning_feedback(self, task_id, arm, feedback, usage, executor_receipt_sha256):
        """Trusted dev feedback only. Caller owns independent execution provenance."""
        with self.journal.locked():
            manifest = self.verify()
            episode = self._episode(task_id, arm)
            request = self._read(episode + "-request.json")
            if request["phase"] != "learning" or (self.root / "frozen-researchers.json").exists():
                raise ValueError("transfer results cannot become learning feedback")
            self._usage(usage, manifest["limits"])
            sha(executor_receipt_sha256)
            if not isinstance(feedback, dict) or feedback.get("scope") != "train_dev_only":
                raise ValueError("explicit permitted feedback scope required")
            value = dict(episode_id=episode, arm=arm, feedback=feedback, usage=usage,
                         executor_receipt_sha256=executor_receipt_sha256,
                         request_sha256=digest(request))
            self._put(episode + "-feedback.json", value)
            return copy.deepcopy(value)

    def update_memory(self, arm, text, evidence_episode_ids, response_sha256):
        """Version a researcher's own reflection. No human-authored tips in study runs."""
        with self.journal.locked():
            manifest = self.verify()
            if arm not in ARMS or not ARMS[arm]["carry_memory"]:
                raise ValueError("this arm does not carry memory")
            if (self.root / "frozen-researchers.json").exists():
                raise ValueError("frozen transfer memory cannot change")
            if not isinstance(text, str) or not text.strip() or len(text) > manifest["limits"]["memory_max_chars"]:
                raise ValueError("invalid research memory")
            sha(response_sha256)
            if not evidence_episode_ids or len(set(evidence_episode_ids)) != len(evidence_episode_ids):
                raise ValueError("unique supporting feedback required")
            evidence = []
            for episode in evidence_episode_ids:
                identifier(episode)
                feedback = self._read(episode + "-feedback.json")
                if feedback["arm"] != arm:
                    raise ValueError("cross-arm experience is forbidden")
                evidence.append(dict(episode_id=episode, feedback_sha256=digest(feedback)))
            previous = self._latest_memory(arm)
            # One reflection per completed task, with no later rewrite of a task's
            # input history. Its usage is included in the episode's total receipt.
            learning = [t for t in manifest["tasks"] if t["phase"] == "learning"]
            generation = previous["generation"] + 1
            if generation > len(learning):
                raise ValueError("reflection allowance exhausted")
            current = self._episode(learning[generation - 1]["id"], arm)
            if current not in evidence_episode_ids:
                raise ValueError("reflection must cite the next completed learning task")
            for later in learning[generation:]:
                if (self.root / (self._episode(later["id"], arm) + "-request.json")).exists():
                    raise ValueError("cannot rewrite memory after a later task started")
            memory = dict(arm=arm, generation=generation, core_sha256=previous["core_sha256"],
                          previous_sha256=digest(previous), text=text, evidence=evidence,
                          response_sha256=response_sha256)
            self._put(f"memory-{arm}-{generation:03}.json", memory)
            return copy.deepcopy(memory)

    def freeze_researchers(self):
        with self.journal.locked():
            manifest = self.verify()
            for task in manifest["tasks"]:
                if task["phase"] == "learning":
                    for arm in ARMS:
                        self._read(self._episode(task["id"], arm) + "-feedback.json")
            frozen = {arm: self._latest_memory(arm) for arm in ARMS}
            self._put("frozen-researchers.json", frozen)
            return copy.deepcopy(frozen)

    def commit_submission(self, task_id, arm, submission, usage):
        """Seal a final task choice before any hidden score is opened."""
        with self.journal.locked():
            manifest = self.verify()
            episode = self._episode(task_id, arm)
            request = self._read(episode + "-request.json")
            if request["phase"] != "transfer" or (self.root / "scoring-claim.json").exists():
                raise ValueError("submission window closed or not a transfer task")
            fields = {"initial_baseline_sha256", "predictor_sha256", "executor_receipt_sha256", "status"}
            if set(submission) != fields or submission["status"] not in {"valid", "researcher_invalid", "infrastructure_failure"}:
                raise ValueError("invalid submission schema")
            if submission["initial_baseline_sha256"] != request["baseline_sha256"]:
                raise ValueError("different baseline or cross-task checkpoint inheritance")
            for k in fields - {"status"}:
                sha(submission[k])
            self._usage(usage, manifest["limits"])
            self._put(episode + "-submission.json", dict(
                request_sha256=digest(request), submission=submission, usage=usage))

    def begin_scoring(self):
        """Permanent one-time claim. A crashed scorer is not silently re-run."""
        with self.journal.locked():
            manifest = self.verify()
            submissions = {}
            for task in manifest["tasks"]:
                if task["phase"] == "transfer":
                    for arm in ARMS:
                        name = self._episode(task["id"], arm) + "-submission.json"
                        submissions[name] = digest(self._read(name))
            self._put("scoring-claim.json", submissions)
            return copy.deepcopy(submissions)

    def record_scores(self, scores, scorer_receipt_sha256):
        """Trusted hidden evaluator reports per-task Brier. Never returned to memory."""
        with self.journal.locked():
            manifest = self.verify()
            self._read("scoring-claim.json")
            sha(scorer_receipt_sha256)
            tasks = [t for t in manifest["tasks"] if t["phase"] == "transfer"]
            if set(scores) != {t["id"] for t in tasks}:
                raise ValueError("must report every registered transfer task")
            gains = {arm: [] for arm in ARMS}
            per_task, incomplete = {}, []
            for task in tasks:
                row = scores[task["id"]]
                if set(row) != {"baseline_brier", "arms", "scorer_sha256", "data_sha256"}:
                    raise ValueError("invalid score schema")
                if row["scorer_sha256"] != task["scorer_sha256"] or row["data_sha256"] != task["data_sha256"]:
                    raise ValueError("task data or scorer changed")
                baseline = probability(row["baseline_brier"])
                if set(row["arms"]) != set(ARMS):
                    raise ValueError("must retain every arm")
                per_task[task["id"]] = {}
                for arm in ARMS:
                    name = self._episode(task["id"], arm) + "-submission.json"
                    submission = self._read(name)["submission"]
                    reported = row["arms"][arm]
                    if submission["status"] == "infrastructure_failure":
                        if reported is not None:
                            raise ValueError("infrastructure outcome must remain unknown")
                        gain = None
                        incomplete.append(dict(task_id=task["id"], arm=arm))
                    else:
                        brier = probability(reported)
                        if submission["status"] == "researcher_invalid" and brier != baseline:
                            raise ValueError("invalid researcher submission uses baseline fallback")
                        gain = baseline - brier
                        gains[arm].append(gain)
                    per_task[task["id"]][arm] = gain
            means = {a: (sum(v) / len(v) if len(v) == len(tasks) else None) for a, v in gains.items()}
            comparisons = {"memory_minus_reset": None, "market_minus_memory": None}
            if not incomplete:
                comparisons = dict(memory_minus_reset=means["memory"] - means["reset"],
                                   market_minus_memory=means["memory_market"] - means["memory"])
            result = dict(evidence_class=manifest["evidence_class"], task_count=len(tasks),
                          scores=scores, per_task_brier_gain=per_task, mean_brier_gain=means,
                          paired_comparisons=comparisons, incomplete=incomplete,
                          scorer_receipt_sha256=scorer_receipt_sha256,
                          significance_claim=False, llm_weight_learning_claim=False,
                          pnl_claim=False, prospective_claim=False)
            self._put("transfer-results.json", result)
            return copy.deepcopy(result)
