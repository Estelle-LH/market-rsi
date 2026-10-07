from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
from datetime import date, timedelta
import hashlib
import inspect
from pathlib import Path
import pickle
import tempfile
import unittest

from research.market_rsi.pmb_simple_lane import episode_manifest as episode_manifest_module
from research.market_rsi.pmb_simple_lane import upstream_lock as upstream_lock_module
from research.market_rsi.pmb_simple_lane.episode_manifest import (
    EPISODE_MANIFEST_SCHEMA,
    EPISODE_ROLES,
    PUBLIC_DIAGNOSTIC_EPISODES,
    REQUIRED_EPISODE_FILES,
    EpisodeManifest,
    EpisodeManifestError,
    ManifestSetValidation,
    require_validated_manifest_set,
    validate_episode_manifests,
    validate_role_roots,
    verify_materialized_episode_files,
)
from research.market_rsi.pmb_simple_lane.upstream_lock import (
    OFFICIAL_UPSTREAM_URL,
    PROSPECTIVE_UPSTREAM_COMMIT,
    UPSTREAM_LOCK_SCHEMA,
    ProspectiveUpstreamVerification,
    UpstreamLock,
    UpstreamLockError,
    require_validated_upstream_verification,
    verify_prospective_upstream,
)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _registered_caller_selected_receipt_paths(
    module: object,
    selected_fields: dict[str, object],
    require_receipt,
) -> tuple[str, ...]:
    """Exercise module callables that accept every caller-selected receipt field."""

    registered = []
    for name, candidate in vars(module).items():
        if name.startswith("__") or not callable(candidate):
            continue
        if getattr(candidate, "__module__", None) != getattr(module, "__name__"):
            continue
        try:
            parameters = inspect.signature(candidate).parameters
        except (TypeError, ValueError):
            continue
        if not set(selected_fields).issubset(parameters):
            continue
        try:
            value = candidate(**selected_fields)
            require_receipt(value)
        except Exception:
            continue
        registered.append(name)
    return tuple(sorted(registered))


class ProspectiveUpstreamLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "PredictionMarketBench"
        (self.root / "prediction_market_bench").mkdir(parents=True)
        self.bytes_by_path = {
            "LICENSE": b"synthetic MIT license fixture\n",
            "pyproject.toml": b"[project]\nname='synthetic-pmb'\n",
            "prediction_market_bench/__init__.py": b"# synthetic fixture\n",
            "prediction_market_bench/agent.py": b"class AgentContext: pass\n",
        }
        for relative, content in self.bytes_by_path.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.lock_document = {
            "schema": UPSTREAM_LOCK_SCHEMA,
            "source_url": OFFICIAL_UPSTREAM_URL,
            "commit_sha": PROSPECTIVE_UPSTREAM_COMMIT,
            "tree": [
                {
                    "path": relative,
                    "sha256": _digest(content),
                    "length": len(content),
                }
                for relative, content in sorted(self.bytes_by_path.items())
            ],
            "license": {
                "path": "LICENSE",
                "sha256": _digest(self.bytes_by_path["LICENSE"]),
                "length": len(self.bytes_by_path["LICENSE"]),
                "spdx": "MIT",
            },
            "import_origins": [
                {
                    "module": "prediction_market_bench",
                    "path": "prediction_market_bench/__init__.py",
                },
                {
                    "module": "prediction_market_bench.agent",
                    "path": "prediction_market_bench/agent.py",
                },
            ],
        }
        self.import_origins = {
            "prediction_market_bench": self.root
            / "prediction_market_bench/__init__.py",
            "prediction_market_bench.agent": self.root
            / "prediction_market_bench/agent.py",
        }

    def verify(self, document=None, **overrides):
        kwargs = {
            "observed_source_url": OFFICIAL_UPSTREAM_URL,
            "observed_commit_sha": PROSPECTIVE_UPSTREAM_COMMIT,
            "dirty": False,
            "observed_import_origins": self.import_origins,
        }
        kwargs.update(overrides)
        return verify_prospective_upstream(
            self.lock_document if document is None else document,
            self.root,
            **kwargs,
        )

    def test_exact_synthetic_commitment_passes_but_never_admits_runtime(self) -> None:
        first = self.verify()
        second = self.verify(UpstreamLock.from_mapping(self.lock_document))
        self.assertIsInstance(first, ProspectiveUpstreamVerification)
        self.assertEqual(first.lock_sha256, second.lock_sha256)
        self.assertEqual(first.tree_file_count, 4)
        self.assertEqual(first.import_origin_count, 2)
        self.assertEqual(first.evidence_scope, "local_synthetic_commitment_only")
        self.assertFalse(first.runtime_admitted)
        self.assertIs(require_validated_upstream_verification(first), first)

    def test_direct_upstream_instances_are_revalidated(self) -> None:
        valid = UpstreamLock.from_mapping(self.lock_document)

        wrong_source = replace(
            valid, source_url="https://github.com/example/PredictionMarketBench.git"
        )
        with self.assertRaisesRegex(UpstreamLockError, "official PMB URL"):
            self.verify(wrong_source)

        wrong_license = replace(valid, license_spdx="LicenseRef-Proprietary")
        with self.assertRaisesRegex(UpstreamLockError, "SPDX MIT"):
            self.verify(wrong_license)

    def test_upstream_verification_summary_cannot_be_freely_constructed(self) -> None:
        with self.assertRaisesRegex(UpstreamLockError, "only be created"):
            ProspectiveUpstreamVerification(
                lock_sha256="0" * 64,
                tree_file_count=1,
                import_origin_count=1,
            )

        fabricated = object.__new__(ProspectiveUpstreamVerification)
        object.__setattr__(fabricated, "lock_sha256", "0" * 64)
        object.__setattr__(fabricated, "tree_file_count", 1)
        object.__setattr__(fabricated, "import_origin_count", 1)
        object.__setattr__(
            fabricated, "evidence_scope", "local_synthetic_commitment_only"
        )
        object.__setattr__(fabricated, "runtime_admitted", False)
        with self.assertRaisesRegex(UpstreamLockError, "authentic"):
            require_validated_upstream_verification(fabricated)

    def test_only_exact_unchanged_upstream_receipt_identity_authenticates(self) -> None:
        authentic = self.verify()

        for transformed in (
            copy(authentic),
            deepcopy(authentic),
            pickle.loads(pickle.dumps(authentic)),
        ):
            self.assertIsNot(transformed, authentic)
            with self.assertRaisesRegex(UpstreamLockError, "authentic"):
                require_validated_upstream_verification(transformed)

        with self.assertRaisesRegex(UpstreamLockError, "only be created"):
            replace(authentic)

        fabricated = object.__new__(ProspectiveUpstreamVerification)
        for field in (
            "lock_sha256",
            "tree_file_count",
            "import_origin_count",
            "evidence_scope",
            "runtime_admitted",
            "_validation_token",
        ):
            object.__setattr__(fabricated, field, getattr(authentic, field))
        with self.assertRaisesRegex(UpstreamLockError, "authentic"):
            require_validated_upstream_verification(fabricated)

        copied_and_retargeted = copy(authentic)
        object.__setattr__(copied_and_retargeted, "lock_sha256", "0" * 64)
        with self.assertRaisesRegex(UpstreamLockError, "authentic"):
            require_validated_upstream_verification(copied_and_retargeted)

    def test_every_upstream_receipt_field_is_bound_to_issuance_snapshot(self) -> None:
        mutations = {
            "lock_sha256": "0" * 64,
            "tree_file_count": 5,
            "import_origin_count": 3,
            "evidence_scope": "other_local_scope",
            "runtime_admitted": True,
            "_validation_token": object(),
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field):
                authentic = self.verify()
                object.__setattr__(authentic, field, replacement)
                with self.assertRaisesRegex(UpstreamLockError, "authentic"):
                    require_validated_upstream_verification(authentic)

    def test_no_callable_registers_caller_selected_upstream_evidence(self) -> None:
        self.assertIsNone(
            getattr(upstream_lock_module, "_issue_upstream_verification", None)
        )
        self.assertEqual(
            _registered_caller_selected_receipt_paths(
                upstream_lock_module,
                {
                    "lock_sha256": "a" * 64,
                    "tree_file_count": 999,
                    "import_origin_count": 999,
                },
                require_validated_upstream_verification,
            ),
            (),
        )

    def test_url_and_exact_40_hex_prospective_sha_fail_closed(self) -> None:
        wrong_url = deepcopy(self.lock_document)
        wrong_url["source_url"] = "https://github.com/example/PredictionMarketBench.git"
        with self.assertRaisesRegex(UpstreamLockError, "official PMB URL"):
            UpstreamLock.from_mapping(wrong_url)

        short_sha = deepcopy(self.lock_document)
        short_sha["commit_sha"] = PROSPECTIVE_UPSTREAM_COMMIT[:-1]
        with self.assertRaisesRegex(UpstreamLockError, "40 lowercase hex"):
            UpstreamLock.from_mapping(short_sha)

        other_sha = deepcopy(self.lock_document)
        other_sha["commit_sha"] = "0" * 40
        with self.assertRaisesRegex(UpstreamLockError, "reviewed prospective"):
            UpstreamLock.from_mapping(other_sha)

        with self.assertRaisesRegex(UpstreamLockError, "observed source URL"):
            self.verify(observed_source_url=OFFICIAL_UPSTREAM_URL.removesuffix(".git"))
        with self.assertRaisesRegex(UpstreamLockError, "observed commit"):
            self.verify(observed_commit_sha="0" * 40)

    def test_tree_license_and_unknown_fields_fail_closed(self) -> None:
        unknown = deepcopy(self.lock_document)
        unknown["checkout_admitted"] = True
        with self.assertRaisesRegex(UpstreamLockError, "unknown"):
            UpstreamLock.from_mapping(unknown)

        mismatched_license = deepcopy(self.lock_document)
        mismatched_license["license"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(UpstreamLockError, "disagrees"):
            UpstreamLock.from_mapping(mismatched_license)

        (self.root / "unexpected.txt").write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(UpstreamLockError, "tree paths differ"):
            self.verify()

    def test_dirty_byte_drift_and_import_diversion_fail_closed(self) -> None:
        with self.assertRaisesRegex(UpstreamLockError, "dirty"):
            self.verify(dirty=True)

        agent_path = self.root / "prediction_market_bench/agent.py"
        agent_path.write_bytes(b"changed synthetic bytes\n")
        with self.assertRaisesRegex(UpstreamLockError, "tree bytes differ"):
            self.verify()
        agent_path.write_bytes(self.bytes_by_path["prediction_market_bench/agent.py"])

        outside = Path(self.temporary.name).resolve() / "diverted.py"
        outside.write_text("# diverted", encoding="utf-8")
        diverted = dict(self.import_origins)
        diverted["prediction_market_bench.agent"] = outside
        with self.assertRaisesRegex(UpstreamLockError, "escapes checkout root"):
            self.verify(observed_import_origins=diverted)

    def test_checkout_and_import_symlinks_fail_closed(self) -> None:
        target = Path(self.temporary.name).resolve() / "outside.py"
        target.write_bytes(self.bytes_by_path["prediction_market_bench/agent.py"])
        agent_path = self.root / "prediction_market_bench/agent.py"
        agent_path.unlink()
        try:
            agent_path.symlink_to(target)
        except OSError as exc:  # pragma: no cover - platform capability
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaisesRegex(UpstreamLockError, "symlink"):
            self.verify()


def _episode_document(
    episode_id: str,
    utc_date: str,
    role: str,
    *,
    venue: str = "kalshi",
    domain: str = "crypto",
    shared_file: tuple[str, int] | None = None,
) -> dict:
    files = []
    for name in sorted(REQUIRED_EPISODE_FILES):
        content = f"{episode_id}:{name}".encode("utf-8")
        digest_and_length = (_digest(content), len(content))
        if shared_file is not None and name == "metadata.json":
            digest_and_length = shared_file
        files.append(
            {
                "name": name,
                "sha256": digest_and_length[0],
                "length": digest_and_length[1],
            }
        )
    return {
        "schema": EPISODE_MANIFEST_SCHEMA,
        "episode_id": episode_id,
        "venue": venue,
        "domain": domain,
        "utc_date": utc_date,
        "role": role,
        "relative_directory": episode_id,
        "files": files,
    }


class EpisodeManifestTests(unittest.TestCase):
    def _diagnostic_validation(self) -> ManifestSetValidation:
        return validate_episode_manifests(
            [
                _episode_document(
                    "KXBTCD-26JAN2017",
                    "2026-01-17",
                    "public_diagnostic_train",
                )
            ]
        )

    def _final_validation(self) -> ManifestSetValidation:
        start = date(2027, 1, 1)
        return validate_episode_manifests(
            [
                _episode_document(
                    f"FINAL-IDENTITY-{index:02d}",
                    (start + timedelta(days=index)).isoformat(),
                    "sealed_final",
                )
                for index in range(20)
            ]
        )

    def test_four_public_episodes_are_permanently_diagnostic(self) -> None:
        public_dates = {
            "KXNFLGAME-26JAN11BUFJAC": "2026-01-11",
            "KXBTCD-26JAN2017": "2026-01-17",
            "KXNCAAF-26": "2026-01-19",
            "KXHIGHNY-26JAN20": "2026-01-20",
        }
        documents = [
            _episode_document(episode_id, public_dates[episode_id], "public_diagnostic_train")
            for episode_id in sorted(PUBLIC_DIAGNOSTIC_EPISODES)
        ]
        manifests = [EpisodeManifest.from_mapping(item) for item in documents]
        result = validate_episode_manifests(manifests)
        self.assertEqual(result.episode_count, 4)
        self.assertEqual(result.roles, ("public_diagnostic_train",))
        self.assertFalse(result.data_opened)
        self.assertFalse(result.admission_granted)
        self.assertIs(require_validated_manifest_set(result), result)
        self.assertTrue(all(not item.promotion_eligible for item in manifests))

        relabeled = deepcopy(documents[0])
        relabeled["role"] = "train"
        with self.assertRaisesRegex(EpisodeManifestError, "permanently diagnostic"):
            EpisodeManifest.from_mapping(relabeled)

    def test_manifest_role_never_grants_promotion_authority(self) -> None:
        for index, role in enumerate(sorted(EPISODE_ROLES)):
            with self.subTest(role=role):
                manifest = EpisodeManifest.from_mapping(
                    _episode_document(
                        f"SYNTH-NON-AUTHORITY-{index}",
                        f"2028-01-{index + 1:02d}",
                        role,
                    )
                )
                self.assertFalse(manifest.promotion_eligible)

    def test_direct_episode_instances_are_revalidated(self) -> None:
        document = _episode_document(
            "KXBTCD-26JAN2017", "2026-01-17", "public_diagnostic_train"
        )
        valid = EpisodeManifest.from_mapping(document)

        relabeled = replace(valid, role="train")
        with self.assertRaisesRegex(EpisodeManifestError, "permanently diagnostic"):
            validate_episode_manifests([relabeled])

        invalid_metadata = replace(valid, venue="other", domain="stocks", files=())
        with self.assertRaisesRegex(EpisodeManifestError, "venue"):
            validate_episode_manifests([invalid_metadata])

    def test_fabricated_final_validation_summary_is_not_proof(self) -> None:
        with self.assertRaisesRegex(EpisodeManifestError, "only be created"):
            ManifestSetValidation(
                manifest_set_sha256="0" * 64,
                episode_count=20,
                roles=("sealed_final",),
                sealed_final_distinct_dates=20,
            )

        fabricated = object.__new__(ManifestSetValidation)
        object.__setattr__(fabricated, "manifest_set_sha256", "0" * 64)
        object.__setattr__(fabricated, "episode_count", 20)
        object.__setattr__(fabricated, "roles", ("sealed_final",))
        object.__setattr__(fabricated, "sealed_final_distinct_dates", 20)
        object.__setattr__(fabricated, "preopen_commitments_valid", True)
        object.__setattr__(fabricated, "data_opened", False)
        object.__setattr__(fabricated, "admission_granted", False)
        with self.assertRaisesRegex(EpisodeManifestError, "authentic"):
            require_validated_manifest_set(fabricated)

    def test_only_exact_unchanged_manifest_receipt_identity_authenticates(self) -> None:
        authentic = self._diagnostic_validation()

        for transformed in (
            copy(authentic),
            deepcopy(authentic),
            pickle.loads(pickle.dumps(authentic)),
        ):
            self.assertIsNot(transformed, authentic)
            with self.assertRaisesRegex(EpisodeManifestError, "authentic"):
                require_validated_manifest_set(transformed)

        with self.assertRaisesRegex(EpisodeManifestError, "only be created"):
            replace(authentic)

        fabricated = object.__new__(ManifestSetValidation)
        for field in (
            "manifest_set_sha256",
            "episode_count",
            "roles",
            "sealed_final_distinct_dates",
            "preopen_commitments_valid",
            "data_opened",
            "admission_granted",
            "_validation_token",
        ):
            object.__setattr__(fabricated, field, getattr(authentic, field))
        with self.assertRaisesRegex(EpisodeManifestError, "authentic"):
            require_validated_manifest_set(fabricated)

    def test_copied_public_receipt_cannot_be_retargeted_to_sealed_final(self) -> None:
        copied = copy(self._diagnostic_validation())
        object.__setattr__(copied, "manifest_set_sha256", "0" * 64)
        object.__setattr__(copied, "episode_count", 20)
        object.__setattr__(copied, "roles", ("sealed_final",))
        object.__setattr__(copied, "sealed_final_distinct_dates", 20)
        with self.assertRaisesRegex(EpisodeManifestError, "authentic"):
            require_validated_manifest_set(copied)

    def test_v3_forged_sealed_final_issuer_is_absent_and_fails_closed(self) -> None:
        self.assertIsNone(
            getattr(episode_manifest_module, "_issue_manifest_set_validation", None)
        )
        selected = {
            "manifest_set_sha256": "b" * 64,
            "episode_count": 20,
            "roles": ("sealed_final",),
            "sealed_final_distinct_dates": 20,
        }
        self.assertEqual(
            _registered_caller_selected_receipt_paths(
                episode_manifest_module,
                selected,
                require_validated_manifest_set,
            ),
            (),
        )

        forged = object.__new__(ManifestSetValidation)
        for field, value in {
            **selected,
            "preopen_commitments_valid": True,
            "data_opened": False,
            "admission_granted": False,
        }.items():
            object.__setattr__(forged, field, value)
        with self.assertRaisesRegex(EpisodeManifestError, "authentic"):
            require_validated_manifest_set(forged)

    def test_every_manifest_receipt_field_is_bound_to_issuance_snapshot(self) -> None:
        cases = (
            (self._diagnostic_validation, "manifest_set_sha256", "0" * 64),
            (self._diagnostic_validation, "episode_count", 2),
            (self._diagnostic_validation, "roles", ("train",)),
            (self._final_validation, "sealed_final_distinct_dates", 21),
            (self._diagnostic_validation, "preopen_commitments_valid", False),
            (self._diagnostic_validation, "data_opened", True),
            (self._diagnostic_validation, "admission_granted", True),
            (self._diagnostic_validation, "_validation_token", object()),
        )
        for factory, field, replacement in cases:
            with self.subTest(field=field):
                authentic = factory()
                object.__setattr__(authentic, field, replacement)
                with self.assertRaisesRegex(EpisodeManifestError, "authentic"):
                    require_validated_manifest_set(authentic)

    def test_exact_files_and_relative_path_are_required(self) -> None:
        document = _episode_document("SYNTH-ONE", "2026-02-01", "train")
        document["files"].pop()
        with self.assertRaisesRegex(EpisodeManifestError, "each required"):
            EpisodeManifest.from_mapping(document)

        escaped = _episode_document("SYNTH-TWO", "2026-02-02", "train")
        escaped["relative_directory"] = "../SYNTH-TWO"
        with self.assertRaisesRegex(EpisodeManifestError, "unsafe"):
            EpisodeManifest.from_mapping(escaped)

    def test_cross_role_date_and_file_overlap_fail_closed(self) -> None:
        train = _episode_document("TRAIN-ONE", "2026-02-01", "train")
        same_date = _episode_document("DEV-ONE", "2026-02-01", "hidden_dev")
        with self.assertRaisesRegex(EpisodeManifestError, "more than one role"):
            validate_episode_manifests([train, same_date])

        shared = (train["files"][0]["sha256"], train["files"][0]["length"])
        dev = _episode_document(
            "DEV-TWO", "2026-03-01", "hidden_dev", shared_file=shared
        )
        with self.assertRaisesRegex(EpisodeManifestError, "file bytes"):
            validate_episode_manifests([train, dev])

    def test_prior_date_or_episode_exposure_cannot_be_cleaned_by_new_bytes(self) -> None:
        manifest = _episode_document("NEW-BYTES", "2026-03-01", "hidden_dev")
        prior_same_date = {
            "episode_id": "OLD-BYTES",
            "utc_date": "2026-03-01",
            "role": "public_diagnostic_train",
        }
        with self.assertRaisesRegex(EpisodeManifestError, "permanently taints"):
            validate_episode_manifests([manifest], prior_exposures=[prior_same_date])

        prior_same_id = {
            "episode_id": "NEW-BYTES",
            "utc_date": "2026-02-28",
            "role": "hidden_dev",
        }
        with self.assertRaisesRegex(EpisodeManifestError, "permanently taints"):
            validate_episode_manifests([manifest], prior_exposures=[prior_same_id])

    def test_sealed_final_requires_twenty_distinct_untouched_dates(self) -> None:
        start = date(2027, 1, 1)
        nineteen = [
            _episode_document(
                f"FINAL-{index:02d}",
                (start + timedelta(days=index)).isoformat(),
                "sealed_final",
            )
            for index in range(19)
        ]
        with self.assertRaisesRegex(EpisodeManifestError, "at least 20 distinct"):
            validate_episode_manifests(nineteen)

        same_date = [
            _episode_document(f"FINAL-SAME-{index:02d}", start.isoformat(), "sealed_final")
            for index in range(20)
        ]
        with self.assertRaisesRegex(EpisodeManifestError, "at least 20 distinct"):
            validate_episode_manifests(same_date)

        twenty = nineteen + [
            _episode_document(
                "FINAL-19", (start + timedelta(days=19)).isoformat(), "sealed_final"
            )
        ]
        result = validate_episode_manifests(twenty)
        self.assertEqual(result.sealed_final_distinct_dates, 20)
        self.assertFalse(result.data_opened)
        self.assertFalse(result.admission_granted)

    def test_chronology_is_strict(self) -> None:
        train = _episode_document("TRAIN-LATE", "2026-04-02", "train")
        dev = _episode_document("DEV-EARLY", "2026-04-01", "hidden_dev")
        with self.assertRaisesRegex(EpisodeManifestError, "must precede hidden_dev"):
            validate_episode_manifests([train, dev])

    def test_role_roots_are_exact_disjoint_and_not_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            roots = {role: base / role for role in EPISODE_ROLES}
            for root in roots.values():
                root.mkdir()
            validate_role_roots(roots)

            nested = dict(roots)
            nested["train"] = roots["public_diagnostic_train"] / "nested"
            with self.assertRaisesRegex(EpisodeManifestError, "not nested"):
                validate_role_roots(nested)

            target = base / "target"
            target.mkdir()
            link = base / "linked-final"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:  # pragma: no cover - platform capability
                self.skipTest(f"symlinks unavailable: {exc}")
            linked = dict(roots)
            linked["sealed_final"] = link
            with self.assertRaisesRegex(EpisodeManifestError, "symlink"):
                validate_role_roots(linked)

    def test_materialized_file_bytes_pass_and_symlink_escape_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            episode_id = "SYNTH-MATERIALIZED"
            episode_dir = root / episode_id
            episode_dir.mkdir()
            files = []
            for name in sorted(REQUIRED_EPISODE_FILES):
                content = f"fixture:{name}".encode("utf-8")
                (episode_dir / name).write_bytes(content)
                files.append({"name": name, "sha256": _digest(content), "length": len(content)})
            document = _episode_document(
                episode_id, "2026-02-01", "public_diagnostic_train"
            )
            document["files"] = files
            manifest = EpisodeManifest.from_mapping(document)
            self.assertEqual(verify_materialized_episode_files(manifest, root), manifest.sha256)

            outside = root.parent / f"{root.name}-outside-settlement.json"
            outside.write_bytes(b"fixture:settlement.json")
            self.addCleanup(lambda: outside.exists() and outside.unlink())
            settlement = episode_dir / "settlement.json"
            settlement.unlink()
            try:
                settlement.symlink_to(outside)
            except OSError as exc:  # pragma: no cover - platform capability
                self.skipTest(f"symlinks unavailable: {exc}")
            with self.assertRaisesRegex(EpisodeManifestError, "symlink"):
                verify_materialized_episode_files(manifest, root)


if __name__ == "__main__":
    unittest.main()
