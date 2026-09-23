"""Portable zero-network tests for the P0 candidate integration consumer."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from market_rsi import digest
from supervisor_harness import p0_candidate_admission_integration as integration
from supervisor_harness import protocol_source_release


CONTROLLED_NAMES = (
    "supervisor_harness/build_2024_train_candidate_ledger.py",
    "supervisor_harness/formal_train_admission.py",
    "supervisor_harness/p0_2024_outcome_orientation.py",
    "supervisor_harness/p0_candidate_admission_integration.py",
    "supervisor_harness/p0_polymarket_v2_cursor_acquisition.py",
    "supervisor_harness/protocol_source_release.py",
)


def pretty(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True,
                       allow_nan=False) + "\n").encode("ascii")


def run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        timeout=20, check=False)
    if completed.returncode:
        raise AssertionError("local synthetic Git fixture failed")
    return completed.stdout.strip()


def candidate_result() -> dict:
    return {
        "schema": integration.SCHEMA,
        "status": "candidate_only",
        "denominator": {
            "candidate_rows": 285,
            "mapped_oriented_rows": 284,
            "explicitly_unresolved_rows": 1,
            "cursor_candidate_streams": 284,
        },
        "unresolved_event": {
            "schedule_game_id": "2024_22_KC_PHI",
            "event_id": "17330",
            "event_slug": "nfl-kc-phi-2025-02-09",
            "reason": "moneyline_missing_or_ambiguous",
            "mapping_resolved": False,
            "orientation_resolved": False,
        },
        "claim_boundaries": {
            "candidate_only": True,
            "source_rights_verified": False,
            "provider_origin_authenticated": False,
            "network_execution_authorized": False,
            "formal_train_admitted": False,
            "dev_data_read": False,
            "final_data_read": False,
            "prediction_improvement_proven": False,
        },
    }


class PortableFixture:
    tag = "market-rsi-protocol-vfixture1"

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # macOS exposes the private temporary tree through /var; use its
        # canonical /private path so the production no-symlink walker is tested.
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.seed = self.root / "seed"
        self.bare = self.root / "local-remote.git"
        self.clone_a = self.root / "alpha-clone"
        self.clone_b = self.root / "differently-named-beta-clone"
        self.worktree = self.root / "release-worktree"
        self.artifact_root = self.root / "external-artifacts"
        self.receipt_root = self.root / "external-receipts"
        self.counter = 0

        self.seed.mkdir()
        for index, name in enumerate(CONTROLLED_NAMES):
            path = self.seed / "research" / "market_rsi" / Path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("synthetic controlled source %d\n" % index).encode())
        run_git(self.seed, "init")
        run_git(self.seed, "config", "user.name", "Fixture")
        run_git(self.seed, "config", "user.email", "fixture@example.invalid")
        run_git(self.seed, "add", ".")
        run_git(self.seed, "commit", "-m", "synthetic reviewed source")
        run_git(self.seed, "tag", "-a", self.tag, "-m", "synthetic annotated release")
        subprocess.run(
            ["git", "clone", "--bare", str(self.seed), str(self.bare)],
            capture_output=True, timeout=20, check=True)
        self._clone(self.clone_a)
        self._clone(self.clone_b)
        run_git(self.clone_a, "worktree", "add", "--detach", str(self.worktree), self.tag)

        artifact_bytes = {
            "ledger": b'{"synthetic":"ledger"}\n',
            "ledger_receipt": b'{"synthetic":"ledger-receipt"}\n',
            "catalog": b'{"synthetic":"catalog"}\n',
            "mapping": b"synthetic,mapping\r\n",
        }
        relatives = {
            "ledger": PurePosixPath("fixtures/ledger.json"),
            "ledger_receipt": PurePosixPath("fixtures/ledger-receipt.json"),
            "catalog": PurePosixPath("fixtures/catalog.json"),
            "mapping": PurePosixPath("fixtures/mapping.csv"),
        }
        pinned = {}
        for name, raw in artifact_bytes.items():
            path = self.artifact_root.joinpath(*relatives[name].parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pinned[name] = (
                relatives[name], hashlib.sha256(raw).hexdigest(), len(raw), 4096)
        self.pinned = MappingProxyType(pinned)
        self.receipt_root.mkdir()

    def _clone(self, target: Path) -> None:
        subprocess.run(
            ["git", "clone", str(self.bare), str(target)],
            capture_output=True, timeout=20, check=True)
        run_git(target, "remote", "set-url", "origin", integration.AUTHORIZED_ORIGIN)

    def extra_clone(self, name: str) -> Path:
        target = self.root / name
        self._clone(target)
        return target

    def source_hashes(self, code_root: Path) -> dict[str, str]:
        return {
            name: hashlib.sha256(
                (code_root / "research" / "market_rsi" / Path(name)).read_bytes()
            ).hexdigest()
            for name in sorted(CONTROLLED_NAMES)
        }

    @staticmethod
    def publication(repository: dict, source_hashes: dict[str, str]) -> dict:
        return {
            "schema": "market_rsi_protocol_publication_v1",
            "origin": repository["origin"],
            "tag": repository["release_tag"],
            "commit": repository["release_commit"],
            "tag_object": repository["release_tag_object"],
            "source_sha256": repository["controlled_source_sha256"],
            "source_hashes": source_hashes,
            "isolation_proven": False,
            "model_authorship_proven": False,
        }

    def receipt(self, code_root: Path, receipt_id: str, *,
                mutate=None, rebind_publication: bool = False,
                location: Path | None = None) -> tuple[Path, str, dict]:
        source_hashes = self.source_hashes(code_root)
        repository = {
            "code_root": str(code_root),
            "origin": integration.AUTHORIZED_ORIGIN,
            "integration_source_relative": str(integration.INTEGRATION_SOURCE_RELATIVE),
            "release_tag": self.tag,
            "release_commit": run_git(
                code_root, "rev-parse", "refs/tags/" + self.tag + "^{commit}"),
            "release_tag_object": run_git(
                code_root, "rev-parse", "refs/tags/" + self.tag),
            "controlled_source_sha256": digest(source_hashes),
            "controlled_source_file_count": len(source_hashes),
            "publication_receipt_sha256": "1" * 64,
        }
        repository["publication_receipt_sha256"] = digest(
            self.publication(repository, source_hashes))
        config = {
            "receipt_id": receipt_id,
            "purpose": integration.TRUST_RECEIPT_PURPOSE,
            "repository": repository,
            "artifact_store": {
                "artifact_root": str(self.artifact_root),
                "role": "read_only_pinned_candidate_bytes_only",
                "artifacts": {
                    name: {
                        "relative_path": str(relative),
                        "size_bytes": exact_size,
                        "sha256": sha256,
                    }
                    for name, (relative, sha256, exact_size, _) in self.pinned.items()
                },
            },
            "candidate_contract": dict(integration.CANDIDATE_CONTRACT),
            "claim_boundaries": dict(integration.CLAIM_BOUNDARIES),
        }
        if mutate is not None:
            mutate(config)
        if rebind_publication:
            config["repository"]["publication_receipt_sha256"] = digest(
                self.publication(config["repository"], source_hashes))
        value = {
            "schema": integration.TRUST_RECEIPT_SCHEMA,
            "config": config,
            "config_sha256": digest(config),
        }
        raw = pretty(value)
        self.counter += 1
        final = location or self.receipt_root / ("receipt-%03d.json" % self.counter)
        final.parent.mkdir(parents=True, exist_ok=True)
        temporary = final.parent / (".receipt-%03d.tmp" % self.counter)
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(descriptor, raw[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, final)
        directory = os.open(final.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return final, hashlib.sha256(raw).hexdigest(), value

    @contextmanager
    def boundary(self, code_root: Path, *, compose: bool = True,
                 module_override: tuple[object, Path] | None = None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(integration, "PINNED_FILES", self.pinned))
            stack.enter_context(patch.object(
                protocol_source_release, "FILES", CONTROLLED_NAMES))
            stack.enter_context(patch.object(
                integration, "__file__",
                str(code_root / integration.INTEGRATION_SOURCE_RELATIVE)))
            for relative, module in integration._CRITICAL_MODULES.items():
                loaded = code_root / "research" / "market_rsi" / Path(relative)
                if module_override is not None and module is module_override[0]:
                    loaded = module_override[1]
                stack.enter_context(patch.object(module, "__file__", str(loaded)))
            if compose:
                stack.enter_context(patch.object(
                    integration, "_compose_snapshot", return_value=candidate_result()))
            yield

    def call(self, code_root: Path, receipt: Path, receipt_sha256: str, *,
             module_override: tuple[object, Path] | None = None) -> dict:
        with self.boundary(code_root, module_override=module_override):
            return integration.integrate_candidate(
                trust_receipt_path=receipt,
                expected_trust_receipt_sha256=receipt_sha256)

    def close(self) -> None:
        self.temporary.cleanup()


def synthetic_snapshot() -> integration.CandidateSnapshot:
    source_artifacts = {
        name: {
            "path": str(integration.ledger_builder.SOURCE_FILES[name]),
            "sha256": integration.ledger_builder.PINNED_SHA256[name],
        }
        for name in sorted(integration.ledger_builder.SOURCE_FILES)
    }
    rows = []
    for index in range(284):
        game_id = "fixture_%03d" % index
        event_id = str(20_000 + index)
        row = {
            "candidate_id": "game:" + game_id,
            "schedule_game_id": game_id,
            "game_date": "2024-09-01",
            "source_event_id": event_id,
            "source_event_slug": "nfl-fixture-%03d" % index,
            "source_event_start_utc": "2024-09-01T00:00:00Z",
            "mapping_status": "mapped",
            "missing_reason": None,
            "source_binding": {
                "schedule_identity_sha256": "1" * 64,
                "catalog_identity_sha256": "2" * 64,
                "mapping_evidence_sha256": "3" * 64,
                "source_artifact_sha256": {
                    name: integration.ledger_builder.PINNED_SHA256[name]
                    for name in integration._MAPPED_SOURCE_ARTIFACT_FIELDS
                },
            },
        }
        row["row_commitment_sha256"] = (
            integration.ledger_builder.canonical_digest(row))
        rows.append(row)
    missing = {
        "candidate_id": "game:2024_22_KC_PHI",
        "schedule_game_id": "2024_22_KC_PHI",
        "game_date": "2025-02-09",
        "source_event_id": None,
        "source_event_slug": None,
        "source_event_start_utc": None,
        "mapping_status": "missing",
        "missing_reason": "moneyline_missing_or_ambiguous",
        "source_binding": {
            "schedule_identity_sha256": "4" * 64,
            "catalog_identity_sha256": "5" * 64,
            "mapping_failure_sha256": "6" * 64,
            "source_artifact_sha256": {
                name: integration.ledger_builder.PINNED_SHA256[name]
                for name in integration._MISSING_SOURCE_ARTIFACT_FIELDS
            },
        },
        "unmapped_catalog_event_evidence": {
            "source_event_id": "17330",
            "source_event_slug": "nfl-kc-phi-2025-02-09",
            "claimed_as_mapping": False,
        },
    }
    missing["row_commitment_sha256"] = (
        integration.ledger_builder.canonical_digest(missing))
    rows.append(missing)
    ledger = {
        "schema": integration.ledger_builder.SCHEMA,
        "season": 2024,
        "role": "train_candidate_only",
        "admission_claim": False,
        "provider_cost_usd": "0",
        "denominator": {
            "candidate_rows": 285, "mapped_rows": 284, "missing_rows": 1},
        "source_artifacts": source_artifacts,
        "rows": rows,
    }
    ledger_raw = pretty(ledger)
    ledger_sha = hashlib.sha256(ledger_raw).hexdigest()
    receipt_raw = pretty({
        "schema": "market_rsi_2024_train_candidate_denominator_receipt_v1",
        "ledger_path": str(integration.LEDGER_RELATIVE),
        "ledger_sha256": ledger_sha,
        "candidate_rows": 285,
        "mapped_rows": 284,
        "missing_rows": 1,
        "admission_claim": False,
        "provider_cost_usd": "0",
    })
    catalog = b'{"synthetic":"catalog"}\n'
    mapping = b"synthetic,mapping\r\n"
    return integration.CandidateSnapshot(
        ledger=ledger_raw, ledger_receipt=receipt_raw,
        catalog=catalog, mapping=mapping,
        sha256=MappingProxyType({
            "ledger": ledger_sha,
            "ledger_receipt": hashlib.sha256(receipt_raw).hexdigest(),
            "catalog": hashlib.sha256(catalog).hexdigest(),
            "mapping": hashlib.sha256(mapping).hexdigest(),
        }))


def synthetic_orientations(snapshot: integration.CandidateSnapshot) -> dict:
    ledger = json.loads(snapshot.ledger)
    receipts = []
    for index, row in enumerate(ledger["rows"][:-1]):
        receipts.append({
            "nflverse_game_id": row["schedule_game_id"],
            "polymarket_event_id": row["source_event_id"],
            "event_slug": row["source_event_slug"],
            "catalog_sha256": row["source_binding"]["source_artifact_sha256"][
                "catalog_payload"],
            "mapping_sha256": row["source_binding"]["source_artifact_sha256"][
                "mapped_rows"],
            "condition_id": "0x" + ("%064x" % (index + 1)),
            "away_token_id": str(index * 2 + 1),
            "home_token_id": str(index * 2 + 2),
        })
    return {
        "candidate_orientation_receipts": receipts,
        "unoriented_source_events": [{
            "event_id": "17330",
            "event_slug": "nfl-kc-phi-2025-02-09",
            "reason": "absent_from_candidate_mapping",
        }],
        "missing_orientation_inferred": False,
        "formal_train_admitted": False,
        "source_rights_verified": False,
        "network_execution_authorized": False,
    }


def mutate_snapshot(snapshot: integration.CandidateSnapshot, mutate) -> integration.CandidateSnapshot:
    ledger = json.loads(snapshot.ledger)
    mutate(ledger)
    ledger_raw = pretty(ledger)
    receipt = json.loads(snapshot.ledger_receipt)
    receipt["ledger_sha256"] = hashlib.sha256(ledger_raw).hexdigest()
    receipt_raw = pretty(receipt)
    hashes = dict(snapshot.sha256)
    hashes["ledger"] = hashlib.sha256(ledger_raw).hexdigest()
    hashes["ledger_receipt"] = hashlib.sha256(receipt_raw).hexdigest()
    return integration.CandidateSnapshot(
        ledger=ledger_raw, ledger_receipt=receipt_raw,
        catalog=snapshot.catalog, mapping=snapshot.mapping,
        sha256=MappingProxyType(hashes))


class TrustedLocalRootReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = PortableFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def setUp(self) -> None:
        integration._seen_receipt_ids.clear()

    def test_two_clones_and_worktree_pass_with_own_receipts(self) -> None:
        outputs = []
        for code_root, receipt_id in (
                (self.fixture.clone_a, "clone-alpha"),
                (self.fixture.clone_b, "clone-beta"),
                (self.fixture.worktree, "worktree-release")):
            receipt, receipt_sha, _ = self.fixture.receipt(
                code_root, receipt_id)
            output = self.fixture.call(code_root, receipt, receipt_sha)
            outputs.append(output)
            self.assertEqual(output["status"], "candidate_only")
            self.assertEqual(output["denominator"]["candidate_rows"], 285)
            self.assertEqual(output["unresolved_event"]["event_id"], "17330")
            self.assertFalse(output["claim_boundaries"]["formal_train_admitted"])
            rendered = json.dumps(output, sort_keys=True)
            self.assertNotIn(str(code_root), rendered)
            self.assertNotIn(str(self.fixture.artifact_root), rendered)
            self.assertNotIn(str(receipt), rendered)
        self.assertEqual(
            [item["trusted_local_root_receipt_id"] for item in outputs],
            ["clone-alpha", "clone-beta", "worktree-release"])

    def test_replay_is_deterministic_and_environment_and_cwd_are_ignored(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "deterministic-replay")
        original_cwd = os.getcwd()
        try:
            os.chdir(self.fixture.receipt_root)
            with patch.dict(os.environ, {
                    "MARKET_RSI_REPO": str(self.fixture.clone_b),
                    "GIT_DIR": str(self.fixture.bare),
                    "HOME": str(self.fixture.root / "attacker-home")}, clear=False):
                first = self.fixture.call(
                    self.fixture.clone_a, receipt, receipt_sha)
                second = self.fixture.call(
                    self.fixture.clone_a, receipt, receipt_sha)
        finally:
            os.chdir(original_cwd)
        self.assertEqual(first, second)

    def test_interface_is_keyword_only_explicit_and_strict(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "strict-interface")
        with self.assertRaises(TypeError):
            integration.integrate_candidate()
        with self.assertRaises(TypeError):
            integration.integrate_candidate(receipt, receipt_sha)
        with self.assertRaisesRegex(ValueError, "pathlib.Path"):
            integration.integrate_candidate(
                trust_receipt_path=str(receipt),
                expected_trust_receipt_sha256=receipt_sha)
        with self.assertRaisesRegex(ValueError, "canonical absolute"):
            integration.integrate_candidate(
                trust_receipt_path=Path("relative-receipt.json"),
                expected_trust_receipt_sha256=receipt_sha)
        with self.assertRaisesRegex(ValueError, "nonzero lowercase"):
            integration.integrate_candidate(
                trust_receipt_path=receipt,
                expected_trust_receipt_sha256="0" * 64)
        for invalid in (receipt_sha.upper(), receipt_sha[:63]):
            with self.subTest(invalid=invalid[:8]):
                with self.assertRaisesRegex(ValueError, "nonzero lowercase"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=invalid)

    def test_wrong_expected_hash_and_byte_mutation_fail_before_parsing(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "hash-authenticity")
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "caller-supplied digest"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256="1" * 64)
        receipt.write_bytes(receipt.read_bytes() + b" ")
        os.chmod(receipt, 0o600)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "caller-supplied digest"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

    def test_noncanonical_duplicate_unknown_and_internal_digest_receipts_fail(self) -> None:
        receipt, _, value = self.fixture.receipt(
            self.fixture.clone_a, "strict-json")
        del receipt
        variants = [
            json.dumps(value, sort_keys=True).encode(),
            pretty(value) + b"\n",
            b"\xef\xbb\xbf" + pretty(value),
            b'{"schema":"a","schema":"b","config":{},"config_sha256":"' +
            b"1" * 64 + b'"}\n',
        ]
        unknown = deepcopy(value)
        unknown["config"]["claim_boundaries"]["extra"] = False
        unknown["config_sha256"] = digest(unknown["config"])
        variants.append(pretty(unknown))
        bad_internal = deepcopy(value)
        bad_internal["config_sha256"] = "1" * 64
        variants.append(pretty(bad_internal))
        noncanonical_root = deepcopy(value)
        noncanonical_root["config"]["repository"]["code_root"] = "/a/../b"
        noncanonical_root["config_sha256"] = digest(noncanonical_root["config"])
        variants.append(pretty(noncanonical_root))
        with patch.object(integration, "PINNED_FILES", self.fixture.pinned):
            for raw in variants:
                with self.subTest(raw=raw[:16]):
                    with self.assertRaises(ValueError):
                        integration._validate_trust_receipt(raw)

    def test_oversize_wrong_mode_hardlink_and_unsafe_ancestor_fail(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "mode-checks")
        os.chmod(receipt, 0o644)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "mode 0600"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)
        os.chmod(receipt, 0o600)
        link = self.fixture.receipt_root / "receipt-hardlink.json"
        os.link(receipt, link)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "single-link"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)
        link.unlink()
        oversized = self.fixture.receipt_root / "oversized.json"
        oversized.write_bytes(b"x" * (integration._RECEIPT_MAX_BYTES + 1))
        os.chmod(oversized, 0o600)
        with self.assertRaisesRegex(ValueError, "bounded"):
            integration._secure_read_file(
                oversized, maximum_bytes=integration._RECEIPT_MAX_BYTES,
                receipt_leaf=True)
        original_mode = stat_mode = self.fixture.receipt_root.stat().st_mode & 0o777
        os.chmod(self.fixture.receipt_root, 0o770)
        try:
            with self.assertRaisesRegex(ValueError, "unsafe directory"):
                integration._secure_read_file(
                    receipt, maximum_bytes=integration._RECEIPT_MAX_BYTES,
                    receipt_leaf=True)
        finally:
            os.chmod(self.fixture.receipt_root, original_mode)
        self.assertEqual(stat_mode, original_mode)

    def test_wrong_owner_and_special_directory_bits_fail_closed(self) -> None:
        safe_mode = 0o040700
        for uid, mode in ((os.geteuid() + 1, safe_mode),
                          (os.geteuid(), safe_mode | 0o020),
                          (os.geteuid(), safe_mode | 0o2000)):
            value = type("SyntheticStat", (), {"st_mode": mode, "st_uid": uid})()
            with self.subTest(uid=uid, mode=mode):
                with self.assertRaisesRegex(ValueError, "unsafe directory"):
                    integration._validate_directory_stat(value)

    def test_symlink_leaf_parent_and_hardlinked_source_or_artifact_fail(self) -> None:
        area = self.fixture.root / "path-attacks"
        area.mkdir()
        target = area / "target.json"
        target.write_bytes(b"{}\n")
        leaf_link = area / "leaf-link.json"
        leaf_link.symlink_to(target)
        with self.assertRaises(ValueError):
            integration._secure_read_file(leaf_link, maximum_bytes=32)
        real_parent = area / "real-parent"
        real_parent.mkdir()
        nested = real_parent / "value.json"
        nested.write_bytes(b"{}\n")
        parent_link = area / "parent-link"
        parent_link.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            integration._secure_read_file(parent_link / "value.json", maximum_bytes=32)

        source = (self.fixture.clone_a / "research" / "market_rsi" /
                  Path(CONTROLLED_NAMES[0]))
        source_alias = area / "source-alias.py"
        os.link(source, source_alias)
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "source-hardlink")
        try:
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, "single-link"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)
        finally:
            source_alias.unlink()

        relative, _, _, maximum = self.fixture.pinned["mapping"]
        artifact = self.fixture.artifact_root.joinpath(*relative.parts)
        artifact_alias = area / "artifact-alias.csv"
        os.link(artifact, artifact_alias)
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "artifact-hardlink")
        try:
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, "single-link"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)
        finally:
            artifact_alias.unlink()

    def test_file_mutation_and_transient_ancestor_swap_fail(self) -> None:
        area = self.fixture.root / "race-attacks"
        parent = area / "parent"
        alternate = area / "alternate"
        parent.mkdir(parents=True)
        alternate.mkdir()
        path = parent / "value.json"
        raw = b'{"fixed":true}\n'
        path.write_bytes(raw)
        real_read = os.read
        changed = False

        def mutate_leaf(descriptor, size):
            nonlocal changed
            value = real_read(descriptor, size)
            if value and not changed:
                before = path.stat()
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
                changed = True
            return value

        with patch.object(integration.os, "read", side_effect=mutate_leaf):
            with self.assertRaisesRegex(ValueError, "file changed"):
                integration._secure_read_file(path, maximum_bytes=128)

        path.write_bytes(raw)
        parked = area / "parent-parked"
        swapped = False

        def swap_ancestor(descriptor, size):
            nonlocal swapped
            value = real_read(descriptor, size)
            if value and not swapped:
                parent.rename(parked)
                parent.symlink_to(alternate, target_is_directory=True)
                parent.unlink()
                parked.rename(parent)
                swapped = True
            return value

        with patch.object(integration.os, "read", side_effect=swap_ancestor):
            with self.assertRaisesRegex(ValueError, "ancestor directory"):
                integration._secure_read_file(path, maximum_bytes=128)

    def test_equal_nested_and_receipt_inside_roots_fail(self) -> None:
        cases = []
        cases.append(lambda config: config["artifact_store"].update(
            artifact_root=str(self.fixture.clone_a)))
        nested = self.fixture.clone_a / "nested-artifacts"
        nested.mkdir()
        cases.append(lambda config: config["artifact_store"].update(
            artifact_root=str(nested)))
        for index, mutate in enumerate(cases):
            receipt, receipt_sha, _ = self.fixture.receipt(
                self.fixture.clone_a, "separation-%d" % index, mutate=mutate)
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, "must remain separate"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)
        inside = self.fixture.clone_a / "inside-receipt.json"
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "receipt-inside", location=inside)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "must remain separate"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

    def test_wrong_origin_lightweight_missing_or_moved_tag_fail(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "actual-wrong-origin")
        run_git(self.fixture.clone_a, "remote", "set-url", "origin",
                "https://example.invalid/old.git")
        try:
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, "authorized standalone"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)
        finally:
            run_git(self.fixture.clone_a, "remote", "set-url", "origin",
                    integration.AUTHORIZED_ORIGIN)

        light_tag = "market-rsi-protocol-vlight1"
        run_git(self.fixture.clone_a, "tag", light_tag)
        def lightweight(config):
            repo = config["repository"]
            repo["release_tag"] = light_tag
            repo["release_commit"] = run_git(
                self.fixture.clone_a, "rev-parse", light_tag + "^{commit}")
            repo["release_tag_object"] = run_git(
                self.fixture.clone_a, "rev-parse", light_tag)
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "lightweight-tag", mutate=lightweight,
            rebind_publication=True)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "annotated"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

        def missing(config):
            repo = config["repository"]
            repo["release_tag"] = "market-rsi-protocol-vmissing1"
            repo["release_commit"] = "1" * 40
            repo["release_tag_object"] = "2" * 40
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "missing-tag", mutate=missing,
            rebind_publication=True)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "Git identity"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "moved-tag",
            mutate=lambda config: config["repository"].update(
                release_tag_object="3" * 40),
            rebind_publication=True)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "tag object or commit"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "wrong-release-commit",
            mutate=lambda config: config["repository"].update(
                release_commit="4" * 40),
            rebind_publication=True)
        with self.fixture.boundary(self.fixture.clone_a):
            with self.assertRaisesRegex(ValueError, "tag object or commit"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

    def test_raw_origin_rewrite_and_multiple_values_fail(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "raw-origin-rewrite")
        malicious = "https://attacker.invalid/market-rsi.git"
        rewrite_key = "url.%s.insteadOf" % integration.AUTHORIZED_ORIGIN
        run_git(self.fixture.clone_a, "remote", "set-url", "origin", malicious)
        run_git(self.fixture.clone_a, "config", "--local", rewrite_key, malicious)
        try:
            # This is the exact old bypass: Git presents the authorized URL
            # after insteadOf even though the raw repository value is hostile.
            self.assertEqual(
                run_git(self.fixture.clone_a, "remote", "get-url", "origin"),
                integration.AUTHORIZED_ORIGIN)
            self.assertEqual(
                run_git(
                    self.fixture.clone_a, "config", "--local", "--no-includes",
                    "--get-all", "remote.origin.url"),
                malicious)
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, "authorized standalone"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)
        finally:
            run_git(self.fixture.clone_a, "config", "--local", "--unset-all",
                    rewrite_key)
            run_git(self.fixture.clone_a, "remote", "set-url", "origin",
                    integration.AUTHORIZED_ORIGIN)

        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "multiple-raw-origins")
        run_git(self.fixture.clone_a, "config", "--local", "--add",
                "remote.origin.url", integration.AUTHORIZED_ORIGIN)
        try:
            origins = subprocess.run(
                ["git", "-C", str(self.fixture.clone_a), "config", "--local",
                 "--no-includes", "--get-all", "remote.origin.url"],
                capture_output=True, text=True, timeout=20, check=True
            ).stdout.splitlines()
            self.assertEqual(origins, [integration.AUTHORIZED_ORIGIN] * 2)
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, "authorized standalone"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)
        finally:
            run_git(self.fixture.clone_a, "config", "--local", "--unset-all",
                    "remote.origin.url")
            run_git(self.fixture.clone_a, "config", "--local", "--add",
                    "remote.origin.url", integration.AUTHORIZED_ORIGIN)

    def test_replace_ref_cannot_substitute_tagged_source(self) -> None:
        replaced = self.fixture.extra_clone("replacement-object-attack")
        run_git(replaced, "config", "user.name", "Fixture")
        run_git(replaced, "config", "user.email", "fixture@example.invalid")
        changed = (replaced / "research" / "market_rsi" /
                   Path(CONTROLLED_NAMES[0]))
        changed.write_bytes(changed.read_bytes() + b"replacement bytes\n")
        run_git(replaced, "add", str(changed))
        run_git(replaced, "commit", "-m", "replacement source")
        released_commit = run_git(
            replaced, "rev-parse", "refs/tags/%s^{commit}" % self.fixture.tag)
        replacement_commit = run_git(replaced, "rev-parse", "HEAD")
        run_git(replaced, "replace", released_commit, replacement_commit)
        receipt, receipt_sha, _ = self.fixture.receipt(
            replaced, "replacement-object-substitution")
        with self.fixture.boundary(replaced):
            with self.assertRaisesRegex(ValueError, "release differs"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

    def test_repository_fsmonitor_cannot_execute(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "fsmonitor-disabled")
        hook = self.fixture.root / "malicious-fsmonitor.sh"
        marker = self.fixture.root / "fsmonitor-executed"
        hook.write_text(
            "#!/bin/sh\n"
            "printf executed > %s\n"
            "printf 'token\\0'\n" % marker)
        hook.chmod(0o700)
        run_git(self.fixture.clone_a, "config", "--local", "core.fsmonitor",
                str(hook))
        try:
            # Establish that the configured command is executable by an
            # ordinary status call, then prove the consumer never invokes it.
            run_git(self.fixture.clone_a, "status", "--porcelain")
            self.assertEqual(marker.read_text(), "executed")
            marker.unlink()
            output = self.fixture.call(
                self.fixture.clone_a, receipt, receipt_sha)
            self.assertEqual(output["status"], "candidate_only")
            self.assertFalse(marker.exists())
        finally:
            run_git(self.fixture.clone_a, "config", "--local", "--unset-all",
                    "core.fsmonitor")

    def test_dirty_source_count_digest_tag_mismatch_and_publication_fail(self) -> None:
        source = (self.fixture.clone_a / "research" / "market_rsi" /
                  Path(CONTROLLED_NAMES[0]))
        original = source.read_bytes()
        source.write_bytes(original + b"dirty\n")
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "dirty-source")
        try:
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, "not clean"):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)
        finally:
            source.write_bytes(original)

        for label, mutation, message in (
            ("wrong-count",
             lambda config: config["repository"].update(
                 controlled_source_file_count=len(CONTROLLED_NAMES) + 1),
             "count or digest"),
            ("wrong-digest",
             lambda config: config["repository"].update(
                 controlled_source_sha256="4" * 64),
             "count or digest"),
            ("wrong-publication",
             lambda config: config["repository"].update(
                 publication_receipt_sha256="5" * 64),
             "publication receipt"),
        ):
            receipt, receipt_sha, _ = self.fixture.receipt(
                self.fixture.clone_a, label, mutate=mutation)
            with self.fixture.boundary(self.fixture.clone_a):
                with self.assertRaisesRegex(ValueError, message):
                    integration.integrate_candidate(
                        trust_receipt_path=receipt,
                        expected_trust_receipt_sha256=receipt_sha)

        mismatch = self.fixture.extra_clone("tag-current-mismatch")
        run_git(mismatch, "config", "user.name", "Fixture")
        run_git(mismatch, "config", "user.email", "fixture@example.invalid")
        changed = mismatch / "research" / "market_rsi" / Path(CONTROLLED_NAMES[0])
        changed.write_bytes(changed.read_bytes() + b"new reviewed bytes\n")
        run_git(mismatch, "add", str(changed))
        run_git(mismatch, "commit", "-m", "post-tag source change")
        receipt, receipt_sha, _ = self.fixture.receipt(
            mismatch, "tag-current-mismatch")
        with self.fixture.boundary(mismatch):
            with self.assertRaisesRegex(ValueError, "release differs"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

    def test_mixed_loaded_source_and_cross_root_receipt_fail(self) -> None:
        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "mixed-module")
        alternate = (self.fixture.clone_b / "research" / "market_rsi" /
                     Path("supervisor_harness/formal_train_admission.py"))
        with self.assertRaisesRegex(ValueError, "another checkout"):
            self.fixture.call(
                self.fixture.clone_a, receipt, receipt_sha,
                module_override=(integration.formal_train_admission, alternate))

        receipt, receipt_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "clone-alpha-cross-use")
        with self.fixture.boundary(self.fixture.clone_b):
            with self.assertRaisesRegex(ValueError, "another checkout"):
                integration.integrate_candidate(
                    trust_receipt_path=receipt,
                    expected_trust_receipt_sha256=receipt_sha)

    def test_artifact_path_size_hash_extra_and_substitution_fail(self) -> None:
        mutations = []
        for name in self.fixture.pinned:
            mutations.extend((
                lambda config, name=name: config["artifact_store"]["artifacts"][
                    name].update(relative_path="fixtures/other.bin"),
                lambda config, name=name: config["artifact_store"]["artifacts"][
                    name].update(size_bytes=999),
                lambda config, name=name: config["artifact_store"]["artifacts"][
                    name].update(sha256="6" * 64),
            ))
        mutations.extend((
            lambda config: config["artifact_store"]["artifacts"].update(
                extra=deepcopy(config["artifact_store"]["artifacts"]["mapping"])),
            lambda config: config["artifact_store"]["artifacts"].pop("mapping"),
        ))
        with patch.object(integration, "PINNED_FILES", self.fixture.pinned):
            for index, mutation in enumerate(mutations):
                _, _, value = self.fixture.receipt(
                    self.fixture.clone_a, "artifact-binding-%d" % index,
                    mutate=mutation)
                with self.subTest(index=index):
                    with self.assertRaises(ValueError):
                        integration._validate_trust_receipt(pretty(value))

        relative, sha256, size, maximum = self.fixture.pinned["catalog"]
        path = self.fixture.artifact_root.joinpath(*relative.parts)
        original = path.read_bytes()
        real_read = os.read
        changed = False
        def substitute(descriptor, count):
            nonlocal changed
            value = real_read(descriptor, count)
            if value and not changed:
                before = path.stat()
                path.write_bytes(original)
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
                changed = True
            return value
        with patch.object(integration.os, "read", side_effect=substitute):
            with self.assertRaisesRegex(ValueError, "file changed"):
                integration._secure_read_file(
                    path, maximum_bytes=maximum, exact_size=size,
                    expected_sha256=sha256)

    def test_receipt_id_reuse_with_different_bytes_fails(self) -> None:
        first, first_sha, _ = self.fixture.receipt(
            self.fixture.clone_a, "one-batch-id")
        self.fixture.call(self.fixture.clone_a, first, first_sha)
        second, second_sha, _ = self.fixture.receipt(
            self.fixture.clone_b, "one-batch-id")
        with self.assertRaisesRegex(ValueError, "reused with different bytes"):
            self.fixture.call(self.fixture.clone_b, second, second_sha)

    def test_receipt_authority_aliases_and_candidate_drift_fail(self) -> None:
        mutations = (
            lambda config: config["claim_boundaries"].update(
                network_execution_authorized=True),
            lambda config: config["claim_boundaries"].update(
                provider_verified=True),
            lambda config: config["candidate_contract"].update(mapped_rows=285),
            lambda config: config["candidate_contract"].update(
                unresolved_event_id=None),
        )
        with patch.object(integration, "PINNED_FILES", self.fixture.pinned):
            for index, mutation in enumerate(mutations):
                _, _, value = self.fixture.receipt(
                    self.fixture.clone_a, "authority-%d" % index,
                    mutate=mutation)
                with self.subTest(index=index):
                    with self.assertRaises(ValueError):
                        integration._validate_trust_receipt(pretty(value))

    def test_no_real_release_or_canary_is_fabricated(self) -> None:
        source = Path(integration.__file__).read_text()
        self.assertNotIn("ls-remote", source)
        self.assertNotIn("CANONICAL_CODE_CHECKOUT", source)
        self.assertNotIn("PRESERVED_ARTIFACT_ROOT", source)
        self.assertNotIn(os.sep + "Users" + os.sep, source)
        with self.assertRaises(TypeError):
            integration.integrate_candidate()


class CandidateSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = synthetic_snapshot()

    @staticmethod
    def recommit(row: dict) -> None:
        row.pop("row_commitment_sha256", None)
        row["row_commitment_sha256"] = (
            integration.ledger_builder.canonical_digest(row))

    def compose(self, snapshot: integration.CandidateSnapshot) -> dict:
        with patch.object(
                integration.orientation, "verify_preserved_2024_orientation",
                return_value=synthetic_orientations(self.snapshot)):
            return integration._compose_snapshot(snapshot)

    def test_synthetic_candidate_remains_285_284_1_and_unresolved(self) -> None:
        value = self.compose(self.snapshot)
        self.assertEqual(value["denominator"], {
            "candidate_rows": 285,
            "mapped_oriented_rows": 284,
            "explicitly_unresolved_rows": 1,
            "cursor_candidate_streams": 284,
        })
        self.assertEqual(value["unresolved_event"]["event_id"], "17330")
        self.assertFalse(value["unresolved_event"]["mapping_resolved"])
        self.assertFalse(value["claim_boundaries"]["formal_train_admitted"])
        self.assertFalse(value["claim_boundaries"]["network_execution_authorized"])

    def test_all_prior_authority_aliases_fail(self) -> None:
        for field in (
                "rights_verified", "provider_verified",
                "network_access_authorized", "formal_training_authorized",
                "improvement_claim_allowed"):
            def mutate(ledger, field=field):
                ledger["rows"][0][field] = True
                self.recommit(ledger["rows"][0])
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "authority escalation"):
                    self.compose(mutate_snapshot(self.snapshot, mutate))

    def test_any_dev_or_final_field_fails_even_when_false(self) -> None:
        for field in ("dev_score", "Final", "final_data_read"):
            def mutate(ledger, field=field):
                ledger["rows"][0][field] = False
                self.recommit(ledger["rows"][0])
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "Dev/Final"):
                    self.compose(mutate_snapshot(self.snapshot, mutate))

    def test_denominator_and_event_17330_cannot_drift(self) -> None:
        with self.assertRaises(ValueError):
            self.compose(mutate_snapshot(
                self.snapshot,
                lambda ledger: ledger["denominator"].update(mapped_rows=285)))
        def infer(ledger):
            row = ledger["rows"][-1]
            row["source_event_id"] = "17330"
            row["source_event_slug"] = "nfl-kc-phi-2025-02-09"
            self.recommit(row)
        with self.assertRaisesRegex(ValueError, "explicitly unresolved"):
            self.compose(mutate_snapshot(self.snapshot, infer))

    def test_orientation_identity_mismatch_and_formal_registry_fail(self) -> None:
        def mismatch(ledger):
            row = ledger["rows"][0]
            row["source_event_id"] = "999999"
            self.recommit(row)
        with self.assertRaisesRegex(ValueError, "ledger/orientation identity"):
            self.compose(mutate_snapshot(self.snapshot, mismatch))
        with patch.object(
                integration.formal_train_admission,
                "TRUSTED_RECEIPT_COMMITMENTS", {"unexpected": {}}):
            with self.assertRaisesRegex(ValueError, "cannot consume formal"):
                self.compose(self.snapshot)

    def test_reviewed_modules_and_tests_remain_controlled(self) -> None:
        required = {
            "supervisor_harness/build_2024_train_candidate_ledger.py",
            "supervisor_harness/test_build_2024_train_candidate_ledger.py",
            "supervisor_harness/p0_2024_outcome_orientation.py",
            "supervisor_harness/test_p0_2024_outcome_orientation.py",
            "supervisor_harness/formal_train_admission.py",
            "supervisor_harness/test_formal_train_admission.py",
            "supervisor_harness/test_supervisor_watchdog.py",
            "supervisor_harness/p0_polymarket_v2_cursor_acquisition.py",
            "supervisor_harness/test_p0_polymarket_v2_cursor_acquisition.py",
            "supervisor_harness/p0_candidate_admission_integration.py",
            "supervisor_harness/test_p0_candidate_admission_integration.py",
        }
        self.assertTrue(required.issubset(protocol_source_release.PROTOCOL_FILES))


if __name__ == "__main__":
    unittest.main()
