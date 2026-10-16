"""Portable protocol counterexamples from the rejected02 investigation.

Exercise the actual tools with synthetic public text, not private run records
or model-produced source. Passing these tests is not parser-repair acceptance.
"""
import unittest

from edgar_forecast_tools import FilingTools


class FilingToolContract(unittest.TestCase):
    def setUp(self):
        self.tools = FilingTools.__new__(FilingTools)
        self.tools.files = {'filings/example.md': 'Header\nSynthetic revenue | 12\n'}
        self.tools.calls = self.tools.returned = 0

    def test_search_hits_have_line_not_character_offset_or_source_hash(self):
        value = self.tools.dispatch('search_files', {
            'query': 'revenue', 'path_prefix': 'filings/', 'max_hits': 1})
        self.assertEqual(value['total_matching_lines'], 1)
        hit = value['hits'][0]
        self.assertEqual(set(hit), {'path', 'line', 'text'})
        self.assertEqual(hit['line'], 2)
        self.assertNotIn('offset', hit)
        self.assertNotIn('source_sha256', hit)

    def test_read_returns_exact_character_chunk_without_invented_source_hash(self):
        value = self.tools.dispatch('read_file', {
            'path': 'filings/example.md', 'offset': 7, 'characters': 18})
        self.assertEqual(value['text'], self.tools.files['filings/example.md'][7:25])
        self.assertEqual(value['offset'], 7)
        self.assertNotIn('source_sha256', value)

    def test_limits_are_shared_across_search_and_read(self):
        self.tools.calls = 79
        self.tools.dispatch('search_files', {
            'query': 'revenue', 'path_prefix': 'filings/', 'max_hits': 1})
        with self.assertRaisesRegex(ValueError, 'Tool call limit'):
            self.tools.dispatch('read_file', {
                'path': 'filings/example.md', 'offset': 0, 'characters': 10})

    def test_unknown_paths_remain_rejected(self):
        with self.assertRaises(ValueError):
            self.tools.dispatch('read_file', {
                'path': 'filings/unknown.md', 'offset': 0, 'characters': 10})


if __name__ == '__main__':
    unittest.main()
