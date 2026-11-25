"""Author-only effort opt-in: synthetic authority/HTTP, actual owner checks.

The full assembly test retains the existing engine, role implementations,
temporary budget owner and original scorer. Financial data/admission, provider
bytes, program execution and independent-review receipts are explicit fixtures;
this is not live authority, model autonomy, container execution or forecast gain.
"""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_earnings_capacity_runtime as owner_fixture
import test_earnings_open_assembly as assembly_fixture
import earnings_capacity_runtime as runtime
import earnings_open_assembly as assembly
import earnings_open_fresh_grant as fresh
import earnings_open_resources as resources
from earnings_http import RawOpenAIHTTP
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


AUTHOR_AUTHORIZATION = "允许只将 Author 改为 high（建议）"
ROLE_EFFORTS = {"controller": "max", "author": "high", "review": "max", "forecast": "max"}
AUTHORITY_SOURCE = "configs/earnings_coevolution/research_followup_authority.json"
COUNT, GENERATE = "/v1/responses/input_tokens", "/v1/responses"


def authority():
    return {"schema": "earnings_research_followup_authority_v1", "human_authorization": fresh.AUTHORIZATION,
        "original_total_cap_nano_usd": 200_000_000_000, "original_per_model_cap_nano_usd": 100_000_000_000,
        "new_subgrant_nano_usd": 50_000_000_000, "first_window_cap_nano_usd": fresh.FIRST_CAP,
        "baseline": deepcopy(fresh.BASELINE),
        "scope": "Existing financial data/scorer/model/sole ledger, fresh IDs only; prior grants remain closed; no retries/refunds/purchases/pushes.",
        "window": {"issued_utc": "2098-12-31T22:30:00Z", "cutoff_utc": "2099-01-01T00:00:00Z",
                   "deadline_utc": "2099-01-01T00:01:00Z"},
        "author_configuration": {"reasoning_effort": "high", "human_authorization": AUTHOR_AUTHORIZATION}}


class _EffortFixture:
    def __init__(self, owner):
        temporary = tempfile.TemporaryDirectory(prefix="author-effort-invented-")
        owner.addCleanup(temporary.cleanup)
        self.root, self.serial = Path(temporary.name).resolve(), 0
        self.config = self.root / "invented-authority.json"
        self.policy = authority()
        self.save_policy()
        self.runtime = {"schema": "earnings_capacity_runtime_v2", "purpose": "capacity_episode",
            "id": "invented-author-effort", "root": str(self.root / "inert-episode"),
            "source_commit": "a" * 40, "ledger": str(self.root / "never-opened-ledger.sqlite3"),
            "baseline": {"invented": True}, "cutoff_utc": self.policy["window"]["cutoff_utc"],
            "deadline_utc": self.policy["window"]["deadline_utc"], "additional_cap_nano_usd": fresh.FIRST_CAP,
            "rates": {"api_model": "gpt-6.1-sol", "effort": "max", "input": "2", "cached": ".1",
                      "write": "2.5", "output": "10"},
            "sources": {"factory_author": engine.pin(assembly.__file__)},
            "role_efforts": deepcopy(ROLE_EFFORTS)}
        self.grant = {key: deepcopy(self.runtime[key]) for key in (
            "id", "root", "source_commit", "ledger", "baseline", "cutoff_utc", "deadline_utc", "additional_cap_nano_usd")}
        self.grant.update(schema=fresh.SCHEMA, sources={AUTHORITY_SOURCE: engine.pin(self.config)["sha256"]})

    def save(self, label, body):
        self.serial += 1
        return engine.save(self.root / f"{self.serial:03d}-{label}.json", body)

    def save_policy(self):
        # Each fixture is owned synthetic input; no real authority file changes.
        self.config.write_text(json.dumps(self.policy))

    def study(self):
        return {"new_live_grant": self.save("inert-grant", self.grant)}

    @contextmanager
    def scope(self):
        with patch.object(fresh, "CONFIG", self.config):
            yield


class AuthorEffortContractTests(unittest.TestCase):
    def test_exact_policy_addition_preserves_all_existing_authority_fields_and_is_optional_for_legacy(self):
        f = _EffortFixture(self)
        with f.scope():
            self.assertEqual(fresh.policy(), f.policy)
            previous = deepcopy(f.policy)
            previous.pop("author_configuration")
            f.policy = previous
            f.save_policy()
            self.assertEqual(fresh.policy(), previous)
        self.assertEqual(previous["original_total_cap_nano_usd"], 200_000_000_000)
        self.assertEqual(previous["original_per_model_cap_nano_usd"], 100_000_000_000)
        self.assertEqual(previous["window"], authority()["window"])
        self.assertEqual(previous["baseline"], fresh.BASELINE)

    def test_policy_rejects_any_other_effort_authorization_or_extra_author_configuration(self):
        invalid = [None, True, "high", {}, {"reasoning_effort": "max", "human_authorization": AUTHOR_AUTHORIZATION},
            {"reasoning_effort": "high", "human_authorization": "Not the human authorization"},
            {"reasoning_effort": "high", "human_authorization": AUTHOR_AUTHORIZATION, "new_budget": 1}]
        for value in invalid:
            with self.subTest(value=value):
                f = _EffortFixture(self)
                f.policy["author_configuration"] = value
                f.save_policy()
                with f.scope(), self.assertRaises(ValueError): fresh.policy()

    def test_exact_role_map_is_copied_and_only_author_changes_effort(self):
        f = _EffortFixture(self)
        before = deepcopy(f.runtime)
        with f.scope(): actual = resources.validate_role_efforts(f.runtime, f.study())
        self.assertEqual(actual, ROLE_EFFORTS)
        actual["author"] = "max"
        self.assertEqual(f.runtime, before)
        self.assertEqual(f.runtime["rates"]["effort"], "max")
        self.assertEqual(resources.role_limits()["author"],
                         {"max_input_tokens": 24000, "max_output_tokens": 49152, "wall_seconds": 900})

    def test_legacy_schema_cannot_add_role_map(self):
        f = _EffortFixture(self)
        missing = dict(f.runtime)
        missing.pop("role_efforts")
        with f.scope(), self.assertRaises(ValueError):
            resources.validate_role_efforts(missing, {})
        for schema in ("earnings_capacity_runtime_v1", "earnings_capacity_runtime_v3"):
            with self.subTest(optin_schema=schema), f.scope(), self.assertRaises(ValueError):
                resources.validate_role_efforts(dict(f.runtime, schema=schema), f.study())

    def test_map_requires_all_exact_roles_builtin_types_and_author_high_only(self):
        class DictSubclass(dict): pass
        class StrSubclass(str): pass
        invalid = [None, True, [], DictSubclass(ROLE_EFFORTS), {**ROLE_EFFORTS, "extra": "max"}]
        invalid += [{key: value for key, value in ROLE_EFFORTS.items() if key != role} for role in ROLE_EFFORTS]
        invalid += [{**ROLE_EFFORTS, role: value} for role, value in (
            ("author", "max"), ("author", "low"), ("controller", "high"), ("forecast", "high"),
            ("review", "high"), ("author", True), ("author", StrSubclass("high")))]
        for value in invalid:
            f = _EffortFixture(self)
            f.runtime["role_efforts"] = value
            with self.subTest(value=repr(value)), f.scope(), self.assertRaises(ValueError):
                resources.validate_role_efforts(f.runtime, f.study())

    def test_no_model_global_effort_or_runtime_purpose_change_can_borrow_author_optin(self):
        for change in ({"rates": {"api_model": "gpt-5.5", "effort": "max"}},
                       {"rates": {"api_model": "gpt-6.1-sol", "effort": "high"}},
                       {"purpose": "controller_protocol"}):
            f = _EffortFixture(self)
            changed = deepcopy(f.runtime)
            changed.update(change)
            with self.subTest(change=change), f.scope(), self.assertRaises(ValueError):
                resources.validate_role_efforts(changed, f.study())

    def test_missing_old_or_mismatched_grants_and_wrong_authority_factory_or_source_refuse(self):
        for kind in ("missing", "old-schema", "source-missing", "source-wrong", "factory-wrong", "policy-missing"):
            f = _EffortFixture(self)
            study = None
            if kind == "missing": study = {}
            elif kind == "old-schema": f.grant["schema"] = "earnings_open_grant_v1"
            elif kind == "source-missing": f.grant["sources"].pop(AUTHORITY_SOURCE)
            elif kind == "source-wrong": f.grant["sources"][AUTHORITY_SOURCE] = "f" * 64
            elif kind == "factory-wrong": f.runtime["sources"]["factory_author"] = engine.pin(runtime.__file__)
            else:
                f.policy.pop("author_configuration")
                f.save_policy()
                f.grant["sources"][AUTHORITY_SOURCE] = engine.pin(f.config)["sha256"]
            with self.subTest(kind=kind), f.scope(), self.assertRaises((ValueError, KeyError)):
                resources.validate_role_efforts(f.runtime, f.study() if study is None else study)
        for field in ("id", "root", "source_commit", "ledger", "baseline", "cutoff_utc", "deadline_utc", "additional_cap_nano_usd"):
            f = _EffortFixture(self)
            f.grant[field] = "DIFFERENT_SYNTHETIC_JOIN"
            with self.subTest(field=field), f.scope(), self.assertRaises(ValueError):
                resources.validate_role_efforts(f.runtime, f.study())


class AuthorEffortPhysicalGuardTests(unittest.TestCase):
    def test_author_high_and_other_role_max_mismatches_refuse_both_endpoints_before_any_send(self):
        temporary = tempfile.TemporaryDirectory(prefix="author-effort-wire-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        slots = {str(root / role): {"max_input_tokens": 10000, "max_output_tokens": 32768, "wall_seconds": 900}
                 for role in ROLE_EFFORTS}
        efforts = {str(root / role): value for role, value in ROLE_EFFORTS.items()}
        rates = {"api_model": "gpt-6.1-sol", "effort": "max", "input": "2", "cached": ".1", "write": "2.5", "output": "10"}
        checked = Mock()
        facade = runtime._OwnedHTTP(RawOpenAIHTTP("", 600), checked, slots, rates, efforts=efforts)
        for role in ROLE_EFFORTS:
            slot = root / role
            slot.mkdir()
            facade.record_prefix = slot / "http-invented-mismatch"
            wrong = "max" if role == "author" else "high"
            for endpoint in (COUNT, GENERATE):
                with self.subTest(role=role, endpoint=endpoint), \
                        patch("earnings_http.http.client.HTTPSConnection", side_effect=AssertionError("No send")), \
                        self.assertRaisesRegex(ValueError, "model|effort"):
                    facade.post(endpoint, {"model": rates["api_model"], "reasoning": {"effort": wrong}})
        checked.assert_not_called()

    def test_physical_effort_map_must_match_exact_slots_and_builtin_max_high_values(self):
        limits = {"max_input_tokens": 10000, "max_output_tokens": 32768, "wall_seconds": 900}
        slots = {"/synthetic/author": limits, "/synthetic/controller": limits}
        rates = {"api_model": "gpt-6.1-sol", "effort": "max", "input": "2", "cached": ".1", "write": "2.5", "output": "10"}
        for value in ({}, {"/synthetic/author": "high"}, {"/synthetic/author": True, "/synthetic/controller": "max"},
                      {"/synthetic/author": "low", "/synthetic/controller": "max"},
                      {"/synthetic/author": "high", "/synthetic/controller": "max", "/extra": "max"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime._OwnedHTTP(RawOpenAIHTTP("", 600), Mock(), slots, rates, efforts=value)

    def test_legacy_owner_context_and_real_controller_requests_keep_original_effort_without_optin(self):
        helper = owner_fixture.CapacityRuntimeOwnerTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        f = helper.fixture("author-effort-legacy", purpose="controller_protocol")
        before = deepcopy(f.spec)
        with f.exchange(), f.open() as owned:
            owned["roles"]["controller"](f.prompt(), f.slots["controller"][0])
        self.assertEqual(f.spec, before)
        self.assertNotIn("role_efforts", runtime.preflight_runtime(f.binding))
        self.assertEqual([payload["reasoning"] for _, payload in f.calls], [{"effort": "xhigh"}] * 2)
        self.assertEqual(f.rows()[-1][3:], (92800, "settled"))
        changed = f.save_spec(lambda spec: spec.update(role_efforts=deepcopy(ROLE_EFFORTS)))
        with self.assertRaises(ValueError): runtime.preflight_runtime(changed)


class AuthorEffortOwnerIntegrationTests(unittest.TestCase):
    def test_actual_author_high_controller_forecast_max_count_generation_and_original_accounting(self):
        helper = assembly_fixture.OpenAssemblyTests()
        self.addCleanup(helper.doCleanups)
        f = helper.fixture()
        config = f.home / "invented-effort-authority.json"
        policy = authority()
        config.write_text(json.dumps(policy))
        cutoff, deadline = (policy["window"][key] for key in ("cutoff_utc", "deadline_utc"))
        original_rates = deepcopy(f.runtime["rates"])
        self.assertEqual(original_rates["effort"], "max")
        f.runtime.update(role_efforts=deepcopy(ROLE_EFFORTS), cutoff_utc=cutoff, deadline_utc=deadline)
        f.runtime["limits"].update(resources.role_limits())
        f.envelope["role_limits"] = resources.role_limits()
        f.envelope["window"] = {"cutoff_utc": cutoff, "deadline_utc": deadline}
        f.native["batch_config"]["deadline_utc"] = deadline
        grant = engine.read(f.envelope["grant"])
        grant.update(schema=fresh.SCHEMA, cutoff_utc=cutoff, deadline_utc=deadline)
        grant["sources"] = {**grant["sources"], AUTHORITY_SOURCE: engine.pin(config)["sha256"]}
        f.envelope["sources"] = deepcopy(grant["sources"])
        f.envelope["grant"] = f.save("invented-high-grant", grant)
        study = engine.read(f.envelope["study"])
        study["new_live_grant"] = f.envelope["grant"]
        f.envelope["study"] = f.save("high-study", study)
        f.runtime["forecast_study"] = f.envelope["study"]
        f.runtime_binding = f.save("high-runtime", f.runtime)
        f.episode_binding = f.save("high-episode", f.envelope)
        f.plan["episode"] = f.episode_binding
        baseline = f.native["baseline"]
        f.native["micro_config"]["fixed_context"] = {"model_sha256": baseline["M"], "evaluation_sha256": baseline["K"],
            "data_scope_sha256": digest({"study": f.envelope["study"], "cik": f.envelope["cik"], "kernel": f.envelope["evaluation_kernel"]}),
            "authority_sha256": digest({key: f.envelope[key] for key in ("mode", "grant", "window")}),
            "resource_policy_sha256": digest(f.runtime_binding)}
        transport_policy = engine.read(f.assembly["transport_policy"])
        transport_policy.update(schema="edgar_foreground_role_socket_policy_v1",
            author_socket_timeout_seconds=900, author_reasoning_effort="high")
        f.assembly.update(episode=f.episode_binding, runtime=f.runtime_binding, native=f.save("high-native", f.native),
            matched_plan=f.save("high-plan", f.plan), transport_policy=f.save("high-transport", transport_policy))
        review = engine.read(f.assembly["independent_review"])
        review.update(reviewed_sources=grant["sources"], episode=f.episode_binding,
            reviewed_configuration_sha256=digest({key: value for key, value in f.assembly.items() if key != "independent_review"}))
        f.assembly["independent_review"] = f.save("high-fixture-review", review)
        f.assembly_binding = f.save("high-assembly", f.assembly)
        limits, window, ledger_before = deepcopy(f.runtime["limits"]), deepcopy(f.envelope["window"]), f.ledger_rows()
        sequence = [f.raw.research(), f.raw.final(), helper.choose(f, "H"), lambda p: helper.author(f, p),
            lambda p: helper.research(f, p), f.raw.final(), lambda p: helper.research(f, p), f.raw.final(),
            lambda p: helper.research(f, p), f.raw.final(), helper.choose(f, "continue")]
        with helper.scope(f), patch.object(fresh, "CONFIG", config), f.exchange(sequence):
            result = engine.read(assembly.run(f.episode_binding, f.assembly_binding))
        self.assertEqual(result["outcome"]["completed_rounds"], 2)
        for role, expected in ROLE_EFFORTS.items():
            context = engine.read(engine.pin(f.root / f"context-{role}.json"))
            self.assertEqual(context["rates"], dict(original_rates, effort=expected))
            self.assertEqual(context["limits"], limits[role])
            self.assertEqual(context["cutoff_utc"], cutoff)
        observed = {"author": set(), "controller": set(), "forecast": set()}
        for intent_path in (f.root / "roles").glob("*/http-*.intent.json"):
            intent = engine.read(engine.pin(intent_path))
            role = next((name for name in observed if intent_path.parent.name.startswith(name + "-")), None)
            if role is None or intent["endpoint"] not in (COUNT, GENERATE): continue
            payload = intent["payload"]
            self.assertEqual(payload["model"], original_rates["api_model"])
            self.assertEqual(payload["reasoning"], {"effort": ROLE_EFFORTS[role]})
            observed[role].add(intent["endpoint"])
            if intent["endpoint"] == GENERATE:
                self.assertLessEqual(payload["max_output_tokens"], limits[role]["max_output_tokens"])
        self.assertEqual(observed, {role: {COUNT, GENERATE} for role in observed})
        self.assertEqual(f.runtime["rates"], original_rates)
        self.assertEqual(f.runtime["limits"], limits)
        self.assertEqual(f.envelope["window"], window)
        self.assertEqual(f.ledger_rows()[:len(ledger_before)], ledger_before)
        self.assertTrue(all(row[4] == "settled" for row in f.ledger_rows()))
        self.assertEqual(result["outcome"]["result"]["feedback"]["observation"]["prediction"]["score_out_of_5"], 5)


if __name__ == "__main__": unittest.main()
