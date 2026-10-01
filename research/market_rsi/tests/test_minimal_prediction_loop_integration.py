import ast
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_rsi import digest
from minimal_prediction_loop import loop as loop_module
from minimal_prediction_loop.lineage import PredictionLineage
from minimal_prediction_loop.loop import recover_bound_round, run_two_round_synthetic_loop


class MinimalPredictionLoopIntegrationTests(unittest.TestCase):
    def test_two_round_keep_revert_restart_and_sealed_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "loop"
            receipt = run_two_round_synthetic_loop(root)
            self.assertEqual(receipt["decisions"], ["KEEP", "REVERT"])
            self.assertEqual(receipt["final_parent_sha256"], receipt["rounds"][0]["candidate_sha256"])
            self.assertNotEqual(receipt["final_parent_sha256"], receipt["rounds"][1]["candidate_sha256"])
            self.assertEqual(receipt["used_round_ids"], ["round-1", "round-2"])
            self.assertEqual(receipt["used_dev_ids"], ["dev-1", "dev-2"])
            self.assertEqual(receipt["promoted_dev_ids"], ["dev-1", "dev-2"])
            self.assertTrue(receipt["round_1_dev_promoted_into_round_2_train"])
            self.assertTrue(receipt["restart_receipts_stable"])
            self.assertFalse(any(receipt["candidate_views"].values()))
            self.assertTrue(all(
                round_receipt["real_isolation_admitted"] is False
                for round_receipt in receipt["rounds"]
            ))
            for round_receipt in receipt["rounds"]:
                score = round_receipt["score_receipt"]
                self.assertEqual(
                    score["prediction_journal_sha256"],
                    round_receipt["prediction_journal_sha256"],
                )
                self.assertEqual(
                    score["prediction_receipt_sha256"],
                    round_receipt["prediction_receipt_sha256"],
                )
                self.assertEqual(
                    score["full_score_sha256"], round_receipt["score_receipt_sha256"]
                )
                self.assertEqual(
                    score["trusted_rows_sha256"], score["dev_dataset_sha256"]
                )
                artifact = root / round_receipt["score_artifact_relative_path"]
                self.assertTrue(artifact.is_file())
                self.assertEqual(
                    hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    score["full_score_sha256"],
                )
                self.assertEqual(digest(json.loads(artifact.read_bytes())), score["full_score_sha256"])
                for field in (
                    "dev_dataset_sha256",
                    "trusted_rows_sha256",
                    "public_rows_sha256",
                    "candidate_records_sha256",
                    "scorer_spec_sha256",
                    "complete_mask_sha256",
                ):
                    self.assertEqual(len(score[field]), 64)
            self.assertEqual(receipt["authority"]["provider_calls"], 0)
            self.assertEqual(receipt["authority"]["network_calls"], 0)
            self.assertEqual(receipt["authority"]["paid_calls"], 0)
            self.assertFalse(receipt["authority"]["real_data_admitted"])
            self.assertFalse(receipt["authority"]["real_isolation_admitted"])
            self.assertFalse(receipt["authority"]["protected_dev_opened"])
            self.assertFalse(receipt["authority"]["final_opened"])
            self.assertFalse(receipt["authority"]["final_scored"])
            self.assertFalse(receipt["authority"]["promotion_authorized"])
            self.assertFalse(receipt["authority"]["pnl_evaluated"])
            self.assertFalse(receipt["authority"]["pmb_used"])
            stored = json.loads((root / "integration-receipt.json").read_text())
            body = {key: value for key, value in stored.items() if key != "receipt_sha256"}
            self.assertEqual(stored["receipt_sha256"], digest(body))

            restarted_lineage = PredictionLineage(root / "lineage").audit()
            restarted_lifecycle = loop_module._CheckpointedLifecycle.resume(
                root / "data-lifecycle"
            ).audit()
            self.assertEqual(restarted_lineage["parent_sha256"], receipt["final_parent_sha256"])
            self.assertIsNone(restarted_lineage["active_round"])
            self.assertFalse(restarted_lineage["final_feedback_allowed"])
            self.assertFalse(restarted_lifecycle["transfer_submissions_frozen"])
            self.assertFalse(restarted_lifecycle["transfer_scored"])
            self.assertEqual(
                receipt["ledger_checkpoints"]["lineage"],
                restarted_lineage["ledger_checkpoint"],
            )
            self.assertEqual(
                receipt["ledger_checkpoints"]["lifecycle"],
                restarted_lifecycle["ledger_checkpoint"],
            )

    def test_cross_ledger_crash_recovery_never_advances_parent_before_promotion(self):
        for failure_point in ("complete", "decide"):
            with self.subTest(failure_point=failure_point), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "loop"
                target = (
                    loop_module._CheckpointedLifecycle
                    if failure_point == "complete"
                    else PredictionLineage
                )
                method = "complete_dev_score" if failure_point == "complete" else "decide"
                with patch.object(target, method, side_effect=RuntimeError("injected crash")):
                    with self.assertRaisesRegex(RuntimeError, "injected crash"):
                        run_two_round_synthetic_loop(root)

                lineage_before = PredictionLineage(root / "lineage").audit()
                lifecycle_before = loop_module._CheckpointedLifecycle.resume(
                    root / "data-lifecycle"
                ).audit()
                self.assertEqual(lineage_before["decisions"], [])
                self.assertEqual(
                    lineage_before["parent_sha256"],
                    lineage_before["active_round"]["parent_before_sha256"],
                )
                if failure_point == "complete":
                    self.assertEqual(lifecycle_before["completed_rounds"], [])
                    self.assertEqual(
                        lifecycle_before["active_dev_claim"]["round_id"], "round-1"
                    )
                else:
                    self.assertEqual(lifecycle_before["completed_rounds"], ["round-1"])
                    self.assertIsNone(lifecycle_before["active_dev_claim"])

                recovered = recover_bound_round(root, round_id="round-1")
                self.assertEqual(recovered["decision"], "KEEP")
                self.assertTrue(recovered["recovered_without_rescore"])
                after = loop_module._CheckpointedLifecycle.resume(
                    root / "data-lifecycle"
                ).audit()
                self.assertEqual(after["completed_rounds"], ["round-1"])
                self.assertEqual(after["promoted_dev_ids"], ["dev-1"])

    def test_outcome_substitution_cannot_escape_frozen_dev_commitment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "loop"
            root.mkdir()
            rows = loop_module._synthetic_rows()
            lifecycle = loop_module._CheckpointedLifecycle.create(
                root / "data-lifecycle",
                experiment_id="outcome-substitution-test",
                rounds=[{
                    "round_id": "round-1",
                    "train_datasets": [loop_module._dataset("train-1", rows["train_round_1"])],
                    "dev_datasets": [loop_module._dataset("dev-1", rows["dev_round_1"])],
                }],
                transfer_datasets=[{
                    "dataset_id": "final-sealed-1",
                    "content_sha256": "f" * 64,
                }],
            )
            initial_parent = "1" * 64
            lineage = PredictionLineage.create(
                root / "lineage",
                experiment_id="outcome-substitution-test",
                initial_parent_sha256=initial_parent,
                keep_rule={
                    "metric": "candidate_minus_market_brier",
                    "operator": "<",
                    "threshold": 0.0,
                    "minimum_rows": 4,
                    "minimum_events": 2,
                    "minimum_dates": 2,
                },
            )
            altered = [{**row, "outcome": 1 - row["outcome"]} for row in rows["dev_round_1"]]
            original_public = loop_module.build_candidate_views(
                rows["train_round_1"], rows["dev_round_1"]
            )["evaluation"]
            altered_public = loop_module.build_candidate_views(
                rows["train_round_1"], altered
            )["evaluation"]
            self.assertEqual(original_public, altered_public)

            with self.assertRaisesRegex(ValueError, "frozen Dev dataset commitment"):
                loop_module._run_round(
                    root,
                    round_id="round-1",
                    dev_id="dev-1",
                    train_rows=rows["train_round_1"],
                    dev_rows=altered,
                    candidate_name="outcome-substitution",
                    probabilities={"event-a": 0.80, "event-b": 0.20},
                    lifecycle=lifecycle,
                    lineage=lineage,
                )
            lifecycle_state = lifecycle.audit()
            lineage_state = lineage.audit()
            self.assertEqual(lifecycle_state["completed_rounds"], [])
            self.assertEqual(lifecycle_state["promoted_dev_ids"], [])
            self.assertEqual(lineage_state["decisions"], [])
            self.assertEqual(lineage_state["parent_sha256"], initial_parent)
            self.assertIsNone(lineage_state["active_round"]["score_receipt"])

    def test_recovery_rejects_tampered_full_score_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "loop"
            with patch.object(
                loop_module._CheckpointedLifecycle,
                "complete_dev_score",
                side_effect=RuntimeError("injected crash"),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected crash"):
                    run_two_round_synthetic_loop(root)
            artifacts = list((root / loop_module.TRUSTED_SCORE_DIRECTORY).glob("*.json"))
            self.assertEqual(len(artifacts), 1)
            artifacts[0].write_text("{}")
            with self.assertRaisesRegex(ValueError, "artifact bytes"):
                recover_bound_round(root, round_id="round-1")

    def test_recovery_rejects_compact_metrics_that_contradict_full_score(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "loop"
            root.mkdir()
            rows = loop_module._synthetic_rows()
            dev_rows = rows["dev_round_1"]
            dev_commitment = digest(dev_rows)
            lifecycle = loop_module._CheckpointedLifecycle.create(
                root / "data-lifecycle",
                experiment_id="compact-score-substitution-test",
                rounds=[{
                    "round_id": "round-1",
                    "train_datasets": [loop_module._dataset("train-1", rows["train_round_1"])],
                    "dev_datasets": [loop_module._dataset("dev-1", dev_rows)],
                }],
                transfer_datasets=[{
                    "dataset_id": "final-sealed-1",
                    "content_sha256": "f" * 64,
                }],
            )
            initial_parent = "1" * 64
            candidate_sha256 = "c" * 64
            journal_sha256 = "d" * 64
            prediction_receipt_sha256 = "e" * 64
            lineage = PredictionLineage.create(
                root / "lineage",
                experiment_id="compact-score-substitution-test",
                initial_parent_sha256=initial_parent,
                keep_rule={
                    "metric": "candidate_minus_market_brier",
                    "operator": "<",
                    "threshold": 0.0,
                    "minimum_rows": 4,
                    "minimum_events": 2,
                    "minimum_dates": 2,
                },
            )
            public_rows = loop_module.build_candidate_views(
                rows["train_round_1"], dev_rows
            )["evaluation"]
            candidate_records = [
                {
                    "event_id": row["event_id"],
                    "market_id": row["market_id"],
                    "cutoff_ms": row["cutoff_ms"],
                    "probability": {
                        "event-a": 0.20,
                        "event-b": 0.80,
                    }[row["event_id"]],
                }
                for row in public_rows
            ]
            full_score = loop_module.score_probability_forecasts(
                dev_rows,
                candidate_records,
                spec=loop_module.ProperScoreSpec(bootstrap_replicates=200),
            )
            self.assertGreater(
                full_score["aggregate_metrics"]["candidate_minus_market_brier"], 0.0
            )
            loop_module._persist_trusted_score_artifact(
                root, round_id="round-1", score=full_score
            )
            lifecycle.claim_dev_score(
                "round-1", candidate_set_sha256=candidate_sha256
            )
            lineage.start_round(
                round_id="round-1",
                changed_stage="prediction",
                candidate_sha256=candidate_sha256,
                prediction_journal_sha256=journal_sha256,
                prediction_receipt_sha256=prediction_receipt_sha256,
                public_rows_sha256=full_score["input_commitments"]["public_rows_sha256"],
                dev_id="dev-1",
                evaluation_role="dev",
            )
            genuine = loop_module._score_receipt(
                "dev-1",
                full_score,
                dev_dataset_sha256=dev_commitment,
                prediction_journal_sha256=journal_sha256,
                prediction_receipt_sha256=prediction_receipt_sha256,
            )
            forged = {
                **genuine,
                "candidate_brier": 0.04,
                "candidate_minus_market_brier": 0.04 - genuine["market_brier"],
            }
            self.assertLess(forged["candidate_minus_market_brier"], 0.0)
            lineage.bind_dev_score(round_id="round-1", score_receipt=forged)

            with self.assertRaisesRegex(ValueError, "differs from the trusted score artifact"):
                recover_bound_round(root, round_id="round-1")
            lifecycle_state = lifecycle.audit()
            lineage_state = lineage.audit()
            self.assertEqual(lifecycle_state["completed_rounds"], [])
            self.assertEqual(lifecycle_state["promoted_dev_ids"], [])
            self.assertEqual(lineage_state["decisions"], [])
            self.assertEqual(lineage_state["parent_sha256"], initial_parent)

    def test_lineage_and_lifecycle_suffix_truncation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "loop"
            run_two_round_synthetic_loop(root)
            lineage_ledger = root / "lineage" / "ledger.jsonl"
            lines = lineage_ledger.read_text().splitlines()
            lineage_ledger.write_text("\n".join(lines[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "durable checkpoint"):
                PredictionLineage(root / "lineage").audit()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "loop"
            run_two_round_synthetic_loop(root)
            lifecycle_ledger = root / "data-lifecycle" / "data-exposure-ledger.jsonl"
            lines = lifecycle_ledger.read_text().splitlines()
            lifecycle_ledger.write_text("\n".join(lines[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "durable checkpoint"):
                loop_module._CheckpointedLifecycle.resume(root / "data-lifecycle")

    def test_run_identity_is_one_shot_and_existing_root_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "loop"
            run_two_round_synthetic_loop(root)
            with self.assertRaises(FileExistsError):
                run_two_round_synthetic_loop(root)

    def test_loop_imports_no_pmb_or_pnl_module(self):
        source = Path(__file__).parents[1] / "minimal_prediction_loop" / "loop.py"
        tree = ast.parse(source.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertFalse(any("pmb" in name.lower() for name in imports))
        self.assertFalse(any("taking_replay" in name or "pnl" in name.lower() for name in imports))


if __name__ == "__main__":
    unittest.main()
