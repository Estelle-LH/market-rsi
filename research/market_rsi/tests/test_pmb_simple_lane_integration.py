from __future__ import annotations

import copy
import hashlib
import json
import pickle
from pathlib import Path
import tempfile
import unittest

from research.market_rsi.pmb_simple_lane import (
    ArtifactStore,
    EpisodeLease,
    SyntheticFoundationCommitment,
    SyntheticFoundationError,
    bind_synthetic_foundation,
    require_validated_synthetic_foundation,
)
from research.market_rsi.pmb_simple_lane.episode_manifest import (
    EPISODE_MANIFEST_SCHEMA,
    REQUIRED_EPISODE_FILES,
    EpisodeManifest,
    ManifestSetValidation,
    validate_episode_manifests,
)
from research.market_rsi.pmb_simple_lane.experiment_spec import (
    CAUSAL_STAGES,
    SPEC_SCHEMA,
    ExperimentSpec,
)
from research.market_rsi.pmb_simple_lane.upstream_lock import (
    OFFICIAL_UPSTREAM_URL,
    PROSPECTIVE_UPSTREAM_COMMIT,
    UPSTREAM_LOCK_SCHEMA,
    ProspectiveUpstreamVerification,
    verify_prospective_upstream,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manifest_validation():
    episode_id = "KXBTCD-26JAN2017"
    document = {
        "schema": EPISODE_MANIFEST_SCHEMA,
        "episode_id": episode_id,
        "venue": "kalshi",
        "domain": "crypto",
        "utc_date": "2026-01-17",
        "role": "public_diagnostic_train",
        "relative_directory": episode_id,
        "files": [
            {"name": name, "sha256": _sha(f"{episode_id}:{name}"), "length": len(name)}
            for name in sorted(REQUIRED_EPISODE_FILES)
        ],
    }
    return validate_episode_manifests([EpisodeManifest.from_mapping(document)])


def _upstream_verification():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve() / "PredictionMarketBench"
        (root / "prediction_market_bench").mkdir(parents=True)
        files = {
            "LICENSE": b"synthetic MIT fixture\n",
            "prediction_market_bench/__init__.py": b"# synthetic fixture\n",
        }
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        lock = {
            "schema": UPSTREAM_LOCK_SCHEMA,
            "source_url": OFFICIAL_UPSTREAM_URL,
            "commit_sha": PROSPECTIVE_UPSTREAM_COMMIT,
            "tree": [
                {"path": path, "sha256": hashlib.sha256(content).hexdigest(), "length": len(content)}
                for path, content in sorted(files.items())
            ],
            "license": {
                "path": "LICENSE",
                "sha256": hashlib.sha256(files["LICENSE"]).hexdigest(),
                "length": len(files["LICENSE"]),
                "spdx": "MIT",
            },
            "import_origins": [
                {
                    "module": "prediction_market_bench",
                    "path": "prediction_market_bench/__init__.py",
                }
            ],
        }
        return verify_prospective_upstream(
            lock,
            root,
            observed_source_url=OFFICIAL_UPSTREAM_URL,
            observed_commit_sha=PROSPECTIVE_UPSTREAM_COMMIT,
            dirty=False,
            observed_import_origins={
                "prediction_market_bench": root / "prediction_market_bench/__init__.py"
            },
        )


def _experiment(upstream_sha: str, manifest_sha: str) -> ExperimentSpec:
    stages = {}
    for index, stage in enumerate(CAUSAL_STAGES):
        baseline = _sha(f"baseline:{index}")
        stages[stage] = {
            "baseline_sha256": baseline,
            "candidate_sha256": _sha("candidate:prediction") if stage == "prediction" else baseline,
        }
    return ExperimentSpec.from_mapping(
        {
            "schema": SPEC_SCHEMA,
            "experiment_id": "pmb-synthetic-integration-a-01",
            "track": "track_a",
            "problem": "Can a frozen candidate improve executable-price prediction over a no-change baseline?",
            "evidence_role": "public_diagnostic_train",
            "promotion_eligible": False,
            "changed_stage": "prediction",
            "causal_stage_hashes": stages,
            "target": {"kind": "future_price_change"},
            "horizon": {"seconds": 900},
            "executable_price": {"rule": "contra_bbo_midpoint"},
            "max_lateness": {"seconds": 5},
            "row_mask": {"rule": "fixed_common_mask"},
            "cadence": {"seconds": 60},
            "baseline": {"kind": "no_change"},
            "normalizer": {"kind": "train_only_zscore"},
            "trainer": {"kind": "frozen_linear"},
            "loss": {"kind": "mean_squared_error"},
            "scorer": {"kind": "paired_track_a_v1"},
            "feature_signs": {"policy": "predeclared"},
            "costs": {"included": True},
            "latency": {"market_data_ms": 250},
            "exclusions": {"policy": "no_imputation"},
            "missingness": {"future_mark": "invalidate_row"},
            "seeds": {"controller": 17, "trainer": 23},
            "source_commitments": {
                "upstream_sha256": upstream_sha,
                "episode_manifest_sha256": manifest_sha,
                "adapter_sha256": _sha("adapter"),
            },
            "runtime_commitments": {"environment_sha256": _sha("environment")},
            "schema_commitments": {"report_sha256": _sha("report-schema")},
            "track_b": None,
        }
    )


class SyntheticFoundationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = _upstream_verification()
        self.manifests = _manifest_validation()
        self.experiment = _experiment(
            self.upstream.lock_sha256, self.manifests.manifest_set_sha256
        )

    def test_cross_component_receipt_is_canonical_and_has_zero_authority(self) -> None:
        receipt = bind_synthetic_foundation(
            self.upstream, self.manifests, self.experiment
        )
        self.assertIsInstance(receipt, SyntheticFoundationCommitment)
        self.assertEqual(receipt.evidence_role, "public_diagnostic_train")
        self.assertFalse(receipt.runtime_admitted)
        self.assertFalse(receipt.data_admitted)
        self.assertFalse(receipt.execution_authorized)
        self.assertIs(require_validated_synthetic_foundation(receipt), receipt)
        self.assertEqual(receipt.sha256, bind_synthetic_foundation(
            self.upstream, self.manifests, self.experiment
        ).sha256)

    def test_commitment_drift_and_authority_expansion_fail_closed(self) -> None:
        drifted = _experiment(_sha("wrong-upstream"), self.manifests.manifest_set_sha256)
        with self.assertRaisesRegex(SyntheticFoundationError, "upstream lock"):
            bind_synthetic_foundation(self.upstream, self.manifests, drifted)
        with self.assertRaisesRegex(ValueError, "only be created"):
            ProspectiveUpstreamVerification(
                self.upstream.lock_sha256,
                self.upstream.tree_file_count,
                self.upstream.import_origin_count,
            )
        with self.assertRaisesRegex(ValueError, "only be created"):
            ManifestSetValidation(
                self.manifests.manifest_set_sha256,
                self.manifests.episode_count,
                self.manifests.roles,
                self.manifests.sealed_final_distinct_dates,
                admission_granted=True,
            )
        with self.assertRaisesRegex(SyntheticFoundationError, "only be created"):
            SyntheticFoundationCommitment(
                self.upstream.lock_sha256,
                self.manifests.manifest_set_sha256,
                self.experiment.sha256,
                "public_diagnostic_train",
                execution_authorized=True,
            )

    def test_binder_requires_exact_sealed_experiment_type(self) -> None:
        class Pretender:
            canonical_bytes = self.experiment.canonical_bytes
            sha256 = self.experiment.sha256

        with self.assertRaisesRegex(SyntheticFoundationError, "exact sealed"):
            bind_synthetic_foundation(
                self.upstream, self.manifests, Pretender()  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(TypeError, "sealed"):
            type("StatefulExperiment", (ExperimentSpec,), {})
        fabricated_receipt = object.__new__(SyntheticFoundationCommitment)
        with self.assertRaisesRegex(SyntheticFoundationError, "authentic"):
            require_validated_synthetic_foundation(fabricated_receipt)

    def test_foundation_receipt_identity_and_issuance_snapshot_are_exact(self) -> None:
        receipt = bind_synthetic_foundation(
            self.upstream, self.manifests, self.experiment
        )
        for transformed in (
            copy.copy(receipt),
            copy.deepcopy(receipt),
            pickle.loads(pickle.dumps(receipt)),
        ):
            with self.assertRaisesRegex(SyntheticFoundationError, "authentic"):
                require_validated_synthetic_foundation(transformed)

        copied = copy.copy(receipt)
        object.__setattr__(copied, "upstream_lock_sha256", "f" * 64)
        with self.assertRaisesRegex(SyntheticFoundationError, "authentic"):
            require_validated_synthetic_foundation(copied)

        forged = object.__new__(SyntheticFoundationCommitment)
        for name, value in receipt.as_dict().items():
            object.__setattr__(forged, name, value)
        object.__setattr__(forged, "_validation_token", receipt._validation_token)
        with self.assertRaisesRegex(SyntheticFoundationError, "authentic"):
            require_validated_synthetic_foundation(forged)

        object.__setattr__(receipt, "experiment_spec_sha256", "e" * 64)
        with self.assertRaisesRegex(SyntheticFoundationError, "authentic"):
            require_validated_synthetic_foundation(receipt)

    def test_fabricated_summaries_and_noncanonical_spec_fail_closed(self) -> None:
        fabricated_upstream = object.__new__(ProspectiveUpstreamVerification)
        object.__setattr__(fabricated_upstream, "lock_sha256", self.upstream.lock_sha256)
        object.__setattr__(fabricated_upstream, "tree_file_count", 2)
        object.__setattr__(fabricated_upstream, "import_origin_count", 1)
        object.__setattr__(fabricated_upstream, "evidence_scope", "local_synthetic_commitment_only")
        object.__setattr__(fabricated_upstream, "runtime_admitted", False)
        with self.assertRaisesRegex(SyntheticFoundationError, "authentic validator"):
            bind_synthetic_foundation(
                fabricated_upstream, self.manifests, self.experiment
            )

        fabricated_manifests = object.__new__(ManifestSetValidation)
        object.__setattr__(
            fabricated_manifests,
            "manifest_set_sha256",
            self.manifests.manifest_set_sha256,
        )
        object.__setattr__(fabricated_manifests, "episode_count", 20)
        object.__setattr__(fabricated_manifests, "roles", ("sealed_final",))
        object.__setattr__(fabricated_manifests, "sealed_final_distinct_dates", 20)
        object.__setattr__(fabricated_manifests, "preopen_commitments_valid", True)
        object.__setattr__(fabricated_manifests, "data_opened", False)
        object.__setattr__(fabricated_manifests, "admission_granted", False)
        with self.assertRaisesRegex(SyntheticFoundationError, "authentic validator"):
            bind_synthetic_foundation(
                self.upstream, fabricated_manifests, self.experiment
            )

        copied_upstream = copy.copy(self.upstream)
        object.__setattr__(copied_upstream, "lock_sha256", "a" * 64)
        copied_manifests = copy.copy(self.manifests)
        object.__setattr__(copied_manifests, "manifest_set_sha256", "b" * 64)
        object.__setattr__(copied_manifests, "episode_count", 20)
        object.__setattr__(copied_manifests, "roles", ("sealed_final",))
        object.__setattr__(copied_manifests, "sealed_final_distinct_dates", 20)
        for candidate_upstream, candidate_manifests in (
            (copied_upstream, self.manifests),
            (self.upstream, copied_manifests),
        ):
            with self.assertRaisesRegex(SyntheticFoundationError, "authentic validator"):
                bind_synthetic_foundation(
                    candidate_upstream, candidate_manifests, self.experiment
                )

        pretty = json.dumps(self.experiment.to_mapping(), indent=2).encode("utf-8")
        noncanonical = ExperimentSpec(pretty, hashlib.sha256(pretty).hexdigest())
        with self.assertRaisesRegex(SyntheticFoundationError, "not canonical"):
            bind_synthetic_foundation(
                self.upstream, self.manifests, noncanonical
            )

    def test_receipt_binds_one_shot_synthetic_lease_lifecycle(self) -> None:
        receipt = bind_synthetic_foundation(
            self.upstream, self.manifests, self.experiment
        )
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory) / "artifacts", allow_temporary=True)
            lease = EpisodeLease.create(
                store,
                "pmb-synthetic-integration-01",
                registration={
                    "foundation_sha256": receipt.sha256,
                    "experiment_spec_sha256": self.experiment.sha256,
                    "authority": "none",
                },
            )
            lease.capture_start_snapshot({"synthetic": True, "data_opened": False})
            lease.stop_early(1, intent={"scope": "synthetic"}, reason="fixture complete")
            lease.synthesize_and_freeze(
                synthesis={"mode": "synthetic"},
                candidate={"experiment_spec_sha256": self.experiment.sha256},
            )
            lease.begin_terminal_review({"foundation_sha256": receipt.sha256})
            lease.close(
                "passed",
                review={"independent": True, "authority_expanded": False},
                end_snapshot={"data_opened": False, "paid_calls": 0},
            )
            inspection = EpisodeLease.inspect(store, "pmb-synthetic-integration-01")
            self.assertEqual(inspection["state"], "closed_passed")
            self.assertEqual(inspection["restart_disposition"], "terminal_read_only")


if __name__ == "__main__":
    unittest.main()
