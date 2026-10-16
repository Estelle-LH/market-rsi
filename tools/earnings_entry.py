"""Source-bound one-forecast entry; not a self-evolution or trading claim."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import time
import uuid

from edgar_forecast_audit import load_scorer
from edgar_forecast_model_pilot import digest, strict_single_number
from edgar_forecast_openai import REPO, PILOT, PLAN_HASH, credential, ProviderHTTPError, forecast, research_recipe_message
from edgar_forecast_tools import FilingTools
from earnings_night_budget import NightBudget, DeadlineHTTP, history_snapshot, utc_epoch
from edgar_forecast_budget import BudgetStop
from earnings_http import RawOpenAIHTTP

SOURCES = ("tools/earnings_entry.py", "tools/earnings_http.py", "tools/earnings_night_budget.py", "tools/earnings_clock.py",
           "tools/edgar_forecast_openai.py", "tools/edgar_forecast_budget.py",
           "tools/edgar_forecast_full_budget.py", "tools/edgar_forecast_model_pilot.py",
           "tools/edgar_forecast_tools.py", "tools/edgar_forecast_audit.py")
BASELINE = {"max_rowid": 3695, "request_count": 3695, "charged_nano_usd": 124849835700,
            "rows_sha256": "7bee7f75ccfd7e2f495dca36fb5778c0030b750ed9472c25750ba8a464466e90"}
DEADLINE = "2026-10-13T15:03:10Z"
CUTOFF = "2026-10-13T14:33:10Z"
ARCHIVE = PILOT.parent.parent / "earnings-overnight-20261012"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def strict_json(text):
    def invalid(value):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid)


def strict_predictions(response, targets):
    if (response.get("error") is not None or any(i.get("type") == "refusal"
            or i.get("refusal") is not None
            or any(c.get("type") == "refusal" for c in i.get("content", []))
            for i in response["output"])):
        raise ValueError("Refusal or provider error is not a financial forecast")
    if response.get("status") != "completed" or any(i.get("type") == "function_call" for i in response["output"]):
        raise ValueError("Unfinished or tool-bearing final response")
    text = "".join(c["text"] for i in response["output"] if i.get("type") == "message"
                   for c in i.get("content", []) if c.get("type") == "output_text")
    payload = strict_json(text)
    values = payload.get("predictions") if type(payload) is dict else None
    if (type(payload) is not dict or set(payload) != {"predictions"} or len(targets) != 5
            or len(set(targets)) != 5 or type(values) is not list or len(values) != 5):
        raise ValueError("Exactly five original targets required")
    if (any(type(i) is not dict or set(i) != {"target_id", "predicted_value"}
            or type(i.get("target_id")) is not str for i in values)
            or strict_single_number(payload, targets)):
        raise ValueError("Five unique IDs and original single finite numeric values required")
    return payload


def checked(binding):
    path = Path(binding["path"]).absolute()
    if path.resolve() != path or path.is_symlink() or not path.is_file():
        raise ValueError("Canonical regular artifact required")
    data = path.read_bytes()
    if digest(data) != binding["sha256"]:
        raise ValueError("Bound artifact changed")
    return data


def policy_sha(config):
    policy = {k: v for k, v in config.items() if k not in ("review", "launch_policy_sha256")}
    return digest(json.dumps(policy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def load_research_recipe(config):
    if "research_recipe" not in config:
        return None
    binding = config["research_recipe"]
    if (type(binding) is not dict or set(binding) != {"path", "sha256"}
            or type(binding["path"]) is not str or type(binding["sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])):
        raise ValueError("Exact immutable recipe binding required")
    recipe = strict_json(checked(binding).decode())
    parent = config.get("parent_feedback_sha256")
    task = config.get("task_id")
    if (type(parent) is not str or not re.fullmatch(r"[0-9a-f]{64}", parent)
            or type(task) is not str or not task or type(recipe) is not dict
            or set(recipe) != {"schema", "task_id", "parent_feedback_sha256", "research_instructions"}
            or recipe["schema"] != "earnings_research_recipe_v1" or recipe["task_id"] != task
            or recipe["parent_feedback_sha256"] != parent):
        raise ValueError("Recipe task/parent/schema identity differs")
    research_recipe_message(recipe)  # Check the actual message ceiling before credentials.
    return recipe


def load_parent_plan(config, recipe, *, questions=None):
    context = config.get("parent_plan_context")
    if context is None:
        return None
    if (recipe is None or type(context) is not dict
            or set(context) != {"recipe", "feedback_packet"}):
        raise ValueError("One bound parent plan and current recipe required")
    for binding in context.values():
        if (type(binding) is not dict or set(binding) != {"path", "sha256"}
                or type(binding["path"]) is not str or not Path(binding["path"]).is_absolute()
                or type(binding["sha256"]) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])):
            raise ValueError("Exact parent plan/packet bindings required")
    parent = strict_json(checked(context["recipe"]).decode())
    packet = strict_json(checked(context["feedback_packet"]).decode())
    feedback = packet.get("feedback") if type(packet) is dict else None
    observation = feedback.get("observation") if type(feedback) is dict else None
    if (type(packet) is not dict
            or set(packet) != {"schema", "task_id", "parent_feedback_sha256", "questions", "feedback", "prior_recipe"}
            or packet["schema"] != "earnings_controller_packet_v1"
            or packet["task_id"] != config["task_id"] or packet["prior_recipe"] != parent
            or packet["parent_feedback_sha256"] != recipe["parent_feedback_sha256"]
            or type(packet["questions"]) is not str or not packet["questions"]
            or (questions is not None and packet["questions"] != questions)
            or type(observation) is not dict
            or observation.get("schema") != "earnings_aggregate_feedback_v1"
            or observation.get("task_id") != config["task_id"] or observation.get("cik") != config["cik"]):
        raise ValueError("Parent/current plan and task feedback lineage differs")
    from edgar_forecast_openai import research_recipe_messages
    research_recipe_messages(recipe, parent)  # Same actual compiler/combined ceiling before credentials.
    return parent


def durable_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def absolute_window(seconds):
    if seconds <= 0 or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise BudgetStop("No positive exclusive alarm window")
    old = signal.getsignal(signal.SIGALRM)
    def timeout(signum, frame):
        raise BudgetStop("Absolute forecast deadline")
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


class ReceiptHTTP:
    def __init__(self, client, output):
        self.client, self.output = client, output

    def post(self, endpoint, payload):
        identity = str(uuid.uuid4())
        prefix = self.output / ("http-" + identity)
        intent = {"endpoint": endpoint, "payload": payload,
                  "utc_epoch": time.time(), "retry_allowed": False}
        if endpoint == "/v1/responses":
            records = sorted(self.output.glob("[0-9][0-9]-request.json"))
            if not records:
                raise ValueError("Generation requires its preserved ledger reservation receipt")
            record = strict_json(records[-1].read_text())
            if any(payload.get(k) != v for k, v in record["payload"].items()):
                raise ValueError("Physical generation payload differs from counted/reserved request")
            intent.update(budget_request_id=record["request_id"],
                          complete_reservation=record,
                          request_receipt_sha256=digest(records[-1].read_bytes()))
        durable_json(prefix.with_suffix(".intent.json"), intent)
        if isinstance(self.client, DeadlineHTTP) and isinstance(self.client.client, RawOpenAIHTTP):
            self.client.client.record_prefix = prefix
        try:
            response = self.client.post(endpoint, payload)
        except BaseException as error:
            failure = {"exception_type": type(error).__name__, "retry_allowed": False}
            if isinstance(error, ProviderHTTPError):
                failure.update(error.detail)
            durable_json(prefix.with_suffix(".failed.json"), failure)
            raise
        durable_json(prefix.with_suffix(".response.json"), response)
        return response


def validate_review(config):
    if config["launch_policy_sha256"] != policy_sha(config):
        raise ValueError("Actual launch policy changed")
    if "loop_authorization" in config:
        from earnings_loop_policy import validate_child
        validate_child(config)
        return
    review = strict_json(checked(config["review"]).decode())
    if review.get("source_commit") != config["source_commit"] or review.get("verdict") != "PASS_FOR_ONE_BOUNDED_FORECAST":
        raise ValueError("Exact launch review missing")
    if review.get("launch_policy_sha256") != config["launch_policy_sha256"]:
        raise ValueError("Launch policy review differs")


def preflight(config, *, require_review=True):
    commit = config["source_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Exact source commit required")
    if (config["baseline"] != BASELINE or config["deadline_utc"] != DEADLINE
            or config["new_request_cutoff_utc"] != CUTOFF
            or config["max_forecast_rollouts"] != 6):
        raise ValueError("Original CP0/window/rollout authority changed")
    if (str(Path(sys.executable).absolute()) != config["python"]["path"]
            or digest(Path(sys.executable).read_bytes()) != config["python"]["sha256"]):
        raise ValueError("Actual Python runtime changed")
    for name in SOURCES:
        data = subprocess.run(["git", "show", commit + ":" + name], cwd=REPO, check=True, capture_output=True).stdout
        if data != (REPO / name).read_bytes():
            raise ValueError("Committed source differs")
    recipe = load_research_recipe(config)
    load_parent_plan(config, recipe)
    if digest((PILOT / "pilot-plan.json").read_bytes()) != PLAN_HASH:
        raise ValueError("Original data definition changed")
    plan = strict_json((PILOT / "pilot-plan.json").read_text())
    company = next(c for c in plan["companies"] if c["cik"] == config["cik"])
    tools = FilingTools(company)
    load_parent_plan(config, recipe, questions=tools.files["questions.md"])
    targets = re.findall(r"^### (T\d+) \|", tools.files["questions.md"], re.M)
    if targets != ["T001", "T002", "T003", "T004", "T005"]:
        raise ValueError("Five-target task identity changed")
    prior = strict_json(checked(config["prior_batch"]).decode())["config"]
    if config["model"] != "gpt-6.1-sol" or config["runtime_config"] != prior:
        raise ValueError("Previously-scored model/config changed")
    if config["prior_batch"]["sha256"] != "2f785ba3dc1ebf9472391757ae94991088b4517c40385c5eaa4ad0d9e001192d":
        raise ValueError("Original scored batch identity changed")
    checked(config["scorer"])
    scorer, _ = load_scorer(Path(config["scorer"]["path"]))
    checked(config["qa"])
    ledger = Path(config["ledger"]).absolute()
    if ledger.resolve() != ledger or ledger != PILOT / "api-budget.sqlite3":
        raise ValueError("Only the existing sole ledger allowed")
    with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("BEGIN")
        if (db.execute("SELECT * FROM config").fetchall() != [(1, 200_000_000_000, 100_000_000_000, 0)]
                or history_snapshot(db, config["baseline"]["max_rowid"]) != config["baseline"]
                or db.execute("SELECT 1 FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()):
            raise BudgetStop("Source-bound prior accounting or idle state changed")
    if require_review:
        validate_review(config)
    return company, targets, scorer


def run_one(config, client_factory=None):
    company, targets, scorer = preflight(config)
    clock_window = None
    if "loop_authorization" in config or "inherited_clock" in config:
        from earnings_clock import capture_or_load
        if "loop_authorization" in config:
            root = strict_json(checked(config["loop_authorization"]["envelope"]).decode())["root"]
        else:
            root = str(Path(config["inherited_clock"]["binding"]["path"]).parent)
        clock_window, _ = capture_or_load(root, config, create=False)
        if time.monotonic() >= clock_window["cutoff_monotonic"]:
            raise BudgetStop("Original shared forecast launch cutoff")
    if time.time() >= utc_epoch(config["new_request_cutoff_utc"]):
        raise BudgetStop("Final-thirty-minute launch cutoff")
    output = Path(config["output"]).absolute()
    if output.resolve() != output or output.parent != ARCHIVE / "attempts":
        raise ValueError("Canonical output required")
    attempts = output.parent
    attempts.mkdir(parents=True, exist_ok=True)
    lock_file = os.open(attempts / ".worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_file, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if sum(p.is_dir() for p in attempts.iterdir()) >= 6:
            raise BudgetStop("Six forecast attempts already consumed")
        return _claimed_forecast(config, company, targets, scorer, output, client_factory, clock_window)


def preflight_capacity_episode(envelope, *, for_live=False):
    """Readonly new-study check. Legacy six slots/window/budget remain unchanged."""
    if type(envelope) is dict and envelope.get('schema') == 'earnings_capacity_episode_v3':
        from earnings_live_capacity import admit
        return admit(envelope)
    from earnings_loop_policy import validate_capacity_episode
    from earnings_research_state import ResearchState, sha
    study = validate_capacity_episode(envelope)
    if (study["data"]["path"] != str(PILOT / "pilot-plan.json") or study["data"]["sha256"] != PLAN_HASH
            or digest(checked(study["data"])) != PLAN_HASH
            or study["prior_batch"]["sha256"] != "2f785ba3dc1ebf9472391757ae94991088b4517c40385c5eaa4ad0d9e001192d"
            or study["runtime_config"] != strict_json(checked(study["prior_batch"]).decode())["config"]
            or study["model"] != {"requested_model": "gpt-6.1-sol", "serving_snapshot": "unknown", "serving_snapshot_verified": False}
            or str(Path(sys.executable).absolute()) != study["python"]["path"]
            or digest(Path(sys.executable).read_bytes()) != study["python"]["sha256"]):
        raise ValueError("Original data/base model/config and exact runtime required")
    if study["scorer"]["sha256"] != "00283f8dec7565ebf22d3fb232ca4e956d23c76ef2c2e3f40b8f8f65dc23b563":
        raise ValueError("Original scorer required")
    checked(study["scorer"])
    plan = strict_json(checked(study["data"]).decode())
    company = next(c for c in plan["companies"] if c["cik"] == envelope["cik"])
    admitted = next(c for c in study["cases"] if c["cik"] == envelope["cik"])
    manifest_sha = digest(json.dumps(company["allowed_files"], sort_keys=True, separators=(",", ":")).encode())
    if admitted["allowed_manifest_sha256"] != manifest_sha or any(admitted[k] != company[k] for k in ("cutoff", "target_accession", "visible_root")):
        raise ValueError("Actual company information boundary differs")
    state = ResearchState(company, envelope["id"])
    initial = state.load(envelope["initial_state"])
    if initial != state.empty():
        raise ValueError("Every new trajectory must have the same empty starting record facility")
    ledger = Path(study["sole_ledger"])
    if ledger != PILOT / "api-budget.sqlite3" or ledger.resolve() != ledger:
        raise ValueError("Existing sole cumulative ledger required")
    with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
        if (db.execute("SELECT * FROM config").fetchall() != [(1, 200_000_000_000, 100_000_000_000, 0)]
                or history_snapshot(db, BASELINE["max_rowid"]) != BASELINE
                or db.execute("SELECT 1 FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()):
            raise BudgetStop("Original cumulative accounting/history/idle boundary differs")
    if for_live:
        raise BudgetStop("No fresh bounded grant or source-bound paid capacity role adapter; offline only")
    return company, state


def _claimed_forecast(config, company, targets, scorer, output, client_factory, clock_window=None):
    hard_deadline = time.monotonic() + max(0, utc_epoch(config["deadline_utc"]) - time.time())
    if clock_window is not None:
        hard_deadline = min(hard_deadline, clock_window["deadline_monotonic"])
    output.mkdir(parents=True, exist_ok=False)
    durable_json(output / "identity.json", config)
    result = {"status": "FAILED_NO_RETRY", "planned_targets": 5, "scored_targets": 0}
    budget = None
    try:
        if clock_window is not None:
            durable_json(output / "clock-window.json", clock_window)
        recipe = load_research_recipe(config)
        parent_plan = load_parent_plan(config, recipe)
        if recipe is not None:
            durable_json(output / "effective-recipe.json", {"recipe": recipe,
                "binding": config["research_recipe"],
                "parent_feedback_sha256": config["parent_feedback_sha256"]})
        if parent_plan is not None:
            durable_json(output / "effective-parent-plan.json", {"recipe": parent_plan,
                "context": config["parent_plan_context"], "current_recipe": config["research_recipe"],
                "scope": "One previous method plan; no previous evidence table or calculations supplied."})
        budget = NightBudget(config["ledger"], baseline=config["baseline"], deadline_utc=config["new_request_cutoff_utc"],
            **({} if clock_window is None else {"captured_deadline": clock_window["cutoff_monotonic"]}))
        runtime = config["runtime_config"]
        factory = client_factory or (lambda: RawOpenAIHTTP(credential(), runtime["request_timeout_seconds"]))
        transport = DeadlineHTTP(factory(), deadline_utc=config["new_request_cutoff_utc"],
            rollout_seconds=runtime["company_wall_seconds"], captured_deadline=budget.monotonic_deadline)
        client = ReceiptHTTP(transport, output)
        seconds = min(runtime["company_wall_seconds"], hard_deadline - time.monotonic(),
                      utc_epoch(config["deadline_utc"]) - time.time())
        with absolute_window(seconds):
            started = time.monotonic()
            args = (client, runtime["models"][config["model"]], runtime, company, budget, output)
            options = {} if recipe is None else {"research_recipe": recipe}
            if parent_plan is not None:
                options["parent_research_recipe"] = parent_plan
            result.update(forecast(*args, **options))
            responses = sorted(output.glob("[0-9][0-9]-response.json"))
            predictions = strict_predictions(strict_json(responses[-1].read_text()), targets)
            score = scorer(predictions_payload=predictions, benchmark_qa_payload=strict_json(checked(config["qa"]).decode()))
            durable_json(output / "score.json", score)
        if time.time() >= utc_epoch(config["deadline_utc"]) or time.monotonic() - started >= seconds:
            raise BudgetStop("Late forecast; valid usage retained, output not accepted")
        result.update(status="COMPLETED_SCORED", scored_targets=5, points=score["score_out_of_5"])
    except Exception as error:
        result.update(status="FAILED_NO_RETRY", error_type=type(error).__name__)
        if isinstance(error, BudgetStop):
            result["boundary_reason"] = str(error)
        if isinstance(error, ProviderHTTPError):
            result.update(error.detail)
    finally:
        if budget is not None:
            try:
                durable_json(output / "budget-summary.json", budget.summary())
            finally:
                budget.close()
    if result["status"] == "COMPLETED_SCORED" and (time.monotonic() >= hard_deadline
            or time.time() >= utc_epoch(config["deadline_utc"])):
        result.update(status="FAILED_NO_RETRY", scored_targets=0,
                      error_type="BudgetStop", boundary_reason="Late terminal acceptance")
    durable_json(output / "result.json", result)
    return result


class CapacityForecast:
    """Existing financial loop with explicit borrowed resources; no live grant."""
    def __init__(self, context_binding, *, budget, client_factory, study_binding,
                 evaluation_kernel, clock_binding, transport_policy_binding=None):
        from copy import deepcopy
        import math
        from edgar_forecast_openai import unit
        def bound(value):
            if type(value) is not dict or set(value) != {"path", "sha256"}:
                raise ValueError("Exact forecast artifact binding required")
            checked(value)
            return deepcopy(value)
        self.binding, self.study_binding, self.clock_binding = map(bound,
            (context_binding, study_binding, clock_binding))
        self.context = strict_json(checked(self.binding).decode())
        self.transport_policy_binding = None if transport_policy_binding is None else bound(transport_policy_binding)
        self.study = strict_json(checked(self.study_binding).decode())
        ctx, study = self.context, self.study
        plan_bound = type(ctx) is dict and ctx.get('schema') == 'earnings_capacity_forecast_transport_v2'
        names = {"schema", "source_commit", "root", "rates", "limits", "slots", "cutoff_utc", "cutoff_monotonic"}
        if (type(ctx) is not dict or set(ctx) != names | ({'runtime'} if plan_bound else set())
                or ctx["schema"] not in {"earnings_capacity_forecast_transport_v1", "earnings_capacity_forecast_transport_v2"}
                or type(ctx["source_commit"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", ctx["source_commit"])
                or type(study) is not dict or study.get("schema") != "earnings_coevolution_study_v1"
                or study.get("model") != {"requested_model": "gpt-6.1-sol", "serving_snapshot": "unknown",
                                          "serving_snapshot_verified": False}):
            raise ValueError("Bound original forecast context/study/model required")
        if plan_bound:
            from earnings_round_plan import validate_context
            validate_context(ctx, 'forecast')
        self.prior_binding = bound(study["prior_batch"])
        self.runtime = study["runtime_config"]
        self.kernel = deepcopy(evaluation_kernel)
        if (self.runtime != strict_json(checked(self.prior_binding).decode())["config"]
                or study["scorer"] != self.kernel.get("scorer")
                or ctx["rates"] != self.runtime["models"][study["model"]["requested_model"]]
                or not callable(client_factory)
                or any(not callable(getattr(budget, k, None)) for k in ("active", "reserve", "settle", "uncertain", "summary"))):
            raise ValueError("Original runtime/rates/kernel and explicit borrowed resources required")
        runtime = self.runtime
        fields = ("max_input_tokens", "max_output_tokens", "company_wall_seconds", "max_turns_per_company", "request_timeout_seconds")
        if (any(type(runtime.get(k)) is not int or runtime[k] < 1 for k in fields)
                or not 1 <= runtime["max_turns_per_company"] <= 24
                or ("final_max_output_tokens" in runtime and
                    (type(runtime["final_max_output_tokens"]) is not int or runtime["final_max_output_tokens"] < 1))):
            raise ValueError("Original finite forecast resource values required")
        expected = {"max_input_tokens": runtime["max_input_tokens"],
                    "max_output_tokens": max(runtime["max_output_tokens"], runtime.get("final_max_output_tokens", 0)),
                    "wall_seconds": runtime["company_wall_seconds"]}
        if (ctx["limits"] != expected or any(type(ctx["limits"][k]) is not int for k in expected)
                or type(ctx["cutoff_monotonic"]) not in (int, float)
                or not math.isfinite(ctx["cutoff_monotonic"]) or ctx["cutoff_monotonic"] < 0):
            raise ValueError("Forecast must inherit its original resources, not Controller limits")
        rates = ctx["rates"]
        if type(rates) is not dict or set(rates) != {"api_model", "effort", "input", "cached", "write", "output"}:
            raise ValueError("Exact original forecast rates required")
        for key in ("input", "cached", "write", "output"):
            if rates[key] is not None: unit(rates[key])
        root, slots = Path(ctx["root"]), ctx["slots"]
        if (not root.is_absolute() or root.resolve() != root or root.parent == root
                or type(slots) is not list or len(slots) < 1 or (not plan_bound and len(slots) > 6)
                or any(type(s) is not str for s in slots) or len(set(slots)) != len(slots)
                or any(not Path(s).is_absolute() or str(Path(s)) != s or Path(s).resolve() != Path(s)
                       or Path(s).parent != root / "roles" for s in slots)):
            raise ValueError("Canonical unique declared forecast slots required")
        self.window = strict_json(checked(self.clock_binding).decode())
        self.budget, self.factory = budget, client_factory
        self._check()

    def _check(self, worker=None):
        from earnings_clock import capture_or_load
        import earnings_execution_receipt as measurement
        if (strict_json(checked(self.binding).decode()) != self.context
                or strict_json(checked(self.study_binding).decode()) != self.study
                or strict_json(checked(self.prior_binding).decode())["config"] != self.runtime
                or strict_json(checked(self.clock_binding).decode()) != self.window):
            raise ValueError("Original forecast context/config/clock drift")
        if self.context['schema'] == 'earnings_capacity_forecast_transport_v2':
            from earnings_round_plan import validate_context
            validate_context(self.context, 'forecast')
        window, binding = capture_or_load(self.context["root"], {
            "source_commit": self.context["source_commit"], "new_request_cutoff_utc": self.context["cutoff_utc"],
            "deadline_utc": self.window["deadline_utc"]}, create=False)
        if (binding != self.clock_binding or window != self.window
                or window["cutoff_monotonic"] != self.context["cutoff_monotonic"]):
            raise ValueError("Forecast changed original shared clock")
        for value in self.kernel.values(): checked(value)
        self.socket_timeout()
        if worker is not None:
            from earnings_capacity_worker import CapacityWorker, SAVE_TOOL
            from edgar_forecast_tools import TOOLS
            if not isinstance(worker, CapacityWorker): raise ValueError("Actual earnings capacity worker required")
            worker._check()
            company = worker.state_api.company
            definitions = TOOLS + [SAVE_TOOL]
            if getattr(worker, 'open_program_protocol', None) is not None:
                from earnings_open_worker import ProgramWorker
                if type(worker) is not ProgramWorker:
                    raise ValueError('Exact opt-in program worker required')
                definitions = worker.program_definitions()
            if (worker.state_api.load(worker.state_binding) != worker.state
                    or worker.files != FilingTools(company).files or worker.definitions != definitions):
                raise ValueError("Forecast worker state or original tool/data facility drift")
            admitted = next((case for case in self.study["cases"] if case["cik"] == company["cik"]), None)
            if (admitted is None or admitted.get("evaluation_kernel") != self.kernel
                    or any(admitted[k] != company[k] for k in ("cutoff", "target_accession", "visible_root"))
                    or admitted["allowed_manifest_sha256"] != digest(json.dumps(company["allowed_files"],
                        sort_keys=True, separators=(",", ":")).encode())
                    or worker.capacity.baseline["model"]["requested_model"] != self.context["rates"]["api_model"]):
                raise ValueError("Forecast company/data/kernel/model differs from original study")
            measurement.kernel(self.kernel, worker.files["questions.md"])

    def socket_timeout(self):
        """Explicit repaired foreground policy; original runtime bytes remain."""
        if self.transport_policy_binding is None:
            return self.runtime["request_timeout_seconds"]
        policy = strict_json(checked(self.transport_policy_binding).decode())
        if (type(policy) is not dict or set(policy) != {"schema", "source_commit",
                "original_runtime_request_timeout_seconds", "effective_socket_timeout_seconds",
                "role_and_global_deadlines_unchanged", "retry_allowed"}
                or policy != {"schema": "edgar_foreground_slow_call_policy_v1",
                    "source_commit": self.context["source_commit"],
                    "original_runtime_request_timeout_seconds": self.runtime["request_timeout_seconds"],
                    "effective_socket_timeout_seconds": 600,
                    "role_and_global_deadlines_unchanged": True, "retry_allowed": False}
                or type(policy["effective_socket_timeout_seconds"]) is not int
                or type(policy["original_runtime_request_timeout_seconds"]) is not int
                or type(policy["role_and_global_deadlines_unchanged"]) is not bool
                or type(policy["retry_allowed"]) is not bool):
            raise ValueError("Exact source-bound 600-second foreground policy required")
        return policy["effective_socket_timeout_seconds"]

    def forecast(self, worker, slot):
        from copy import deepcopy
        import math
        import earnings_execution_receipt as measurement
        from earnings_controller import _CapacityDeadlineHTTP
        self._check(worker)
        ctx, output = self.context, Path(slot)
        if str(output) not in ctx["slots"] or output.resolve() != output or not output.is_absolute():
            raise ValueError("Forecast outside exact declared slot")
        if output.exists(): raise FileExistsError("Consumed forecast slot remains closed")
        initial_binding = deepcopy(worker.state_binding)
        initial_message, initial_receipt = worker.state_api.consume(initial_binding)
        expected_context = worker.capacity.prepare(expected_pair_sha256=worker.pair,
            questions=worker.files["questions.md"], state_message=initial_message,
            **({} if getattr(worker, "shadow_proposal_sha256", None) is None else
               {"shadow_proposal_sha256": worker.shadow_proposal_sha256}))
        if getattr(worker, 'open_program_protocol', None) is not None:
            from earnings_open_worker import ProgramWorker
            if type(worker) is not ProgramWorker:
                raise ValueError('Exact opt-in program worker required')
            expected_context = worker.expected_context()
        if worker.context != expected_context or worker.state_receipt != initial_receipt:
            raise ValueError("Forecast initial capacity/state payload differs")
        budget_cutoff = getattr(self.budget, "monotonic_deadline", ctx["cutoff_monotonic"])
        if type(budget_cutoff) not in (int, float) or not math.isfinite(budget_cutoff) or budget_cutoff < 0:
            raise ValueError("Finite original budget cutoff required")
        hard = min(ctx["cutoff_monotonic"], budget_cutoff, self.window["deadline_monotonic"],
                   time.monotonic() + self.runtime["company_wall_seconds"])
        def timely():
            self._check(worker)
            if (worker.context != expected_context or worker.state_receipt != initial_receipt
                    or worker.state_api.consume(initial_binding)[1] != initial_receipt):
                raise ValueError("Forecast initial payload/state commitment drift")
            if time.time() >= utc_epoch(ctx["cutoff_utc"]) or time.monotonic() >= hard:
                raise BudgetStop("Original capacity forecast cutoff")
        timely()
        self.budget.active()
        output.mkdir(parents=True, exist_ok=False)
        durable_json(output / "identity.json", {"context": self.binding, "study": self.study_binding,
            "kernel": self.kernel, "clock": self.clock_binding, "source_commit": ctx["source_commit"],
            "evidence_scope": "unverified_transport_component", "model_authorship_verified": False})
        result = {"status": "FAILED_NO_RETRY", "planned_targets": 5, "scored_targets": 0,
                  "retry_allowed": False, "evidence_scope": "unverified_transport_component", "model_authorship_verified": False}
        failure, started = None, time.monotonic()
        try:
            timely()
            client = self.factory()
            client.timeout = min(client.timeout, self.socket_timeout())
            transport = _CapacityDeadlineHTTP(client, timely, deadline_utc=ctx["cutoff_utc"],
                rollout_seconds=self.runtime["company_wall_seconds"], captured_deadline=hard)
            with absolute_window(hard - time.monotonic()):
                result.update(forecast(ReceiptHTTP(transport, output), ctx["rates"], self.runtime,
                    worker.state_api.company, self.budget, output, capacity_worker=worker))
                scorer, qa, targets = measurement.kernel(self.kernel, worker.files["questions.md"])
                responses = sorted(output.glob("[0-9][0-9]-response.json"))
                predictions = strict_predictions(strict_json(responses[-1].read_text()), targets)
                score = scorer(predictions_payload=predictions, benchmark_qa_payload=qa)
                durable_json(output / "score.json", score)
            timely()
            result.update(status="COMPLETED_SCORED", scored_targets=5, points=score["score_out_of_5"])
        except BaseException as error:
            failure = error
        finally:
            try: durable_json(output / "budget-summary.json", self.budget.summary())
            except BaseException as error: failure = failure or error
        if failure is None:
            try: timely(); self.budget.active()
            except BaseException as error: failure = error
        if failure is not None:
            result.update(status="FAILED_NO_RETRY", scored_targets=0, error_type=type(failure).__name__)
            result.pop("points", None)
        result["wall_seconds"] = time.monotonic() - started
        durable_json(output / "result.json", result)
        if failure is not None:
            if not isinstance(failure, Exception): raise failure
            raise RuntimeError("Capacity forecast failed once; inspect originals: " + type(failure).__name__) from failure
        return {name: {"path": str(output / (name + ".json")), "sha256": digest((output / (name + ".json")).read_bytes())}
                for name in ("result", "score")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = strict_json(args.config.read_text())
    if args.preflight_only:
        _, targets, _ = preflight(config)
        print(json.dumps({"status": "OFFLINE_PREFLIGHT_PASS", "targets": len(targets)}))
    else:
        result = run_one(config)
        print(json.dumps(result))
        raise SystemExit(0 if result["status"] == "COMPLETED_SCORED" else 2)


if __name__ == "__main__":
    main()
