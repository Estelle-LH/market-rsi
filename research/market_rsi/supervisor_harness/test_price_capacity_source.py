"""Synthetic static checks only: no account, imports of generated code or Train."""
from unittest import TestCase, main
from unittest.mock import patch

from supervisor_harness import price_capacity_source as s

SOURCE = """def apply(context):
    lessons = context.get('history', [])
    if isinstance(lessons, dict):
        lessons = [lessons.get('last_experiment', {})]
    negative = [x for x in lessons if x.get('decision') == 'REVERT']
    return {'negative_count': len(negative), 'remaining_questions': [x.get('question') for x in negative]}
"""
TEST = """from capacity import apply
def test_capacity():
    result = apply({'history': [{'decision': 'REVERT', 'question': 'synthetic followup'}]})
    assert result['negative_count'] == 1
    assert result['remaining_questions'] == ['synthetic followup']
if __name__ == '__main__':
    test_capacity()
"""


class CapacitySourceTests(TestCase):
    def test_source_and_test_are_only_parsed_not_imported_or_run(self):
        with patch('importlib.util.spec_from_file_location') as imported, patch('subprocess.Popen') as launch:
            self.assertTrue(s.validate_source(SOURCE)['passed'])
            self.assertTrue(s.validate_source(TEST, is_test=True)['passed'])
        self.assertFalse(imported.called); self.assertFalse(launch.called)
        self.assertFalse(s.validate_source(SOURCE)['arbitrary_code_containment'])

    def test_closed_io_process_network_dynamic_and_model_calls(self):
        for text in ("import os", "import socket", "import subprocess", "from pathlib import Path",
                "import json", "open('x')", "eval('x')", "exec('x')", "getattr(context, 'x')",
                "globals()", "context.__class__", "context.read_text()", "context.fit()",
                "context.sample()", "context.load('x')", "context.call_provider()", "(lambda: 1)()"):
            source = SOURCE.replace("    lessons = context.get('history', [])", "    " + text)
            with self.subTest(text=text), self.assertRaises((ValueError, SyntaxError)):
                s.validate_source(source)

    def test_module_execution_defaults_api_alias_and_test_main(self):
        bad = (SOURCE + '\napply({})\n', SOURCE + '\nX = apply({})\n',
            SOURCE.replace('apply(context)', 'apply(context={})'), SOURCE.replace('apply(context)', 'apply(*context)'),
            SOURCE.replace('def apply(context)', '@apply\ndef apply(context)'), SOURCE + '\ncontext.x = 1\n',
            SOURCE + '\nX = [i for i in range(3)]\n', SOURCE.replace('apply(context)', 'apply(context: apply({}))'),
            SOURCE.replace('apply(context):', 'apply(context) -> apply({}):'), SOURCE + '\nX: apply({}) = 1\n')
        for source in bad:
            with self.subTest(source=source), self.assertRaises(ValueError): s.validate_source(source)
        for test in (TEST.replace('test_capacity()', 'test_capacity(context)'), TEST.split('if __name__')[0],
                TEST.replace('from capacity import apply', 'from other import apply'),
                TEST.replace('from capacity import apply', 'from capacity import *')):
            with self.subTest(test=test), self.assertRaises(ValueError): s.validate_source(test, is_test=True)

    def test_pure_helpers_math_constants_and_distinct_module_name(self):
        source = """import math as m
LIMIT = 5
def bounded(value):
    return min(LIMIT, max(0, value))
def apply(context):
    return {'magnitude': bounded(abs(context.get('delta', 0))), 'finite': m.isfinite(context.get('delta', 0))}
"""
        self.assertTrue(s.validate_source(source)['passed'])
        self.assertTrue(s.validate_source(TEST.replace('from capacity', 'from researcher_v2'),
            is_test=True, module_name='researcher_v2')['passed'])
        with self.assertRaises(ValueError): s.validate_source(source, module_name='math')
        with self.assertRaises(ValueError): s.validate_source('#' * 24577)


if __name__ == '__main__': main()
