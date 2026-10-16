"""Shared source-bound resources, not a paid grant or full-cycle admission.

Caller supplies reviewed roles and transport explicitly. Existing live entry
guards remain unchanged; tests of this component use owned synthetic ledgers.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import inspect
import os
from pathlib import Path
import re
import time

import earnings_entry as e
import earnings_clock as clock
import earnings_controller as controller
from earnings_night_budget import NightBudget, utc_epoch
from edgar_forecast_budget import BudgetStop
from edgar_forecast_full_budget import MODELS
from edgar_forecast_openai import unit
from earnings_loop_policy import LIMITS
from earnings_http import RawOpenAIHTTP

FIELDS = {"schema", "purpose", "id", "source_commit", "root", "ledger", "baseline",
          "cutoff_utc", "deadline_utc", "additional_cap_nano_usd", "rates", "limits", "slots", "sources"}
CORE = {"runtime": __file__, "budget": inspect.getsourcefile(NightBudget),
        "clock": clock.__file__, "controller": controller.__file__}


class _OwnedHTTP(RawOpenAIHTTP):
    """Preserve the original raw client/receipts while checking every send."""
    def __init__(self, client, check, slots, rates, efforts=None):
        if not isinstance(client, RawOpenAIHTTP):
            raise ValueError("Explicit original raw transport required")
        self.original, self.check, self.slots, self.rates = client, check, slots, rates
        if efforts is not None and (type(efforts) is not dict or set(efforts)!=set(slots)
                or rates.get('effort')!='max'
                or any(type(v) is not str or v not in {'max','high'} for v in efforts.values())):
            raise ValueError('Exact validated per-slot reasoning efforts required')
        self.efforts=None if efforts is None else dict(efforts)

    timeout = property(lambda self: self.original.timeout,
                       lambda self, value: setattr(self.original, "timeout", value))
    record_prefix = property(lambda self: self.original.record_prefix,
                             lambda self, value: setattr(self.original, "record_prefix", value))

    def post(self, endpoint, payload):
        if type(payload) is not dict or payload.get("model") != self.rates["api_model"]:
            raise ValueError("Physical request changed the fixed model or reasoning effort")
        prefix, loan = self.record_prefix, None
        if (endpoint not in {"/v1/responses/input_tokens", "/v1/responses"}
                or not isinstance(prefix, Path)
                or str(prefix.parent) not in self.slots or prefix.resolve() != prefix):
            raise ValueError("Original declared raw send intent required")
        effort=self.rates['effort'] if self.efforts is None else self.efforts[str(prefix.parent)]
        if payload.get('reasoning')!={'effort':effort}:
            raise ValueError('Physical request changed its exact declared role reasoning effort')
        intent = e.strict_json(_path(str(prefix.with_suffix(".intent.json")), file=True).read_text())
        if type(intent) is not dict or intent.get("endpoint") != endpoint or intent.get("payload") != payload:
            raise ValueError("Original physical payload/intent drift")
        if endpoint == "/v1/responses":
            record = intent.get("complete_reservation")
            if (type(record) is not dict or set(record) != {"request_id", "reserved_nano_usd", "payload"}
                    or type(record["payload"]) is not dict):
                raise ValueError("Exact preserved reservation receipt required")
            receipts = sorted(prefix.parent.glob("[0-9][0-9]-request.json"))
            if not receipts: raise ValueError("Preserved reservation receipt required")
            captured = _read({"path": str(receipts[-1]), "sha256": intent["request_receipt_sha256"]})
            if e.strict_json(captured.decode()) != record:
                raise ValueError("Original reservation receipt drift")
            if intent["budget_request_id"] != record["request_id"]:
                raise ValueError("Original in-flight request differs")
            maximum = payload.get("max_output_tokens")
            if (type(maximum) is not int or not 1 <= maximum <= self.slots[str(prefix.parent)]["max_output_tokens"]
                    or type(payload.get("store")) is not bool or payload["store"] is not False
                    or payload != dict(record["payload"], max_output_tokens=maximum, service_tier="default", store=False)):
                raise ValueError("Physical generation differs from counted request/limits")
            count_path = receipts[-1].with_name(receipts[-1].name.replace("-request.json", "-count.json"))
            count = e.strict_json(_path(str(count_path), file=True).read_text())["input_tokens"]
            ceiling = max(unit(self.rates[k]) for k in ("input", "cached", "write") if self.rates[k] is not None)
            if (type(count) is not int or count < 0 or count > self.slots[str(prefix.parent)]["max_input_tokens"]
                    or count * ceiling + maximum * unit(self.rates["output"]) > record["reserved_nano_usd"]):
                raise ValueError("Physical generation exceeds original reservation")
            loan = (record["request_id"], record["payload"]["model"], record["reserved_nano_usd"])
        self.check(loan)
        response = self.original.post(endpoint, payload)
        self.check(loan)
        return response


def _path(value, *, file=False):
    if type(value) is not str or not value:
        raise ValueError("Explicit canonical path required")
    path = Path(value)
    if (not path.is_absolute() or str(path) != value or path.resolve() != path
            or path.parent == path or (file and not path.is_file())):
        raise ValueError("Canonical regular resource path required")
    return path


def _read(bound):
    if (type(bound) is not dict or set(bound) != {"path", "sha256"}
            or type(bound["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", bound["sha256"])):
        raise ValueError("Exact source/config binding required")
    _path(bound["path"], file=True)
    return e.checked(bound)


def preflight_runtime(binding):
    """Read-only commitments; no budget owner, claim or factory invocation."""
    value = e.strict_json(_read(binding).decode())
    if type(value) is dict and value.get('schema') == 'earnings_population_runtime_v1':
        from earnings_population_runtime import preflight
        return preflight(binding)
    plan_bound = type(value) is dict and value.get('schema') == 'earnings_capacity_runtime_v3'
    expanded = type(value) is dict and value.get("schema") in {"earnings_capacity_runtime_v2", "earnings_capacity_runtime_v3"}
    role_efforts=type(value) is dict and 'role_efforts' in value
    handoff=type(value) is dict and 'feedback_handoff' in value
    fields = FIELDS | ({'forecast_study'} if expanded else set()) | ({'episode', 'matched_plan'} if plan_bound else set()) | ({'role_efforts'} if role_efforts else set()) | ({'feedback_handoff'} if handoff else set())
    if (type(value) is not dict or set(value) != fields
            or value["schema"] not in {"earnings_capacity_runtime_v1", "earnings_capacity_runtime_v2", "earnings_capacity_runtime_v3"}
            or (expanded and value["purpose"] != "capacity_episode")):
        raise ValueError("Exact earnings runtime commitment required")
    if role_efforts and (value['schema']!='earnings_capacity_runtime_v2' or value['purpose']!='capacity_episode'):
        raise ValueError('Per-role effort is opt-in only on the reviewed open v2 route')
    purpose = value["purpose"]
    roles = {"controller"} if purpose == "controller_protocol" else {"controller", "author", "review", "forecast"}
    if (purpose not in {"controller_protocol", "capacity_episode"}
            or type(value["id"]) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", value["id"])
            or type(value["source_commit"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", value["source_commit"])):
        raise ValueError("Exact runtime purpose/id/source required")
    root = _path(value["root"])
    _path(value["ledger"], file=True)
    cap = value["additional_cap_nano_usd"]
    if type(cap) is not int or cap < 1:
        raise ValueError("Explicit downward-only additional ceiling required")
    if cap > 20_000_000_000:
        from earnings_open_fresh_grant import authorized_cumulative_cap
        if authorized_cumulative_cap(value) != cap:
            raise ValueError("Exact approved24/25 cumulative allowance required above legacy USD20")
    baseline = value["baseline"]
    if (type(baseline) is not dict or set(baseline) != {"max_rowid", "request_count", "charged_nano_usd", "rows_sha256"}
            or any(type(baseline[k]) is not int or baseline[k] < 0 for k in ("max_rowid", "request_count", "charged_nano_usd"))
            or type(baseline["rows_sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", baseline["rows_sha256"])):
        raise ValueError("Frozen original accounting history required")
    if utc_epoch(value["cutoff_utc"]) > utc_epoch(value["deadline_utc"]):
        raise ValueError("Original cutoff must precede terminal deadline")
    if time.time() >= utc_epoch(value["cutoff_utc"]):
        raise BudgetStop("Runtime original cutoff reached")
    rates = value["rates"]
    if (type(rates) is not dict or set(rates) != {"api_model", "effort", "input", "cached", "write", "output"}
            or rates["api_model"] not in MODELS or type(rates["effort"]) is not str or not rates["effort"]):
        raise ValueError("Explicit fixed model/rates required")
    for name in ("input", "cached", "write", "output"):
        if name == "write" and rates[name] is None: continue
        if type(rates[name]) is not str: raise ValueError("Exact price strings required")
        unit(rates[name])
    if any(type(value[k]) is not dict or set(value[k]) != roles for k in ("limits", "slots")):
        raise ValueError("All declared role resources required")
    forecast_limits = None
    core = CORE
    if plan_bound:
        import earnings_round_plan as round_plan
        round_plan.validate_runtime_plan(value)
    if expanded:
        study = e.strict_json(_read(value["forecast_study"]).decode())
        if (type(study) is not dict or study.get("schema") != "earnings_coevolution_study_v1"
                or study.get("model") != {"requested_model": "gpt-6.1-sol", "serving_snapshot": "unknown",
                                          "serving_snapshot_verified": False}):
            raise ValueError("Exact original forecast study/model required")
        runtime = study["runtime_config"]
        if (runtime != e.strict_json(_read(study["prior_batch"]).decode())["config"]
                or rates != runtime["models"][study["model"]["requested_model"]]):
            raise ValueError("Forecast original runtime/rates drift")
        for key in ("max_input_tokens", "max_output_tokens", "company_wall_seconds", "max_turns_per_company",
                    "request_timeout_seconds", *(["final_max_output_tokens"] if "final_max_output_tokens" in runtime else [])):
            if type(runtime.get(key)) is not int or runtime[key] < 1:
                raise ValueError("Exact positive original forecast resource required")
        if runtime["max_turns_per_company"] > 24:
            raise ValueError("Original bounded forecast turn protocol required")
        forecast_limits = {"max_input_tokens": runtime["max_input_tokens"],
            "max_output_tokens": max(runtime["max_output_tokens"], runtime.get("final_max_output_tokens", 0)),
            "wall_seconds": runtime["company_wall_seconds"]}
        core = dict(CORE, forecast_entry=e.__file__, forecaster=inspect.getsourcefile(e.forecast))
    if plan_bound:
        core = dict(core, round_plan=round_plan.__file__)
    open_author=open_controller=None
    if handoff:
        from earnings_controller_handoff import validate_handoff
        validate_handoff(value)
        from earnings_open_resources import role_limits
        open_controller=role_limits()['controller']
    if expanded and value['schema']=='earnings_capacity_runtime_v2':
        from earnings_open_resources import author_ceiling, controller_ceiling
        open_author=author_ceiling(value,study)
        open_controller=controller_ceiling(value,study)
        if role_efforts:
            from earnings_open_resources import validate_role_efforts
            validate_role_efforts(value,study)
    seen = set()
    for role in roles:
        limits, slots = value["limits"][role], value["slots"][role]
        ceilings = forecast_limits if role == "forecast" and expanded else LIMITS
        if role=='author' and open_author is not None:ceilings=open_author
        if role=='controller' and open_controller is not None:ceilings=open_controller
        if (type(limits) is not dict or set(limits) != set(LIMITS)
                or any(type(limits[k]) is not int or not 1 <= limits[k] <= ceilings[k] for k in LIMITS)
                or (role == "forecast" and expanded and limits != forecast_limits)
                or type(slots) is not list or len(slots) < 1
                or (not plan_bound and len(slots) > (6 if role == "forecast" else 3))):
            raise ValueError("Bounded exact role resources required")
        for raw in slots:
            slot = _path(raw)
            if slot.parent != root / "roles" or raw in seen:
                raise ValueError("Unique declared role slot required")
            seen.add(raw)
    sources = value["sources"]
    if type(sources) is not dict or set(sources) != set(core) | {"factory_" + name for name in roles}:
        raise ValueError("Complete trusted source bindings required")
    for name, bound in sources.items():
        _read(bound)
        if name in core and bound["path"] != str(Path(core[name]).resolve()):
            raise ValueError("Runtime core source substituted")
    return value


@contextmanager
def open_capacity_runtime(binding, *, client_factory, role_factories):
    """Own one lock/clock/budget through all role calls; consumed IDs stay shut."""
    if type(binding) is not dict: raise ValueError("Exact original runtime binding required")
    binding = dict(binding)
    value = preflight_runtime(binding)
    names = set(value["slots"])
    if (not callable(client_factory) or type(role_factories) is not dict or set(role_factories) != names
            or any(not callable(f) for f in role_factories.values())):
        raise ValueError("Explicit trusted factories required; no fallback")
    for name, factory in role_factories.items():
        path = inspect.getsourcefile(factory)
        if path is None or str(Path(path).resolve()) != value["sources"]["factory_" + name]["path"]:
            raise ValueError("Role constructor source differs")
    parent, root = Path(value["ledger"]).parent, Path(value["root"])
    lock_path, claims = parent / ".capacity-runtime.lock", parent / ".capacity-runtime-claims"
    if claims.resolve() != claims or (claims.exists() and not claims.is_dir()):
        raise ValueError("Canonical claim registry required")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        preflight_runtime(binding)
        claims.mkdir(exist_ok=True)
        identity = e.digest(value["id"].encode())
        e.durable_json(claims / (identity + ".json"), {"runtime": binding, "id": value["id"],
            "source_commit": value["source_commit"], "retry_allowed": False, "scope": "unverified_runtime_component"})
        budget, error, summary = None, None, None
        try:
            config = {"source_commit": value["source_commit"], "new_request_cutoff_utc": value["cutoff_utc"],
                      "deadline_utc": value["deadline_utc"]}
            if 'feedback_handoff' in value:
                from earnings_controller_handoff import inherited_clock
                config['inherited_clock']=inherited_clock(value)
            window, clock_binding = clock.capture_or_load(root, config)
            seal=Path(clock_binding['path']).with_name('clock.binding.json')
            seal_binding = {"path": str(seal),"sha256": e.digest(seal.read_bytes())}
            budget = NightBudget(value["ledger"], baseline=value["baseline"], deadline_utc=value["cutoff_utc"],
                clock=time.time, monotonic=time.monotonic, captured_deadline=window["cutoff_monotonic"],
                additional_cap_nano_usd=value["additional_cap_nano_usd"],
                **({"runtime_binding": binding} if value["additional_cap_nano_usd"] > 20_000_000_000 else {}))
            live = [True]
            efforts=value.get('role_efforts')
            slot_efforts=None if efforts is None else {slot:efforts[name]
                for name,slots in value['slots'].items() for slot in slots}
            contexts, roles = {}, {}
            def guard(loan=None):
                if not live[0]: raise BudgetStop("Runtime owner already closed")
                preflight_runtime(binding)
                _read(clock_binding)
                _read(seal_binding)
                if clock.capture_or_load(root, config, create=False)[1] != clock_binding:
                    raise ValueError("Original captured clock binding changed")
                for bound in contexts.values(): _read(bound)
                if time.monotonic() >= window["cutoff_monotonic"]:
                    raise BudgetStop("Original runtime monotonic cutoff reached")
                if loan is None: budget.active()
                else: budget.check_reserved(*loan)
            def guarded_factory():
                guard()
                client = client_factory()
                guard()
                return _OwnedHTTP(client, guard, {s: value["limits"][name]
                    for name, slots in value["slots"].items() for s in slots}, value["rates"],efforts=slot_efforts)
            for name in sorted(names):
                guard()
                path = root / ("context-" + name + ".json")
                e.durable_json(path, {"schema": "earnings_capacity_" + name +
                    ("_transport_v2" if value['schema'] == 'earnings_capacity_runtime_v3' else "_transport_v1"),
                    "source_commit": value["source_commit"], "root": value["root"],
                    "rates":dict(value['rates'],effort=efforts[name]) if efforts is not None else value['rates'],
                    "limits": value["limits"][name], "slots": value["slots"][name],
                    "cutoff_utc": value["cutoff_utc"], "cutoff_monotonic": window["cutoff_monotonic"],
                    **({'runtime': binding} if value['schema'] == 'earnings_capacity_runtime_v3' else {})})
                contexts[name] = {"path": str(path), "sha256": e.digest(path.read_bytes())}
                roles[name] = role_factories[name](dict(contexts[name]), budget=budget, client_factory=guarded_factory)
                if not callable(roles[name]): raise ValueError("Role factory must return callable")
            guard()
            yield {"budget": budget, "window": deepcopy(window), "clock_binding": dict(clock_binding),
                   "roles": roles, "context_bindings": {name: dict(bound) for name, bound in contexts.items()}}
            guard()
        except BaseException as caught:
            error = type(caught).__name__
            raise
        finally:
            original_error = error
            terminal_error = None
            try:
                if budget is not None: summary = budget.summary()
                if error is None: guard()
            except BaseException as caught:
                terminal_error = caught
                error = error or type(caught).__name__
            finally:
                try:
                    if budget is not None:
                        live[0] = False
                        budget.close()
                except BaseException as caught:
                    terminal_error = terminal_error or caught
                    error = error or type(caught).__name__
            e.durable_json(claims / (identity + ".result.json"), {
                "status": "COMPLETED_COMPONENT_CONTEXT" if error is None else "FAILED_NO_RETRY",
                "error_type": error, "budget_summary": summary, "runtime": binding, "clock": locals().get("clock_binding"),
                "scope": "unverified_runtime_component", "retry_allowed": False, "model_authorship_verified": False})
            if error is not None and original_error is None:
                if terminal_error is not None and not isinstance(terminal_error, Exception):
                    raise terminal_error
                raise RuntimeError("Runtime terminal failure; inspect originals before a fresh attempt: " + error)
