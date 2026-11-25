"""Synthetic instruction/boundary regressions; no research-quality claim."""
from copy import deepcopy
import re
import unittest
from unittest.mock import patch

import earnings_open_roles as roles
from edgar_forecast_tools import FilingTools, TOOLS
from market_rsi import digest
import test_earnings_open_roles as role_fixture
import test_earnings_research_state as state_fixture


class AuthorEvidenceLimitsTests(unittest.TestCase):
    def test_original_evidence_limits_are_explicit_for_both_R_request_stages(self):
        text = roles.AUTHOR
        compact = re.sub(r"\s+", "", text)
        for required in ("read_file", "offset>=0", "characters1..20000", "query1..200", "max_hits1..50"):
            self.assertIn(required, compact)
        self.assertIn("logical", text)
        self.assertIn("initial", text.lower())
        self.assertIn("research_observations", text)
        self.assertIn("research_requests", text)

    def test_initial_and_final_Author_physical_requests_keep_same_evidence_instructions(self):
        helper = role_fixture.OpenRoleTests("test_author_finalization_documents_actual_schema_and_preserves_exact_candidate_fields")
        helper.setUp(); self.addCleanup(helper.doCleanups)
        chosen = helper.choice("R")
        source = "PROGRAM={'axis':'R'}\ndef run(p): return {'advice':'Check original units'}\n"
        payload = {"decision_sha256": digest(chosen), "source_text": source,
                   "test_text": "CASES=[{'input':{},'expected':{'advice':'Check original units'}}]"}
        helper.generations = [helper.tool_response(helper.call()), helper.message(payload)]
        service = helper.service(author=True, max_turns=2)
        with patch.object(roles, "budgeted_response", side_effect=helper.fake_paid):
            service.author(chosen, {"axis": "R"}, str(helper.slot))
        self.assertEqual(len(helper.requests), 2)
        for request in helper.requests:
            self.assertTrue(request["instructions"].startswith(roles.AUTHOR))
            self.assertIn("20000", request["instructions"])
            self.assertIn("research_observations", request["instructions"])
        self.assertEqual(helper.requests[0]["instructions"], roles.AUTHOR)
        self.assertEqual(helper.requests[-1]["instructions"], roles.AUTHOR + roles.FINALIZE + roles.FINAL_AUTHOR)

    def test_original_read_implementation_and_schema_limits_are_not_enlarged(self):
        data = state_fixture.ResearchStateTests("test_append_preserves_parent_and_old_history")
        data.setUp(); self.addCleanup(data.doCleanups)
        tools = FilingTools(data.company)
        spec = next(row for row in TOOLS if row["name"] == "read_file")["parameters"]["properties"]
        self.assertEqual(spec, {"path": {"type": "string"}, "offset": {"type": "integer"}, "characters": {"type": "integer"}})
        before = deepcopy(tools.files)
        for characters in (1, 20000):
            value = tools.dispatch("read_file", {"path": "filings/old.md", "offset": 0, "characters": characters})
            self.assertEqual(value["text"], before["filings/old.md"][:characters])
        for arguments in ({"path": "filings/old.md", "offset": -1, "characters": 1},
                          {"path": "filings/old.md", "offset": 0, "characters": 20001},
                          {"path": "../private", "offset": 0, "characters": 1}):
            with self.assertRaises(ValueError): tools.dispatch("read_file", arguments)
        self.assertEqual(tools.files, before)
