"""Inert delta delivery/AST checks; no provider, ledger or candidate execution."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_population_delta_author as delta
from earnings_open_program import candidate, program
from market_rsi import digest


CASES = "CASES = [{'input': None, 'expected': 2}]"
R = "PROGRAM = {'axis':'R'}\nNOTE = 'α'\ndef run(payload):\n    return 1\n"
H = "PROGRAM = {'axis':'H', 'tools':[]}\ndef run(payload):\n    return 1\n"


def choice(axis='R'):
    return dict(schema='earnings_capacity_decision_v1', axis=axis,
        component='research_policy' if axis == 'R' else 'tool_interface',
        parent_pair_sha256='a'*64, feedback_sha256='b'*64,
        hypothesis='Test one synthetic implementation change.', expected_effect='Synthetic bounded experiment.')


def reply(value):
    return dict(status='completed', error=None, output=[dict(type='message', role='assistant',
        status='completed', content=[dict(type='output_text', text=json.dumps(value))])])


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.parent = self.root/'parent.py'
        self.chosen = choice()
        self.bind(R)

    def bind(self, source):
        self.parent.write_bytes(source.encode('utf-8'))
        self.bound = dict(path=str(self.parent), sha256=hashlib.sha256(self.parent.read_bytes()).hexdigest())
        return self.bound

    def patch(self, edits=None, **changes):
        value = dict(decision_sha256=digest(self.chosen), parent_source_sha256=self.bound['sha256'],
            edits=edits if edits is not None else [dict(kind='replace', old_text='return 1', new_text='return 2')],
            test_text=CASES)
        value.update(changes)
        return value

    def assemble(self, value=None):
        return delta.assemble(self.bound, self.chosen, reply(self.patch() if value is None else value))

    def test_R_and_H_original_candidate_parser_with_no_execution(self):
        for axis, text in [('R', R), ('H', H)]:
            with self.subTest(axis=axis):
                self.chosen = choice(axis)
                self.bind(text)
                result = self.assemble()
                self.assertEqual(set(result), {'decision_sha256', 'source_text', 'test_text'})
                parsed = candidate(result, program(text.encode(), axis), self.chosen)
                self.assertEqual(parsed['profile']['axis'], axis)
                self.assertFalse(parsed['tests_executed'])
                self.assertEqual(self.parent.read_bytes(), text.encode())

    def test_Unicode_CRLF_unsorted_original_anchors_preserve_every_other_byte(self):
        original = R.replace('\n', '\r\n')
        self.bind(original)
        edits = [dict(kind='replace', old_text='return 1', new_text='return 2'),
                 dict(kind='replace', old_text="NOTE = 'α'", new_text="NOTE = '研究'")]
        value, decision_before = self.patch(edits), deepcopy(self.chosen)
        raw = reply(value)
        untouched = deepcopy(raw)
        result = delta.assemble(self.bound, self.chosen, raw)
        self.assertEqual(result['source_text'], original.replace('return 1', 'return 2').replace("NOTE = 'α'", "NOTE = '研究'"))
        self.assertEqual(self.parent.read_bytes(), original.encode())
        self.assertEqual(raw, untouched)
        self.assertEqual(self.chosen, decision_before)

    def test_replace_then_one_append_and_deletion(self):
        value = self.patch([dict(kind='replace', old_text="NOTE = 'α'\n", new_text=''),
            dict(kind='append', old_text='', new_text='\n# new method helper\n')])
        self.assertEqual(self.assemble(value)['source_text'], R.replace("NOTE = 'α'\n", '')+'\n# new method helper\n')

    def test_adjacent_ranges_and_sixteen_edits(self):
        source = R + ''.join(f'# marker{i:02d}\n' for i in range(16))
        self.bind(source)
        edits = [dict(kind='replace', old_text=f'# marker{i:02d}\n', new_text=f'# changed{i:02d}\n') for i in range(16)]
        self.assertTrue(self.assemble(self.patch(edits))['source_text'].endswith('# changed15\n'))
        with self.assertRaises(ValueError):
            self.assemble(self.patch(edits+[dict(kind='append', old_text='', new_text='# excess\n')]))

    def test_missing_ambiguous_and_overlapping_anchors(self):
        cases = [([dict(kind='replace', old_text='absent', new_text='x')], R),
            ([dict(kind='replace', old_text='needle', new_text='x')], R+'# needle needle\n'),
            ([dict(kind='replace', old_text='aa', new_text='x')], R+'# aaa\n'),
            ([dict(kind='replace', old_text='return 1', new_text='return 2'),
              dict(kind='replace', old_text='turn 1', new_text='turn 3')], R),
            ([dict(kind='replace', old_text='return 1', new_text='return 2'),
              dict(kind='replace', old_text='return 2', new_text='return 3')], R)]
        for edits, source in cases:
            with self.subTest(edits=edits):
                self.bind(source)
                with self.assertRaises(ValueError):
                    self.assemble(self.patch(edits))

    def test_noop_empty_append_multiple_append_and_append_order(self):
        for edits in ([], [dict(kind='replace', old_text='return 1', new_text='return 1')],
                [dict(kind='replace', old_text='', new_text='# x')],
                [dict(kind='append', old_text='', new_text='')],
                [dict(kind='append', old_text='not empty', new_text='x')],
                [dict(kind='replace', old_text='    return 1\n', new_text=''),
                 dict(kind='append', old_text='', new_text='    return 1\n')],
                [dict(kind='append', old_text='', new_text='# first\n'), dict(kind='append', old_text='', new_text='# second\n')],
                [dict(kind='append', old_text='', new_text='# first\n'), dict(kind='replace', old_text='return 1', new_text='return 2')]):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                self.assemble(self.patch(edits))

    def test_exact_fields_types_and_wrong_hashes(self):
        for changes in ({'decision_sha256':'c'*64}, {'parent_source_sha256':'d'*64},
                {'source_text':R}, {'edits':None}, {'edits':'replace'}, {'test_text':None}):
            value = self.patch()
            value.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.assemble(value)
        for edit in (dict(kind='replace', old_text='return 1', new_text='return 2', extra=True),
                dict(kind='unknown', old_text='return 1', new_text='return 2'),
                dict(kind='replace', old_text=1, new_text='return 2')):
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.assemble(self.patch([edit]))

    def test_parent_binding_hash_axis_and_metadata_drift(self):
        original = deepcopy(self.bound)
        self.parent.write_bytes((R+'# drift\n').encode())
        with self.assertRaises(ValueError):
            self.assemble()
        self.bind(R)
        with self.assertRaises(ValueError):
            delta.assemble(self.bound, choice('H'), reply(self.patch()))
        for bad in (dict(original, extra=True), dict(path='relative.py', sha256='a'*64),
                    dict(path=str(self.parent), sha256='A'*64)):
            with mock.patch.object(delta, 'checked') as read, self.assertRaises(ValueError):
                delta.assemble(bad, self.chosen, reply(self.patch()))
            read.assert_not_called()

    def test_syntax_metadata_and_cases_use_original_parser(self):
        for patch in (self.patch([dict(kind='replace', old_text='return 1', new_text='return (')]),
                self.patch([dict(kind='replace', old_text="'axis':'R'", new_text="'axis':'H'")]),
                self.patch(test_text='CASES = list()'), self.patch(test_text='CASES = []'),
                self.patch(test_text="CASES = [{'input': None, 'expected': 2, 'extra': 0}]")):
            with self.subTest(patch=patch), self.assertRaises((ValueError, SyntaxError)):
                self.assemble(patch)

    def test_alias_symlink_hardlink_directory_missing_rejected_before_read(self):
        directory = self.root/'directory'
        directory.mkdir()
        nested = self.root/'nested'
        nested.mkdir()
        alias = str(nested/'..'/'parent.py')
        foreign = self.root/'foreign.py'
        foreign.write_bytes(R.encode())
        link = self.root/'linked.py'
        link.symlink_to(foreign)
        hard = self.root/'hard.py'
        os.link(foreign, hard)
        for path in (alias, str(link), str(hard), str(directory), str(self.root/'missing.py')):
            with self.subTest(path=path), mock.patch.object(delta, 'checked') as read:
                with self.assertRaises(ValueError):
                    delta.assemble(dict(path=path, sha256=self.bound['sha256']), self.chosen, reply(self.patch()))
                read.assert_not_called()

    def test_original_UTF8_byte_ceilings_not_character_ceilings(self):
        self.bind(R)
        padding = '\n#'+'x'*(65536-len(R.encode())-2)
        result = self.assemble(self.patch([dict(kind='append', old_text='', new_text=padding)],
            test_text=CASES+' '*(32768-len(CASES.encode()))))
        self.assertEqual(len(result['source_text'].encode()), 65536)
        for patch in (self.patch([dict(kind='append', old_text='', new_text=padding+'x')]),
                self.patch([dict(kind='append', old_text='', new_text='#'+'界'*22000)]),
                self.patch(test_text=CASES+' '*(32769-len(CASES.encode())))):
            with self.subTest(overflow=True), self.assertRaises(ValueError):
                self.assemble(patch)

    def test_only_original_completed_no_tool_public_envelope(self):
        raw = reply(self.patch())
        variants = [self.patch(), dict(raw, status='incomplete'), dict(raw, error={'failure':True}),
            dict(raw, output=[*raw['output'], dict(type='function_call')]),
            dict(raw, output=raw['output']*2)]
        duplicate = deepcopy(raw)
        duplicate['output'][0]['content'][0]['text'] = '{"decision_sha256":"x","decision_sha256":"y"}'
        variants.append(duplicate)
        for response in variants:
            with self.subTest(response=response), self.assertRaises(ValueError):
                delta.assemble(self.bound, self.chosen, response)

    def test_parent_and_candidate_top_level_statements_are_never_executed(self):
        self.bind(R+"raise RuntimeError('never execute on host')\n")
        self.assertIn('never execute on host', self.assemble()['source_text'])


class DeltaRoleTests(unittest.TestCase):
    setUp = AssemblyTests.setUp
    bind = AssemblyTests.bind
    patch = AssemblyTests.patch
    def service(self):
        service = object.__new__(delta.DeltaAuthor)
        class Broker:
            def current_programs(inner):
                return {'R': {'source_sha256': self.bound['sha256']}}
            def research_context(inner, *, include_source=False):
                self.assertTrue(include_source)
                return {'synthetic': True, 'original_R_evidence_abi': {'phase': 'one'}}
        service.broker = Broker()
        return service

    def test_delegates_original_raw_binding_and_saves_only_actual_delta(self):
        service, original = self.service(), reply(self.patch())
        binding = dict(path=str(self.root/'raw.json'), sha256='e'*64)
        captured = {}
        def run(prompt, slot, instructions, format, decode, artifact, status):
            captured.update(prompt=prompt, instructions=instructions, format=format,
                            patch=decode(original), artifact=artifact, status=status)
            return binding
        service._run_open = mock.Mock(side_effect=run)
        before = program(R.encode(), 'R')
        self.assertIs(service.author(self.chosen, before, str(self.root/'slot'), parent_binding=self.bound), binding)
        self.assertEqual(captured['patch'], self.patch())
        self.assertEqual(captured['artifact'], 'delta')
        self.assertEqual(captured['format']['name'], delta.FORMAT_NAME)
        self.assertEqual(set(captured['format']['schema']['properties']), delta.FIELDS)
        self.assertEqual(captured['prompt']['parent_source'], self.bound)
        self.assertEqual(captured['prompt']['research_context']['original_R_evidence_abi']['phase'], 'one')
        self.assertNotIn('Return only decision_sha256, source_text and test_text', captured['instructions'])
        self.assertNotIn('source_text contains exactly one', captured['instructions'])
        self.assertIn('Arbitrary standard Python algorithms', captured['instructions'])
        self.assertIn('read_current_program(axis)', captured['instructions'])
        self.assertIn('parent_source_sha256', service._final_instruction())

    def test_broker_or_before_profile_mismatch_stops_before_model(self):
        service = self.service()
        service._run_open = mock.Mock()
        with self.assertRaises(ValueError):
            service.author(self.chosen, {'axis':'H'}, 'unused', parent_binding=self.bound)
        service.broker.current_programs = lambda: {'R': {'source_sha256':'f'*64}}
        with self.assertRaises(ValueError):
            service.author(self.chosen, {'axis':'R'}, 'unused', parent_binding=self.bound)
        service._run_open.assert_not_called()

    def test_parent_drift_after_role_start_is_rejected_at_assembly(self):
        service = self.service()
        original = reply(self.patch())
        def run(prompt, slot, instructions, format, decode, artifact, status):
            self.parent.write_bytes((R+'# concurrent drift\n').encode())
            return decode(original)
        service._run_open = mock.Mock(side_effect=run)
        with self.assertRaises(ValueError):
            service.author(self.chosen, {'axis':'R'}, 'unused', parent_binding=self.bound)

    def test_original_open_role_loop_with_scripted_generations_no_paid_accounting_claim(self):
        # Original loop and tool artifacts; model/count/budget responses are explicitly mocked.
        from test_earnings_open_roles import OpenRoleTests
        import earnings_open_roles as roles
        fixture = OpenRoleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        old = fixture.service(author=True, max_turns=2)
        fixture.broker.current_programs = lambda: {'R': {'source_sha256':self.bound['sha256']}}
        fixture.broker.handler = lambda *_: {'value': {'text':R, 'source_sha256':self.bound['sha256']}}
        service = delta.DeltaAuthor(old.binding, budget=fixture.budget, client_factory=fixture.factory,
            broker=fixture.broker, max_turns=2)
        fixture.generations = [fixture.tool_response(fixture.call(name='read_current_program', arguments={'axis':'R'})),
                               fixture.message(self.patch())]
        with mock.patch.object(roles, 'budgeted_response', side_effect=fixture.fake_paid):
            bound = service.author(self.chosen, {'axis':'R'}, str(fixture.slot), parent_binding=self.bound)
        self.assertEqual(len(fixture.requests), 2)
        self.assertEqual(fixture.requests[-1]['tool_choice'], 'none')
        self.assertTrue(all(r['text']['format']['name']==delta.FORMAT_NAME for r in fixture.requests))
        self.assertEqual(Path(bound['path']).read_bytes(), (fixture.slot/'02-response.json').read_bytes())
        saved = json.loads((fixture.slot/'delta.json').read_text())
        self.assertEqual(saved['delta'], self.patch())
        self.assertEqual(saved['original'], bound)
        self.assertFalse((fixture.slot/'candidate.py').exists())
        self.assertEqual(self.parent.read_bytes(), R.encode())


if __name__ == '__main__':
    unittest.main()
