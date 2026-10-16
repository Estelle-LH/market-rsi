"""Static real-capacity admission on owned, entirely invented fixtures.

The original financial task admission is an explicit stand-in, and Git/Python
anchors are scripted. State/file/SQLite/hash and study/envelope validation use
the real helper. No real company data, protected QA, credentials or paid ledger
are read; admission itself has no provider dispatch. Time freshness belongs to
the owner, not this static validator.
"""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_live_capacity as live
from earnings_research_state import ResearchState

DEFAULT = object()


class AdmissionFixture:
    def __init__(self, case):
        temporary = tempfile.TemporaryDirectory(prefix="earnings-live-admission-synthetic-")
        case.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.repo = self.home / "source"
        self.repo.mkdir()
        self.source_name = "tools/earnings_live_capacity.py"
        self.source_path = self.repo / self.source_name
        self.source_path.parent.mkdir()
        self.source_bytes = b"synthetic public source commitment; never executed\n"
        self.source_path.write_bytes(self.source_bytes)
        self.pilot = self.home / "invented-pilot"
        self.pilot.mkdir()
        self.run_root = self.home / "invented-attempts"
        self.run_id = "edgar-real-rh-20261014-01"
        self.root = self.run_root / self.run_id
        self.visible = self.home / "invented-visible"
        self.visible.mkdir()
        files = {"questions.md": "\n".join(f"### T{i:03d} | Invented target" for i in range(1, 6)),
                 "filing_index.tsv": "date_filed\tform_type\taccession\tpath\n"}
        self.company = {"cik": "CIK0000003545", "cutoff": "2026-02-01",
                        "target_accession": "invented-hidden-target", "visible_root": str(self.visible),
                        "allowed_files": []}
        for name, text in files.items():
            data = text.encode()
            (self.visible / name).write_bytes(data)
            self.company["allowed_files"].append(
                {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        self.runtime = {"request_timeout_seconds": 180, "max_turns_per_company": 2,
                        "max_input_tokens": 100000, "max_output_tokens": 25000,
                        "company_wall_seconds": 1800,
                        "models": {"gpt-6.1-sol": deepcopy(live.original.RATE)}}
        self.serial = 0
        self.python = self.save({"synthetic": "Python commitment only"}, "python-anchor")
        self.ledger = self.pilot / "api-budget.sqlite3"
        with sqlite3.connect(self.ledger) as db:
            db.execute("CREATE TABLE config (id INTEGER PRIMARY KEY, cap INTEGER, model_cap INTEGER, blocked INTEGER)")
            db.execute("CREATE TABLE requests (id TEXT PRIMARY KEY, model TEXT, reserved INTEGER, charged INTEGER, status TEXT)")
            db.execute("INSERT INTO config VALUES (1,200000000000,100000000000,0)")
            db.execute("INSERT INTO requests VALUES ('invented-prior','gpt-6.1-sol',1000,1000,'settled')")
        with sqlite3.connect(self.ledger) as db:
            baseline = live.history_snapshot(db)
        cutoff = datetime(2026, 10, 14, 23, 0, tzinfo=timezone.utc)
        self.grant = {"schema": "earnings_real_rh_grant_v1", "id": self.run_id,
            "root": str(self.root), "source_commit": "b" * 40,
            "sources": {self.source_name: hashlib.sha256(self.source_bytes).hexdigest()},
            "python": self.python, "data": self.save({"invented": "public plan"}, "plan"),
            "runtime": self.save(self.runtime, "original-runtime"),
            "scorer": self.save({"invented": "host scorer commitment"}, "scorer"),
            "qa": self.save({"invented": "not real answers"}, "qa"),
            "cik": self.company["cik"], "ledger": str(self.ledger), "baseline": baseline,
            "cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
            "deadline_utc": (cutoff + timedelta(seconds=45)).isoformat().replace("+00:00", "Z"),
            "additional_cap_nano_usd": 10000000000, "human_authorization": live.AUTHORIZATION,
            "allowed_egress": deepcopy(live.EGRESS), "bootstrap_no_model_call": True}
        kernel = {name: deepcopy(self.grant[name]) for name in ("scorer", "qa")}
        expected_case = {name: self.company[name] for name in ("cik", "cutoff", "target_accession", "visible_root")}
        expected_case.update(evaluation_kernel=deepcopy(kernel), allowed_manifest_sha256=live.e.digest(
            json.dumps(self.company["allowed_files"], sort_keys=True, separators=(",", ":")).encode()))
        self.prior = {"schema": "original_runtime_snapshot_v1", "source": self.grant["runtime"],
                      "config": deepcopy(self.runtime)}
        self.study = {"schema": "earnings_coevolution_study_v1", "data": self.grant["data"],
            "scorer": self.grant["scorer"], "runtime_config": deepcopy(self.runtime), "python": self.python,
            "sole_ledger": str(self.ledger), "cases": [expected_case],
            "model": {"requested_model": "gpt-6.1-sol", "serving_snapshot": "unknown",
                      "serving_snapshot_verified": False}, "prior_batch": self.save(self.prior, "prior-runtime")}
        self.state = ResearchState(self.company, self.run_id)
        empty_state = self.state.save(self.home / "invented-states", self.state.empty())
        self.envelope = {"schema": live.SCHEMA, "id": self.run_id, "mode": "real_provider",
            "source_commit": self.grant["source_commit"], "sources": deepcopy(self.grant["sources"]),
            "study": self.save(self.study, "study"), "root": str(self.root), "cik": self.company["cik"],
            "max_rounds": 3, "role_limits": {name: deepcopy(live.policy.LIMITS)
                for name in ("controller", "author", "review")},
            "slots": [{name: str(self.root / "roles" / f"{name}-{index:02d}")
                for name in ("controller", "author", "review", "forecast")} for index in range(1, 4)],
            "initial_state": empty_state, "grant": self.save(self.grant, "grant"),
            "window": {name: self.grant[name] for name in ("cutoff_utc", "deadline_utc")},
            "evaluation_kernel": kernel}
        self.git = Mock(return_value=SimpleNamespace(stdout=self.source_bytes))
        self.task = Mock(return_value=(self.company, self.runtime))
        self.credentials = Mock(side_effect=AssertionError("Admission must not load credentials"))
        self.provider = Mock(side_effect=AssertionError("Admission must not instantiate a provider"))

    def save(self, value, name):
        self.serial += 1
        path = self.home / (name + f"-{self.serial:02d}.json")
        data = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()
        path.write_bytes(data)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    def grant_envelope(self, changes, *, mirror=True):
        grant, envelope = deepcopy(self.grant), deepcopy(self.envelope)
        grant.update(changes)
        envelope["grant"] = self.save(grant, "modified-grant")
        if mirror:
            for field in ("id", "root", "source_commit", "sources", "cik"):
                envelope[field] = deepcopy(grant[field])
            envelope["window"] = {name: grant[name] for name in ("cutoff_utc", "deadline_utc")}
        return envelope

    def study_envelope(self, changes):
        study, envelope = deepcopy(self.study), deepcopy(self.envelope)
        study.update(changes)
        envelope["study"] = self.save(study, "modified-study")
        return envelope

    def snapshot(self):
        return {str(path.relative_to(self.home)): ("symlink", str(path.readlink()))
                if path.is_symlink() else ("bytes", path.read_bytes())
                for path in self.home.rglob("*") if path.is_file() or path.is_symlink()}

    @contextmanager
    def admitted_anchors(self):
        # Deliberate, named stand-ins: no claim of actual financial admission,
        # committed-source retrieval or the production Python binary identity.
        with ExitStack() as stack:
            for mocked in (
                patch.object(live, "ROOT", self.run_root),
                patch.object(live, "sources", return_value=[self.source_name]),
                patch.object(live.e, "REPO", self.repo), patch.object(live.e, "PILOT", self.pilot),
                patch.object(live, "task", self.task), patch.object(live.subprocess, "run", self.git),
                patch.object(live.original, "pin", return_value=self.python),
                patch.object(live.e, "credential", self.credentials),
                patch.object(live.original, "RawOpenAIHTTP", self.provider),
            ):
                stack.enter_context(mocked)
            yield
        self.credentials.assert_not_called()
        self.provider.assert_not_called()


class LiveAdmissionTests(unittest.TestCase):
    def fixture(self):
        return AdmissionFixture(self)

    def test_cached_Git_commit_never_caches_working_bytes_or_authority(self):
        fixture=self.fixture()
        with fixture.admitted_anchors():
            live.admit(fixture.envelope)
            live.admit(fixture.envelope)
            self.assertEqual(fixture.git.call_count,1)
            fixture.source_path.write_bytes(b'changed actual source')
            with self.assertRaises(ValueError): live.admit(fixture.envelope)
            fixture.source_path.write_bytes(fixture.source_bytes)
            with self.assertRaises(ValueError):
                live.admit(fixture.grant_envelope({'human_authorization':'not approved'}))

    def test_cached_Git_commit_still_checks_ledger_prefix(self):
        fixture=self.fixture()
        with fixture.admitted_anchors():
            live.admit(fixture.envelope)
            with sqlite3.connect(fixture.ledger) as db: db.execute('UPDATE requests SET charged=2')
            with self.assertRaises(ValueError): live.admit(fixture.envelope)

    def refused(self, fixture, envelope=DEFAULT):
        before = fixture.snapshot()
        with fixture.admitted_anchors():
            with self.assertRaises((ValueError, FileNotFoundError, KeyError, TypeError)):
                live.admit(fixture.envelope if envelope is DEFAULT else envelope)
        self.assertEqual(fixture.snapshot(), before)
        self.assertFalse(fixture.root.exists())

    def test_exact_v3_real_provider_admission_is_read_only_and_no_send(self):
        fixture = self.fixture()
        envelope = deepcopy(fixture.envelope)
        before = fixture.snapshot()
        with fixture.admitted_anchors():
            company, state = live.admit(envelope)
        self.assertEqual(company, fixture.company)
        self.assertEqual(state.empty(), fixture.state.empty())
        self.assertEqual(envelope, fixture.envelope)
        self.assertEqual(fixture.snapshot(), before)
        self.assertFalse(fixture.root.exists())
        fixture.git.assert_called_once_with(["git", "show", "b" * 40 + ":" + fixture.source_name],
                                            cwd=fixture.repo, check=True, capture_output=True)
        fixture.task.assert_called_once_with(fixture.grant)

    def test_schema_mode_exact_fields_and_three_rounds_required(self):
        fixture = self.fixture()
        bad = [None, [], dict(fixture.envelope, schema="earnings_capacity_episode_v2"),
               dict(fixture.envelope, mode="offline_replay"), dict(fixture.envelope, mode="REAL_PROVIDER"),
               dict(fixture.envelope, max_rounds=2), dict(fixture.envelope, max_rounds=True),
               dict(fixture.envelope, max_rounds=3.0), dict(fixture.envelope, client_factory="not allowed")]
        missing = deepcopy(fixture.envelope); missing.pop("grant"); bad.append(missing)
        for index, envelope in enumerate(bad):
            with self.subTest(index=index):
                self.refused(fixture, envelope)

    def test_exact_authorization_egress_and_no_model_bootstrap_required(self):
        fixture = self.fixture()
        for field, value in (("human_authorization", live.AUTHORIZATION + " broaden scope"),
                             ("human_authorization", "approved"),
                             ("allowed_egress", list(reversed(live.EGRESS))),
                             ("allowed_egress", live.EGRESS + ["protected_answers"]),
                             ("bootstrap_no_model_call", False), ("bootstrap_no_model_call", 1),
                             ("schema", "earnings_real_rh_grant_v0")):
            with self.subTest(field=field, value=value):
                self.refused(fixture, fixture.grant_envelope({field: value}))

    def test_exact_integer_role_limits_cannot_use_equal_floats_or_bool(self):
        fixture = self.fixture()
        for role in ("controller", "author", "review"):
            for field in live.policy.LIMITS:
                envelope = deepcopy(fixture.envelope)
                envelope["role_limits"][role][field] = float(live.policy.LIMITS[field])
                with self.subTest(role=role, field=field):
                    self.refused(fixture, envelope)
        for value in (None, {}, {"controller": deepcopy(live.policy.LIMITS)}):
            envelope = deepcopy(fixture.envelope); envelope["role_limits"] = value
            self.refused(fixture, envelope)
        envelope = deepcopy(fixture.envelope)
        envelope["role_limits"]["controller"]["wall_seconds"] = True
        self.refused(fixture, envelope)

    def test_grant_missing_or_extra_field_and_bad_binding_denied(self):
        fixture = self.fixture()
        for grant in ({}, dict(fixture.grant, model="gpt-other")):
            envelope = deepcopy(fixture.envelope); envelope["grant"] = fixture.save(grant, "bad-grant")
            self.refused(fixture, envelope)
        envelope = deepcopy(fixture.envelope); envelope["grant"]["sha256"] = "c" * 64
        self.refused(fixture, envelope)

    def test_positive_integer_downward_budget_ceiling_and_not_over_USD10(self):
        fixture = self.fixture()
        for amount in (1, 5000000000, 10000000000):
            with self.subTest(valid=amount), fixture.admitted_anchors():
                live.admit(fixture.grant_envelope({"additional_cap_nano_usd": amount}))
        for amount in (0, -1, 10000000001, 10000000000.0, True, "10000000000", None):
            with self.subTest(invalid=amount):
                self.refused(fixture, fixture.grant_envelope({"additional_cap_nano_usd": amount}))

    def test_new_ID_namespace_root_binding_and_canonical_paths(self):
        fixture = self.fixture()
        for changes in ({"id": "edgar-real-feedback-20261014-02"},
                        {"id": "edgar-real-rh-20261014-1"},
                        {"id": "edgar-real-rh-20261014-001"},
                        {"root": str(fixture.run_root / "unbound-old-id")},
                        {"root": str(fixture.root / ".." / fixture.run_id)}):
            with self.subTest(changes=changes):
                self.refused(fixture, fixture.grant_envelope(changes))
        envelope = deepcopy(fixture.envelope); envelope["id"] = "edgar-real-rh-20261014-02"
        self.refused(fixture, envelope)

    def test_envelope_grant_source_and_case_bindings_cannot_disagree(self):
        fixture = self.fixture()
        for field, value in (("source_commit", "c" * 40), ("sources", {}), ("cik", "invented-other")):
            with self.subTest(field=field):
                envelope = deepcopy(fixture.envelope); envelope[field] = value
                self.refused(fixture, envelope)

    def test_source_closure_hash_working_bytes_and_committed_bytes_required(self):
        fixture = self.fixture()
        for changes in ({"sources": {}}, {"sources": {fixture.source_name: "c" * 64}},
                        {"source_commit": "B" * 40}, {"source_commit": "b" * 39}):
            with self.subTest(changes=changes):
                self.refused(fixture, fixture.grant_envelope(changes))
        fixture.git.return_value = SimpleNamespace(stdout=b"different committed source\n")
        self.refused(fixture)
        fixture.git.return_value = SimpleNamespace(stdout=fixture.source_bytes)
        fixture.source_path.write_bytes(b"different working source\n")
        self.refused(fixture)

    def test_exact_existing_python_binding_required(self):
        fixture = self.fixture()
        binding = dict(fixture.python, sha256="c" * 64)
        self.refused(fixture, fixture.grant_envelope({"python": binding}))

    def test_original_financial_task_admission_refusal_propagates_without_provider(self):
        fixture = self.fixture()
        fixture.task.side_effect = ValueError("Synthetic stand-in: original task binding changed")
        self.refused(fixture)
        fixture.task.assert_called_once_with(fixture.grant)

    def test_original_runtime_snapshot_study_not_old_xhigh_model(self):
        fixture = self.fixture()
        changed = deepcopy(fixture.runtime); changed["models"]["gpt-6.1-sol"]["effort"] = "xhigh"
        self.refused(fixture, fixture.study_envelope({"runtime_config": changed}))
        for model in ({"requested_model": "gpt-5.5", "serving_snapshot": "unknown", "serving_snapshot_verified": False},
                      {"requested_model": "gpt-6.1-sol", "serving_snapshot": "invented", "serving_snapshot_verified": True}):
            self.refused(fixture, fixture.study_envelope({"model": model}))
        prior = dict(fixture.prior, config=changed)
        self.refused(fixture, fixture.study_envelope({"prior_batch": fixture.save(prior, "old-xhigh-snapshot")}))
        prior = dict(fixture.prior, source=dict(fixture.grant["runtime"], sha256="c" * 64))
        self.refused(fixture, fixture.study_envelope({"prior_batch": fixture.save(prior, "wrong-runtime-source")}))

    def test_study_fixed_data_scorer_python_ledger_case_and_kernel(self):
        fixture = self.fixture()
        for field, value in (("schema", "wrong-study"), ("data", dict(fixture.grant["data"], sha256="c" * 64)),
                             ("scorer", dict(fixture.grant["scorer"], sha256="c" * 64)),
                             ("python", dict(fixture.python, sha256="c" * 64)),
                             ("sole_ledger", str(fixture.home / "new-budget.sqlite3")), ("cases", [])):
            with self.subTest(field=field):
                self.refused(fixture, fixture.study_envelope({field: value}))
        case = deepcopy(fixture.study["cases"][0]); case["cutoff"] = "2026-02-02"
        self.refused(fixture, fixture.study_envelope({"cases": [case]}))
        envelope = deepcopy(fixture.envelope)
        envelope["evaluation_kernel"]["scorer"]["sha256"] = "c" * 64
        self.refused(fixture, envelope)
        envelope = deepcopy(fixture.envelope); envelope["evaluation_kernel"]["qa"]["sha256"] = "c" * 64
        self.refused(fixture, envelope)

    def test_fresh_empty_state_identity_and_canonical_hash_required(self):
        fixture = self.fixture()
        state = fixture.state.append(fixture.state.empty(), {"kind": "assumption", "hypothesis": "Invented prior note"})
        envelope = deepcopy(fixture.envelope)
        envelope["initial_state"] = fixture.state.save(fixture.home / "invented-nonempty-state", state)
        self.refused(fixture, envelope)
        state = fixture.state.empty(); state["task_id"] = "old-episode"
        envelope["initial_state"] = fixture.save(state, "wrong-task-state")
        self.refused(fixture, envelope)
        envelope = deepcopy(fixture.envelope); envelope["initial_state"]["sha256"] = "c" * 64
        self.refused(fixture, envelope)
        state = fixture.state.empty()
        path = fixture.home / "noncanonical-state.json"; path.write_bytes(json.dumps(state).encode())
        envelope["initial_state"] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.refused(fixture, envelope)

    def test_original_cumulative_ledger_location_caps_block_and_prefix_preserved(self):
        fixture = self.fixture()
        self.refused(fixture, fixture.grant_envelope({"ledger": str(fixture.home / "new-budget.sqlite3")}))
        for field, value in (("cap", 200000000001), ("model_cap", 100000000001), ("blocked", 1)):
            with self.subTest(field=field):
                with sqlite3.connect(fixture.ledger) as db:
                    db.execute("UPDATE config SET " + field + "=?", (value,))
                self.refused(fixture)
                with sqlite3.connect(fixture.ledger) as db:
                    db.execute("UPDATE config SET cap=200000000000, model_cap=100000000000, blocked=0")
        with sqlite3.connect(fixture.ledger) as db:
            db.execute("UPDATE requests SET charged=999 WHERE id='invented-prior'")
        self.refused(fixture)

    def test_grant_frozen_ledger_history_digest_count_charge_and_rowid(self):
        fixture = self.fixture()
        for field, value in (("rows_sha256", "c" * 64), ("request_count", 0),
                             ("charged_nano_usd", 999), ("max_rowid", 0)):
            with self.subTest(field=field):
                baseline = dict(fixture.grant["baseline"], **{field: value})
                self.refused(fixture, fixture.grant_envelope({"baseline": baseline}))

    def test_three_exact_role_rows_unique_direct_canonical_paths(self):
        fixture = self.fixture()
        rows = fixture.envelope["slots"]
        malformed = [rows[:2], rows + [deepcopy(rows[0])]]
        bad = deepcopy(rows); bad[0].pop("review"); malformed.append(bad)
        bad = deepcopy(rows); bad[0]["other"] = str(fixture.root / "roles" / "other"); malformed.append(bad)
        bad = deepcopy(rows); bad[1]["controller"] = bad[0]["controller"]; malformed.append(bad)
        bad = deepcopy(rows); bad[0]["forecast"] = str(fixture.root / "roles" / "nested" / "forecast"); malformed.append(bad)
        bad = deepcopy(rows); bad[0]["forecast"] = "relative-forecast"; malformed.append(bad)
        bad = deepcopy(rows); bad[0]["forecast"] = None; malformed.append(bad)
        for index, value in enumerate(malformed):
            with self.subTest(index=index):
                envelope = deepcopy(fixture.envelope); envelope["slots"] = value
                self.refused(fixture, envelope)

    def test_cutoff_and_terminal_grace_ordering_is_static_not_expiration_proof(self):
        fixture = self.fixture()
        cutoff = datetime(2000, 1, 1, tzinfo=timezone.utc)
        past = {"cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
                "deadline_utc": (cutoff + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")}
        with fixture.admitted_anchors():
            live.admit(fixture.grant_envelope(past))  # Owner freshness check is a distinct C4 edge.
        for seconds in (-1, 61):
            changes = dict(past, deadline_utc=(cutoff + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"))
            self.refused(fixture, fixture.grant_envelope(changes))
        self.refused(fixture, fixture.grant_envelope({"cutoff_utc": "2000-01-01T00:00:00+00:00"}))
        envelope = deepcopy(fixture.envelope); envelope["window"]["deadline_utc"] = past["deadline_utc"]
        self.refused(fixture, envelope)


if __name__ == "__main__":
    unittest.main()
