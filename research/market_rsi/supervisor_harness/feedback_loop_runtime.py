"""Connect the loop to existing original transactions and global fit accounting.

Trusted input/implementation/review/reconciliation callbacks remain mandatory.
No new grant, scientific choice, arbitrary command runner or retry policy.
"""
from datetime import datetime, timezone
import fcntl
from pathlib import Path

from supervisor_harness import coevo_pilot_transaction as t
from supervisor_harness import opened_train_discovery_worker as w
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch


def pin(path):
    return {"path": str(Path(path).resolve()), "sha256": w.sha(path)}


class PilotRuntime:
    def __init__(self, root, repo, authorization_binding, configuration_binding):
        self.root, self.repo = Path(root), Path(repo)
        if not self.root.is_absolute() or self.root.resolve() != self.root:
            raise ValueError("exact permanent pilot root required")
        if authorization_binding["path"] != str(self.root / "authorization.json"):
            raise ValueError("original root authority required")
        self.authority, self.configuration = authorization_binding, configuration_binding
        self.config = t._configuration(configuration_binding, self.root)
        grant = t.c._read(authorization_binding)
        self.fixed_grant = grant
        if (grant.get("granted") is not True or grant.get("batch_id") != self.config["batch_id"]
                or grant.get("limits") != self.config["limits"]
                or any(grant.get(k) != self.config[k] for k in t.TIMES)
                or grant.get("closed") != {k: True for k in
                    ("Dev", "Final", "external_data", "external_literature", "paid_provider", "release", "push", "promotion")}):
            raise ValueError("exact unchanged bounded grant required")
        transfer = grant.get("account_transfer", {})
        t.input_limit(grant)
        if (transfer.get("approved") is not True or transfer.get("destination") != t.DESTINATION
                or transfer.get("requested_model") != t.c.MODEL or transfer.get("serving_snapshot") != "unknown"
                or transfer.get("payload_scope") != ["private Train-derived aggregate feedback", "research memory/history", "relevant candidate source context"]
                or any(transfer.get(k) is not False for k in ("raw_train_transfer", "tools_enabled", "automatic_retry"))):
            raise ValueError("unchanged compact tools-closed account boundary required")
        if grant["limits"]["sampled_rss_bytes"] != 1073741824:
            raise ValueError("native worker cannot enforce a tighter sampled RSS grant")

    def admit(self, context):
        """The coordinator is not a budget ledger; recheck the actual one."""
        grant = t.c._read(self.authority)
        if grant != self.fixed_grant or t._configuration(self.configuration, self.root) != self.config:
            raise ValueError("configuration or authority drift")
        ledger = t._file(self.root / "ledger.json")
        if (ledger.get("schema") != "market_rsi_coevo_pilot_ledger_v1"
                or ledger.get("batch_id") != grant["batch_id"]
                or ledger.get("authorization_sha256") != self.authority["sha256"]):
            raise ValueError("sole global accounting identity drift")
        stage = context["stage"]
        now = datetime.now(timezone.utc)
        finishing = stage in {"result_review", "reconcile"}
        limit = grant["deadline_utc"] if finishing else grant["selection_cutoff_utc"]
        if not t.c._time(grant["start_utc"]) <= now < t.c._time(limit):
            return False
        if ledger["status"] != "open" and not (
                finishing and ledger["status"] == "closed_at_attempt_cap"):
            return False
        if any(d["status"] == "reserved" for d in ledger["controller_decisions"]):
            return False
        if any(a["status"] in {"reserved", "uncertain"} for a in ledger["attempts"]):
            return False
        limits = grant["limits"]
        if stage in {"input", "controller"}:
            return (len(ledger["controller_decisions"]) < limits["original_controller_decisions"]
                    and len(ledger["attempts"]) < limits["candidate_attempts"]
                    and sum(a["fits_reserved"] for a in ledger["attempts"]) + 4 <= limits["statistical_fits"])
        if stage == "execute":
            return (len(ledger["attempts"]) < limits["candidate_attempts"]
                    and sum(a["fits_reserved"] for a in ledger["attempts"]) + 4 <= limits["statistical_fits"])
        return True

    def controller(self, context):
        prepared = context["outputs"]["input"]
        if prepared["authorization"] != self.authority or prepared["configuration"] != self.configuration:
            raise ValueError("input attempted to change grant")
        response = t.call(self.root, prepared["input"], self.authority, prepared["review"],
                          self.repo, configuration_binding=self.configuration)
        packet = t.c._read(prepared["input"])
        directory = self.root / "decisions" / packet["bindings"]["feedback"]["sha256"]
        return {"decision": response, "directory": str(directory),
                "artifacts": [pin(directory / name) for name in
                    ("input.json", "claim.json", "response.json", "completion.json", "ack.json")]}

    def execute(self, context):
        if not self.admit({**context, "stage": "execute"}):
            raise RuntimeError("global admission closed")
        name = context["outputs"]["implement"]["native_name"]
        if type(name) is not str or not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("exact prepared root child required")
        native = self.root / name
        if native.resolve() != native:
            raise ValueError("native root symlink")
        request = t._file(native / "ready_request.json")
        selection = t._file(native / "selection.json")
        review_binding = context["outputs"]["source_review"]["review"]
        review = t.c._read(review_binding)
        response = context["outputs"]["controller"]["decision"]
        expected = {"passed": True, "authorization_sha256": self.authority["sha256"],
            "request_sha256": w.sha(native / "ready_request.json"),
            "execution_source_sha256": w.sha(__file__)}
        if any(type(review.get(k)) is not type(v) or review.get(k) != v for k, v in expected.items()):
            raise ValueError("exact independent execution review required")
        if (request["max_fits"] != 4 or request["attempt_id"] != selection["attempt_id"]
                or selection["controller_decision_sha256"] != t.c._digest(response)
                or request["candidate_id"] != response["candidate"]["candidate_id"]
                or selection["research_parent_sha256"] != response["candidate"]["actual_parent_sha256"]):
            raise ValueError("actual original candidate binding drift")
        if request["max_wall_seconds"] > self.fixed_grant["limits"]["per_attempt_seconds"]:
            raise ValueError("request exceeds exact granted per-attempt duration")
        w.validate(request, self.repo)
        with (self.root / ".pilot.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self.admit({**context, "stage": "execute"}):
                raise RuntimeError("global admission closed under lock")
            ledger = t._file(self.root / "ledger.json")
            if (not any(d.get("status") == "completed" and d.get("decision_sha256") == t.c._digest(response)
                        for d in ledger["controller_decisions"])
                    or any(a["attempt_id"] == request["attempt_id"] for a in ledger["attempts"])):
                raise RuntimeError("original missing or attempt already consumed")
            row = {"attempt_id": request["attempt_id"], "candidate_id": request["candidate_id"],
                "native": str(native), "fits_reserved": 4, "actual_fits": None,
                "status": "reserved", "source_commit": request["source_commit"],
                "source_review_sha256": review_binding["sha256"],
                "controller_decision_sha256": t.c._digest(response),
                "research_parent_sha256": selection["research_parent_sha256"], "no_retry": True}
            ledger["attempts"].append(row); t._ledger(self.root / "ledger.json", ledger)
            try:
                batch = ContinuousDiscoveryBatch(native)
                state = batch.snapshot()
                if (state["batch_id"] != self.fixed_grant["batch_id"]
                        or any(state[k] != self.fixed_grant[k] for k in ("start_utc", "deadline_utc"))):
                    raise ValueError("native batch deadline or authority identity drift")
                if state["incumbent"]["candidate_sha256"] != response["candidate"]["comparison_incumbent_sha256"]:
                    raise ValueError("native comparison incumbent drift")
                batch.select_controller_pool([selection])
                receipt = w.execute(batch, request, self.repo)
                progress = Path(receipt["output"]) / "fit_progress.json"
                if progress.exists():
                    fits = t._file(progress)
                    row.update(actual_fits=fits["fit_calls_entered"], valid_fits_completed=fits["fit_calls_completed"])
                    if (any(type(row[k]) is not int for k in ("actual_fits", "valid_fits_completed"))
                            or not 0 <= row["valid_fits_completed"] <= row["actual_fits"] <= 4
                            or (receipt["outcome"] == "succeeded" and
                                (row["actual_fits"], row["valid_fits_completed"]) != (4, 4))):
                        row.update(invalid_fit_counters=fits, actual_fits=None, valid_fits_completed=None)
                        raise ValueError("inconsistent fit counters; actual accounting uncertain")
                elif not (native / "worker" / (request["attempt_id"] + ".process.json")).exists():
                    row.update(actual_fits=0, valid_fits_completed=0)
                row.update(status=receipt["outcome"] if row["actual_fits"] is not None else "uncertain",
                    worker_wall_seconds=receipt["wall_seconds"], sampled_peak_rss_kib=receipt["sampled_peak_rss_kib"])
                if row["status"] == "uncertain":
                    raise RuntimeError("actual fit accounting unknown; inspect without retry")
                return {"receipt": receipt, "artifacts": [pin(native / "worker" /
                    (request["attempt_id"] + ".receipt.json"))]}
            except BaseException as error:
                process = native / "worker" / (request["attempt_id"] + ".process.json")
                row.update(status="uncertain" if process.exists() else "failed_before_process",
                    error=str(error))
                if row["actual_fits"] is None and not process.exists():
                    row["actual_fits"] = 0
                raise
            finally:
                row["accounted_at_utc"] = datetime.now(timezone.utc).isoformat()
                if len(ledger["attempts"]) >= self.fixed_grant["limits"]["candidate_attempts"]:
                    ledger["status"] = "closed_at_attempt_cap"
                t._ledger(self.root / "ledger.json", ledger)

    def handlers(self, *, input, implement, source_review, result_review, reconcile):
        """Callbacks are Supervisor code, never strings from Controller output."""
        callbacks = {"input": input, "implement": implement, "source_review": source_review,
                     "result_review": result_review, "reconcile": reconcile}
        if not all(callable(v) for v in callbacks.values()):
            raise ValueError("all trusted preparation and independent review handlers required")
        return {**callbacks, "controller": self.controller, "execute": self.execute}
