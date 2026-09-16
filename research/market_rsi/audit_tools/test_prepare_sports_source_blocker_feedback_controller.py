import copy
import tempfile
from pathlib import Path
import unittest

from market_rsi import fresh_json, file_hash
from audit_tools.prepare_sports_source_blocker_feedback_controller import (
    build_source_blocker_findings,
    load_entitlement,
)


def entitlement():
    return {
        "schema": "sportradar_push_entitlement_preflight_v1",
        "access": "trial",
        "http_status": 403,
        "redirect_present": False,
        "redirect_host": "",
        "redirect_scheme": "",
        "stream_entitlement_observed": False,
        "api_key_persisted": False,
        "signed_redirect_persisted": False,
        "provider_sla_proven": False,
        "market_lead_proven": False,
    }


class SportsSourceBlockerFeedbackTests(unittest.TestCase):
    def test_replaces_old_decision_and_keeps_options_open(self):
        prior = [
            {"id": "evidence"},
            {"id": "next-controller-decision", "instructions": "old"},
        ]
        findings = build_source_blocker_findings(
            prior, entitlement(), {"jobs": {"secret": {}}, "available_usd": "10"})
        self.assertEqual(sum(row["id"] == "next-controller-decision" for row in findings), 1)
        decision = findings[-1]
        self.assertNotIn("jobs", decision["budget"])
        self.assertIn("Replay", decision["instructions"])
        self.assertIn("market-response", decision["instructions"])
        self.assertIn("finite opened-Train target/horizon", decision["instructions"])
        self.assertIn("fixed new algorithm", decision["instructions"])
        self.assertIn("Do not assume 5s, 30s, 60s", decision["instructions"])

    def test_alternative_sources_keep_transfer_limits(self):
        findings = build_source_blocker_findings([], entitlement(), {"jobs": {}})
        research = next(row for row in findings
                        if row["id"] == "public-source-alternative-research")
        self.assertEqual(len(research["sources"]), 4)
        self.assertTrue(all(source["transfer_limit"] for source in research["sources"]))
        self.assertIn("not a full NFL play-by-play", research["sources"][-1]["transfer_limit"])

    def test_entitlement_loader_rejects_changed_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entitlement.json"
            value = entitlement()
            fresh_json(path, value)
            spec = {"path": path, "sha256": file_hash(path), "schema": value["schema"]}
            loaded, receipt = load_entitlement(spec)
            self.assertEqual(loaded["http_status"], 403)
            self.assertEqual(receipt["sha256"], file_hash(path))
            changed = copy.deepcopy(value)
            changed["api_key_persisted"] = True
            changed_path = Path(directory) / "changed-entitlement.json"
            fresh_json(changed_path, changed)
            spec["path"] = changed_path
            spec["sha256"] = file_hash(changed_path)
            with self.assertRaisesRegex(ValueError, "boundary"):
                load_entitlement(spec)


if __name__ == "__main__":
    unittest.main()
