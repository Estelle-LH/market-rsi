from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from market_rsi import digest, file_hash
from supervisor_harness import p0_gate1_controller_live_entry as entry
from supervisor_harness import gate1_canary_receipt
from supervisor_harness import p0_gate1_controller_supervisor_parent as parent_module
from supervisor_harness import protocol_source_release
from supervisor_harness.p0_gate1_controller_adapter import expected_packet
from supervisor_harness.p0_gate1_controller_supervisor_parent import (
    CANARY_CHILD_ENTRY, CANARY_RELEASE_TAG, PROGRESS_TIMEOUT_SECONDS,
    _FIRST_CANARY_BOOTSTRAP_CAPABILITY, _child_command, _preflight_canary,
    _preflight_packet, parser, run, verified_first_canary_publication,
)
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import frozen_catalog_bytes
from supervisor_harness.p0_gate1_trade_query import SYNTHETIC_CATALOG_COMMITMENT_ID


class Gate1ControllerSupervisorParentTests(unittest.TestCase):
    REAL_TAG = "market-rsi-protocol-v9.9.9"
    COMMIT = "3" * 40
    TAG_OBJECT = "4" * 40

    def publication(self) -> dict:
        source_hashes = protocol_source_release.source_hashes()
        return {
            "schema": "market_rsi_protocol_publication_v1",
            "origin": protocol_source_release.ORIGIN,
            "tag": self.REAL_TAG,
            "commit": self.COMMIT,
            "tag_object": self.TAG_OBJECT,
            "source_sha256": digest(source_hashes),
            "source_hashes": source_hashes,
            "isolation_proven": False,
            "model_authorship_proven": False,
        }

    def bootstrap_args(self, root: Path) -> tuple[SimpleNamespace, object, dict]:
        packet = root / "controller-input.json"
        packet.write_text(json.dumps(expected_packet()))
        runtime = root / "runtime.json"
        runtime.write_text('{"schema":"test-runtime"}\n')
        publication = self.publication()
        with patch.object(
                protocol_source_release, "verify_published",
                return_value=publication) as verified:
            token = verified_first_canary_publication(
                release_tag=self.REAL_TAG,
                expected_source_sha256=publication["source_sha256"])
        verified.assert_called_once_with(
            tag=self.REAL_TAG,
            expected_source_sha256=publication["source_sha256"])
        bootstrap = root / gate1_canary_receipt.FIRST_CANARY_BOOTSTRAP_FILE
        bootstrap.write_text(json.dumps(
            gate1_canary_receipt.first_canary_bootstrap_document(
                publication=publication,
                runtime_sha256=digest(json.loads(runtime.read_text())),
                child_entry=CANARY_CHILD_ENTRY),
            sort_keys=True, separators=(",", ":")) + "\n")
        args = SimpleNamespace(
            cycle_id="gate1-first-bootstrap-test",
            packet=packet,
            expected_packet_file_sha256=file_hash(packet),
            expected_packet_canonical_sha256=digest(expected_packet()),
            runtime_receipt=runtime,
            prior_canary_receipt=bootstrap,
            prior_canary_sha256=file_hash(bootstrap),
            release_tag=self.REAL_TAG,
            expected_release_commit=self.COMMIT,
            expected_release_tag_object=self.TAG_OBJECT,
            expected_source_sha256=publication["source_sha256"],
            supervisor_root=root / "supervisor",
        )
        return args, token, publication

    def test_first_canary_bootstrap_preflight_is_exact_and_programmatic(self):
        with tempfile.TemporaryDirectory() as directory:
            args, token, publication = self.bootstrap_args(
                Path(directory).resolve())
            verified = _preflight_canary(
                args, child_entry=CANARY_CHILD_ENTRY,
                bootstrap_capability=_FIRST_CANARY_BOOTSTRAP_CAPABILITY,
                verified_publication=token)
            self.assertTrue(verified["passed"])
            self.assertEqual(verified["provider_calls"], 0)
            self.assertEqual(verified["publication"], publication)
            destinations = {action.dest for action in parser()._actions}
            self.assertNotIn("first_canary_bootstrap", destinations)
            self.assertNotIn("child_entry", destinations)

    def test_publication_factory_rejects_synthetic_cross_release_and_forgery(self):
        exact = self.publication()
        cases = []
        synthetic = dict(exact)
        synthetic["tag"] = CANARY_RELEASE_TAG
        cases.append((CANARY_RELEASE_TAG, synthetic, "real first-canary"))
        cross = dict(exact)
        cross["tag"] = "market-rsi-protocol-v9.9.8"
        cases.append((self.REAL_TAG, cross, "exact release"))
        forged = json.loads(json.dumps(exact))
        forged["source_hashes"][
            gate1_canary_receipt.FIRST_CANARY_CHILD_RELATIVE] = "9" * 64
        forged["source_sha256"] = digest(forged["source_hashes"])
        cases.append((self.REAL_TAG, forged, "child"))
        stale = json.loads(json.dumps(exact))
        stale["source_hashes"].pop(
            gate1_canary_receipt.FIRST_CANARY_CHILD_RELATIVE)
        stale["source_sha256"] = digest(stale["source_hashes"])
        cases.append((self.REAL_TAG, stale, "child"))
        for requested_tag, publication, message in cases:
            with self.subTest(message=message), patch.object(
                    protocol_source_release, "verify_published",
                    return_value=publication):
                with self.assertRaisesRegex(ValueError, message):
                    verified_first_canary_publication(
                        release_tag=requested_tag,
                        expected_source_sha256=publication["source_sha256"])

    def test_mutated_verified_publication_fails_before_root_or_process(self):
        with tempfile.TemporaryDirectory() as directory:
            args, token, publication = self.bootstrap_args(
                Path(directory).resolve())
            publication["commit"] = "8" * 40
            token._raw = json.dumps(
                publication, sort_keys=True, separators=(",", ":"))
            with patch.object(parent_module.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(ValueError, "bootstrap capability"):
                    run(
                        args, child_entry=CANARY_CHILD_ENTRY,
                        bootstrap_capability=(
                            _FIRST_CANARY_BOOTSTRAP_CAPABILITY),
                        verified_publication=token)
            popen.assert_not_called()
            self.assertFalse(args.supervisor_root.exists())

    def test_first_canary_arbitrary_capability_release_and_child_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            args, token, _ = self.bootstrap_args(Path(directory).resolve())
            for capability, child, release in (
                    (object(), CANARY_CHILD_ENTRY, self.REAL_TAG),
                    (_FIRST_CANARY_BOOTSTRAP_CAPABILITY,
                     Path(__file__).resolve(), self.REAL_TAG),
                    (_FIRST_CANARY_BOOTSTRAP_CAPABILITY, CANARY_CHILD_ENTRY,
                     "market-rsi-protocol-v0.1.22")):
                args.release_tag = release
                with self.assertRaisesRegex(
                        ValueError, "bootstrap capability"):
                    _preflight_canary(
                        args, child_entry=child,
                        bootstrap_capability=capability,
                        verified_publication=token)
                args.release_tag = self.REAL_TAG
            self.assertFalse(args.supervisor_root.exists())

    def test_bootstrap_rejection_precedes_parent_root_and_process(self):
        mutations = ("release", "child", "prior")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                args, token, _ = self.bootstrap_args(Path(directory).resolve())
                child = CANARY_CHILD_ENTRY
                message = "bootstrap capability"
                if mutation == "release":
                    args.release_tag = "market-rsi-protocol-v0.1.22"
                elif mutation == "child":
                    child = Path(__file__).resolve()
                else:
                    args.prior_canary_sha256 = "9" * 64
                    message = "bootstrap hash mismatch"
                with patch.object(parent_module.subprocess, "Popen") as popen:
                    with self.assertRaisesRegex(ValueError, message):
                        run(
                            args, child_entry=child,
                            bootstrap_capability=(
                                _FIRST_CANARY_BOOTSTRAP_CAPABILITY),
                            verified_publication=token)
                popen.assert_not_called()
                self.assertFalse(args.supervisor_root.exists())

    def test_bootstrap_proof_without_capability_is_not_a_prior_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, _ = self.bootstrap_args(Path(directory).resolve())
            with self.assertRaisesRegex(ValueError, "canary receipt"):
                _preflight_canary(args, child_entry=CANARY_CHILD_ENTRY)

    def test_child_command_binds_exact_entry_and_claim_without_secrets(self):
        args = SimpleNamespace(
            root=Path("/tmp/out"), claim_root=Path("/tmp/claims"),
            global_state_root=Path("/tmp/state"),
            decision_doc=Path("/tmp/decision"), budget_root=Path("/tmp/budget"),
            packet=Path("/tmp/packet"), runtime_receipt=Path("/tmp/runtime"),
            env_file=Path("/tmp/env"), tokenizer_cache=Path("/tmp/cache"),
            catalog=Path("/tmp/catalog"),
            expected_catalog_file_sha256="6" * 64,
            catalog_commitment_id="reviewed-catalog",
            experiment_id="experiment", budget_cap_usd="200",
            cycle_id="gate1-parent-test",
            expected_packet_file_sha256="1" * 64,
            expected_packet_canonical_sha256="2" * 64,
            expected_head_sha256="2" * 64,
            expected_decision_sha256="3" * 64,
            prior_canary_receipt=Path("/tmp/canary-result.json"),
            prior_canary_sha256="4" * 64,
            release_tag="market-rsi-protocol-v0.1.11",
            expected_release_commit="7" * 40,
            expected_release_tag_object="8" * 40,
            expected_source_sha256="5" * 64,
        )
        claim = Path("/tmp/supervisor-claim")
        command = _child_command(args, claim)
        self.assertEqual(command[1], str(Path(entry.__file__).resolve()))
        self.assertEqual(command.count("--supervisor-claim"), 1)
        self.assertEqual(command.count("--release-tag"), 1)
        self.assertEqual(command.count("--expected-source-sha256"), 1)
        self.assertIn(str(claim), command)
        self.assertNotIn("TINKER_API_KEY", " ".join(command))
        self.assertIn("--catalog-commitment-id", command)
        args.catalog = None
        args.expected_catalog_file_sha256 = None
        args.catalog_commitment_id = None
        review_only_command = _child_command(args, claim)
        self.assertNotIn("--catalog", review_only_command)
        self.assertNotIn("--catalog-commitment-id", review_only_command)

    def test_canary_child_override_is_programmatic_and_exact(self):
        args = SimpleNamespace(
            root=Path("/tmp/out"), claim_root=Path("/tmp/claims"),
            global_state_root=Path("/tmp/state"),
            decision_doc=Path("/tmp/decision"), budget_root=Path("/tmp/budget"),
            packet=Path("/tmp/packet"), runtime_receipt=Path("/tmp/runtime"),
            env_file=Path("/tmp/env"), tokenizer_cache=Path("/tmp/cache"),
            catalog=Path("/tmp/catalog"),
            expected_catalog_file_sha256="6" * 64,
            catalog_commitment_id="synthetic-canary",
            experiment_id="experiment", budget_cap_usd="200",
            cycle_id="gate1-parent-test",
            expected_packet_file_sha256="1" * 64,
            expected_packet_canonical_sha256="2" * 64,
            expected_head_sha256="2" * 64,
            expected_decision_sha256="3" * 64,
            prior_canary_receipt=Path("/tmp/canary-result.json"),
            prior_canary_sha256="4" * 64,
            release_tag=CANARY_RELEASE_TAG,
            expected_release_commit="7" * 40,
            expected_release_tag_object="8" * 40,
            expected_source_sha256="5" * 64,
        )
        command = _child_command(
            args, Path("/tmp/claim"), child_entry=CANARY_CHILD_ENTRY)
        self.assertEqual(command[1], str(CANARY_CHILD_ENTRY))
        self.assertEqual(command.count("--supervisor-claim"), 1)
        self.assertNotIn("--child-entry", command)

    def test_arbitrary_programmatic_child_override_is_rejected(self):
        args = SimpleNamespace(release_tag=CANARY_RELEASE_TAG)
        with self.assertRaisesRegex(ValueError, "exact Gate 1"):
            _child_command(
                args, Path("/tmp/claim"), child_entry=Path(__file__).resolve())

    def test_real_pretty_packet_binds_file_and_canonical_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            args = SimpleNamespace(
                packet=packet,
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256=digest(expected_packet()),
            )
            result = _preflight_packet(args)
            self.assertEqual(result["packet_file_sha256"], file_hash(packet))
            self.assertEqual(
                result["packet_canonical_sha256"], digest(expected_packet()))

    def test_file_hash_mismatch_stops_parent_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            args = SimpleNamespace(
                packet=packet,
                expected_packet_file_sha256="1" * 64,
                expected_packet_canonical_sha256=digest(expected_packet()),
            )
            with self.assertRaisesRegex(ValueError, "packet file differs"):
                _preflight_packet(args)

    def test_canonical_hash_mismatch_stops_parent_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            args = SimpleNamespace(
                packet=packet,
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256="2" * 64,
            )
            with self.assertRaisesRegex(ValueError, "canonical packet differs"):
                _preflight_packet(args)

    def test_mismatch_stops_before_parent_root_or_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            packet = parent / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            supervisor_root = parent / "must-not-exist"
            args = SimpleNamespace(
                cycle_id="gate1-prelaunch-mismatch",
                packet=packet,
                expected_packet_file_sha256="3" * 64,
                expected_packet_canonical_sha256=digest(expected_packet()),
                supervisor_root=supervisor_root,
            )
            with patch(
                    "supervisor_harness.p0_gate1_controller_supervisor_parent."
                    "subprocess.Popen") as popen:
                with self.assertRaisesRegex(ValueError, "packet file differs"):
                    run(args)
            popen.assert_not_called()
            self.assertFalse(supervisor_root.exists())

    def test_synthetic_catalog_stops_before_parent_root_or_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            packet = base / "controller-input.json"
            packet.write_text(json.dumps(expected_packet()))
            catalog = base / "synthetic-catalog.json"
            catalog.write_bytes(frozen_catalog_bytes())
            args = SimpleNamespace(
                cycle_id="gate1-synthetic-rejected",
                packet=packet,
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256=digest(expected_packet()),
                catalog=catalog,
                expected_catalog_file_sha256=file_hash(catalog),
                catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID,
                supervisor_root=base / "supervisor",
            )
            with patch.object(parent_module.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(ValueError, "reviewed real Train"):
                    run(args)
            popen.assert_not_called()
            self.assertFalse(args.supervisor_root.exists())

    def test_canary_rejection_stops_before_parent_root_or_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            packet = base / "controller-input.json"
            packet.write_text(json.dumps(expected_packet()))
            runtime = base / "runtime.json"
            runtime.write_text('{"schema":"test-runtime"}\n')
            args = SimpleNamespace(
                cycle_id="gate1-canary-rejected",
                packet=packet,
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256=digest(expected_packet()),
                catalog=None, expected_catalog_file_sha256=None,
                catalog_commitment_id=None,
                runtime_receipt=runtime,
                supervisor_root=base / "supervisor",
            )
            with (patch.object(parent_module, "_preflight_canary",
                               side_effect=ValueError("canary rejected")),
                  patch.object(parent_module.subprocess, "Popen") as popen):
                with self.assertRaisesRegex(ValueError, "canary rejected"):
                    run(args)
            popen.assert_not_called()
            self.assertFalse(args.supervisor_root.exists())

    def test_parent_progress_window_covers_full_provider_deadline(self):
        self.assertGreater(
            PROGRESS_TIMEOUT_SECONDS, entry.adapter.SAMPLE_TIMEOUT_SECONDS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / "controller-input.json"
            packet.write_text(
                json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
            args = SimpleNamespace(
                root=root / "gate1-progress-window",
                claim_root=root / "claims",
                global_state_root=root / "state",
                decision_doc=root / "decision.md",
                budget_root=root / "budget",
                packet=packet,
                runtime_receipt=root / "runtime.json",
                env_file=root / "offline.env",
                tokenizer_cache=root / "tokenizer-cache",
                catalog=root / "catalog.json",
                expected_catalog_file_sha256="6" * 64,
                catalog_commitment_id="reviewed-catalog",
                experiment_id="experiment", budget_cap_usd="200",
                cycle_id="gate1-progress-window",
                expected_packet_file_sha256=file_hash(packet),
                expected_packet_canonical_sha256=digest(expected_packet()),
                expected_head_sha256="2" * 64,
                expected_decision_sha256="3" * 64,
                prior_canary_receipt=root / "canary-result.json",
                prior_canary_sha256="4" * 64,
                release_tag="market-rsi-protocol-v0.1.13",
                expected_release_commit="7" * 40,
                expected_release_tag_object="8" * 40,
                expected_source_sha256="5" * 64,
                supervisor_root=root / "supervisor",
            )
            args.claim_root.mkdir()
            child = Mock(pid=321)
            child.poll.return_value = 0
            with (
                patch(
                    "supervisor_harness."
                    "p0_gate1_controller_supervisor_parent.subprocess.Popen",
                    return_value=child),
                patch.object(
                    parent_module.supervisor,
                    "stable_process_command_sha256", return_value="6" * 64),
                patch.object(
                    parent_module.supervisor, "supervise_started",
                    return_value={"passed": True}) as supervised,
                patch.object(entry, "_reviewed_catalog",
                             return_value=(b"{}", "test")),
                patch.object(parent_module, "_preflight_canary",
                             return_value={"passed": True}),
            ):
                self.assertEqual(run(args), {"passed": True})
            self.assertEqual(
                supervised.call_args.kwargs["progress_timeout_seconds"],
                PROGRESS_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
