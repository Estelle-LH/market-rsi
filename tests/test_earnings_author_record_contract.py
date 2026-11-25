"""Author sees the existing wire types; no data or state-schema migration."""
import inspect
import unittest
from earnings_open_roles import AUTHOR
from earnings_research_state import ResearchState
from earnings_open_worker import ProgramWorker


class AuthorRecordContractTests(unittest.TestCase):
    def test_prompt_declares_real_wrapped_records_and_text_inputs(self):
        for value in ("Markdown text", "TSV text", "'sha256':...", "'record':...", "possibly empty",
                      "source_path", "source_sha256", "period_end", "quote", "literal", "inputs",
                      "hypothesis", "not pre-normalized", "optional evidence phase"):
            self.assertIn(value, AUTHOR)
        self.assertIn('set(item) != {"sha256", "record"}', inspect.getsource(ResearchState.validate))
        source=inspect.getsource(ProgramWorker.__init__)
        self.assertIn("'records':deepcopy(self.state['records'])", source)
