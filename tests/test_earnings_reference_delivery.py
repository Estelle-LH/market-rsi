"""Invented reference paging and mocked Author delivery; never run prior code."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import earnings_open_broker as broker_module
import earnings_open_roles as roles
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
import test_earnings_research_state as state_fixture


class ReferenceDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.data = state_fixture.ResearchStateTests()
        self.data.setUp(); self.addCleanup(self.data.doCleanups)
        self.root = self.data.root
        prefix = "PROGRAM={'axis':'R'}\n# Invented reference α, never executed.\n"
        self.text = prefix + 'x'*(17734-len(prefix))
        self.source = self.root/'invented-reference.py'
        self.source.write_bytes(self.text.encode('utf-8'))
        self.source_binding = engine.pin(self.source)
        self.base = {'schema':'earnings_repair_context_v1',
            'human_task':'Inspect a synthetic reference without implicit execution.',
            'prior_candidate':{'source':self.source_binding, 'axis':'R', 'status':'rejected',
                'parent_score_out_of_5':1.5, 'score_out_of_5':1.0},
            'observations':['Invented empty extraction.'],
            'verification':['Inspect explicit pages and retain exact source binding.'],
            'non_claims':['Synthetic interface check, not evidence of repair.']}
        self.runner, self.literature = mock.Mock(), mock.Mock()
        self.number = 0

    def broker(self, mode='paged_reference', *, no_context=False):
        self.number += 1
        binding = None
        if not no_context:
            context = deepcopy(self.base)
            if mode != 'legacy': context['prior_candidate']['source_delivery'] = mode
            binding = engine.save(self.root/f'context-{self.number}.json', context)
        return broker_module.ResearchBroker(self.root/f'broker-{self.number}',
            company=self.data.company, capacity=mock.Mock(), runner=self.runner,
            literature=self.literature, trace_slots={}, research_context_binding=binding)

    def read(self, broker, offset=0, characters=6000):
        result = broker.dispatch('read_reference_program', {'offset':offset,'characters':characters})
        saved = engine.read(result['research_receipt'])
        self.assertEqual(saved['value'], result['value'])
        return result['value']

    def test_default_and_legacy_do_not_expand_tools_and_legacy_retains_full_source(self):
        empty, legacy = self.broker(no_context=True), self.broker('legacy')
        for broker in (empty, legacy):
            self.assertEqual(broker.definitions, broker_module.DEFINITIONS)
            self.assertNotIn('read_reference_program', [x['name'] for x in broker.definitions])
            with self.assertRaises(ValueError): self.read(broker)
        self.assertIsNone(empty.research_context(include_source=True))
        self.assertEqual(legacy.research_context(include_source=True)['prior_candidate']['source_text'], self.text)
        self.assertNotIn('source_text', legacy.research_context()['prior_candidate'])

    def test_paged_context_retains_exact_reference_but_no_implicit_source(self):
        broker = self.broker()
        plain, full = broker.research_context(), broker.research_context(include_source=True)
        self.assertEqual(plain, full)
        self.assertEqual(full['prior_candidate']['source'], self.source_binding)
        self.assertEqual(full['prior_candidate']['source_delivery'], 'paged_reference')
        self.assertNotIn('source_text', full['prior_candidate'])
        self.assertNotIn(self.text, json.dumps(full, ensure_ascii=False))
        plain['prior_candidate']['source']['sha256'] = '0'*64
        self.assertEqual(broker.research_context()['prior_candidate']['source'], self.source_binding)

    def test_only_paged_tool_declares_exact_bounded_integer_schema(self):
        broker = self.broker()
        specs = [x for x in broker.definitions if x['name']=='read_reference_program']
        self.assertEqual(len(specs), 1)
        params = specs[0]['parameters']
        self.assertEqual(set(params['properties']), {'offset','characters'})
        for name, lo, hi in (('offset',0,64000), ('characters',1,6000)):
            self.assertEqual({key:params['properties'][name][key] for key in ('type','minimum','maximum')},
                             {'type':'integer','minimum':lo,'maximum':hi})
        self.assertEqual(set(params['required']), {'offset','characters'})
        self.assertIs(params['additionalProperties'], False)
        self.assertEqual([x for x in broker.definitions if x['name']!='read_reference_program'],
                         broker_module.DEFINITIONS)

    def test_pagination_reconstructs_exact_unicode_text_and_original_byte_hash(self):
        broker, offset, pages = self.broker(), 0, []
        while offset < len(self.text):
            page = self.read(broker, offset, 6000)
            end = min(offset+6000, len(self.text))
            self.assertEqual(page, {'source_sha256':self.source_binding['sha256'],
                'offset':offset, 'next_offset':end, 'total_characters':len(self.text),
                'text':self.text[offset:end], 'read_only_reference':True})
            pages.append(page['text']); offset = page['next_offset']
        self.assertEqual(''.join(pages), self.text)
        self.assertEqual(hashlib.sha256(''.join(pages).encode('utf-8')).hexdigest(), self.source_binding['sha256'])
        self.assertEqual(self.source.read_bytes(), self.text.encode('utf-8'))
        self.runner.run.assert_not_called(); self.literature.dispatch.assert_not_called()

    def test_end_of_source_page_is_empty_and_never_opens_another_file(self):
        broker = self.broker()
        page = self.read(broker, len(self.text), 1)
        self.assertEqual(page['text'], '')
        self.assertEqual(page['offset'], len(self.text))
        self.assertEqual(page['next_offset'], len(self.text))
        self.assertEqual(page['total_characters'], len(self.text))
        self.assertIs(page['read_only_reference'], True)
        self.assertEqual(broker.files.calls, 0)
        with self.assertRaises(ValueError): self.read(broker, len(self.text)+1, 1)
        self.runner.run.assert_not_called()

    def test_invalid_bounds_types_and_extra_paths_fail_before_action(self):
        broker = self.broker()
        for args in ({'offset':-1,'characters':1}, {'offset':64001,'characters':1},
                     {'offset':True,'characters':1}, {'offset':0.0,'characters':1},
                     {'offset':0,'characters':0}, {'offset':0,'characters':6001},
                     {'offset':0,'characters':True}, {'offset':0,'characters':1.0},
                     {'offset':0,'characters':1,'path':'/private/tmp/other.py'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                broker.dispatch('read_reference_program', args)
        self.assertEqual(broker.calls, 0)
        self.runner.run.assert_not_called()

    def test_unsupported_source_delivery_modes_are_rejected(self):
        for mode in ('full_source','paged','',None,True,1):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.broker(mode).research_context(include_source=True)

    def test_context_source_and_definition_drift_fail_closed_without_execution(self):
        broker = self.broker()
        broker.definitions[-1]['description'] += ' drift'
        with self.assertRaises(ValueError): self.read(broker)
        broker = self.broker()
        context_path = Path(broker.research_context_binding['path'])
        context_path.write_bytes(b'{}')
        with self.assertRaises(ValueError): self.read(broker)
        broker = self.broker()
        self.source.write_bytes(self.text.encode('utf-8')+b'# changed')
        with self.assertRaises(ValueError): self.read(broker)
        with self.assertRaises(ValueError): broker.research_context(include_source=True)
        self.runner.run.assert_not_called()

    def test_actual_mocked_author_request_keeps_binding_not_full_paged_source(self):
        for mode in ('paged_reference','legacy'):
            f = role_fixture.OpenRoleTests(); f.setUp(); self.addCleanup(f.doCleanups)
            f.broker = self.broker(mode)
            service = f.service(author=True, max_turns=1)
            choice = f.choice('R')
            f.generations = [f.message({'decision_sha256':digest(choice),
                'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
                'test_text':"CASES=[{'input':{},'expected':{}}]"})]
            # Isolate delivery from token packing/counting; paid generation is
            # mocked too. No source is executed and no real ledger is opened.
            with mock.patch.object(roles, 'pack', side_effect=lambda _c, request, *_a, **_k:deepcopy(request)), \
                    mock.patch.object(roles, 'budgeted_response', side_effect=f.fake_paid):
                service.author(choice, {'axis':'R'}, str(f.slot))
            request = f.requests[0]
            payload = json.loads(request['input'][0]['content'])
            self.assertEqual(payload, json.loads((f.slot/'effective-input.json').read_bytes()))
            reference = payload['research_context']['prior_candidate']
            self.assertEqual(reference['source'], self.source_binding)
            names = [item['name'] for item in request['tools']]
            if mode=='paged_reference':
                self.assertNotIn('source_text', reference)
                self.assertNotIn(self.text, request['input'][0]['content'])
                self.assertIn('read_reference_program', names)
            else:
                self.assertEqual(reference['source_text'], self.text)
                self.assertNotIn('read_reference_program', names)

    def test_author_and_run_python_advertise_existing_serialized_output_contract(self):
        description = next(x['description'] for x in broker_module.DEFINITIONS if x['name']=='run_python')
        for text in (roles.AUTHOR, description):
            with self.subTest(text=text):
                self.assertIn(str(broker_module.MAX_RESULT_BYTES), text)
                self.assertIn('serialized', text.lower())
                self.assertIn('ok', text)
                self.assertIn('value', text)
                self.assertRegex(text.lower(), rf'(?:output|result).{{0,180}}{broker_module.MAX_RESULT_BYTES}|{broker_module.MAX_RESULT_BYTES}.{{0,180}}(?:output|result)')


if __name__ == '__main__':
    unittest.main()
