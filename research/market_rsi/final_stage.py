"""Sealed transfer evaluation, not a new research or candidate-selection loop.

No real data is admitted yet. Live creation calls the closed independent gate
BEFORE opening hidden files. Fixture mode is limited to fixture-named studies.
The existing isolated fit/predict transport is reused with an explicit final-only
binding; no final outputs are committed to StudyState or sent to a model.
"""
import copy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time

import development_harbor as execution
from harbor_process import WALL_SECONDS, REAP_SECONDS, run_bounded_development
from failure_review import DISPOSITION, validate_review
from final_failure import read_final_failure
from inspection_stream import permitted_artifact
from market_rsi import Journal, digest, file_hash, fresh_json, identifier
from market_scoring import NumericScoreSpec, numeric_rows, score_pair
from paid_budget import money
from prediction_stream import PUBLIC_FIELDS, encoded, validate_rows
from sandbox_receipts import read_sandbox_receipts, sandbox_usage
from trial_inputs import execution_profile
from worker_receipts import Receipts, read_regular


ARMS = ("reset", "archive", "learn")
FINAL_SCORE_ALLOWANCE_SECONDS = 30


def _bytes(reads, path):
    path = str(Path(path).absolute())
    data = read_regular(path)
    reads.files[path] = hashlib.sha256(data).hexdigest()
    return data


def _restore_reads(commitment):
    if digest({k: v for k, v in commitment.items() if k != "sha256"}) != commitment["sha256"]:
        raise ValueError("final input commitment changed")
    reads = Receipts()
    reads.files = dict(commitment["files"])
    reads.absent_paths = set(commitment["absent_paths"])
    reads.revalidate()
    return reads


def _spec(value):
    value = copy.deepcopy(value)
    value["sessions"] = tuple(value["sessions"])
    return NumericScoreSpec(**value)


def _closed_context(runner):
    config, study, budget, manifest, state = runner._load()
    if (state["active"] is not None or state["transfer_frozen"] is None
            or state["learning_frozen"] is None or study._causal_review_ids(state)):
        raise ValueError("all learning states and transfer submissions must seal before any hidden-file read")
    if config["live"]:
        execution.require_admission(study.root)  # Never a fixture flag/callback.
    elif not manifest["experiment_id"].startswith("fixture-"):
        raise ValueError("offline final evaluation requires an explicitly synthetic study")
    if manifest["final_stage_source_sha256"] != file_hash(__file__):
        raise ValueError("final implementation was not frozen before research")
    return config, study, budget, manifest, state


class FinalStage:
    def __init__(self, runner):
        self.runner = runner
        self.root = Path(json.loads(read_regular(runner.root / "config.json"))["study_path"]) / "final-evaluation"
        self.journal = Journal(self.root)

    @classmethod
    def create(cls, runner, *, hidden_paths, baseline_paths):
        config, study, budget, manifest, state = _closed_context(runner)
        tasks = [t for t in manifest["tasks"] if t["phase"] == "transfer"]
        wanted = {t["task_id"] for t in tasks}
        if set(hidden_paths) != wanted or set(baseline_paths) != wanted:
            raise ValueError("exact sealed transfer tasks required; no added or selected test tasks")
        count = len(tasks) * 4  # One baseline plus all three arms; no post-score pruning.
        upper = money(execution.UPPER_USD) * count
        if upper > money(budget.snapshot()["buckets"]["final"]["available_usd"]):
            raise ValueError("entire final execution allocation exceeds the protected remainder")
        if time.time() + count * (WALL_SECONDS + REAP_SECONDS) + FINAL_SCORE_ALLOWANCE_SECONDS > datetime.fromisoformat(manifest["deadline_utc"]).timestamp():
            raise TimeoutError("full planned final batch cannot fit the reporting deadline")
        common_reads = Receipts()
        for path in (runner.root / "config.json", runner.root / "config-commitment.json",
                     study.root / "manifest.json", study.root / "learning-freeze.json",
                     study.root / "transfer-freeze.json", study.journal.path):
            _bytes(common_reads, path)
        runtime = config["runtime"]
        profile = execution_profile(runtime)
        public_games, public_markets, public_ids, public = set(), set(), set(), {}
        for task in manifest["tasks"]:
            entry = config["task_data"][task["task_id"]]
            catalog = {x["artifact_id"]: x for x in task["data_catalog"]}
            public[task["task_id"]] = {}
            for split in ("train", "dev"):
                raw = _bytes(common_reads, entry[split + "_path"])
                rows = permitted_artifact(raw, catalog[entry[split + "_id"]], task, runtime["feature_names"])["rows"]
                public[task["task_id"]][split] = rows
                public_games.update(r["game_id"] for r in rows)
                public_markets.update(r["market_id"] for r in rows)
                public_ids.update(r["row_id"] for r in rows)
        jobs, hidden, hidden_games, hidden_markets, hidden_ids = [], {}, set(), set(), set()
        for task in tasks:
            tid = task["task_id"]
            # Baseline source was committed before the first research request.
            source_reads = Receipts()
            base = _bytes(source_reads, baseline_paths[tid]).decode()
            if hashlib.sha256(base.encode()).hexdigest() != manifest["baseline_source_hashes"][tid]:
                raise ValueError("final baseline is not the original source")
            raw = _bytes(common_reads, hidden_paths[tid])
            if hashlib.sha256(raw).hexdigest() != task["opaque_test_commitment"]:
                raise ValueError("hidden bytes differ from the original opaque commitment")
            obj = json.loads(raw)
            if (set(obj) != {"schema", "experiment_id", "task_id", "materialized", "score_spec"}
                    or obj["schema"] != "market_hidden_transfer_v1"
                    or obj["experiment_id"] != manifest["experiment_id"] or obj["task_id"] != tid):
                raise ValueError("wrong hidden task identity/schema")
            spec = _spec(obj["score_spec"])
            if ((config["live"] and spec.evidence_class != "untouched")
                    or (not config["live"] and spec.evidence_class != "synthetic")
                    or task["evaluation_contract"].get("primary_metric") != "mse"
                    or spec.target != task["evaluation_contract"].get("target")
                    or spec.prediction_min != runtime["prediction_min"] or spec.prediction_max != runtime["prediction_max"]):
                raise ValueError("final metric, target, evidence class or bounds changed")
            numeric_rows(obj["materialized"], spec)  # Endpoint consistency, NOT source clock certification.
            rows = obj["materialized"]
            games, markets, ids = ({r[k] for r in rows} for k in ("game_id", "market_id", "row_id"))
            if (games & (public_games | hidden_games) or markets & (public_markets | hidden_markets)
                    or ids & (public_ids | hidden_ids)):
                raise ValueError("hidden games/contracts/rows overlap public experience or another final task")
            hidden_games.update(games); hidden_markets.update(markets); hidden_ids.update(ids)
            evaluation = [{k: copy.deepcopy(row[k]) for k in PUBLIC_FIELDS if k != "features"}
                          | {"features": {k: row["features"][k] for k in runtime["feature_names"]}} for row in rows]
            train = public[tid]["train"]
            validate_rows(train, evaluation, runtime["feature_names"])
            # Every prior learning task can enter Archive/Learn history. All of
            # that information plus current public Dev must predate this Test.
            available = [r["label_available_ms"] for t in manifest["tasks"]
                if t["phase"] == "learning" or t["task_id"] == tid
                for split in ("train", "dev") for r in public[t["task_id"]][split]]
            if max(available) // 86400000 >= evaluation[0]["decision_ms"] // 86400000:
                raise ValueError("permitted prior experience/Dev is not strictly earlier than hidden Test")
            limits = dict(profile["prediction"], prediction_min=runtime["prediction_min"], prediction_max=runtime["prediction_max"])
            packet = {"train": train, "evaluation": evaluation, "feature_names": runtime["feature_names"], "limits": limits}
            requests = [{"type": "fit", "request_id": "0"*32, "train": train, "features": runtime["feature_names"]}]
            requests += [{"type": "predict", "request_id": "0"*32, "row": row} for row in evaluation]
            if any(len(encoded(r)) + 1 > limits["max_request_bytes"] for r in requests):
                raise ValueError("final request exceeds the original execution byte allowance")
            hidden[tid] = {"path": str(Path(hidden_paths[tid]).absolute()), "sha256": task["opaque_test_commitment"],
                           "score_spec": asdict(spec)}
            for arm in ("baseline", *ARMS):
                source, submitted = base, None
                reads = Receipts()
                reads.files.update(source_reads.files)
                if arm != "baseline":
                    submitted = state["submissions"][arm][task["task_index"]]
                    if submitted["task_id"] != tid:
                        raise ValueError("sealed submission task changed")
                    if submitted["trial_id"] is not None:
                        saved = reads.read(study.root / "steps" / submitted["trial_id"] / "completion.json")
                        source = saved["payload"]["candidate_code"]
                    if hashlib.sha256(source.encode()).hexdigest() != submitted["source_sha256"]:
                        raise ValueError("final candidate differs from the sealed source")
                job_id = f"final-task-{task['task_index']:03d}-{arm}"
                jobs.append({"job_id": job_id, "arm": arm, "task_id": tid, "task_index": task["task_index"],
                    "source": source, "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "source_receipts": reads.commitment(), "packet": packet, "submitted": submitted})
        common_reads.revalidate()
        for job in jobs:
            _restore_reads(job["source_receipts"])
        obj = cls(runner)
        obj.root.mkdir(mode=0o700, exist_ok=False)  # Fixed per-study path: no duplicate final batch.
        plan = {"schema": "market_final_stage_v1", "runner_path": str(runner.root), "live": config["live"],
            "study_manifest_sha256": digest(manifest), "transfer_freeze_sha256": digest(state["transfer_frozen"]),
            "source_sha256": file_hash(__file__), "runtime": runtime, "deadline_utc": manifest["deadline_utc"],
            "jobs": jobs, "hidden": hidden, "common_receipts": common_reads.commitment(),
            "upper_usd": str(upper), "scientific_admission": False,
            "scope": "sealed transfer tasks only; learning-task hidden sets remain unopened"}
        with obj.journal.locked():
            fresh_json(obj.root / "plan.json", plan)
            obj.journal.append("created", {"plan_sha256": digest(plan)})
        return obj

    def _load(self):
        config, study, budget, manifest, state = _closed_context(self.runner)
        plan = json.loads(read_regular(self.root / "plan.json"))
        events = self.journal.read()
        if (not events or events[0]["event"] != "created" or events[0]["payload"] != {"plan_sha256": digest(plan)}
                or plan["source_sha256"] != file_hash(__file__) or plan["study_manifest_sha256"] != digest(manifest)
                or plan["transfer_freeze_sha256"] != digest(state["transfer_frozen"])):
            raise ValueError("final plan/source/selection seal changed")
        _restore_reads(plan["common_receipts"])
        for job in plan["jobs"]:
            _restore_reads(job["source_receipts"])
        active, complete, scored, failures, reviews, review_ids = None, [], False, {}, {}, set()
        for event in events[1:]:
            payload = event["payload"]
            if event["event"] == "claimed":
                if active is not None or scored or set(failures) - set(reviews) or len(complete) >= len(plan["jobs"]) or payload != {"job_id": plan["jobs"][len(complete)]["job_id"]}:
                    raise ValueError("duplicate or reordered final execution")
                active = payload["job_id"]
            elif event["event"] == "completed":
                if active != payload["job_id"]:
                    raise ValueError("final completion without matching claim")
                saved = json.loads(read_regular(self.root / "jobs" / active / "verified-final.json"))
                if (digest(saved) != payload["sha256"] or saved["job_id"] != active
                        or saved["status"] not in {"completed_predictions", "failed_unscored"}):
                    raise ValueError("final execution evidence changed")
                if saved["status"] == "failed_unscored":
                    failures[active] = digest(saved)
                complete.append(active); active = None
            elif event["event"] == "failure_reviewed":
                identifier(payload["review_id"])
                review = json.loads(read_regular(self.root / "reviews" / payload["review_id"] / "review.json"))
                validate_review(review)
                if (active is not None or scored or review["trial_id"] not in failures
                        or review["trial_id"] in reviews or review["review_id"] in review_ids
                        or review["study_manifest_sha256"] != plan["study_manifest_sha256"]
                        or review["completion_sha256"] != failures[review["trial_id"]]
                        or payload != {"review_id": review["review_id"], "sha256": digest(review)}):
                    raise ValueError("final failure review changed or refers to another outcome")
                reviews[review["trial_id"]] = review
                review_ids.add(review["review_id"])
            elif event["event"] == "scored":
                if active is not None or scored or set(failures) - set(reviews) or len(complete) != len(plan["jobs"]):
                    raise ValueError("premature/repeated final score")
                if payload != {"sha256": digest(json.loads(read_regular(self.root / "result.json")))}:
                    raise ValueError("final score changed")
                scored = True
            else:
                raise ValueError("unknown final transition")
        return plan, budget, active, complete, scored, failures, reviews

    def _bundle(self, plan, job):
        common, source = _restore_reads(plan["common_receipts"]), _restore_reads(job["source_receipts"])
        binding = {"schema": "market_sealed_final_execution_v1", "purpose": "sealed_final_only",
            "mode": "fit_predict", "action": "experiment", "candidate_sha256": job["source_sha256"],
            "execution_packet_sha256": digest(job["packet"]), "runtime_sha256": digest(plan["runtime"]),
            "owner": {"experiment_id": json.loads(read_regular(self.runner.root / "config.json"))["experiment_id"],
                "phase": "transfer", "arm": job["arm"], "task_id": job["task_id"], "task_index": job["task_index"]},
            "transfer_freeze_sha256": plan["transfer_freeze_sha256"],
            # Existing generic executor names: these are the sealed study and
            # selected source receipts, not a fictitious fresh model/coder call.
            "research_receipts": common.commitment(), "coding_receipts": source.commitment(),
            "hidden_labels_uploaded": False, "scientific_admission": False}
        return {"binding": binding, "binding_sha256": digest(binding), "packet": job["packet"],
            "candidate_source": job["source"], "runtime": plan["runtime"],
            "research_receipts": common, "coding_receipts": source, "executed": False}

    def tick(self, *, env_file=None, fixture_execute=None):
        with self.journal.locked():
            plan, budget, active, complete, scored, failures, reviews = self._load()
            if active is not None:
                return {"action": "reconcile_pending", "job_id": active}
            if set(failures) - set(reviews):
                return {"action": "causal_review_required", "job_ids": sorted(set(failures) - set(reviews))}
            if len(complete) == len(plan["jobs"]):
                return {"action": "scored" if scored else "ready_for_score"}
            remaining = len(plan["jobs"]) - len(complete)
            if time.time() + remaining * (WALL_SECONDS + REAP_SECONDS) + FINAL_SCORE_ALLOWANCE_SECONDS > datetime.fromisoformat(plan["deadline_utc"]).timestamp():
                return {"action": "window_closed"}
            if money(execution.UPPER_USD) * remaining > money(budget.snapshot()["buckets"]["final"]["available_usd"]):
                return {"action": "budget_blocked"}
            if plan["live"] and (fixture_execute is not None or env_file is None):
                raise ValueError("exact live final execution inputs required")
            if not plan["live"] and fixture_execute is None:
                raise ValueError("explicit fabricated executor required; never run candidate code on Mac")
            job = plan["jobs"][len(complete)]
            bundle = self._bundle(plan, job)
            self.journal.append("claimed", {"job_id": job["job_id"]})
        root = self.root / "jobs" / job["job_id"]
        execution.prepare_job(bundle, root)
        if plan["live"]:
            run_bounded_development(root, budget.root, env_file, deadline_utc=plan["deadline_utc"])
        else:
            fixture_execute(bundle, root, budget)
        return self.reconcile_pending()

    def _verify_execution(self, plan, budget, job):
        root, reads = self.root / "jobs" / job["job_id"], Receipts()
        claim, packet, runtime, _ = execution.verify_job(root)
        expected = self._bundle(plan, job)
        if (reads.read(root / "binding.json") != expected["binding"] or packet != job["packet"]
                or runtime != plan["runtime"] or claim["deployed_hashes"]["public/candidate.py"] != job["source_sha256"]):
            raise ValueError("final execution belongs to another candidate or input")
        if (root / "failure.json").exists():
            result = read_final_failure(root, reads, claim, packet, runtime, budget, live=plan["live"])
            return result, reads
        reads.absent(root / "failure.json")
        reads.absent(root / "collected/failure.json")
        reads.absent(root / "command-error.json")
        result = execution.verify_outputs(root)
        metering = read_sandbox_receipts(root, reads, claim, budget, "transfer", expected_live=plan["live"])
        for name in ("claim.json", "packet.json", "declared-runtime.json", "sources.json", "libraries.json", "command.json", "collection.json",
                     "collected/isolation.json", "collected/execution.json", "collected/protocol.json",
                     "collected/candidate-stderr.log", "collected/candidate-diagnostic.json",
                     "collected/predictions/claim.json", "collected/predictions/predictions.jsonl",
                     "collected/predictions/complete.json"):
            _bytes(reads, root / name)
        reads.revalidate()
        return {"job_id": job["job_id"], "status": "completed_predictions", "predictions": result["predictions"],
            "execution_receipts": reads.commitment(), "usage_at_verification": sandbox_usage(metering),
            "scored": False, "scientific_admission": False}, reads

    def reconcile_pending(self):
        """No retry. Unknown jobs stay pending; verified closed failures need review."""
        with self.journal.locked():
            plan, budget, active, complete, _, _, _ = self._load()
            if active is None:
                raise ValueError("no pending final execution")
            job = plan["jobs"][len(complete)]
            verified, reads = self._verify_execution(plan, budget, job)
            path = self.root / "jobs" / active / "verified-final.json"
            if path.exists():
                saved = json.loads(read_regular(path))
                comparable = dict(verified, usage_at_verification=saved["usage_at_verification"])
                if comparable != saved:
                    raise ValueError("interrupted final completion differs from actual receipts")
            else:
                fresh_json(path, verified)
                saved = verified
            reads.revalidate()
            self.journal.append("completed", {"job_id": active, "sha256": digest(saved)})
            return {"action": "completed", "job_id": active, "status": saved["status"], "scored": False}

    def review_failure(self, job_id, *, review_id, rationale, evidence_paths):
        """Trusted runner judgment only; no code fix, repeat or model feedback."""
        identifier(job_id); identifier(review_id)
        with self.journal.locked():
            plan, budget, active, _, scored, failures, reviews = self._load()
            if active is not None or scored or job_id not in set(failures) - set(reviews):
                raise ValueError("one completed unreviewed final failure required")
            job = next(j for j in plan["jobs"] if j["job_id"] == job_id)
            verified, reads = self._verify_execution(plan, budget, job)
            path = self.root / "jobs" / job_id / "verified-final.json"
            saved = json.loads(read_regular(path))
            if dict(verified, usage_at_verification=saved["usage_at_verification"]) != saved:
                raise ValueError("final failure differs from its original receipt")
            root = self.root / "jobs" / job_id
            citations = {}
            if not isinstance(evidence_paths, list):
                raise ValueError("exact reviewed runner evidence paths required")
            for item in evidence_paths:
                item = str(Path(item).absolute())
                if item not in reads.files or item in citations:
                    raise ValueError("unverified or repeated final-review citation")
                citations[item] = reads.files[item]
            if (str(root / "collected/protocol.json") not in citations or not set(citations) &
                    {str(root / n) for n in ("command.json", "runtime.json", "libraries.json", "collected/isolation.json")}):
                raise ValueError("candidate stderr alone cannot establish final failure cause")
            review = {"schema": "market_failure_review_v1", "review_id": review_id, "trial_id": job_id,
                "study_manifest_sha256": plan["study_manifest_sha256"], "completion_sha256": digest(saved),
                "disposition": DISPOSITION, "reviewer_origin": "trusted_runner_causal_review", "rationale": rationale,
                "evidence_citations": citations, "verified_receipt_commitments": [reads.commitment()["sha256"]],
                "review_source_sha256": file_hash(Path(__file__).with_name("failure_review.py")),
                "accounting_at_review": verified["usage_at_verification"]}
            validate_review(review)
            reads.revalidate()
            path = self.root / "reviews" / review_id / "review.json"
            if path.exists():
                if json.loads(read_regular(path)) != review:
                    raise ValueError("interrupted final review differs from reverified evidence")
            else:
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=False)
                fresh_json(path, review)
            self.journal.append("failure_reviewed", {"review_id": review_id, "sha256": digest(review)})
            return {"reviewed_job_id": job_id, "automatic_retry": False, "automatic_causal_diagnosis": False}

    def status_report(self):
        """Report every planned job even when the numeric comparison is incomplete."""
        with self.journal.locked():
            plan, budget, active, complete, scored, failures, reviews = self._load()
            jobs = []
            for job in plan["jobs"]:
                status = ("failed_unscored" if job["job_id"] in failures else "completed_predictions" if job["job_id"] in complete
                          else "pending_unreconciled" if job["job_id"] == active else "not_started")
                jobs.append({"job_id": job["job_id"], "task_id": job["task_id"], "arm": job["arm"], "status": status,
                    "reviewed": job["job_id"] in reviews})
            return {"planned_executions": len(jobs), "terminal_executions": len(complete),
                "failed_executions": len(failures), "jobs": jobs, "report_complete": scored,
                "comparison_complete": scored and not failures, "numeric_score": None,
                "budget_snapshot": budget.snapshot(), "scientific_admission": False,
                "note": "Status only; absent/failed predictions have no fabricated numeric score."}

    def score(self):
        """One all-arm report; no return path into researcher/selection memory."""
        with self.journal.locked():
            plan, budget, active, complete, scored, failures, reviews = self._load()
            if active is not None or scored or set(failures) - set(reviews) or len(complete) != len(plan["jobs"]):
                raise ValueError("every planned final execution must complete before the single report")
            if time.time() + FINAL_SCORE_ALLOWANCE_SECONDS > datetime.fromisoformat(plan["deadline_utc"]).timestamp():
                raise TimeoutError("final scoring allowance cannot fit before the report deadline")
            predictions, read_sets = {}, []
            for job in plan["jobs"]:
                verified, reads = self._verify_execution(plan, budget, job)
                saved = json.loads(read_regular(self.root / "jobs" / job["job_id"] / "verified-final.json"))
                if dict(verified, usage_at_verification=saved["usage_at_verification"]) != saved:
                    raise ValueError("final predictions/receipts changed after completion")
                predictions.setdefault(job["task_id"], {})[job["arm"]] = verified["predictions"]
                read_sets.append(reads)
            tasks = {}
            for tid, entry in plan["hidden"].items():
                data = json.loads(read_regular(entry["path"]))
                spec, p = _spec(entry["score_spec"]), predictions[tid]
                def paired(first, second):
                    if p[first] is None or p[second] is None:
                        return None  # Not zero, not a smaller mask, not an omitted task.
                    return score_pair(data["materialized"], p[first], p[second], spec)
                tasks[tid] = {"against_common_baseline": {arm: paired("baseline", arm) for arm in ARMS},
                    "archive_vs_reset": paired("reset", "archive"), "learn_vs_archive": paired("archive", "learn"),
                    "completion_by_arm": {a: "failed_unscored" if values is None else "completed_predictions" for a, values in p.items()},
                    "comparison_complete": all(value is not None for value in p.values())}
            for reads in read_sets:
                reads.revalidate()
            _restore_reads(plan["common_receipts"])
            result = {"schema": "market_final_report_v1", "plan_sha256": digest(plan), "tasks": tasks,
                "planned_executions": len(plan["jobs"]), "verified_executions": len(complete),
                "successful_executions": len(complete) - len(failures), "failed_executions": len(failures),
                "full_comparison_available": not failures, "failed_job_ids": sorted(failures),
                "missing_score_policy": "null with every planned task retained; no aggregate winner or failure imputation",
                "scientific_admission": False, "promotion": False, "net_pnl": None,
                "net_pnl_status": "not computed; requires separately admitted fees/execution/censoring contract",
                "model_weights_updated": False, "researcher_feedback": False, "synthetic": not plan["live"]}
            path = self.root / "result.json"
            if path.exists():
                if json.loads(read_regular(path)) != result:
                    raise ValueError("interrupted report differs; do not replace a final score")
            else:
                fresh_json(path, result)
            self.journal.append("scored", {"sha256": digest(result)})
            return result
