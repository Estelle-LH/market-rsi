"""Pure navigation tests; actual10 replay is explicit and never executes code."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_delta_author as m
from market_rsi import digest


BASE = "PROGRAM={'axis':'R'}\nNOTE='α'\ndef helper():\n    return 1\ndef run(p):\n    return helper()\n"
CASES = "CASES=[{'input':None,'expected':2}]"


class ReviewIndex(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.chosen = dict(schema='earnings_capacity_decision_v1', axis='R',
            component='research_policy', parent_pair_sha256='a'*64, feedback_sha256='b'*64,
            hypothesis='Synthetic edit navigation', expected_effect='Test actual changed source')
        self.version = 'c'*64
        self.make()

    def save(self, name, value, *, raw=False):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = value.encode('utf-8') if raw else json.dumps(value, sort_keys=True).encode()
        path.write_bytes(data)
        return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest())

    def make(self, source=BASE, edits=None):
        self.parent_text = source
        self.parent = self.save('parent.py', source, raw=True)
        self.patch = dict(decision_sha256=digest(self.chosen), parent_source_sha256=self.parent['sha256'],
            edits=edits or [dict(kind='replace', old_text='return 1', new_text='return 2')], test_text=CASES)
        self.refresh()

    def refresh(self):
        response = dict(status='completed', output=[dict(type='message', role='assistant',
            content=[dict(type='output_text', text=json.dumps(self.patch))])])
        self.original = self.save('response.json', response)
        self.business = m.assemble(self.parent, self.chosen, response)
        self.source = self.save('candidate.py', self.business['source_text'], raw=True)
        self.tests = self.save('cases.py', CASES, raw=True)
        self.assembly_value = dict(schema='earnings_population_delta_assembly_v1', axis=self.chosen['axis'],
            parent_version_id=self.chosen['parent_pair_sha256'], parent_source=self.parent,
            raw_patch_response=self.original, source=self.source, tests=self.tests,
            scientific_decision_sha256=digest(self.chosen), assembled_business_sha256=digest(self.business))
        self.assembly = self.save('delta-assembly.json', self.assembly_value)

    def index(self, **changes):
        args = dict(parent_binding=self.parent, chosen=self.chosen, original_binding=self.original,
                    source_binding=self.source, version_id=self.version, assembly_binding=self.assembly)
        args.update(changes)
        return m.review_index(**args)

    def page(self, ref):
        self.assertEqual(ref['tool'], 'read_population_program')
        args = ref['arguments']
        self.assertEqual((args['version_id'], args['axis']), (self.version, self.chosen['axis']))
        self.assertTrue(1 <= args['characters'] <= 4000)
        source = Path(self.source['path']).read_bytes().decode()
        return source[args['offset']:args['offset']+args['characters']]

    def test_exact_identities_entrypoint_and_original_source_unchanged(self):
        result = self.index()
        self.assertEqual(result['source'], self.source)
        self.assertEqual(result['parent'], self.parent)
        self.assertEqual(result['raw_patch_response'], self.original)
        self.assertEqual(result['assembly'], self.assembly)
        self.assertEqual(result['decision_sha256'], digest(self.chosen))
        self.assertEqual(result['entrypoint']['name'], 'run')
        self.assertIn('def run', self.page(result['first_read']))
        self.assertIn('helper', [x['name'] for x in result['changed_functions']])
        self.assertEqual(Path(self.parent['path']).read_bytes(), BASE.encode())

    def test_unsorted_multiple_edits_unicode_CRLF_and_append_coordinates(self):
        original = BASE.replace('\n', '\r\n')
        self.make(original, [dict(kind='replace', old_text='return 1', new_text='return 200'),
            dict(kind='replace', old_text="NOTE='α'", new_text="NOTE='研究'"),
            dict(kind='append', old_text='', new_text='\r\ndef added(): return "追加"\r\n')])
        result = self.index(); text = Path(self.source['path']).read_bytes().decode()
        self.assertEqual(result['source_characters'], len(text))
        self.assertNotEqual(len(text), len(text.encode()))
        for row in result['changed_ranges']:
            lo, hi = row['candidate']
            if row['kind'] == 'append': self.assertEqual(text[lo:hi], self.patch['edits'][-1]['new_text'])
            else: self.assertIn(text[lo:hi], [e['new_text'] for e in self.patch['edits']])
        self.assertIn('\r\n', self.page(result['first_read']))
        self.assertEqual({x['name'] for x in result['changed_functions']}, {'helper', 'added'})

    def test_deletion_and_unchanged_entrypoint_have_valid_source_coordinates(self):
        self.make(BASE, [dict(kind='replace', old_text="NOTE='α'\n", new_text='')])
        result = self.index()
        row = result['changed_ranges'][0]
        self.assertEqual(row['candidate'][0], row['candidate'][1])
        self.assertIn('def run', self.page(result['first_read']))
        self.assertEqual(result['changed_functions'], [])
        self.make(BASE.replace('    return 1', '    # removable\n    return 1'),
                  [dict(kind='replace', old_text='    # removable\n', new_text='')])
        self.assertIn('helper', [x['name'] for x in self.index()['changed_functions']])

    def test_AST_physical_lines_ignore_unicode_string_literal_separators(self):
        for separator in ('\u0085', '\u2028', '\u2029', '\v', '\f', '\x1c'):
            for newline in ('\n', '\r\n', '\r'):
                for trailing in (True, False):
                    source = BASE.replace("NOTE='α'", "NOTE='α" + separator + "β'")
                    source = source.replace('\n', newline)
                    if not trailing:
                        source = source[:-len(newline)]
                    with self.subTest(separator=repr(separator), newline=repr(newline), trailing=trailing):
                        self.make(source)
                        index = self.index()
                        actual = self.business['source_text']
                        self.assertEqual(index['entrypoint']['start_char'], actual.index('def run(p):'))
                        self.assertEqual(index['entrypoint']['end_char'], len(actual))
                        self.assertTrue(self.page(index['first_read']).startswith('def run(p):'))

    def test_R_and_H_supported_without_body_execution(self):
        marker = self.root/'MUST_NOT_EXECUTE'
        for axis in ('R', 'H'):
            self.chosen.update(axis=axis, component='research_policy' if axis == 'R' else 'tool_interface')
            header = "PROGRAM={'axis':'R'}\n" if axis == 'R' else "PROGRAM={'axis':'H','tools':[]}\n"
            self.make(header+f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef run(p): return 1\n")
            self.assertEqual(self.index()['axis'], axis)
            self.assertFalse(marker.exists())

    def test_compact_index_retains_all_ranges_and_entrypoint(self):
        source = BASE + ''.join(f'def fn{i}(): return {i}\n' for i in range(250))
        edits = [dict(kind='replace', old_text=f'def fn{i}(): return {i}\n',
                      new_text=f'def fn{i}(): return {i+1000}\n') for i in range(15)]
        edits.append(dict(kind='append', old_text='',
            new_text='\n'+''.join(f'def added{i}(): return {i}\n' for i in range(300))))
        self.make(source, edits)
        result = self.index()
        self.assertEqual(len(result['changed_ranges']), 16)
        self.assertTrue(result['omitted_functions'] > 0)
        self.assertEqual(len(result['changed_functions'])+result['omitted_functions'], result['total_changed_functions'])
        self.assertLessEqual(len(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()), 6000)
        self.assertIn('def run', self.page(result['first_read']))

    def test_decorators_and_last_run_declaration_are_navigation_not_execution(self):
        self.make(BASE, [dict(kind='append', old_text='', new_text='\n@decorator\ndef run(p): return 3\n')])
        result = self.index()
        self.assertTrue(self.page(result['first_read']).startswith('@decorator'))
        self.assertEqual(result['entrypoint']['start_char'], self.business['source_text'].index('@decorator'))

    def test_path_omission_is_explicit_and_keeps_all_verified_SHA_identities(self):
        # Synthetic original-read seam exercises metadata sizing only; canonical
        # file/hash checks are tested above and in the original Delta tests.
        source = BASE + ''.join(f'# unique{i:02d}\n' for i in range(15))
        edits = [dict(kind='replace', old_text=f'# unique{i:02d}\n', new_text=f'# altered{i:02d}\n')
                 for i in range(15)] + [dict(kind='append', old_text='', new_text='\n# appended\n')]
        self.make(source, edits)
        bindings = [self.parent, self.original, self.source, self.assembly, self.tests]
        content = {b['sha256']:Path(b['path']).read_bytes() for b in bindings}
        long = lambda b: dict(path='/synthetic-size-only/'+('x'*5000)+'/'+Path(b['path']).name,
                              sha256=b['sha256'])
        parent, original, assembled, tests = map(long, (self.parent,self.original,self.source,self.tests))
        value = dict(self.assembly_value, parent_source=parent,raw_patch_response=original,
                     source=assembled, tests=tests)
        raw = json.dumps(value,sort_keys=True).encode()
        assembly = dict(path='/synthetic-size-only/'+('y'*5000)+'/assembly.json',
                        sha256=hashlib.sha256(raw).hexdigest())
        content[assembly['sha256']] = raw
        with patch.object(m, '_original', side_effect=lambda b:content[b['sha256']]):
            result = m.review_index(parent,self.chosen,original,assembled,
                                   version_id=self.version,assembly_binding=assembly)
        self.assertTrue(result['binding_paths_omitted'])
        for key,bound in (('parent',parent),('source',assembled),
                          ('raw_patch_response',original),('assembly',assembly)):
            self.assertEqual(result[key],dict(sha256=bound['sha256']))
        self.assertEqual(len(result['changed_ranges']),16)
        self.assertIn('def run',self.page(result['first_read']))
        self.assertLessEqual(len(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()),6000)

    def test_existing_pager_schema_still_bounds_offset_and_page_size(self):
        import inspect
        from earnings_population_broker import PopulationBroker
        text = inspect.getsource(PopulationBroker._definitions)
        self.assertNotIn('Start offset0',text)
        self.assertIn('change/function character offsets',text)
        self.assertIn("'maximum': 4000",text)
        self.assertIn("'maximum': 65536",text)

    def test_wrong_identity_and_malformed_version_fail(self):
        for name in ('parent_binding', 'original_binding', 'source_binding', 'assembly_binding'):
            binding = deepcopy(getattr(self, {'parent_binding':'parent','original_binding':'original',
                'source_binding':'source','assembly_binding':'assembly'}[name]))
            binding['sha256'] = 'f'*64
            with self.subTest(name=name), self.assertRaises(ValueError): self.index(**{name:binding})
        with patch.object(m, '_original', side_effect=AssertionError('No file read')):
            with self.assertRaises(ValueError): self.index(version_id='bad')

    def test_wrong_decision_and_validly_rehashed_false_assembly_fail(self):
        changed = dict(self.chosen, hypothesis='Not the original choice')
        with self.assertRaises(ValueError): self.index(chosen=changed)
        for key, value in (('axis','H'), ('parent_version_id','f'*64),
                           ('assembled_business_sha256','f'*64), ('source',self.parent),
                           ('parent_source',self.source), ('scientific_decision_sha256','f'*64)):
            false = dict(self.assembly_value, **{key:value})
            binding = self.save('false-assembly.json', false)
            with self.subTest(key=key), self.assertRaises(ValueError): self.index(assembly_binding=binding)

    def test_changed_tests_or_assembled_source_cannot_reuse_valid_patch(self):
        false = dict(self.assembly_value, tests=self.save('false-cases.py', CASES+'# changed', raw=True))
        with self.assertRaises(ValueError): self.index(assembly_binding=self.save('false-assembly.json', false))
        altered = self.save('false-source.py', self.business['source_text']+'# changed', raw=True)
        false = dict(self.assembly_value, source=altered)
        with self.assertRaises(ValueError): self.index(source_binding=altered,
            assembly_binding=self.save('false-assembly.json', false))

    def test_noop_or_tampered_raw_delta_cannot_be_indexed(self):
        for edit in (dict(kind='replace', old_text='return 1', new_text='return 1'),
                     dict(kind='replace', old_text='missing', new_text='return 2')):
            value = dict(self.patch, edits=[edit])
            raw = dict(status='completed', output=[dict(type='message', role='assistant',
                content=[dict(type='output_text', text=json.dumps(value))])])
            with self.assertRaises(ValueError): self.index(original_binding=self.save('invalid-response.json', raw))


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_REVIEW_INDEX10') == '1',
                     'Explicit original10 read-only navigation replay required')
class Actual10Navigation(unittest.TestCase):
    def actual_index(self):
        root = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016')
        folder = root/'attempts/edgar-population-20261016-10/roles/author-01'
        pin = lambda p: dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        assembly_binding = pin(folder/'delta-assembly.json')
        assembly = json.loads(Path(assembly_binding['path']).read_bytes())
        projection = json.loads(Path(assembly['scientific_decision']['path']).read_bytes())
        chosen = projection['scientific_decision']
        source = Path(assembly['source']['path']).read_bytes().decode()
        self.assertEqual(assembly['source']['sha256'], 'b3935bed3bfcbde0f7192a06d8bcaabafafbae4b75d6b498545c93556c689b0d')
        result = m.review_index(assembly['parent_source'], chosen, assembly['raw_patch_response'],
            assembly['source'], version_id='5eba96ab7c82a1da6ed173ec9c08aec8f067829a494a552f9f73e1cd94ee3c08',
            assembly_binding=assembly_binding)
        return result, source

    def test_exact_candidate_changed_entrypoint_not_inherited_prefix(self):
        result, source = self.actual_index()
        self.assertEqual(result['changed_ranges'][1]['candidate'], [42028, 62841])
        args = result['first_read']['arguments']
        self.assertEqual((args['offset'], args['characters']), (60493, 2348))
        page = source[args['offset']:args['offset']+args['characters']]
        self.assertTrue(page.startswith('def run(payload):'))
        self.assertIn("base_payload['research_observations'] = []", page)
        names = {f['name']: f['start_char'] for f in result['changed_functions']}
        self.assertEqual(names['c_extract'], 46995)
        self.assertEqual(names['c_forecast'], 56384)
        self.assertLessEqual(len(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()), 6000)

    def review_transport(self, *, unfit=False):
        # Original Reviewer/counting/reservation/HTTP/pager paths; count/model
        # replies and the temporary ledger are synthetic. Broker registration
        # is a metadata seam, not Native/live admission or quality evidence.
        from unittest.mock import Mock
        from earnings_population_broker import PopulationBroker
        from earnings_population_roles import PopulationReviewer
        from supervisor_harness import capacity_feedback_engine as engine
        from test_earnings_capacity_controller_transport import _TransportFixture, _wire
        index, source = self.actual_index()
        temp = tempfile.TemporaryDirectory(prefix='review-index-transport-')
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        fixture = _TransportFixture(self, root/'transport')
        fixture.rates['effort'] = 'max'
        slot = fixture.root/'roles/review-01'
        value = dict(fixture.context, schema='earnings_capacity_review_transport_v1',
            rates=fixture.rates, limits=dict(max_input_tokens=20000,max_output_tokens=16384,wall_seconds=600),
            slots=[str(slot)])
        binding = engine.save(fixture.root/'review-context.json',value)
        broker = PopulationBroker.__new__(PopulationBroker)
        broker.root = root/'paging';broker.root.mkdir()
        broker.identity = (broker.root.stat().st_dev,broker.root.stat().st_ino)
        owned = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016')
        prior = json.loads((owned/'inputs/edgar-population-20261016-10/initial-population.json').read_bytes())
        unchanged_h = prior['versions']['29ac9cbd7166c6e83cb1866028485264d6649fcfe152da9414ec5c3b163742b3']['H']
        broker.versions = {index['version_id']:{'R':index['source'],'H':unchanged_h}}
        broker.research_context_binding=None;broker.prior_files=None
        broker.calls=0;broker.returned=0;broker.failed=set();broker.definitions=broker._definitions()
        role=PopulationReviewer(binding,broker=broker,budget=fixture.budget,
                                client_factory=fixture.factory,max_turns=2)
        first=fixture.response();first['output']=[dict(type='function_call',call_id='changed-run',
            name=index['first_read']['tool'],arguments=json.dumps(index['first_read']['arguments']))]
        final=fixture.response(dict(candidate_id=index['version_id'],accepted_for_exploration=False,
            rationale='Inert transport verdict only; no scientific judgment.'))
        replies=[first,final];counts=[];generated=[];test=self

        class Connection:
            def __init__(self,host,timeout):
                test.assertEqual(host,'api.openai.com');self.timeout=timeout
            def request(self,method,endpoint,body,headers):
                test.assertEqual(method,'POST');self.endpoint=endpoint;self.payload=json.loads(body)
            def getresponse(self):
                if self.endpoint=='/v1/responses/input_tokens':
                    counts.append(deepcopy(self.payload))
                    raw=_wire(dict(object='response.input_tokens',input_tokens=20001 if unfit else 100))
                elif self.endpoint=='/v1/responses':
                    generated.append(deepcopy(self.payload))
                    if len(generated)>2:raise AssertionError('No generation retry')
                    raw=_wire(replies[len(generated)-1])
                else:raise AssertionError('Unexpected synthetic endpoint')
                return Mock(status=200,getheader=Mock(return_value='inert-review-index'),
                            read=Mock(side_effect=lambda limit:raw[:limit]))
            def close(self):pass

        prompt=dict(candidate_id=index['version_id'],source_change_index=index)
        with patch('earnings_http.http.client.HTTPSConnection',side_effect=Connection):
            if unfit:
                with self.assertRaisesRegex(RuntimeError,'BudgetStop'):role.review(prompt,str(slot))
            else:role.review(prompt,str(slot))
        return fixture,broker,slot,index,source,counts,generated

    def test_actual_index_reaches_first_final_counted_Reviewer_and_original_pager(self):
        fixture,broker,slot,index,source,counts,generated=self.review_transport()
        self.assertEqual(len(generated),2)
        self.assertEqual(broker.calls,1)
        for request in [*counts,*generated]:
            self.assertEqual(json.loads(request['input'][0]['content'])['source_change_index'],index)
            self.assertEqual(request['model'],'gpt-6.1-sol')
        final=generated[-1];self.assertEqual(final['tool_choice'],'none')
        returned=next(x for x in final['input'] if x.get('type')=='function_call_output')
        page=json.loads(returned['output'])['value']
        self.assertEqual(page['offset'],60493)
        self.assertEqual(page['source_sha256'],index['source']['sha256'])
        self.assertEqual(page['text'],source[60493:62841])
        self.assertIn("base_payload['research_observations'] = []",page['text'])
        self.assertEqual(fixture.budget.db.execute("SELECT status FROM requests WHERE id!='fixture-prior'").fetchall(),
                         [('settled',),('settled',)])
        self.assertTrue((slot/'01-request.json').is_file())
        self.assertTrue((slot/'02-request.json').is_file())

    def test_original_20k_refusal_stops_before_any_generation(self):
        fixture,broker,slot,index,source,counts,generated=self.review_transport(unfit=True)
        self.assertTrue(counts);self.assertEqual(generated,[]);self.assertEqual(broker.calls,0)
        self.assertEqual(fixture.budget.db.execute("SELECT COUNT(*) FROM requests WHERE id!='fixture-prior'").fetchone()[0],0)
        self.assertFalse(json.loads((slot/'result.json').read_bytes())['retry_allowed'])


if __name__ == '__main__': unittest.main()
