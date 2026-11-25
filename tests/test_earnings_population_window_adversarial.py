"""Independent outer-window adversaries, invented fixtures unless opt-in stated.

No production ledger, provider, history replay, scorer/QA or candidate execution.
Native tests stop at the exact identity seam before any batch/lock interaction.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_clock as clock
import earnings_entry as entry
import earnings_population_budget as grant
import earnings_population_completed as completed
import earnings_population_forecast_failure as failed
import earnings_population_run as run
import earnings_population_runtime as runtime
import earnings_population_window as window
from edgar_forecast_budget import BudgetStop
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_run as preparation
import test_earnings_population_runtime as admission


GRANT = {"path": "/invented-owned/grant.json", "sha256": "a" * 64}
COMPANY = "CIK0000017313"
UTC = timezone.utc


def value180():
    return {"window_minutes": 180, "budget_amendment": deepcopy(GRANT), "companies": [COMPANY]}


class PureWindowAdversaries(unittest.TestCase):
    def test_missing_is_legacy90_but_present_duration_is_exact_integer_enum(self):
        self.assertEqual(window.minutes({}), 90)
        self.assertEqual(window.minutes({"window_minutes": 90}), 90)
        self.assertEqual(window.minutes(value180()), 180)
        for value in (None, True, False, 90.0, 180.0, "90", "180", -90, 0, 91, 179, 181, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                window.minutes(dict(value180(), window_minutes=value))
        for value in (None, [], True):
            with self.subTest(runtime=value), self.assertRaises(ValueError):
                window.minutes(value)

    def test_180_requires_exact_binding_shape_and_one_decision_not_merely_truthy_values(self):
        for grant_value in (None, True, {}, {"path": "x"}, dict(GRANT, extra=True),
                            dict(GRANT, path=1), dict(GRANT, path=""),
                            dict(GRANT, sha256=True), dict(GRANT, sha256="bad")):
            with self.subTest(grant=grant_value), self.assertRaises(ValueError):
                window.minutes(dict(value180(), budget_amendment=grant_value))
        for companies in (None, (), COMPANY, [], [COMPANY, COMPANY]):
            with self.subTest(companies=companies), self.assertRaises(ValueError):
                window.minutes(dict(value180(), companies=companies))

    def test_bounds_and_reconstructed_native_start_do_not_consult_or_renew_wall_clock(self):
        start = datetime(2030, 1, 2, 3, 4, 5, 999999, tzinfo=UTC)
        for duration in (90, 180):
            value = {} if duration == 90 else value180()
            expected = start.replace(microsecond=0) + timedelta(minutes=duration)
            bounds = window.bounds(start, value)
            self.assertEqual(bounds["cutoff_utc"], expected.strftime("%Y-%m-%dT%H:%M:%SZ"))
            self.assertEqual(bounds["deadline_utc"], (expected + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            value.update(bounds)
            with patch("time.time", side_effect=AssertionError("No refreshed wall clock")):
                self.assertEqual(window.start_utc(value), "2030-01-02T03:04:05Z")
        for start in (None, "2030-01-02", datetime(2030, 1, 2)):
            with self.subTest(start=start), self.assertRaises(ValueError):
                window.bounds(start, {})

    def test_window_and_grace_boundaries_expiry_and_invalid_now_are_strict(self):
        now = datetime(2030, 1, 1, tzinfo=UTC).timestamp()
        for duration in (90, 180):
            original = {} if duration == 90 else value180()
            original.update(window.bounds(datetime.fromtimestamp(now, UTC), original))
            window.check(original, now)
            self.assertEqual(window.GRACE_SECONDS, 60)
            for key, delta in (("cutoff_utc", 1), ("deadline_utc", 1)):
                changed = deepcopy(original)
                changed[key] = (datetime.fromisoformat(changed[key].replace("Z", "+00:00"))
                                + timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")
                with self.subTest(duration=duration, key=key), self.assertRaises(BudgetStop):
                    window.check(changed, now)
            changed = deepcopy(original)
            changed["deadline_utc"] = (datetime.fromisoformat(changed["cutoff_utc"].replace("Z", "+00:00"))
                                       - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            with self.assertRaises(BudgetStop):
                window.check(changed, now)
            for bad_now in (True, False, "0", None, float("nan"), float("inf"), now + duration * 60):
                with self.subTest(duration=duration, now=bad_now), self.assertRaises(BudgetStop):
                    window.check(original, bad_now)

    def test_original_captured_clock_refuses_duration_source_or_deadline_renewal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "clock-owner"
            config = dict(source_commit="a" * 40, new_request_cutoff_utc="2099-01-01T01:30:00Z",
                          deadline_utc="2099-01-01T01:31:00Z")
            with patch.object(clock, "boot_id", return_value="11111111-1111-1111-1111-111111111111"):
                first, bound = clock.capture_or_load(root, config)
                before = Path(bound["path"]).read_bytes()
                second, same = clock.capture_or_load(root, config)
                self.assertEqual((second, same), (first, bound))
                changed = dict(config, new_request_cutoff_utc="2099-01-01T03:00:00Z",
                               deadline_utc="2099-01-01T03:01:00Z")
                with self.assertRaises((ValueError, BudgetStop)):
                    clock.capture_or_load(root, changed)
                self.assertEqual(Path(bound["path"]).read_bytes(), before)


class RuntimeWindowAdversaries(unittest.TestCase):
    def setUp(self):
        self.f = admission.Fixture(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def amended(self):
        f = self.f
        f.value.update(value180())
        f.value["companies"] = f.ciks[:1]
        runtime.tasks.select_companies.return_value = f.ciks[:1]
        f.study["cases"] = [f.residents[f.ciks[0]]["case"]]
        f.study["campaign_resume"] = {"fixture_only": True}
        f.value["forecast_study"] = admission.save(f.owned / "study.json", f.study)
        plan = admission.save(f.repo / runtime.BUDGET_PLAN, {"fixture_only": "grant-source"})
        f.value["sources"][runtime.BUDGET_PLAN] = plan
        f.expected[runtime.BUDGET_PLAN] = plan["path"]
        f.db.execute("UPDATE config SET cap=400000000000")
        f.db.commit()
        f.value.update(window.bounds(datetime.fromtimestamp(f.now, UTC), f.value))
        return f.value

    def test_actual_preflight_legacy_absent90_and_explicit90_have_same_caps(self):
        f = self.f
        old = runtime.preflight(f.bound())
        new = runtime.preflight(f.bound(dict(f.value, window_minutes=90)))
        for key in ("limits", "baseline", "additional_cap_nano_usd", "original_extra_baseline",
                    "original_extra_cap_nano_usd", "rates", "role_efforts", "cutoff_utc", "deadline_utc"):
            self.assertEqual(new[key], old[key])

    def test_actual_preflight180_keeps_original_sources_review_ledger_and_role_guards(self):
        f = self.f; value = self.amended()
        # Only amendment activation is a trusted inert seam; real preflight,
        # source binding, study, roles, prefix and SQLite checks execute.
        with patch.object(grant, "validate_cap", return_value=400000000000) as activation:
            received = runtime.preflight(f.bound())
            self.assertEqual(received["window_minutes"], 180)
            self.assertEqual(received["limits"], f.value["limits"])
            activation.assert_called_once()
            self.assertEqual(activation.call_args.kwargs, {"amendment": GRANT})
            for mutate in (lambda v: v.update(additional_cap_nano_usd=5000000001),
                           lambda v: v["limits"]["forecast"].update(wall_seconds=1801),
                           lambda v: v["limits"]["author"].update(max_output_tokens=49153),
                           lambda v: v.update(original_extra_cap_nano_usd=50000000001)):
                changed = deepcopy(value); mutate(changed)
                with self.subTest(mutate=mutate), self.assertRaises((ValueError, BudgetStop)):
                    runtime.preflight(f.bound(changed))
            with self.assertRaises(ValueError):
                runtime.preflight(f.bound(reviewed=False))
            f.db.execute("UPDATE config SET cap=400000000001"); f.db.commit()
            with self.assertRaises(BudgetStop):
                runtime.preflight(f.bound())

    def test_invalid_duration_or_nonamended180_stops_before_source_or_ledger_checks(self):
        f = self.f
        for minutes in (None, True, 180.0, "180", -1, 181, 180):
            value = dict(f.value, window_minutes=minutes)
            with (self.subTest(minutes=minutes), patch.object(runtime, "_sources") as sources,
                  patch.object(runtime, "_ledger") as ledger, self.assertRaises(ValueError)):
                runtime.preflight(f.bound(value))
            sources.assert_not_called(); ledger.assert_not_called()


class PrepareWindowAdversaries(unittest.TestCase):
    def setUp(self):
        self.f = preparation.PreparationContracts(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_legacy_prepare_defaults90_without_changing_original_money_or_roles(self):
        value = engine.read(run.prepare(self.f.id))
        self.assertEqual(value["window_minutes"], 90)
        start = datetime.fromisoformat(window.start_utc(value).replace("Z", "+00:00"))
        cutoff = datetime.fromisoformat(value["cutoff_utc"].replace("Z", "+00:00"))
        self.assertEqual((cutoff-start).total_seconds(), 5400)
        self.assertEqual(value["additional_cap_nano_usd"], 5000000000)
        self.assertEqual(value["limits"]["forecast"], {
            "max_input_tokens": 100000, "max_output_tokens": 25000, "wall_seconds": 1800})
        self.assertEqual(value["baseline"], self.f.baseline)

    def test_invalid_new_window_refused_before_idle_or_input_creation(self):
        for minutes in (None, True, False, 90.0, 180.0, "180", -1, 181, 180):
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                run.prepare(self.f.id, window_minutes=minutes, company_count=1)
            self.assertFalse((self.f.owned / "inputs" / self.f.id).exists())
        self.f.idle.assert_not_called()
        with patch.object(grant, "amendment_binding", return_value=deepcopy(GRANT)), \
             self.assertRaises(ValueError):
            run.prepare(self.f.id, window_minutes=180, company_count=2,
                        cumulative400=True, campaign_from="never-read.json")
        self.f.idle.assert_not_called()

    def test_fresh180_prepare_preserves_verified_origin_and_no_resource_or_money_expansion(self):
        f = self.f
        seed_runtime = engine.read(run.prepare(f.id))
        state = engine.read(seed_runtime["initial_population"])
        previous = admission.save(f.owned / "attempts/edgar-population-20261016-26/population-run-result.json",
                                  {"fixture_only": "completed discovery"})
        prior_score = admission.save(f.owned / "synthetic-score-binding.json", {"fixture_only": True})
        origin = dict(population=state, research_feedback={"fixture_only": "scored public feedback"},
                      last_scored_feedback=prior_score, previous_result=previous,
                      reference_candidate={"parent": state["stable_id"]})
        plan = admission.save(f.repo / grant.PLAN, {"human_authorization": "fixture authority"})
        run.source_paths.return_value[grant.PLAN] = plan["path"]
        campaign_plan = admission.save(f.repo / run.CAMPAIGN_PLAN, {"fixture_only": "campaign plan"})
        run.source_paths.return_value[run.CAMPAIGN_PLAN] = campaign_plan["path"]
        f.id = "edgar-population-20261016-27"
        before = deepcopy(origin)
        # These are explicit trusted producer-input seams, not historical or
        # financial admission proofs. Original preparation/bounds/source-copy
        # and immutable new-ID output logic still execute as written.
        with patch.object(completed, "load", return_value=origin) as inherited, \
             patch("earnings_population_campaign_admission.scientific_contract",
                   return_value={"fixture_only": "contract"}), \
             patch.object(run, "_feedback_contract_fields", return_value={}), \
             patch.object(grant, "amendment_binding", return_value=deepcopy(GRANT)):
            new = engine.read(run.prepare(f.id, company_count=1, cumulative400=True,
                                         campaign_from=previous["path"], window_minutes=180))
        inherited.assert_called_once()
        self.assertEqual(inherited.call_args.args, (previous,))
        self.assertEqual(new["window_minutes"], 180)
        self.assertEqual(new["budget_amendment"], GRANT)
        self.assertEqual(new["companies"], [COMPANY])
        self.assertEqual(engine.read(new["initial_population"]), state)
        self.assertEqual(origin, before)
        self.assertEqual(new["baseline"], f.baseline)
        self.assertEqual(new["limits"], seed_runtime["limits"])
        self.assertEqual(new["additional_cap_nano_usd"], 5000000000)
        cutoff = datetime.fromisoformat(new["cutoff_utc"].replace("Z", "+00:00"))
        self.assertLessEqual(abs((cutoff-datetime.now(UTC)).total_seconds()-10800), 2)
        self.assertEqual((datetime.fromisoformat(new["deadline_utc"].replace("Z", "+00:00"))-cutoff).total_seconds(), 60)
        self.assertFalse((f.owned / "attempts" / f.id).exists())


class NativeStartAdversaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.native = self.root / "native"
        self.path = self.native / "controller-01/context.json"
        self.runtime = dict(root=str(self.root / "attempt"), source_commit="a" * 40,
                            slots={"controller": [str(self.root / "attempt/roles/controller-01")]})
        self.binding = admission.save(self.root / "runtime.json", {"fixture": True})
        self.selected = dict(role="controller", company_id=COMPANY, version={"id": "b" * 64})
        self.expected = {"controller-01": self.selected}
        class Reader:
            pin = staticmethod(engine.pin)
            read = staticmethod(engine.read)
        self.reader = Reader()

    def context(self, duration, *, wrong=False):
        self.runtime.update({} if duration == 90 else value180())
        self.runtime.update(window.bounds(datetime(2030, 1, 1, tzinfo=UTC), self.runtime))
        start = "2029-12-31T23:59:59Z" if wrong else "2030-01-01T00:00:00Z"
        admission.save(self.path, dict(schema="earnings_population_native_case_v1",
            company={"cik": COMPANY}, authority=self.binding, source_commit=self.runtime["source_commit"],
            pool_version=self.selected["version"], window={"start_utc": start,
                "deadline_utc": self.runtime["deadline_utc"]}))

    def test_completed_native_legacy90_and_new180_exact_start_before_identity(self):
        for duration in (90, 180):
            self.context(duration)
            with patch.object(completed, "_native_identity", side_effect=RuntimeError("identity-stop")) as identity:
                with self.assertRaisesRegex(RuntimeError, "identity-stop"):
                    completed._native(self.reader, self.native, self.binding, self.runtime, self.expected, {}, None)
                identity.assert_called_once()
                self.context(duration, wrong=True)
                identity.reset_mock()
                with self.assertRaisesRegex(ValueError, "window"):
                    completed._native(self.reader, self.native, self.binding, self.runtime, self.expected, {}, None)
                identity.assert_not_called()

    def test_failed_native_legacy90_and_new180_exact_start_before_identity(self):
        stub = admission.save(self.root / "stub.json", {"fixture_only": True})
        for duration in (90, 180):
            self.context(duration)
            common = dict(work_id="synthetic-failed", pair_sha256="c" * 64,
                          before_native_snapshot=stub, before_native_journal=stub)
            failure = admission.save(self.root / "failure.json", dict(common, owned_requests=[],
                runtime=self.binding, owner_terminal=stub, owner_claim=stub,
                candidate_adopted=False, retry_allowed=False, error_type="LoopHalted", cleanup=[]))
            closure = admission.save(self.root / "closure.json", dict(common,
                schema="earnings_native_failure_closure_v1", status="FAILED_WORK_CLOSED_NO_RETRY",
                failure_evidence=failure, runtime=self.binding, owner_terminal=stub,
                candidate_adopted=False, retry_allowed=False, own_request_count=0, own_charge_nano_usd=0))
            arguments = (self.reader, self.native, self.binding, self.runtime, self.expected, {}, None, closure, stub, [])
            with patch.object(completed, "_native_identity", side_effect=RuntimeError("identity-stop")) as identity:
                with self.assertRaisesRegex(RuntimeError, "identity-stop"):
                    failed._native_failure(*arguments, claim_bound=stub, cleanup=[])
                identity.assert_called_once()
                self.context(duration, wrong=True); identity.reset_mock()
                with self.assertRaisesRegex(ValueError, "window"):
                    failed._native_failure(*arguments, claim_bound=stub, cleanup=[])
                identity.assert_not_called()


class OwnerStartWiring(unittest.TestCase):
    def test_original_execute_routes_same_bound_start_after_original_clock_capture(self):
        for duration in (90, 180):
            f = preparation.ExecutionContracts(); f.setUp(); self.addCleanup(f.doCleanups)
            value = deepcopy(f.value)
            if duration == 180:
                value.update(value180())
            value.update(window.bounds(datetime.fromtimestamp(f.now, UTC), value))
            expected = window.start_utc(value)
            f.loop.side_effect = lambda *args, **kwargs: {"fixture_only": "no model/loop execution"}
            # Explicit owner/services/loop stand-ins are the inherited fixture.
            # Real run.execute and original capture_or_load route the start;
            # neither actual owner admission nor fee activation is claimed.
            with patch.object(run, "preflight", side_effect=engine.read):
                result = engine.read(run.execute(f.bound(value)))
            with self.subTest(duration=duration):
                self.assertEqual(result["status"], "COMPLETED_DISCOVERY_PILOT")
                self.assertEqual(f.instances[0].start_utc, expected)
                self.assertLess(f.events.index("owner_entered"), f.events.index("start_execution"))
                actual_clock = json.loads((f.root / "clock.json").read_bytes())
                self.assertEqual(actual_clock["cutoff_utc"], value["cutoff_utc"])
                self.assertEqual(actual_clock["deadline_utc"], value["deadline_utc"])
                self.assertEqual(value["limits"], f.value["limits"])


class Original26WindowMetadata(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("MARKET_RSI_VERIFY_WINDOW26_METADATA") == "1",
                         "Explicit original26 runtime/Native metadata only")
    def test_original_absent90_runtime_and_native_start_are_unchanged(self):
        runtime_path = Path("/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/"
            "edgar-population-20261016/inputs/edgar-population-20261016-26/runtime-reviewed.json")
        native_path = Path("/private/tmp/market-rsi-edgar-population-20261016-26/forecast-01-00/context.json")
        before = runtime_path.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(),
                         "67efa1dc8b18f0ead5356de63ec6136e891bad7656a4cf528361c63fe711d5ae")
        value = json.loads(before)
        self.assertNotIn("window_minutes", value)
        self.assertEqual(window.minutes(value), 90)
        native = engine.pin(native_path)
        self.assertEqual(native["sha256"], "74274e07f5f11ec1d5d0a726d7a8e6c57dbff69aaf708e18e7e44dc180caff7d")
        context = engine.read(native)
        self.assertEqual(context["window"]["start_utc"], window.start_utc(value))
        self.assertEqual(context["window"]["deadline_utc"], value["deadline_utc"])
        self.assertEqual(value["additional_cap_nano_usd"], 5000000000)
        self.assertEqual(value["limits"]["forecast"]["wall_seconds"], 1800)
        self.assertEqual(runtime_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
