"""Reference-only delivery shares the unchanged 64-KiB program bound.

Broker reads/receipts are real; compute/literature adapters are inert fixtures.
Campaign context guard tests explicitly isolate unrelated ancestry projection.
No candidate source is executed and no live company body is read.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from edgar_forecast_tools import TOOLS
from earnings_open_program import program
from earnings_population_campaign_context import prepare
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_broker as broker_fixture


class ReferenceCapacity(unittest.TestCase):
    def setUp(self):
        self.f = broker_fixture.BrokerTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.broker = self.f.broker
        self.root = self.f.f.root

    def reference(self, size, *, unicode=False):
        prefix = "PROGRAM={'axis':'R'}\ndef run(p): return p\n#"
        if unicode:
            prefix += '财报'
        text = prefix + 'x' * (size - len(prefix.encode()))
        path = self.root / f'reference-{size}-{unicode}.py'
        path.write_text(text)
        return dict(axis='R', source=engine.pin(path), source_delivery='paged_reference',
                    reference_only=True, id='reference-only', parent='prior-parent')

    def context(self, reference):
        return dict(schema='earnings_repair_context_v1', human_task='Inert reference test',
                    prior_candidate=reference, observations={}, verification='fixture', non_claims='fixture')

    def bind(self, reference):
        self.broker.research_context_binding = engine.save(
            self.root / 'context.json', self.context(reference))
        self.broker.definitions = self.broker._definitions()

    def test_full_existing_program_range_reaches_real_reference_tool(self):
        for size in (64000, 64001, 65536):
            with self.subTest(size=size):
                ref = self.reference(size)
                program(engine.activation._read(ref['source']), 'R')
                # Same original broker; each source/context has its own binding.
                self.broker.research_context_binding = engine.save(
                    self.root / f'context-{size}.json', self.context(ref))
                self.broker.definitions = self.broker._definitions()
                result = self.broker.dispatch('read_reference_program',
                    dict(offset=size-1, characters=6000))['value']
                self.assertEqual(result['text'], 'x')
                self.assertEqual(result['next_offset'], size)
                self.assertEqual(result['source_sha256'], ref['source']['sha256'])
                self.assertTrue(result['read_only_reference'])
                eof = self.broker.dispatch('read_reference_program',
                    dict(offset=size, characters=1))['value']
                self.assertEqual(eof['text'], '')
        self.f.runner.run.assert_not_called()
        self.f.literature.dispatch.assert_not_called()

    def test_utf8_bytes_not_character_count_and_existing_page_cap(self):
        ref = self.reference(65536, unicode=True)
        self.bind(ref)
        source = engine.activation._read(ref['source']).decode()
        self.assertLess(len(source), 65536)
        result = self.broker.dispatch('read_reference_program',
            dict(offset=len(source), characters=6000))['value']
        self.assertEqual(result['total_characters'], len(source))
        self.assertEqual(result['text'], '')
        for args in (dict(offset=len(source)+1, characters=1),
                     dict(offset=65537, characters=1), dict(offset=0, characters=6001)):
            with self.assertRaises(ValueError):
                self.broker.dispatch('read_reference_program', args)

    def test_oversize_hash_path_and_axis_are_still_rejected(self):
        ref = self.reference(65537)
        with self.assertRaises(ValueError):
            program(engine.activation._read(ref['source']), 'R')
        with self.assertRaises(ValueError):
            self.bind(ref)
        ref = self.reference(65536)
        for change in ('hash', 'path', 'axis'):
            changed = deepcopy(ref)
            if change == 'hash': changed['source']['sha256'] = '0'*64
            elif change == 'path': changed['source']['path'] += '.missing'
            else: changed['axis'] = 'H'
            self.broker.research_context_binding = engine.save(
                self.root / f'bad-{change}.json', self.context(changed))
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.broker._definitions()

    def test_campaign_guard_uses_same_bound_and_reference_flags(self):
        abi = dict(schema='earnings_original_R_evidence_abi_v1', tools=TOOLS,
            request_phases=1, max_requests=8, second_request_phase_allowed=False,
            search_hit_fields=['path','line','text'],
            read_result_fields=['path','offset','total_characters','text','next_offset'],
            search_has_source_sha256=False, search_has_character_offset=False,
            read_has_source_sha256=False)
        original = dict(schema='earnings_population_rejection_feedback_v1', tool_abi=abi,
                        company_id='fixture', probes=[], qualifications=[])
        campaign = engine.save(self.root/'campaign.json', {'fixture':True})
        for size in (64000, 64001, 65536, 65537):
            ref = self.reference(size, unicode=True)
            origin = engine.save(self.root/f'origin-{size}.json',
                dict(research_feedback=original, reference_candidate=ref))
            study = engine.save(self.root/f'study-{size}.json',
                dict(campaign=campaign, campaign_origin=origin))
            with patch('earnings_population_campaign_context._reference', return_value=ref), \
                    patch('earnings_population_campaign_context._failure_context', return_value=None):
                args = (dict(forecast_study=study),
                        dict(campaign=campaign, round_index=1, feedback={}), dict(probes=[]))
                if size > 65536:
                    with self.assertRaises(ValueError): prepare(*args)
                else:
                    self.assertEqual(prepare(*args)['prior_candidate'], ref)
        for change in (dict(axis='H'), dict(reference_only=False),
                       dict(source_delivery='inline'), dict(source_text='must not inline')):
            ref = self.reference(65536, unicode=True)
            ref.update(change)
            with patch('earnings_population_campaign_context._reference', return_value=ref):
                with self.assertRaises(ValueError): prepare(*args)


if __name__ == '__main__': unittest.main()
