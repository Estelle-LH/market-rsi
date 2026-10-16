"""Paid-but-incomplete Author response is failure, not uncertainty or a candidate.

The reply is invented: no public message/call and only ordinary usage metadata
reporting32768 output/reasoning tokens. No hidden reasoning is present or read.
Tests use owned temporary ledgers and fake HTTPS, never actual paid inference.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import earnings_open_roles as roles
import earnings_open_fresh_grant as fresh
from earnings_capacity_runtime import _OwnedHTTP
from earnings_night_budget import history_snapshot
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_author_transport as author_fixture
import test_earnings_open_author_socket as socket_fixture
import test_earnings_open_roles as role_fixture


def incomplete_with_usage(response):
    """Change public status/usage only; never fabricate hidden reasoning text."""
    response = deepcopy(response)
    response.update(status="incomplete", error=None,
                    incomplete_details={"reason": "max_output_tokens"}, output=[])
    response["usage"]["output_tokens"] = 32768
    response["usage"]["total_tokens"] = response["usage"]["input_tokens"] + 32768
    response["usage"]["output_tokens_details"] = {"reasoning_tokens": 32768}
    return response


class IncompleteAuthorFixture(author_fixture._AuthorFixture):
    """Own instance of the real temporary-budget/raw-transport test protocol."""

    def __init__(self, owner, root):
        super().__init__(owner, root)
        context = deepcopy(self.context)
        context["limits"] = {"max_input_tokens": 10000, "max_output_tokens": 32768, "wall_seconds": 900}
        self.bind_context(context)
        self.broker = role_fixture.Broker()
        def check(loan):
            pending = self.budget.db.execute(
                "SELECT id,model,reserved FROM requests WHERE status='reserved'").fetchall()
            if loan is None:
                owner.assertEqual(pending, [])
                self.budget.active()
            else:
                owner.assertEqual(pending, [loan])
        owned = _OwnedHTTP(self.http, check,
                           {slot: context["limits"] for slot in self.slots}, self.rates)
        self.factory.side_effect = lambda: owned

    def service(self):
        return roles.OpenAuthor(self.context_binding, budget=self.budget,
            client_factory=self.factory, broker=self.broker,
            socket_timeout_seconds=900, max_turns=1)

    def invoke_incomplete(self):
        return self.invoke(incomplete_with_usage(self.response({})),
                           chosen=self.choice(), before={"axis": "R"}, service=self.service())


class IncompleteAuthorTests(unittest.TestCase):
    def test_incomplete_without_public_output_settles_usage_but_never_parses_or_promotes_a_candidate(self):
        temporary = tempfile.TemporaryDirectory(prefix="incomplete-author-")
        self.addCleanup(temporary.cleanup)
        fixture = IncompleteAuthorFixture(self, Path(temporary.name).resolve() / "owned")
        with patch.object(roles, "candidate", side_effect=AssertionError("No public candidate exists")) as parse:
            with self.assertRaises(RuntimeError):
                fixture.invoke_incomplete()
            parse.assert_not_called()
        self.assertEqual(fixture.rows(), [(20 * 2500 + 32768 * 10000, 327702800, "settled")])
        self.assertEqual(len(fixture.calls), 2)
        count, generation = [payload for _, payload in fixture.calls]
        self.assertEqual(generation, dict(count, max_output_tokens=32768, service_tier="default", store=False))
        self.assertEqual(count["model"], fixture.rates["api_model"])
        self.assertEqual(count["reasoning"], {"effort": fixture.rates["effort"]})
        summary = fixture.budget.summary()
        self.assertFalse(summary["blocked"])
        self.assertEqual(summary["unresolved_reserved_usd"], 0)
        self.assertEqual(fixture.budget.db.execute(
            "SELECT COUNT(*) FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()[0], 0)
        self.assertEqual(history_snapshot(fixture.budget.db, fixture.baseline["max_rowid"]), fixture.baseline)
        fixture.budget.active()  # Financially known/settled does not mean research succeeded.
        slot = Path(fixture.slots[0])
        terminal = json.loads((slot / "result.json").read_bytes())
        self.assertEqual(terminal["status"], "FAILED_NO_RETRY")
        self.assertEqual(terminal["error_type"], "RuntimeError")
        self.assertFalse(terminal["retry_allowed"])
        self.assertFalse(terminal["model_authorship_verified"])
        self.assertFalse((slot / "candidate.json").exists())
        self.assertFalse((slot / "decision.json").exists())
        self.assertEqual(fixture.broker.calls, [])
        self.assertEqual((slot / "response.json").read_bytes(), (slot / "01-response.json").read_bytes())
        saved = json.loads((slot / "response.json").read_bytes())
        self.assertEqual(saved["output"], [])
        self.assertEqual(saved["status"], "incomplete")
        self.assertEqual(saved["incomplete_details"], {"reason": "max_output_tokens"})
        self.assertEqual(saved["usage"]["output_tokens"], 32768)
        self.assertEqual(saved["usage"]["output_tokens_details"]["reasoning_tokens"], 32768)
        _, prefix = fixture.intent_records()["/v1/responses"]
        raw = json.loads(prefix.with_suffix(".raw.bin").read_bytes())
        self.assertEqual(raw["output"], [])
        self.assertEqual(raw["status"], "incomplete")
        originals, rows = fixture.originals(), fixture.rows()
        with self.assertRaises(FileExistsError):
            fixture.invoke_incomplete()
        self.assertEqual(fixture.originals(), originals)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(len(fixture.calls), 2)
        fixture.factory.assert_called_once()
        self.assertTrue(all(connection.closed for connection in fixture.connections))

    def test_actual_assembly_halts_and_consumes_owner_without_candidate_shadow_or_new_forecast(self):
        # Reuse exact already-checked role-policy fixture setup, not a fabricated
        # service success. No TestCase class is imported into this namespace.
        setup = socket_fixture.OpenAuthorSocketAssemblyTests(
            "test_new_policy_reaches_only_author_factory_and_forecast_gets_exact_old600_projection")
        self.addCleanup(setup.doCleanups)
        module, helper, fixture = setup.fixture(followup=True)
        incomplete = incomplete_with_usage(fixture.raw.response([]))
        sequence = [fixture.raw.research(), fixture.raw.final(),
                    helper.choose(fixture, "H"), incomplete]
        # This is an incomplete-output transport fixture, not an Alico repair
        # fixture. Do not implicitly import the ambient financial read hint.
        with helper.scope(fixture), fixture.exchange(sequence), \
                patch.object(fresh, "policy", return_value={"continuation": {}}) as owned_policy, \
                self.assertRaises(engine.driver.LoopHalted):
            module.assembly.run(fixture.episode_binding, fixture.assembly_binding)
        owned_policy.assert_called_once_with()
        self.assertEqual(len(fixture.raw.calls), 8)
        rows = fixture.ledger_rows()
        self.assertEqual(len(rows), 5)  # Prior fixture row plus four real counted synthetic generations.
        self.assertTrue(all(row[4] == "settled" for row in rows))
        self.assertGreater(rows[-1][3], 0)
        self.assertLessEqual(rows[-1][3], rows[-1][2])
        author_slot = Path(fixture.slots[1]["author"])
        author_input = engine.read(engine.pin(author_slot / "effective-input.json"))
        self.assertNotIn("research_context", author_input)
        author_result = engine.read(engine.pin(author_slot / "result.json"))
        self.assertEqual(author_result["status"], "FAILED_NO_RETRY")
        self.assertFalse((author_slot / "candidate.json").exists())
        self.assertEqual(engine.read(engine.pin(author_slot / "response.json"))["output"], [])
        self.assertEqual(engine.read(engine.pin(author_slot / "response.json"))["status"], "incomplete")
        self.assertFalse((fixture.root / "candidate-02.json").exists())
        self.assertTrue((fixture.root / "loop" / "round-0001-reconcile.done.json").is_file())
        self.assertTrue((fixture.root / "loop" / "round-0002-implement.failed.json").is_file())
        for stage in ("source_review", "execute", "result_review", "reconcile"):
            self.assertFalse((fixture.root / "loop" / f"round-0002-{stage}.claim.json").exists())
        self.assertTrue(Path(fixture.slots[0]["forecast"]).is_dir())
        self.assertFalse(Path(fixture.slots[1]["forecast"]).exists())
        self.assertFalse(Path(fixture.slots[1]["review"]).exists())
        for round_plan in fixture.plan_rows:
            self.assertFalse(Path(round_plan["parent"]).exists())
            self.assertFalse(Path(round_plan["candidate"]).exists())
        native = engine.read(engine.pin(fixture.paths["batch_root"] / "batch.json"))
        self.assertEqual(native["micro_evolution"]["active_pair"], engine.activation.pair(fixture.native["baseline"]))
        self.assertIsNone(native["micro_evolution"]["pending"])
        self.assertEqual(native["micro_evolution"]["history"], [])
        identity = hashlib.sha256(fixture.envelope["id"].encode()).hexdigest()
        claim_root = Path(fixture.runtime["ledger"]).parent / ".capacity-runtime-claims"
        self.assertTrue((claim_root / (identity + ".json")).is_file())
        owner_terminal = engine.read(engine.pin(claim_root / (identity + ".result.json")))
        self.assertEqual(owner_terminal["status"], "FAILED_NO_RETRY")
        self.assertEqual(owner_terminal["error_type"], "LoopHalted")
        self.assertFalse(owner_terminal["retry_allowed"])
        self.assertFalse(owner_terminal["budget_summary"]["blocked"])
        self.assertEqual(owner_terminal["budget_summary"]["unresolved_reserved_usd"], 0)
        self.assertFalse((fixture.root / "open-result.json").exists())
        self.assertFalse((fixture.root / "terminal-controller.json").exists())
        with helper.scope(fixture), patch.object(module.assembly, "open_capacity_runtime",
                side_effect=AssertionError("Consumed episode may not open another owner")), self.assertRaises(ValueError):
            module.assembly.run(fixture.episode_binding, fixture.assembly_binding)
        self.assertEqual(fixture.ledger_rows(), rows)
        self.assertEqual(len(fixture.raw.calls), 8)


if __name__ == "__main__":
    unittest.main()
