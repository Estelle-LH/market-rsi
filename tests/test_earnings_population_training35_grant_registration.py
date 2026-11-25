"""Exact A2 registration statement on temporary real Reader artifacts.

The AST slice is original trusted Source, NOT candidate code. Only the budget
and physical helper calls in that slice are fixture stubs. This does not run or
authenticate the whole A2 incident, any real grant, ledger, ancestry or Native.
"""
import ast
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_continuation as history
import earnings_population_recovery as recovery
import earnings_population_completed as completed
from supervisor_harness import capacity_feedback_engine as engine


def function(path,name):
    return next(node for node in ast.parse(Path(path).read_bytes()).body
                if isinstance(node,ast.FunctionDef) and node.name==name)


def reader_call(node,method,argument):
    return (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
        and isinstance(node.value.func,ast.Attribute)
        and isinstance(node.value.func.value,ast.Name)
        and node.value.func.value.id=='reader' and node.value.func.attr==method
        and len(node.value.args)==1 and isinstance(node.value.args[0],ast.Name)
        and node.value.args[0].id==argument)


def source_slice():
    original = function(recovery.__file__,'_verify_training_stage_attachment')
    index = next(n for n,node in enumerate(original.body) if reader_call(node,'scan','runtime'))
    return original.body[index-2:index+2]


class GrantRegistrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='training35-grant-independent-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.root,self.repo = self.home/'owned',self.home/'repo'
        self.ledger = self.home/'pilot/api-budget.sqlite3'  # Never opened/created.
        self.reader = history._Reader(self.root,self.ledger,self.repo,
                                      'edgar-population-20261016-35')
        self.review_path = self.home/'review-evidence/independent-review.json'
        self.grant_path = self.ledger.parent/'cumulative400-grant.json'
        for path in (self.review_path,self.grant_path):path.parent.mkdir(parents=True,exist_ok=True)
        self.review = engine.save(self.review_path,{'invented_original_review_bytes':True})
        self.grant = engine.save(self.grant_path,{'invented_original_grant_bytes':True})
        self.runtime = dict(review=self.review,budget_amendment=self.grant)
        self.study = {'same_original_grant_again':self.grant}

    def execute(self,*,budget_error=False):
        events = []
        def budget(*args):
            events.append('existing_budget_success' if not budget_error else 'existing_budget_refusal')
            if budget_error:raise ValueError('Original budget refused')
            return []
        namespace = dict(reader=self.reader,runtime=self.runtime,study=self.study,
            audit={},owner={'budget_summary':{}},evidence=[],Path=Path,
            _training_attachment_physical=lambda *args:[],_budget=budget)
        module = ast.fix_missing_locations(ast.Module(body=deepcopy(source_slice()),type_ignores=[]))
        exec(compile(module,'<original-A2-budget-registration-scan-slice>','exec'),namespace)
        return events

    def test_exact_statement_is_between_original_budget_and_unchanged_two_scans(self):
        body = source_slice()
        self.assertEqual(len(body),4)
        self.assertIsInstance(body[0],ast.AugAssign)
        self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
                            and n.func.id=='_budget' for n in ast.walk(body[0])))
        expected = ast.parse("reader.extra.update(Path(runtime[key]['path']) for key in ('review','budget_amendment'))").body[0]
        self.assertEqual(ast.dump(body[1]),ast.dump(expected))
        self.assertTrue(reader_call(body[2],'scan','runtime'))
        self.assertTrue(reader_call(body[3],'scan','study'))
        legacy = function(completed.__file__,'_load')
        self.assertTrue(any(ast.dump(node)==ast.dump(expected) for node in legacy.body))

    def test_original_real_reader_reproduces_missing_grant_then_exact_slice_succeeds(self):
        self.reader.extra.add(self.review_path)
        with self.assertRaisesRegex(ValueError,'outside exact owned roots'):
            self.reader.scan(self.runtime)
        self.reader.extra.clear()
        self.assertEqual(self.execute(),['existing_budget_success'])
        self.assertEqual(self.reader.extra,{self.review_path,self.grant_path})
        self.assertFalse(self.ledger.exists())

    def test_existing_budget_refusal_stops_before_any_registration_or_scan(self):
        with self.assertRaisesRegex(ValueError,'Original budget refused'):
            self.execute(budget_error=True)
        self.assertEqual(self.reader.extra,set())

    def test_registration_never_weakens_original_review_or_grant_byte_hash(self):
        self.execute()
        for key in ('review','budget_amendment'):
            path = Path(self.runtime[key]['path']); raw = path.read_bytes()
            path.write_bytes(b'{"changed_original_bytes":true}')
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'hash differs'):
                self.reader.scan(self.runtime)
            path.write_bytes(raw)

    def test_unrelated_sibling_and_directory_are_not_added_to_reader_policy(self):
        self.execute()
        sibling = self.grant_path.parent/'unrelated-original.json'
        bound = engine.save(sibling,{'unrelated':True})
        original = Path.read_bytes
        def no_sibling_read(path):
            if path==sibling:raise AssertionError('Forbidden sibling bytes must not be opened')
            return original(path)
        with patch.object(Path,'read_bytes',no_sibling_read), \
             self.assertRaisesRegex(ValueError,'outside exact owned roots'):
            self.reader.read(bound)
        self.assertNotIn(self.grant_path.parent,self.reader.extra)
        self.assertNotIn(self.review_path.parent,self.reader.extra)

    def test_forged_hash_and_noncanonical_registered_alias_still_refuse(self):
        self.execute()
        with self.assertRaisesRegex(ValueError,'hash differs'):
            self.reader.read(dict(self.grant,sha256='0'*64))
        alias = dict(self.grant,path=str(self.grant_path.parent/'..'/'pilot'/self.grant_path.name))
        self.runtime['budget_amendment'] = alias
        with self.assertRaisesRegex(ValueError,'Canonical'):
            self.execute()

    def test_ordinary_owned_legacy_reads_do_not_gain_any_extra_root(self):
        path = self.root/'attempts/edgar-population-20261016-35/ordinary.json'
        path.parent.mkdir(parents=True)
        bound = engine.save(path,{'legacy_original':True})
        self.assertEqual(self.reader.read(bound),{'legacy_original':True})
        self.assertEqual(self.reader.extra,set())
        with self.assertRaisesRegex(ValueError,'outside exact owned roots'):
            self.reader.read(self.grant)


if __name__ == '__main__':
    unittest.main()
