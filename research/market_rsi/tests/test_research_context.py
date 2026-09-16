import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import research_context as context


class ResearchContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "initialization.json"
        context.freeze_common(self.path)

    def mutate(self, key, value):
        payload = json.loads(self.path.read_text())
        payload[key] = value
        self.path.write_text(json.dumps(payload))

    def test_all_arms_have_identical_starting_instructions(self):
        prompts = [context.common_system_prompt(self.path, arm)
                   for arm in sorted(context.ARMS)]
        self.assertEqual(len(set(prompts)), 1)
        self.assertEqual(prompts[0], context.COMMON_SOURCE.read_text())

    def test_exclusive_freeze(self):
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            context.freeze_common(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_source_drift_rejected(self):
        source = Path(self.temp.name) / context.COMMON_SOURCE.name
        source.write_text("changed rules")
        with patch.object(context, "COMMON_SOURCE", source):
            with self.assertRaisesRegex(ValueError, "changed"):
                context.common_system_prompt(self.path, "learn")

    def test_manifest_text_drift_rejected(self):
        self.mutate("system_prompt", "revised prior")
        with self.assertRaisesRegex(ValueError, "changed"):
            context.common_system_prompt(self.path, "learn")

    def test_rehashing_modified_payload_does_not_match_source(self):
        self.mutate("system_prompt", "revised prior")
        self.mutate("common_sha256", context.sha256("revised prior"))
        with self.assertRaisesRegex(ValueError, "changed"):
            context.common_system_prompt(self.path, "learn")

    def test_cannot_relabel_prior_as_agent_learning(self):
        self.mutate("origin", "agent_learned")
        with self.assertRaisesRegex(ValueError, "provenance"):
            context.common_system_prompt(self.path, "learn")

    def test_unknown_arm_rejected(self):
        with self.assertRaises(ValueError):
            context.common_system_prompt(self.path, "market_selection")

    def test_no_extra_fields_can_smuggle_historical_context(self):
        self.mutate("historical_results", "should not be model input")
        with self.assertRaisesRegex(ValueError, "fields"):
            context.common_system_prompt(self.path, "learn")

    def test_only_distilled_common_source_is_loaded(self):
        prompt = context.common_system_prompt(self.path, "reset")
        for value in ("tinker://", "0/100", "13/100", "18/100", "sqlparse",
                      "HANDOFF_2026-08-28", "lighthouseinvest.io"):
            self.assertNotIn(value, prompt)


if __name__ == "__main__":
    unittest.main()
