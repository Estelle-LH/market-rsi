"""Inert admission fixtures; all authority, company and accounting are invented.

No real grant, protected QA, ledger, provider, Git process or Docker is used.
Existing fixture classes are imported via modules, not discoverable subclasses.
"""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch

import earnings_open_admission as admission
import earnings_open_assembly as assembly
from earnings_research_state import ResearchState
import test_earnings_live_admission as old_fixtures
import test_earnings_open_assembly as assembly_fixtures


class InventedOpenAdmission:
    def __init__(self, owner):
        self.base = f = old_fixtures.AdmissionFixture(owner)
        self.open_root = f.home / "invented-open-artifacts"
        f.run_id = "edgar-open-20261014-99"
        f.root = self.open_root / "attempts" / f.run_id
        with sqlite3.connect(f.ledger) as db:
            db.execute("UPDATE requests SET model='gpt-5',reserved=?,charged=?",
                       (admission.BASELINE_CHARGED, admission.BASELINE_CHARGED))
            db.executemany("INSERT INTO requests VALUES (?,'gpt-6.1-sol',0,0,'settled')",
                [(f"invented-prefix-{i}",) for i in range(1, admission.BASELINE_ROWS)])
            baseline = admission.history_snapshot(db, admission.BASELINE_ROWS)
        f.grant.update(schema="earnings_open_grant_v1", id=f.run_id, root=str(f.root),
            baseline=baseline, additional_cap_nano_usd=admission.PILOT_CAP,
            **admission.PILOT_WINDOW,
            human_authorization=admission.AUTHORIZATION, allowed_egress=deepcopy(admission.EGRESS))
        f.envelope.update(schema=admission.SCHEMA, id=f.run_id, root=str(f.root), max_rounds=2,
            role_limits=admission.role_limits(),
            window=deepcopy(admission.PILOT_WINDOW),
            slots=[{role: str(f.root / "roles" / f"{role}-{i:02d}")
                    for role in ("controller", "author", "review", "forecast")} for i in (1, 2)])
        f.state = ResearchState(f.company, f.run_id)
        f.envelope["initial_state"] = f.state.save(f.home / "invented-open-state", f.state.empty())
        f.envelope["grant"] = f.save(f.grant, "invented-open-grant-not-authority")
        self.no_key = Mock(side_effect=AssertionError("No credentials in admission"))
        self.no_provider = Mock(side_effect=AssertionError("No provider in admission"))

    @contextmanager
    def scope(self):
        f = self.base
        with ExitStack() as stack:
            for mock in (
                patch.object(admission, "ROOT", self.open_root),
                patch.object(admission, "sources", return_value=[f.source_name]),
                patch.object(admission, "_COMMITTED", set()),
                patch.object(admission.e, "REPO", f.repo),
                patch.object(admission.e, "PILOT", f.pilot),
                patch.object(admission.original, "task", f.task),
                patch.object(admission.subprocess, "run", f.git),
                patch.object(admission.original.original, "pin", return_value=f.python),
                patch.object(admission.e, "credential", self.no_key),
                patch.object(admission.e, "RawOpenAIHTTP", self.no_provider),
            ):
                stack.enter_context(mock)
            yield
        self.no_key.assert_not_called()
        self.no_provider.assert_not_called()


class OpenAdmissionBoundaryTests(unittest.TestCase):
    def fixture(self):
        return InventedOpenAdmission(self)

    def refuse(self, owned, envelope):
        f = owned.base
        before = f.snapshot()
        with owned.scope(), self.assertRaises((ValueError, TypeError, KeyError, OSError)):
            admission.admit(envelope)
        self.assertEqual(f.snapshot(), before)
        self.assertFalse(f.root.exists())

    def test_valid_invented_admission_reads_only_its_temporary_ledger(self):
        owned = self.fixture()
        f = owned.base
        before = f.snapshot()
        with owned.scope():
            company, state = admission.admit(f.envelope)
        self.assertEqual(company, f.company)
        self.assertEqual(state.empty(), f.state.empty())
        self.assertEqual(f.snapshot(), before)
        self.assertFalse(f.root.exists())
        f.git.assert_called_once()
        f.task.assert_called_once_with(f.grant)

    def test_wrong_schema_mode_rounds_or_extra_fields_cannot_open_authority(self):
        owned = self.fixture()
        f = owned.base
        for change in ({"schema": "earnings_capacity_episode_v3"}, {"mode": "offline_replay"},
                       {"max_rounds": True}, {"max_rounds": 3}, {"unreviewed": "tool"}):
            with self.subTest(change=change):
                self.refuse(owned, dict(deepcopy(f.envelope), **change))
        self.assertEqual(f.git.call_count, 0)
        self.assertEqual(f.task.call_count, 0)

    def test_old_grant_and_old_human_scope_cannot_be_reopened(self):
        owned = self.fixture()
        f = owned.base
        for change in ({"schema": "earnings_real_rh_grant_v1"},
                       {"id": "edgar-real-rh-20261014-02"},
                       {"human_authorization": admission.original.AUTHORIZATION},
                       {"allowed_egress": deepcopy(admission.original.EGRESS)},
                       {"bootstrap_no_model_call": False}):
            with self.subTest(change=change):
                self.refuse(owned, f.grant_envelope(change))
        self.assertEqual(f.git.call_count, 0)

    def test_pilot_ceiling_and_original_prefix_cannot_be_rebased(self):
        owned = self.fixture()
        f = owned.base
        self.assertEqual((admission.BASELINE_ROWS, admission.BASELINE_CHARGED, admission.PILOT_CAP),
                         (4111, 133_562_557_700, 6_500_000_000))
        for change in ({"additional_cap_nano_usd": 10_000_000_000},
                       {"additional_cap_nano_usd": True},
                       {"baseline": dict(f.grant["baseline"], charged_nano_usd=0)},
                       {"baseline": dict(f.grant["baseline"], request_count=0)},
                       {"baseline": dict(f.grant["baseline"], max_rowid=1)},
                       {"baseline": dict(f.grant["baseline"], rows_sha256="0" * 64)}):
            with self.subTest(change=change):
                self.refuse(owned, f.grant_envelope(change))

    def test_fresh_attempt_cannot_extend_original_pilot_window(self):
        owned=self.fixture();f=owned.base
        self.refuse(owned,f.grant_envelope({'cutoff_utc':'2026-10-15T01:20:32Z',
            'deadline_utc':'2026-10-15T01:21:32Z'}))
        self.assertEqual(f.git.call_count,0)

    def test_original_total_and_model_caps_and_history_are_checked_again(self):
        for sql in ("UPDATE config SET cap=201000000000", "UPDATE config SET model_cap=101000000000",
                    "UPDATE config SET blocked=1", "UPDATE requests SET charged=charged+1 WHERE rowid=1"):
            owned = self.fixture()
            f = owned.base
            with sqlite3.connect(f.ledger) as db:
                db.execute(sql)
            with self.subTest(sql=sql):
                self.refuse(owned, f.envelope)

    def test_newer_current_baseline_cannot_refund_open_pilot_spending(self):
        owned = self.fixture()
        f = owned.base
        with sqlite3.connect(f.ledger) as db:
            db.execute("INSERT INTO requests VALUES ('invented-later-cost','gpt-6.1-sol',100,100,'settled')")
            newer = admission.history_snapshot(db)
        self.refuse(owned, f.grant_envelope({"baseline": newer}))

    def test_duplicate_aliased_and_external_ordinary_slots_are_denied(self):
        owned = self.fixture()
        f = owned.base
        for kind in ("duplicate", "slash-alias", "outside", "symlink"):
            envelope = deepcopy(f.envelope)
            if kind == "duplicate":
                envelope["slots"][1]["author"] = envelope["slots"][0]["author"]
            elif kind == "slash-alias":
                envelope["slots"][0]["controller"] = str(f.root / "roles") + "//controller-01"
            elif kind == "outside":
                envelope["slots"][0]["controller"] = str(f.home / "outside")
            else:
                target = f.home / "invented-alias-target"
                target.mkdir()
                alias = f.home / "invented-alias"
                alias.symlink_to(target, target_is_directory=True)
                envelope["slots"][0]["controller"] = str(alias / "controller-01")
            with self.subTest(kind=kind):
                self.refuse(owned, envelope)

    def test_source_closure_contains_guest_and_reused_docker_dependency(self):
        actual = set(admission.sources())
        self.assertTrue({"tools/earnings_open_code.py", "tools/earnings_open_guest.py",
            "research/market_rsi/minimal_prediction_loop/container_adapter.py",
            "research/market_rsi/minimal_prediction_loop/prediction_protocol.py",
            "research/market_rsi/supervisor_harness/local_b_container.py"}.issubset(actual))
        owned = self.fixture()
        f = owned.base
        required = "research/market_rsi/supervisor_harness/local_b_container.py"
        # Invented source closure is deliberately missing one required entry;
        # refusal occurs before Git retrieval, real task or any owner.
        with owned.scope(), patch.object(admission, "sources", return_value=[f.source_name, required]), \
                self.assertRaises(ValueError):
            admission.admit(f.envelope)
        self.assertEqual(f.git.call_count, 0)


class OpenSlotBoundaryTests(unittest.TestCase):
    def fixture(self):
        owned = InventedOpenAdmission(self)
        envelope = deepcopy(owned.base.envelope)
        matched = {"schema": "earnings_matched_plan_v1", "episode": {"invented": "binding only"},
            "rounds": [{"parent": str(owned.base.root / "roles" / f"parent-{i:02d}"),
                "candidate": str(owned.base.root / "roles" / f"candidate-{i:02d}"),
                "downstream": row["forecast"]} for i, row in enumerate(envelope["slots"], 1)]}
        return owned, envelope, matched

    def test_exact_terminal_slot_is_in_same_unique_declared_role_set(self):
        owned, envelope, matched = self.fixture()
        value = admission.slots(envelope, matched)
        self.assertEqual(value["controller"][-1], str(owned.base.root / "roles" / "controller-terminal"))
        self.assertEqual(len(value["controller"]), 3)
        self.assertEqual(len(value["forecast"]), 6)
        self.assertFalse(owned.base.root.exists())

    def test_terminal_duplicate_and_lexical_alias_cannot_hide_collisions(self):
        for kind in ("terminal", "duplicate", "slash-alias", "alias-hidden-duplicate", "outside"):
            owned, envelope, matched = self.fixture()
            if kind == "terminal":
                matched["rounds"][0]["parent"] = str(owned.base.root / "roles" / "controller-terminal")
            elif kind == "duplicate":
                matched["rounds"][1]["parent"] = matched["rounds"][0]["parent"]
            elif kind == "outside":
                matched["rounds"][0]["parent"] = str(owned.base.home / "outside")
            else:
                original = matched["rounds"][0]["parent"]
                altered = original.replace("/roles/", "/roles//")
                matched["rounds"][0 if kind == "slash-alias" else 1]["parent"] = altered
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                admission.slots(envelope, matched)

    def test_short_extra_or_malformed_rows_cannot_be_silently_zipped(self):
        unused, envelope, matched = self.fixture()
        variants = [(dict(envelope, slots=envelope["slots"][:1]), matched),
            (dict(envelope, slots=envelope["slots"] + [deepcopy(envelope["slots"][0])]), matched),
            (envelope, dict(matched, schema="old-matched-plan")),
            (envelope, dict(matched, rounds=matched["rounds"][:1]))]
        for changed, plan in variants:
            with self.assertRaises(ValueError):
                admission.slots(changed, plan)


class OpenAssemblyAdmissionBoundaryTests(unittest.TestCase):
    def fixture(self):
        helper = assembly_fixtures.OpenAssemblyTests()
        self.addCleanup(helper.doCleanups)
        return helper, helper.fixture()

    def refused_before_owner(self, helper, f, assembly_binding):
        before = f.retained_tree()
        with helper.scope(f), \
                patch.object(assembly, "open_capacity_runtime", side_effect=AssertionError("No owner before validation")) as owner, \
                patch.object(assembly, "DockerRunner", side_effect=AssertionError("No Docker before validation")) as docker, \
                self.assertRaises((ValueError, TypeError, KeyError, OSError)):
            assembly.run(f.episode_binding, assembly_binding)
        owner.assert_not_called()
        docker.assert_not_called()
        self.assertEqual(f.retained_tree(), before)
        self.assertFalse(f.paths["batch_root"].exists())
        self.assertFalse(f.paths["registry_root"].exists())
        self.assertEqual(f.factory_calls, 0)

    def test_exact_distinct_review_validation_is_read_only_before_owner(self):
        helper, f = self.fixture()
        before = f.retained_tree()
        with helper.scope(f), patch.object(assembly, "open_capacity_runtime") as owner:
            envelope, unused, native, unused_review = assembly.validate(f.episode_binding, f.assembly_binding)
        self.assertEqual(envelope, f.envelope)
        self.assertEqual(native, f.native)
        self.assertEqual(f.retained_tree(), before)
        owner.assert_not_called()
        self.assertEqual(f.factory_calls, 0)

    def test_missing_root_wrong_source_or_wrong_episode_review_is_denied_before_owner(self):
        helper, f = self.fixture()
        original = assembly.read(f.assembly["independent_review"])
        reviews = [None, dict(original, reviewer="Root"), dict(original, verdict="PASS_SOURCE_ONLY"),
            dict(original, blocking_findings=["unresolved"]), dict(original, reviewed_sources={}),
            dict(original, episode={"path": "other-episode", "sha256": "0" * 64})]
        for index, review in enumerate(reviews):
            value = deepcopy(f.assembly)
            value["independent_review"] = None if review is None else f.save(f"invalid-review-{index}", review)
            binding = f.save(f"invalid-assembly-{index}", value)
            with self.subTest(index=index):
                self.refused_before_owner(helper, f, binding)

    def test_existing_terminal_slot_is_denied_before_creating_episode_or_owner(self):
        helper, f = self.fixture()
        terminal = Path(f.runtime["slots"]["controller"][-1])
        terminal.mkdir(parents=True)
        (terminal / "preserved-attempt.txt").write_text("Invented consumed terminal output; never delete")
        before = f.retained_tree()
        with helper.scope(f), patch.object(assembly, "open_capacity_runtime") as owner, self.assertRaises(ValueError):
            assembly.validate(f.episode_binding, f.assembly_binding)
        owner.assert_not_called()
        self.assertEqual(f.retained_tree(), before)

    def test_runtime_cap_or_baseline_drift_cannot_reset_admitted_resources(self):
        helper, f = self.fixture()
        for field, value in (("additional_cap_nano_usd", f.runtime["additional_cap_nano_usd"] + 1),
                             ("baseline", dict(f.runtime["baseline"], charged_nano_usd=0))):
            runtime = dict(deepcopy(f.runtime), **{field: value})
            updated = dict(deepcopy(f.assembly), runtime=f.save("runtime-reset-not-authority", runtime))
            binding = f.save("assembly-resource-reset", updated)
            with self.subTest(field=field):
                self.refused_before_owner(helper, f, binding)

    def test_consumed_runtime_id_remains_closed_before_any_owner(self):
        helper, f = self.fixture()
        name = hashlib.sha256(f.envelope["id"].encode()).hexdigest() + ".result.json"
        closed = Path(f.runtime["ledger"]).parent / ".capacity-runtime-claims" / name
        closed.parent.mkdir(parents=True)
        closed.write_text('{"fixture":"closed original remains immutable"}')
        self.refused_before_owner(helper, f, f.assembly_binding)


if __name__ == "__main__":
    unittest.main()
