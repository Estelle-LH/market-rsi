"""One bounded parent method reference; no recovered research state or live proof."""
import copy
import json
from unittest.mock import Mock

import test_earnings_forecast_recipe as inherited

worker = inherited.worker
CURRENT = dict(inherited.RECIPE, parent_feedback_sha256="b" * 64)
PARENT = dict(inherited.RECIPE, research_instructions="Prior method: reconcile units from allowed filings.")


class ParentPlanTests(inherited.ForecastRecipeTests):
    def test_empty_single_and_explicit_parent_none_preserve_physical_defaults(self):
        self.assertEqual(worker.research_recipe_messages(None), [])
        self.assertEqual(worker.research_recipe_messages(CURRENT), [worker.research_recipe_message(CURRENT)])
        base, _, _ = self.run_forecast("default-plan")
        explicit, _, _ = self.run_forecast("none-plan", research_recipe=None, parent_research_recipe=None)
        self.assertEqual([json.dumps(p).encode() for _, p in base.requests],
                         [json.dumps(p).encode() for _, p in explicit.requests])
        current, _, _ = self.run_forecast("current-only", research_recipe=CURRENT)
        optional, _, _ = self.run_forecast("current-parent-none", research_recipe=CURRENT, parent_research_recipe=None)
        self.assertEqual(current.requests, optional.requests)

    def test_parent_before_current_is_counted_reserved_sent_and_in_final_history(self):
        before = copy.deepcopy((CURRENT, PARENT))
        provider, budget, output = self.run_forecast("parent-child", research_recipe=CURRENT, parent_research_recipe=PARENT)
        self.assertEqual((CURRENT, PARENT), before)
        messages = worker.research_recipe_messages(CURRENT, PARENT)
        first, final = provider.requests[1][1], provider.requests[3][1]
        self.assertEqual(first["input"][1:], messages)
        self.assertEqual(len(messages), 2)
        prior, current = messages
        self.assertIn("Prior method reference", prior["content"])
        self.assertIn("current recipe controls", prior["content"])
        self.assertIn("No previous evidence tables or calculations are supplied", prior["content"])
        self.assertIn("allowed filings", prior["content"])
        self.assertIn(json.dumps(PARENT, sort_keys=True, separators=(",", ":"), ensure_ascii=False), prior["content"])
        self.assertEqual(current, worker.research_recipe_message(CURRENT))
        self.assertEqual(final["input"][1:3], messages)
        self.assertEqual(first["instructions"], worker.INSTRUCTIONS)
        self.assertEqual(final["tool_choice"], "none")
        self.assertEqual(first["tools"], final["tools"])
        self.assertEqual(first["reasoning"], final["reasoning"])
        self.assertEqual(sum(len(m["content"].encode()) for m in messages) <= 8192, True)
        for turn in (1, 2):
            count, full = provider.requests[2 * (turn - 1)][1], provider.requests[2 * (turn - 1) + 1][1]
            self.assertEqual({k: full[k] for k in count}, count)
            receipt = json.loads((output / f"{turn:02d}-request.json").read_text())
            self.assertEqual(receipt["payload"], count)
            self.assertEqual(receipt["reserved_nano_usd"], 100 * worker.unit("2.5") + full["max_output_tokens"] * worker.unit("10"))
        self.assertEqual([p["max_output_tokens"] for endpoint, p in provider.requests if endpoint == "/v1/responses"], [25000, 65536])
        self.assertEqual(budget.summary()["generation_requests_reserved"], 2)
        self.assertFalse(budget.summary()["blocked"])

    def test_parent_compilation_is_deterministic_and_does_not_mutate_inputs(self):
        original = copy.deepcopy((CURRENT, PARENT))
        messages = worker.research_recipe_messages(CURRENT, PARENT)
        reordered = worker.research_recipe_messages(dict(reversed(list(CURRENT.items()))), dict(reversed(list(PARENT.items()))))
        self.assertEqual(messages, reordered)
        self.assertEqual((CURRENT, PARENT), original)

    def test_parent_missing_current_identity_shape_task_or_size_refuses_before_provider(self):
        bad = [(None, PARENT), (CURRENT, [PARENT]), (CURRENT, {}), (CURRENT, dict(PARENT, extra=True)),
               (CURRENT, dict(PARENT, task_id="different")), (CURRENT, dict(PARENT, parent_feedback_sha256="bad")),
               (CURRENT, dict(PARENT, parent_feedback_sha256=CURRENT["parent_feedback_sha256"])),
               (CURRENT, dict(PARENT, research_instructions="x" * 2201)),
               (CURRENT, dict(PARENT, research_instructions="😀" * 1025))]
        for index, (current, parent) in enumerate(bad):
            with self.subTest(index=index):
                client = Mock()
                with self.assertRaises(ValueError):
                    worker.forecast(client, self.rates, self.config, self.company, Mock(), self.root,
                                    research_recipe=current, parent_research_recipe=parent)
                client.post.assert_not_called()

    def test_combined_byte_ceiling_is_not_doubled(self):
        current = dict(CURRENT, research_instructions="😀" * 1024)
        parent = dict(PARENT, research_instructions="😀" * 1024)
        self.assertLessEqual(len(worker.research_recipe_message(current)["content"].encode()), 8192)
        self.assertLessEqual(len(worker.research_recipe_message(parent)["content"].encode()), 8192)
        client = Mock()
        with self.assertRaisesRegex(ValueError, "Combined"):
            worker.forecast(client, self.rates, self.config, self.company, Mock(), self.root,
                            research_recipe=current, parent_research_recipe=parent)
        client.post.assert_not_called()


if __name__ == "__main__":
    inherited.unittest.main()
