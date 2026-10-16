"""Independent CP6e1 consumer protocol, not eight real mechanical probes.

Matched originals use the actual trial/Task/Forecast/scorer with invented HTTP
and an owned temporary ledger. Every supplied mechanical fact is explicitly a
SYNTHETIC CONSUMER PROTOCOL FIXTURE, never measured compatibility evidence.
Native acceptance below checks receipt interoperability only, not learning,
provider authenticity or a production candidate's eight-check certification.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import test_earnings_shadow_trial as matched_fixture
import earnings_capacity_adapter as adapter
import earnings_effect_review as effect
import earnings_entry as entry
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

EFFECT = "earnings-shadow-v1|tool_interface|tool_return_characters|lower|1|score_nonregression|matched_trial_only"
SYNTHETIC = "SYNTHETIC_CONSUMER_PROTOCOL_NOT_EIGHT_ACTUAL_PROBES"


class _ConsumerFixture:
    def __init__(self, owner, *, axis="H", declaration=EFFECT):
        helper = matched_fixture.MatchedShadowTrialTests(
            "test_actual_H_trial_measures_originals_with_parent_owned_native_claims")
        owner.addCleanup(helper.doCleanups)
        original = adapter.EarningsCapacity.propose

        def prospective(capacity, after, proposal, entries, **options):
            return original(capacity, after, dict(proposal, behavior_change=declaration), entries, **options)

        # Supply the original effect BEFORE the native proposal or either arm.
        # No pending token, recorded original or completed trial is rewritten.
        with patch.object(adapter.EarningsCapacity, "propose", new=prospective):
            self.raw = helper.fixture(axis)
        self.helper, self.owner = helper, owner
        self.comparison = helper.invoke(self.raw)
        self.before = self.raw.native.batch.snapshot()
        self.serial, self.probe_calls, self.proof_change = 0, 0, None
        self.synthetic = self.save("synthetic-facts", {"label": SYNTHETIC,
            "actual_probes_executed": False, "learning": False, "predictive_gain": False})

    def save(self, name, value):
        self.serial += 1
        return engine.save(self.raw.root / f"consumer-{self.serial:03d}-{name}.json", value)

    def binding(self):
        micro = self.before["micro_evolution"]
        pending = micro["pending"]
        return {"proposal_sha256": pending["record_sha256"],
            "before_identity_sha256": digest(self.raw.capacity._selected(self.before)["manifest"]),
            "after_identity_sha256": digest(self.raw.capacity._version(pending["pair"])["manifest"]),
            "tested_pair_sha256": digest(pending["pair"]),
            "anchor_pair_sha256": digest(micro["anchor_pair"])}

    def probe(self, capacity, comparison_binding, output_root):
        self.probe_calls += 1
        self.owner.assertEqual(comparison_binding, self.comparison)
        proof = {"schema": "earnings_mechanical_checks_v1", "binding": self.binding(),
            "scopes": deepcopy(effect.SCOPES), "observations": {
                name: {"facts": dict.fromkeys(facts, True), "artifacts": [self.synthetic]}
                for name, facts in effect.FACTS.items()},
            "sources": {"producer": engine.source_of(self.probe), "synthetic_fixture": self.synthetic},
            "native_state_sha256": self.before["state_sha256"]}
        if self.proof_change is not None:
            self.proof_change(proof, capacity)
        Path(output_root).mkdir(parents=True, exist_ok=False)
        return engine.save(Path(output_root) / "synthetic-consumer-observations.json", proof)

    def registration(self, **changes):
        pending = self.before["micro_evolution"]["pending"]
        value = {"schema": "earnings_effect_review_registration_v1",
            "reviewer_id": self.before["micro_evolution"]["reviewer_id"],
            "proposer_id": pending["proposer_id"], "review_source": engine.source_of(effect.review),
            "probe_source": engine.source_of(self.probe), "scopes": deepcopy(effect.SCOPES)}
        return self.save("registration", dict(value, **changes))

    def consume(self, *, comparison=None, registration=None, output_root=None):
        registration = self.registration() if registration is None else registration
        self.serial += 1
        self.output_root = (self.raw.role_root / "effects" / f"consumer-{self.serial:03d}"
                            if output_root is None else Path(output_root))
        rows, calls = self.raw.rows(), deepcopy(self.raw.calls)
        originals, factories = self.helper.all_originals(self.raw), self.raw.factory.call_count
        try:
            with patch.object(entry, "credential", side_effect=AssertionError("No credentials")), \
                    patch.object(entry, "NightBudget", side_effect=AssertionError("No ledger reopen")), \
                    patch("earnings_http.http.client.HTTPSConnection", side_effect=AssertionError("No review HTTP")):
                return effect.review(self.raw.capacity, self.comparison if comparison is None else comparison,
                    registration_binding=registration, probe=self.probe, output_root=self.output_root)
        finally:
            self.owner.assertEqual(self.raw.rows(), rows)
            self.owner.assertEqual(self.raw.calls, calls)
            self.owner.assertEqual(self.helper.all_originals(self.raw), originals)
            self.owner.assertEqual(self.raw.factory.call_count, factories)


class EffectReviewConsumerTests(unittest.TestCase):
    def assert_reject(self, fixture, reason):
        bound = fixture.consume()
        body = engine.read(bound)
        self.assertEqual(body["review"]["decision"], "reject")
        self.assertEqual(body["review"]["reason"], reason)
        self.assertIs(body["review"]["benefit_observed"], False)
        self.assertIsNone(body["review"]["benefit_evidence_sha256"])
        self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)
        self.assertFalse((fixture.output_root / "benefit.json").exists())
        return bound

    def test_effect_grammar_valid_components_metrics_directions_and_integer_bounds(self):
        for component, metrics in effect.FAMILIES.items():
            for metric in metrics:
                for direction, threshold in (("lower", "1"), ("higher", "999999999")):
                    text = f"earnings-shadow-v1|{component}|{metric}|{direction}|{threshold}|score_nonregression|matched_trial_only"
                    self.assertEqual(effect.effect_criterion(text, component), {
                        "schema": "earnings_shadow_criterion_v1", "component": component,
                        "metric": metric, "direction": direction, "min_delta": int(threshold)})

    def test_effect_grammar_rejects_noncanonical_threshold_types_scope_and_component(self):
        class TextSubclass(str):
            pass
        invalid = [None, True, 1, TextSubclass(EFFECT), "Better reasoning", EFFECT + "|extra",
                   EFFECT.replace("lower", "lowest"), EFFECT.replace("score_nonregression", "score_optional"),
                   EFFECT.replace("matched_trial_only", "predictive_gain"),
                   EFFECT.replace("tool_return_characters", "score_out_of_5")]
        invalid += [EFFECT.replace("|1|", "|" + token + "|")
                    for token in ("0", "-1", "+1", "01", "1.0", "1e0", " 1", "١", "1000000000")]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                effect.effect_criterion(text, "tool_interface")
        for component in ("research_policy", "unknown", None, True):
            with self.subTest(component=component), self.assertRaises(ValueError):
                effect.effect_criterion(EFFECT, component)

    def test_synthetic_consumer_acceptance_binds_actual_native_receipt_without_early_adoption(self):
        fixture = _ConsumerFixture(self)
        measured = engine.read(fixture.comparison)
        self.assertIs(measured["benefit_observed"], True)
        self.assertEqual(measured["claims"], {"learning": False, "model_authorship": False, "predictive_gain": False})
        bound = fixture.consume()
        receipt = engine.read(bound)
        review = receipt["review"]
        self.assertEqual(set(receipt), {"review", "evidence"})
        self.assertEqual(review["decision"], "accept")
        self.assertEqual(review["reason"], "MATCHED_OPERATIONAL_BENEFIT")
        self.assertEqual(set(review["checks"]), set(effect.FACTS))
        self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)
        self.assertEqual(digest(fixture.before["micro_evolution"]["active_pair"]), fixture.raw.active)
        for check in review["checks"].values():
            checked = engine.read({"path": receipt["evidence"][check["evidence_sha256"]], "sha256": check["evidence_sha256"]})
            self.assertEqual(checked["binding"], fixture.binding())
            proof = engine.read(checked["observations"])
            self.assertEqual(engine.read(proof["sources"]["synthetic_fixture"])["label"], SYNTHETIC)
        benefit = engine.read({"path": receipt["evidence"][review["benefit_evidence_sha256"]],
                               "sha256": review["benefit_evidence_sha256"]})
        self.assertEqual(benefit["effect"], EFFECT)
        self.assertIn(benefit["matched_outputs_sha256"], {v["evidence_sha256"] for v in review["checks"].values()})
        rows = fixture.raw.rows()
        # Separate real Native operation on this synthetic protocol fixture.
        fixture.raw.capacity.review(bound, expected_state_sha256=fixture.before["state_sha256"])
        after = fixture.raw.native.batch.snapshot()["micro_evolution"]
        self.assertIsNone(after["pending"])
        self.assertEqual(digest(after["active_pair"]), fixture.raw.tested)
        self.assertEqual(after["previous_pair"], fixture.before["micro_evolution"]["active_pair"])
        self.assertEqual(after["history"][-1]["review"], review)
        self.assertEqual(fixture.raw.rows(), rows)

    def test_broad_original_effect_rejects_without_probe_despite_metric_improvement(self):
        fixture = _ConsumerFixture(self, declaration="Become a better researcher and predict more accurately")
        self.assertIs(engine.read(fixture.comparison)["benefit_observed"], True)
        bound = self.assert_reject(fixture, "UNKNOWN_EFFECT_SEMANTICS")
        self.assertEqual(fixture.probe_calls, 0)
        self.assertEqual(engine.read(bound)["review"]["checks"], {})
        fixture.raw.capacity.review(bound, expected_state_sha256=fixture.before["state_sha256"])
        micro = fixture.raw.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(digest(micro["active_pair"]), fixture.raw.active)
        self.assertEqual(micro["history"][-1]["proposal"]["behavior_change"],
                         "Become a better researcher and predict more accurately")

    def test_no_observed_benefit_rejects_even_with_all_synthetic_positive_facts(self):
        text = "earnings-shadow-v1|research_policy|input_tokens|lower|1|score_nonregression|matched_trial_only"
        fixture = _ConsumerFixture(self, axis="R", declaration=text)
        self.assertIs(engine.read(fixture.comparison)["benefit_observed"], False)
        self.assert_reject(fixture, "NO_MATCHED_BENEFIT")
        self.assertEqual(fixture.probe_calls, 1)

    def test_missing_observation_or_false_fact_is_retained_rejection_not_acceptance(self):
        for kind in ("missing", "false"):
            with self.subTest(kind=kind):
                fixture = _ConsumerFixture(self)
                def negative(proof, capacity):
                    if kind == "missing": proof["observations"].pop("rollback")
                    else: proof["observations"]["rollback"]["facts"]["parent_restored"] = False
                fixture.proof_change = negative
                self.assert_reject(fixture, "MECHANICAL_CHECKS_INCOMPLETE_OR_FAILED")
                self.assertTrue((fixture.output_root / "checks.json").is_file())

    def test_malformed_unknown_or_nonboolean_facts_and_missing_originals_fail_closed(self):
        for kind in ("missing-fact", "unknown-fact", "nonbool", "no-artifacts", "extra-observation-field"):
            with self.subTest(kind=kind):
                fixture = _ConsumerFixture(self)
                def malformed(proof, capacity):
                    row = proof["observations"]["rollback"]
                    if kind == "missing-fact": row["facts"].pop("parent_restored")
                    elif kind == "unknown-fact": row["facts"]["production_rollback"] = True
                    elif kind == "nonbool": row["facts"]["parent_restored"] = 1
                    elif kind == "no-artifacts": row["artifacts"] = []
                    else: row["passed"] = True
                fixture.proof_change = malformed
                with self.assertRaises(ValueError): fixture.consume()
                self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)
                self.assertFalse((fixture.output_root / "review.json").exists())

    def test_unknown_check_changed_scope_and_extra_proof_fields_cannot_accept(self):
        for kind in ("unknown-check", "scope", "extra"):
            with self.subTest(kind=kind):
                fixture = _ConsumerFixture(self)
                def malformed(proof, capacity):
                    if kind == "unknown-check": proof["observations"]["predictive_gain"] = proof["observations"]["rollback"]
                    elif kind == "scope": proof["scopes"]["rollback"] = "Actual production rollback"
                    else: proof["passed"] = True
                fixture.proof_change = malformed
                with self.assertRaises(ValueError): fixture.consume()
                self.assertFalse((fixture.output_root / "review.json").exists())

    def test_comparison_aggregates_benefit_and_claims_are_recomputed_not_trusted(self):
        for key in ("benefit_observed", "delta", "score_delta", "claims"):
            with self.subTest(key=key):
                fixture = _ConsumerFixture(self)
                measured = engine.read(fixture.comparison)
                if key == "benefit_observed": measured[key] = False
                elif key == "delta": measured[key]["tool_return_characters"] -= 1
                elif key == "score_delta": measured[key] += 1
                else: measured[key]["learning"] = True
                with self.assertRaisesRegex(ValueError, "recomputed"):
                    fixture.consume(comparison=fixture.save("changed-comparison", measured))
                self.assertEqual(fixture.probe_calls, 0)
                self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)

    def test_changed_original_count_bytes_and_candidate_source_refuse_before_probe(self):
        for kind in ("count", "candidate-source"):
            with self.subTest(kind=kind):
                fixture = _ConsumerFixture(self)
                path = (Path(fixture.raw.slots[1]) / "01-count.json" if kind == "count"
                        else fixture.raw.root / "harness_v2.py")
                fixture.save("preserved-before-drift", {"bytes_hex": path.read_bytes().hex(), "fixture_only": True})
                path.write_bytes(b"owned synthetic byte drift\n")
                with self.assertRaises(ValueError): fixture.consume()
                self.assertEqual(fixture.probe_calls, 0)
                self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)

    def test_original_effect_and_declared_criterion_must_match_exactly(self):
        fixture = _ConsumerFixture(self, declaration=EFFECT.replace("|1|", "|2|"))
        with self.assertRaisesRegex(ValueError, "criterion differs"):
            fixture.consume()
        self.assertEqual(fixture.probe_calls, 0)
        self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)

    def test_trial_identity_and_current_pending_consumption_are_exact(self):
        for key in ("before_identity_sha256", "after_identity_sha256", "tested_pair_sha256", "pending"):
            with self.subTest(key=key):
                fixture = _ConsumerFixture(self)
                measured = engine.read(fixture.comparison)
                if key == "pending":
                    for arm in ("parent", "child"):
                        measured["originals"][arm]["consumed"]["pending_proposal_sha256"] = "e" * 64
                else:
                    claim = engine.read(measured["trial_claim"])
                    claim[key] = "e" * 64
                    measured["trial_claim"] = fixture.save("different-trial-claim", claim)
                with self.assertRaises(ValueError):
                    fixture.consume(comparison=fixture.save("different-candidate", measured))
                self.assertEqual(fixture.probe_calls, 0)
                self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)

    def test_registration_requires_six_exact_fields_independent_ids_sources_and_scopes(self):
        for key in ("reviewer_id", "proposer_id", "review_source", "probe_source", "scopes", "seventh-field"):
            with self.subTest(key=key):
                fixture = _ConsumerFixture(self)
                if key == "reviewer_id": changes = {key: "fixture-author"}
                elif key == "proposer_id": changes = {key: "other-proposer"}
                elif key in ("review_source", "probe_source"):
                    source = engine.source_of(effect.review if key == "review_source" else fixture.probe)
                    source["module"]["sha256"] = "e" * 64
                    changes = {key: source}
                elif key == "scopes": changes = {key: dict(effect.SCOPES, rollback="Production rollback")}
                else: changes = {"passed": True}
                with self.assertRaisesRegex(ValueError, "registration"):
                    fixture.consume(registration=fixture.registration(**changes))
                self.assertEqual(fixture.probe_calls, 0)

    def test_probe_candidate_source_and_native_state_bindings_cannot_drift(self):
        for kind in ("candidate", "producer", "native-state"):
            with self.subTest(kind=kind):
                fixture = _ConsumerFixture(self)
                def drift(proof, capacity):
                    if kind == "candidate": proof["binding"]["proposal_sha256"] = "e" * 64
                    elif kind == "producer": proof["sources"]["producer"]["module"]["sha256"] = "e" * 64
                    else: proof["native_state_sha256"] = "e" * 64
                fixture.proof_change = drift
                with self.assertRaises(ValueError): fixture.consume()
                self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)
                self.assertFalse((fixture.output_root / "review.json").exists())

    def test_probe_native_mutation_is_detected_not_silently_undone_or_accepted(self):
        fixture = _ConsumerFixture(self)
        def native_reject(proof, capacity):
            pending = fixture.before["micro_evolution"]["pending"]
            receipt = fixture.save("misbehaving-probe-reject", {"review": {
                "reviewer_id": fixture.before["micro_evolution"]["reviewer_id"],
                "proposal_sha256": pending["record_sha256"], "decision": "reject",
                "reason": "Synthetic adversarial producer mutation, not effect evidence",
                "tested_pair_sha256": fixture.raw.tested, "anchor_pair_sha256": fixture.binding()["anchor_pair_sha256"],
                "checks": {}, "benefit_observed": False, "benefit_evidence_sha256": None,
                "actual_write_paths": pending["write_paths"]}, "evidence": {}})
            capacity.review(receipt, expected_state_sha256=fixture.before["state_sha256"])
        fixture.proof_change = native_reject
        with self.assertRaisesRegex(ValueError, "must not mutate"):
            fixture.consume()
        after = fixture.raw.native.batch.snapshot()["micro_evolution"]
        self.assertIsNone(after["pending"])
        self.assertEqual(digest(after["active_pair"]), fixture.raw.active)
        self.assertEqual(after["history"][-1]["review"]["decision"], "reject")
        self.assertFalse((fixture.output_root / "review.json").exists())
        # The current trusted-callback API detects mutation AFTER it occurs;
        # this test does not assert pre-mutation isolation or rollback authority.

    def test_review_requires_new_episode_root_idle_state_and_existing_pending(self):
        for kind in ("outside", "consumed", "busy", "no-pending"):
            with self.subTest(kind=kind):
                fixture = _ConsumerFixture(self)
                options = {}
                if kind == "outside": options["output_root"] = fixture.raw.root / "outside-effect"
                elif kind == "consumed":
                    root = fixture.raw.role_root / "effects" / "old-review"
                    root.mkdir(parents=True, exist_ok=False)
                    original = engine.save(root / "preserve.json", {"closed": True})
                    options["output_root"] = root
                elif kind == "busy":
                    fixture.raw.native.batch.record_capacity_work("claim", work_id="consumer-fixture-busy",
                        pair_sha256=fixture.raw.active, evidence_sha256=digest({"fixture": "busy"}),
                        expected_state_sha256=fixture.before["state_sha256"])
                else:
                    matched_fixture.execution_fixture.ShadowExecutionTests().reject_pending(fixture.raw)
                before = fixture.raw.native.batch.snapshot()
                with self.assertRaises(ValueError): fixture.consume(**options)
                self.assertEqual(fixture.raw.native.batch.snapshot(), before)
                self.assertEqual(fixture.probe_calls, 0)
                if kind == "consumed": self.assertEqual(engine.read(original), {"closed": True})


if __name__ == "__main__":
    unittest.main()
