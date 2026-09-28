import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash
from supervisor_harness import gate1_canary_receipt
from supervisor_harness import p0_gate1_controller_cli_canary_child as child
from supervisor_harness import p0_gate1_controller_live_entry as live_entry
from supervisor_harness import p0_gate1_controller_supervisor_parent as parent
from supervisor_harness import protocol_source_release
from supervisor_harness import run_p0_gate1_controller_production_cli_canary as runner
from supervisor_harness.p0_gate1_controller_adapter import OfflineGate1ProviderFake


REAL_TAG = "market-rsi-protocol-v9.9.9"
REAL_COMMIT = "3" * 40
REAL_TAG_OBJECT = "4" * 40


def _publication() -> dict:
    source_hashes = protocol_source_release.source_hashes()
    return {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": gate1_canary_receipt.PUBLISHED_ORIGIN,
        "tag": REAL_TAG,
        "commit": REAL_COMMIT,
        "tag_object": REAL_TAG_OBJECT,
        "source_sha256": digest(source_hashes),
        "source_hashes": source_hashes,
        "isolation_proven": False,
        "model_authorship_proven": False,
    }


class Gate1FirstCanaryRunnerTests(unittest.TestCase):
    def test_actual_child_bootstrap_and_same_identity_recursion(self):
        publication = _publication()
        source_sha256 = publication["source_sha256"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            disposable_id = digest({"disposable_root": str(root)})[:16]
            bootstrap_root = root / f"bootstrap-{disposable_id}"
            recursive_root = root / f"recursive-{disposable_id}"
            with patch.object(
                    protocol_source_release, "verify_published",
                    return_value=publication) as verify_published:
                bootstrap = runner.execute_first_canary_bootstrap(
                    bootstrap_root, release_tag=REAL_TAG,
                    expected_source_sha256=source_sha256)
                bootstrap_receipt = bootstrap_root / "canary-result.json"
                bootstrap_runtime = digest(json.loads(
                    (bootstrap_root / "runtime.json").read_text()))
                bootstrap_verification = (
                    live_entry.gate1_canary_receipt.verify_gate1_canary_receipt(
                        bootstrap_receipt,
                        expected_receipt_sha256=file_hash(bootstrap_receipt),
                        expected_source_sha256=source_sha256,
                        expected_runtime_sha256=bootstrap_runtime,
                        expected_release_tag=REAL_TAG,
                        expected_release_commit=REAL_COMMIT,
                        expected_release_tag_object=REAL_TAG_OBJECT))

                recursive = runner.execute(
                    recursive_root, no_catalog=True,
                    prior_canary_receipt=bootstrap_receipt,
                    prior_canary_sha256=file_hash(bootstrap_receipt),
                    release_tag=REAL_TAG,
                    expected_source_sha256=source_sha256)
                recursive_receipt = recursive_root / "canary-result.json"
                recursive_runtime = digest(json.loads(
                    (recursive_root / "runtime.json").read_text()))
                recursive_verification = (
                    live_entry.gate1_canary_receipt.verify_gate1_canary_receipt(
                        recursive_receipt,
                        expected_receipt_sha256=file_hash(recursive_receipt),
                        expected_source_sha256=source_sha256,
                        expected_runtime_sha256=recursive_runtime,
                        expected_release_tag=REAL_TAG,
                        expected_release_commit=REAL_COMMIT,
                        expected_release_tag_object=REAL_TAG_OBJECT))

            self.assertEqual(verify_published.call_count, 2)
            self.assertEqual(
                bootstrap["cycle_id"],
                f"bootstrap-{disposable_id}-transaction")
            self.assertEqual(
                recursive["cycle_id"],
                f"recursive-{disposable_id}-transaction")
            for result in (bootstrap, bootstrap_verification,
                           recursive, recursive_verification):
                self.assertTrue(result["passed"])
                self.assertEqual(result["provider_calls"], 0)
                self.assertEqual(result["actual_provider_cost_usd"], "0")
            self.assertEqual(
                recursive_verification["release"],
                {"tag": REAL_TAG, "commit": REAL_COMMIT,
                 "tag_object": REAL_TAG_OBJECT})
            stored_prior = json.loads((
                recursive_root / recursive["cycle_id"]
                / gate1_canary_receipt.PRIOR_VERIFICATION_FILE).read_text())
            self.assertEqual(
                stored_prior["receipt_path"], str(bootstrap_receipt))
            self.assertEqual(
                stored_prior["receipt_sha256"], file_hash(bootstrap_receipt))

    def test_ordinary_real_identity_rejects_cross_release_before_output(self):
        publication = _publication()
        source_sha256 = publication["source_sha256"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "must-not-exist"
            with patch.object(
                    protocol_source_release, "verify_published",
                    return_value=publication):
                with self.assertRaisesRegex(ValueError, "exact release"):
                    runner.execute(
                        output, no_catalog=True,
                        prior_canary_receipt=Path("/tmp/not-read.json"),
                        prior_canary_sha256="a" * 64,
                        release_tag="market-rsi-protocol-v9.9.8",
                        expected_source_sha256=source_sha256)
            self.assertFalse(output.exists())

    def test_bootstrap_is_not_exposed_by_the_runner_cli(self):
        destinations = {action.dest for action in runner.parser()._actions}
        self.assertNotIn("first_canary_bootstrap", destinations)
        self.assertNotIn("bootstrap_capability", destinations)
        self.assertNotIn("child_entry", destinations)
        self.assertNotIn("release_tag", destinations)
        self.assertNotIn("expected_source_sha256", destinations)

    def test_programmatic_bootstrap_selects_only_internal_capability(self):
        output = Path("/tmp/first-canary-programmatic-test")
        token = object()
        with (
            patch.object(parent, "verified_first_canary_publication",
                         return_value=token) as publication,
            patch.object(runner, "_execute",
                         return_value={"passed": True}) as call,
        ):
            self.assertEqual(
                runner.execute_first_canary_bootstrap(
                    output, release_tag="market-rsi-protocol-v9.9.9",
                    expected_source_sha256="a" * 64), {"passed": True})
        publication.assert_called_once_with(
            release_tag="market-rsi-protocol-v9.9.9",
            expected_source_sha256="a" * 64)
        call.assert_called_once_with(
            output, no_catalog=True,
            prior_canary_receipt=None, prior_canary_sha256=None,
            bootstrap_capability=parent._FIRST_CANARY_BOOTSTRAP_CAPABILITY,
            verified_publication=token)

    def test_failed_publication_check_precedes_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "must-not-exist"
            with patch.object(
                    parent, "verified_first_canary_publication",
                    side_effect=ValueError("mock publication rejected")):
                with self.assertRaisesRegex(ValueError, "publication rejected"):
                    runner.execute_first_canary_bootstrap(
                        output, release_tag="market-rsi-protocol-v9.9.9",
                        expected_source_sha256="a" * 64)
            self.assertFalse(output.exists())

    def test_stale_publication_token_precedes_all_artifact_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "must-not-exist"
            publication = {
                "source_sha256": "a" * 64,
                "source_hashes": {"controlled.py": "b" * 64},
            }
            with (
                patch.object(parent, "_publication_from_token",
                             return_value=publication),
                patch.object(runner.protocol_source_release, "source_hashes",
                             return_value={"controlled.py": "c" * 64}),
            ):
                with self.assertRaisesRegex(ValueError, "stale before artifacts"):
                    runner._execute(
                        output, no_catalog=True,
                        prior_canary_receipt=None, prior_canary_sha256=None,
                        bootstrap_capability=(
                            parent._FIRST_CANARY_BOOTSTRAP_CAPABILITY),
                        verified_publication=object())
            self.assertFalse(output.exists())

    def test_ordinary_execute_still_requires_an_exact_prior(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            with self.assertRaisesRegex(ValueError, "prior current-source"):
                runner.execute(output)
            self.assertFalse(output.exists())

    def test_arbitrary_bootstrap_capability_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            with self.assertRaisesRegex(ValueError, "bootstrap capability"):
                runner._execute(
                    output, no_catalog=True,
                    prior_canary_receipt=None, prior_canary_sha256=None,
                    bootstrap_capability=object(), verified_publication=None)
            self.assertFalse(output.exists())

    def test_bootstrap_requires_an_absolute_fresh_output(self):
        output = Path("relative-first-canary-output")
        with self.assertRaisesRegex(ValueError, "absolute first-canary"):
            runner._execute(
                output, no_catalog=True,
                prior_canary_receipt=None, prior_canary_sha256=None,
                bootstrap_capability=parent._FIRST_CANARY_BOOTSTRAP_CAPABILITY,
                verified_publication=None)
        self.assertFalse(output.exists())

    def test_child_environment_is_credential_free_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = root / "offline.env"
            environment.write_bytes(child._OFFLINE_ENVIRONMENT)
            values = child._offline_environment(environment)
            self.assertIs(values["TINKER_API_KEY"], child._OFFLINE_KEY_SENTINEL)
            environment.write_text("TINKER_API_KEY=must-not-be-read\n")
            with self.assertRaisesRegex(ValueError, "credential-free"):
                child._offline_environment(environment)

    def test_child_backend_factory_cannot_construct_a_live_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory).resolve() / "cache"
            fake = OfflineGate1ProviderFake({})
            factory = child._OfflineOnlyBackendFactory(fake, cache)
            self.assertIs(
                factory(child._OFFLINE_KEY_SENTINEL, cache), fake)
            with self.assertRaisesRegex(RuntimeError, "construction changed"):
                factory(child._OFFLINE_KEY_SENTINEL, cache)
            other = child._OfflineOnlyBackendFactory(fake, cache)
            with self.assertRaisesRegex(RuntimeError, "construction changed"):
                other("real-key-shaped-string", cache)

    def test_child_has_no_direct_live_provider_import(self):
        source = Path(child.__file__).read_text()
        self.assertNotIn("from codex_glm_provider", source)
        self.assertNotIn("import codex_glm_provider", source)

    def test_supervisor_failure_writes_bounded_credential_free_artifact(self):
        publication = _publication()

        def failed_parent(args, **_kwargs):
            args.supervisor_root.mkdir(parents=True, mode=0o700)
            (args.supervisor_root / "child.log").write_text(
                "TINKER_API_KEY=must-never-enter-failure-artifact\n")
            result = {
                "schema": "market_bounded_live_supervisor_parent_v1",
                "cycle_id": args.cycle_id,
                "passed": False,
                "child_exit_code": 1,
                "incident_created": True,
                "incident_id": "synthetic-worker-error",
                "automatic_retry": False,
                "watchdog_head_sha256": "5" * 64,
                "credential": "must-never-enter-failure-artifact",
            }
            (args.supervisor_root / "result.json").write_text(
                json.dumps(result, sort_keys=True) + "\n")
            return result

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "failed-supervisor"
            with (
                patch.object(protocol_source_release, "verify_published",
                             return_value=publication),
                patch.object(parent, "run", side_effect=failed_parent),
            ):
                with self.assertRaisesRegex(RuntimeError, "supervisor_passed"):
                    runner.execute_first_canary_bootstrap(
                        output, release_tag=REAL_TAG,
                        expected_source_sha256=publication["source_sha256"])
            failure_path = output / "canary-failure.json"
            failure = json.loads(failure_path.read_text())
            encoded = failure_path.read_text()
            self.assertEqual(failure["schema"], runner.FAILURE_SCHEMA)
            self.assertFalse(failure["passed"])
            self.assertFalse(failure["automatic_retry"])
            self.assertFalse(failure["terminal_checks"]["supervisor_passed"])
            self.assertEqual(
                failure["supervisor_result"]["fields"]["incident_id"],
                "synthetic-worker-error")
            self.assertEqual(
                failure["child_log_sha256"],
                file_hash(output / "supervisor" / "child.log"))
            self.assertEqual(
                failure["child_log_final_line"],
                "[redacted credential-shaped child-log final line]")
            self.assertNotIn("must-never-enter-failure-artifact", encoded)
            self.assertLess(len(encoded.encode()), 16 * 1024)
            self.assertFalse((output / "canary-result.json").exists())

    def test_missing_terminal_evidence_is_runtime_error_not_lookup_error(self):
        publication = _publication()

        def incomplete_parent(args, **_kwargs):
            args.supervisor_root.mkdir(parents=True, mode=0o700)
            (args.supervisor_root / "child.log").write_text(
                "synthetic child exited before durable evidence\n")
            result = {
                "schema": "market_bounded_live_supervisor_parent_v1",
                "cycle_id": args.cycle_id,
                "passed": True,
                "child_exit_code": 0,
                "incident_created": False,
                "incident_id": None,
                "automatic_retry": False,
                "watchdog_head_sha256": "6" * 64,
            }
            (args.supervisor_root / "result.json").write_text(
                json.dumps(result, sort_keys=True) + "\n")
            return result

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "missing-evidence"
            with (
                patch.object(protocol_source_release, "verify_published",
                             return_value=publication),
                patch.object(parent, "run", side_effect=incomplete_parent),
            ):
                with self.assertRaisesRegex(
                        RuntimeError, "budget_job_metered_terminal"):
                    runner.execute_first_canary_bootstrap(
                        output, release_tag=REAL_TAG,
                        expected_source_sha256=publication["source_sha256"])
            failure = json.loads((output / "canary-failure.json").read_text())
            self.assertTrue(
                failure["supervisor_result"]["fields"]["passed"])
            self.assertFalse(failure["evidence_presence"]["budget_job"])
            self.assertFalse(failure["evidence_presence"]["child_result"])
            self.assertFalse(failure["evidence_presence"]["supervisor_claim"])
            self.assertIn(
                "budget_job_metered_terminal", failure["failure_reasons"])
            self.assertIn("terminal_files_present", failure["failure_reasons"])
            self.assertFalse((output / "canary-result.json").exists())

    def test_nonzero_synthetic_meter_is_distinct_from_zero_provider_cost(self):
        publication = _publication()
        synthetic_metered_usd = "0.031"

        def successful_parent(args, **_kwargs):
            budget = runner.PaidBudget(args.budget_root)
            budget.reserve(
                args.cycle_id, "setup", "0.05", "offline-synthetic-meter",
                args.expected_packet_canonical_sha256)
            budget.dispatch(args.cycle_id)
            budget.settle_metered(
                args.cycle_id, synthetic_metered_usd,
                {"terminal": True, "provider_called": False})
            state = runner.SupervisorGlobalState(
                args.global_state_root, args.decision_doc)
            state.claim(
                args.cycle_id,
                expected_head_sha256=args.expected_head_sha256,
                source_sha256=args.expected_source_sha256,
                prior_canary_sha256=args.prior_canary_sha256)
            state.close(
                args.cycle_id, outcome="passed", review_sha256="7" * 64)
            args.root.mkdir(parents=True, mode=0o700)
            args.supervisor_root.mkdir(parents=True, mode=0o700)
            (args.root / "result.json").write_text(
                json.dumps({"cycle_id": args.cycle_id}, sort_keys=True) + "\n")
            (args.supervisor_root / "supervisor-claim.json").write_text(
                json.dumps({"cycle_id": args.cycle_id}, sort_keys=True) + "\n")
            (args.supervisor_root / "child.log").write_text(
                "synthetic terminal child\n")
            result = {
                "schema": "market_bounded_live_supervisor_parent_v1",
                "cycle_id": args.cycle_id,
                "passed": True,
                "child_exit_code": 0,
                "incident_created": False,
                "incident_id": None,
                "automatic_retry": False,
                "watchdog_head_sha256": "8" * 64,
            }
            (args.supervisor_root / "result.json").write_text(
                json.dumps(result, sort_keys=True) + "\n")
            return result

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "nonzero-synthetic-meter"
            with (
                patch.object(protocol_source_release, "verify_published",
                             return_value=publication),
                patch.object(parent, "run", side_effect=successful_parent),
            ):
                result = runner.execute_first_canary_bootstrap(
                    output, release_tag=REAL_TAG,
                    expected_source_sha256=publication["source_sha256"])
            self.assertTrue(result["passed"])
            self.assertEqual(
                result["synthetic_ledger_metered_usd"],
                synthetic_metered_usd)
            self.assertEqual(result["provider_calls"], 0)
            self.assertEqual(result["actual_provider_cost_usd"], "0")
            self.assertFalse((output / "canary-failure.json").exists())


if __name__ == "__main__":
    unittest.main()
