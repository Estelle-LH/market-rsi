from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
if str(RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(RESEARCH_ROOT))

from pmb_simple_lane.experiment_spec import (  # noqa: E402
    CAUSAL_STAGES,
    SPEC_SCHEMA,
    ExperimentSpec,
    ExperimentSpecError,
    assert_experiment_spec_unchanged,
    canonical_json_bytes,
    revalidate_experiment_spec,
    validate_experiment_spec,
    write_experiment_spec,
)


def sha(character: str) -> str:
    return character * 64


def stage_hashes(changed_stage: str, candidate_hash: str | None = None):
    result = {}
    for index, stage in enumerate(CAUSAL_STAGES, start=1):
        baseline = sha(str(index))
        result[stage] = {
            "baseline_sha256": baseline,
            "candidate_sha256": (
                candidate_hash or sha(chr(ord("a") + index - 1))
                if stage == changed_stage
                else baseline
            ),
        }
    return result


def base_spec():
    return {
        "schema": SPEC_SCHEMA,
        "experiment_id": "pmb-diag-track-a-01",
        "track": "track_a",
        "problem": (
            "Can an order-book prediction adjustment improve future executable "
            "midpoint prediction over the no-change baseline?"
        ),
        "evidence_role": "public_diagnostic_train",
        "promotion_eligible": False,
        "changed_stage": "prediction",
        "causal_stage_hashes": stage_hashes("prediction", sha("f")),
        "target": {"kind": "future_price_change", "units": "probability_points"},
        "horizon": {"seconds": 900},
        "executable_price": {"rule": "contra_bbo_midpoint", "side_aware": True},
        "max_lateness": {"seconds": 5},
        "row_mask": {"rule": "fixed_asof_common_mask", "mask_sha256": sha("a")},
        "cadence": {"seconds": 60},
        "baseline": {"kind": "no_change_executable_midpoint", "sha256": sha("b")},
        "normalizer": {"kind": "train_only_zscore", "fit_cutoff": "D-1"},
        "trainer": {"kind": "frozen_linear", "version": "synthetic-v1"},
        "loss": {"kind": "mean_squared_error"},
        "scorer": {"kind": "paired_track_a_v1", "sha256": sha("c")},
        "feature_signs": {"policy": "predeclared", "signs": {"imbalance": 1}},
        "costs": {"fee_schedule": "pmb_pinned", "included": True},
        "latency": {"market_data_ms": 250, "order_ms": 250},
        "exclusions": {"policy": "no_imputation", "ledger_sha256": sha("d")},
        "missingness": {"future_mark": "invalidate_row", "forward_fill": False},
        "seeds": {"controller": 17, "trainer": 23, "simulator": 0},
        "source_commitments": {
            "upstream_sha256": sha("e"),
            "episode_manifest_sha256": sha("1"),
            "candidate_sha256": sha("f"),
            "adapter_sha256": sha("2"),
        },
        "runtime_commitments": {
            "python": "3.12.11",
            "environment_sha256": sha("3"),
        },
        "schema_commitments": {
            "track_a_report_sha256": sha("4"),
            "aggregate_schema_sha256": sha("5"),
        },
        "track_b": None,
    }


def track_b_contract(track_a_id="pmb-diag-track-a-01", evaluation_id="pmb-diag-track-b-01"):
    frozen_prediction = sha("f")
    policy = sha("9")
    hashes = stage_hashes("pnl", policy)
    hashes["prediction"] = {
        "baseline_sha256": frozen_prediction,
        "candidate_sha256": frozen_prediction,
    }
    return {
        "evaluation_id": evaluation_id,
        "track_a_experiment_id": track_a_id,
        "changed_stage": "pnl",
        "causal_stage_hashes": hashes,
        "trading_policy_sha256": policy,
        "frozen_prediction_sha256": frozen_prediction,
        "precommitted": True,
        "track_a_feedback_allowed": False,
    }


class ImmutableExperimentSpecTests(unittest.TestCase):
    def changed(self, *path, value):
        result = copy.deepcopy(base_spec())
        cursor = result
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        return result

    def test_prediction_only_public_diagnostic_is_canonical_and_detached(self):
        raw = base_spec()
        first = ExperimentSpec.from_mapping(raw)
        reordered = {key: raw[key] for key in reversed(tuple(raw))}
        second = ExperimentSpec.from_mapping(reordered)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(canonical_json_bytes(raw), first.canonical_bytes)

        raw["target"]["kind"] = "mutated"
        detached = first.to_mapping()
        detached["target"]["kind"] = "also-mutated"
        self.assertEqual(first.to_mapping()["target"]["kind"], "future_price_change")

    def test_every_complete_frozen_field_is_required_and_nonempty(self):
        frozen_fields = (
            "target",
            "horizon",
            "executable_price",
            "max_lateness",
            "row_mask",
            "cadence",
            "baseline",
            "normalizer",
            "trainer",
            "loss",
            "scorer",
            "feature_signs",
            "costs",
            "latency",
            "exclusions",
            "missingness",
            "seeds",
            "source_commitments",
            "runtime_commitments",
            "schema_commitments",
        )
        for field in frozen_fields:
            with self.subTest(field=field, condition="missing"):
                candidate = base_spec()
                del candidate[field]
                with self.assertRaises(ExperimentSpecError):
                    validate_experiment_spec(candidate)
            with self.subTest(field=field, condition="empty"):
                candidate = base_spec()
                candidate[field] = {}
                with self.assertRaises(ExperimentSpecError):
                    validate_experiment_spec(candidate)

    def test_unknown_field_and_non_json_value_fail_closed(self):
        candidate = base_spec()
        candidate["late_override"] = True
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(candidate)
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(self.changed("target", value={"bad": {1, 2}}))

    def test_problem_must_be_exactly_one_trimmed_sentence(self):
        invalid = (
            "No terminal punctuation",
            "Two sentences. Not one.",
            "Question? Extra!",
            " Leading whitespace?",
            "Line one\nline two?",
        )
        for problem in invalid:
            with self.subTest(problem=problem), self.assertRaises(ExperimentSpecError):
                validate_experiment_spec(self.changed("problem", value=problem))

    def test_exactly_one_declared_causal_stage_may_change(self):
        unchanged = base_spec()
        for pair in unchanged["causal_stage_hashes"].values():
            pair["candidate_sha256"] = pair["baseline_sha256"]
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(unchanged)

        two = base_spec()
        two["causal_stage_hashes"]["objective"]["candidate_sha256"] = sha("8")
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(two)

        mismatch = base_spec()
        mismatch["changed_stage"] = "raw_signal"
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(mismatch)

    def test_stage_hashes_must_bind_exactly_all_five_stages(self):
        missing = base_spec()
        del missing["causal_stage_hashes"]["raw_data"]
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(missing)
        extra = base_spec()
        extra["causal_stage_hashes"]["deployment"] = {
            "baseline_sha256": sha("1"),
            "candidate_sha256": sha("1"),
        }
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(extra)

    def test_no_evidence_role_can_grant_promotion_authority(self):
        for evidence_role in (
            "public_diagnostic_train",
            "train",
            "hidden_dev",
            "sealed_final",
        ):
            with self.subTest(evidence_role=evidence_role):
                candidate = self.changed("evidence_role", value=evidence_role)
                candidate["promotion_eligible"] = True
                with self.assertRaisesRegex(
                    ExperimentSpecError,
                    "never grants promotion or action authority",
                ):
                    validate_experiment_spec(candidate)

    def test_promotion_field_requires_the_exact_false_singleton(self):
        for unsafe_value in (True, 0, 1, None, "false"):
            with self.subTest(unsafe_value=unsafe_value):
                with self.assertRaisesRegex(
                    ExperimentSpecError,
                    "must be exactly false",
                ):
                    validate_experiment_spec(
                        self.changed("promotion_eligible", value=unsafe_value)
                    )

    def test_false_promotion_field_preserves_valid_bytes_and_hashes_for_every_role(self):
        for evidence_role in (
            "public_diagnostic_train",
            "train",
            "hidden_dev",
            "sealed_final",
        ):
            with self.subTest(evidence_role=evidence_role):
                candidate = self.changed("evidence_role", value=evidence_role)
                before_bytes = canonical_json_bytes(candidate)
                before_sha256 = __import__("hashlib").sha256(before_bytes).hexdigest()
                spec = ExperimentSpec.from_mapping(candidate)
                self.assertEqual(spec.canonical_bytes, before_bytes)
                self.assertEqual(spec.sha256, before_sha256)

    def test_stateful_sha256_subclass_attempt_is_rejected_at_definition(self):
        sha256_reads = []

        with self.assertRaisesRegex(TypeError, "sealed"):

            class StatefulSha256Spec(ExperimentSpec):
                @property
                def sha256(self):
                    sha256_reads.append(len(sha256_reads))
                    return sha(str((len(sha256_reads) % 9) + 1))

        self.assertEqual(sha256_reads, [])

    def test_track_a_cannot_smuggle_a_pnl_change(self):
        candidate = base_spec()
        candidate["changed_stage"] = "pnl"
        candidate["causal_stage_hashes"] = stage_hashes("pnl", sha("9"))
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(candidate)

    def test_track_b_requires_fresh_separate_id_and_precommitted_policy(self):
        candidate = base_spec()
        candidate["track_b"] = track_b_contract()
        with self.assertRaisesRegex(ExperimentSpecError, "freshness ledger"):
            validate_experiment_spec(candidate)
        validate_experiment_spec(candidate, used_evaluation_ids=set())
        with self.assertRaisesRegex(ExperimentSpecError, "already been used"):
            validate_experiment_spec(
                candidate, used_evaluation_ids={"pmb-diag-track-b-01"}
            )

        same_id = copy.deepcopy(candidate)
        same_id["track_b"]["evaluation_id"] = same_id["experiment_id"]
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(same_id, used_evaluation_ids=set())

        post_hoc = copy.deepcopy(candidate)
        post_hoc["track_b"]["precommitted"] = False
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(post_hoc, used_evaluation_ids=set())

    def test_track_b_cannot_change_prediction_or_feed_results_back(self):
        candidate = base_spec()
        candidate["track_b"] = track_b_contract()

        changed_prediction = copy.deepcopy(candidate)
        changed_prediction["track_b"]["causal_stage_hashes"]["prediction"][
            "candidate_sha256"
        ] = sha("8")
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(changed_prediction, used_evaluation_ids=set())

        feedback = copy.deepcopy(candidate)
        feedback["track_b"]["track_a_feedback_allowed"] = True
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(feedback, used_evaluation_ids=set())

        wrong_policy = copy.deepcopy(candidate)
        wrong_policy["track_b"]["trading_policy_sha256"] = sha("7")
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(wrong_policy, used_evaluation_ids=set())

    def test_standalone_track_b_spec_changes_only_pnl(self):
        candidate = base_spec()
        contract = track_b_contract()
        candidate.update(
            {
                "experiment_id": contract["evaluation_id"],
                "track": "track_b",
                "changed_stage": "pnl",
                "causal_stage_hashes": copy.deepcopy(contract["causal_stage_hashes"]),
                "track_b": contract,
            }
        )
        validated = validate_experiment_spec(candidate, used_evaluation_ids=set())
        self.assertEqual(validated["changed_stage"], "pnl")

        candidate["causal_stage_hashes"]["raw_signal"]["candidate_sha256"] = sha("7")
        with self.assertRaises(ExperimentSpecError):
            validate_experiment_spec(candidate, used_evaluation_ids=set())

    def test_exclusive_fsync_read_only_write_and_revalidation(self):
        spec = ExperimentSpec.from_mapping(base_spec())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment_spec.json"
            commitment = write_experiment_spec(path, spec)
            self.assertEqual(commitment.sha256, spec.sha256)
            self.assertEqual(path.read_bytes(), spec.canonical_bytes)
            self.assertEqual(os.stat(path).st_mode & 0o222, 0)
            reread = revalidate_experiment_spec(path, spec.sha256)
            self.assertEqual(reread, spec)
            self.assertEqual(assert_experiment_spec_unchanged(commitment), spec)
            with self.assertRaises(ExperimentSpecError):
                write_experiment_spec(path, spec)

    def test_same_byte_replacement_is_rejected_by_file_identity_commitment(self):
        spec = ExperimentSpec.from_mapping(base_spec())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment_spec.json"
            commitment = write_experiment_spec(path, spec)
            replacement = Path(directory) / "replacement.json"
            replacement.write_bytes(spec.canonical_bytes)
            os.chmod(replacement, 0o444)
            path.unlink()
            replacement.rename(path)
            self.assertEqual(revalidate_experiment_spec(path, spec.sha256), spec)
            with self.assertRaisesRegex(ExperimentSpecError, "identity changed"):
                assert_experiment_spec_unchanged(commitment)

    def test_mutation_wrong_hash_and_noncanonical_file_fail_revalidation(self):
        spec = ExperimentSpec.from_mapping(base_spec())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment_spec.json"
            write_experiment_spec(path, spec)
            with self.assertRaises(ExperimentSpecError):
                revalidate_experiment_spec(path, sha("0"))

            os.chmod(path, 0o600)
            value = spec.to_mapping()
            value["target"]["kind"] = "mutated"
            path.write_bytes(canonical_json_bytes(value))
            os.chmod(path, 0o444)
            with self.assertRaisesRegex(ExperimentSpecError, "SHA-256 changed"):
                revalidate_experiment_spec(path, spec.sha256)

            os.chmod(path, 0o600)
            path.write_text(json.dumps(base_spec(), indent=2), encoding="utf-8")
            os.chmod(path, 0o444)
            pretty_sha = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ExperimentSpecError, "not exact canonical"):
                revalidate_experiment_spec(path, pretty_sha)

    def test_writable_and_symlink_specs_fail_revalidation(self):
        spec = ExperimentSpec.from_mapping(base_spec())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "experiment_spec.json"
            write_experiment_spec(path, spec)
            os.chmod(path, 0o600)
            with self.assertRaisesRegex(ExperimentSpecError, "read-only"):
                revalidate_experiment_spec(path, spec.sha256)
            os.chmod(path, 0o444)
            link = root / "shadow.json"
            link.symlink_to(path)
            with self.assertRaisesRegex(ExperimentSpecError, "non-symlink"):
                revalidate_experiment_spec(link, spec.sha256)

    def test_duplicate_json_keys_are_rejected_even_with_matching_hash(self):
        spec = ExperimentSpec.from_mapping(base_spec())
        duplicate = b'{"schema":"x","schema":"y"}'
        forged = ExperimentSpec.__new__(ExperimentSpec)
        object.__setattr__(forged, "canonical_bytes", duplicate)
        object.__setattr__(
            forged,
            "sha256",
            __import__("hashlib").sha256(duplicate).hexdigest(),
        )
        # The dataclass constructor guard can be bypassed only by hostile local
        # Python reflection; decoding still refuses ambiguous duplicate keys.
        with self.assertRaises(ExperimentSpecError):
            forged.to_mapping()
        self.assertEqual(spec.to_mapping()["schema"], SPEC_SCHEMA)


if __name__ == "__main__":
    unittest.main()
