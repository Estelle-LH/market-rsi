"""Default offline Author contract and rejection regressions.

Synthetic fixtures only; no model/ledger/data access or host candidate execution.
Run real containers only with AUTHOR_HANDOFF_REAL_DOCKER=1. Those fixtures are
handwritten and use the existing network-disabled, no-pull production runner.
Historical75–78 raw receipts stay local, outside the portable repository tests.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from earnings_open_roles import OpenAuthor
from earnings_open_program import candidate, program
from earnings_open_source_review import ProgramSourceReview
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from tests import test_earnings_open_capacity as fixtures

CHOICE = dict(schema='earnings_capacity_decision_v1', axis='R', component='research_policy',
    parent_pair_sha256='1'*64, feedback_sha256='2'*64,
    hypothesis='Offline Author handoff fixture', expected_effect='No scientific experiment')
GOOD = "PROGRAM={'axis':'R'}\ndef run(payload):\n    return payload\n"


def envelope(source=GOOD, tests="CASES=[{'input':{},'expected':{}}]"):
    return dict(status='completed', error=None, output=[dict(type='message', status='completed',
        content=[dict(type='output_text',text=json.dumps(dict(decision_sha256=digest(CHOICE),
            source_text=source,test_text=tests)))])])


class AuthorDeliveryContractTests(unittest.TestCase):
    def parse(self, value):
        return candidate(value, {'axis':'R'}, CHOICE)

    def test_valid_delivery_is_parsed_not_claimed_executed(self):
        self.assertFalse(self.parse(envelope())['tests_executed'])

    def test_provider_incomplete_is_not_salvaged(self):
        value=envelope();value.update(status='incomplete',incomplete_details={'reason':'max_output_tokens'})
        with self.assertRaises(ValueError):self.parse(value)

    def test_incomplete_message_is_not_salvaged(self):
        value=envelope();value['output'][0]['status']='incomplete'
        with self.assertRaises(ValueError):self.parse(value)

    def test_invalid_json_rejected(self):
        value=envelope();value['output'][0]['content'][0]['text']='{"source_text":'
        with self.assertRaises(ValueError):self.parse(value)

    def test_syntax_error_rejected(self):
        with self.assertRaises(SyntaxError):self.parse(envelope(GOOD+"broken='"))

    def test_missing_return_is_only_structural_admission(self):
        value=self.parse(envelope("PROGRAM={'axis':'R'}\ndef run(p): pass\n"))
        self.assertFalse(value['tests_executed'])

    def test_long_complete_source_not_subject_to_old6500_limit(self):
        self.assertFalse(self.parse(envelope('#'+'a'*7500+'\n'+GOOD))['tests_executed'])

    def test_exact_existing_source_byte_boundary(self):
        source='#'+'a'*(65536-len(GOOD.encode())-2)+'\n'+GOOD
        self.assertEqual(program(source.encode(),'R'),{'axis':'R'})
        with self.assertRaises(ValueError):program((source+' ').encode(),'R')

    def test_utf8_bytes_not_characters(self):
        source='#'+'中'*22000+'\n'+GOOD
        self.assertLess(len(source),65536)
        with self.assertRaises(ValueError):self.parse(envelope(source))

    def test_stale_decision_rejected(self):
        value=envelope();body=json.loads(value['output'][0]['content'][0]['text'])
        body['decision_sha256']='0'*64;value['output'][0]['content'][0]['text']=json.dumps(body)
        with self.assertRaises(ValueError):self.parse(value)

    def test_literal_tests_not_arbitrary_execution(self):
        with self.assertRaises(ValueError):self.parse(envelope(tests="CASES=__import__('os').system('false')"))

    def test_current_case_limit_not_old_three_case_limit(self):
        case={'input':{},'expected':{}}
        self.assertEqual(len(self.parse(envelope(tests='CASES='+repr([case]*8)))['cases']),8)
        with self.assertRaises(ValueError):self.parse(envelope(tests='CASES='+repr([case]*9)))

    def test_hashes_are_exact(self):
        self.assertEqual(self.parse(envelope())['source_sha256'],hashlib.sha256(GOOD.encode()).hexdigest())

    def test_actual_author_entry_delegates_to_actual_decoder_without_transport(self):
        role=OpenAuthor.__new__(OpenAuthor);role.broker=object()
        def offline(prompt,slot,instructions,fmt,decode,artifact,status):
            self.assertEqual(set(fmt['schema']['properties']),{'decision_sha256','source_text','test_text'})
            return decode(envelope())
        role._run_open=offline
        self.assertEqual(role.author(CHOICE,{'axis':'R'},'offline-unused'),self.parse(envelope()))


def reviewed(fixture, source, runner):
    """Substitute only hand-written synthetic source/runner into real fixture."""
    real_candidate=fixtures.candidate
    def parse(authored,before,chosen):
        authored['source_text']=source
        return real_candidate(authored,before,chosen)
    def service(*args,**kwargs):
        kwargs['runner']=runner
        return ProgramSourceReview(*args,**kwargs)
    with patch.object(fixtures,'candidate',parse), patch.object(fixtures,'ProgramSourceReview',service):
        return fixture.specification()


class ExecutionRejectionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ProgramCapacityTests(methodName='runTest')
        self.f.setUp();self.addCleanup(self.f.doCleanups)

    def reject(self, runner, source):
        spec=reviewed(self.f,source,runner)
        self.assertEqual(engine.read(spec['static_review'])['passed'],True)
        receipt=engine.read(spec['review_receipt'])
        self.assertEqual(receipt['review']['reason'],'PROGRAM_CASES_FAILED')
        self.f.capacity.propose(spec['after'],spec['proposal'],spec['entrypoints'],
            static_review=spec['static_review'],expected_state_sha256=self.f.batch.snapshot()['state_sha256'])
        self.f.capacity.review(spec['review_receipt'],expected_state_sha256=self.f.batch.snapshot()['state_sha256'])
        state=self.f.batch.snapshot()['micro_evolution']
        self.assertEqual(state['active_pair'],self.f.micro['pair'])
        self.assertIsNone(state['pending'])
        self.assertEqual(state['history'][-1]['review']['decision'],'reject')
        return spec

    def test_wrong_output_rejected_by_review_and_native(self):
        class Runner:
            blocked=False
            def run(self,source,payload):return {'value':99,'synthetic':True}
        self.reject(Runner(),"PROGRAM={'axis':'R'}\ndef run(p): return 99\n")

    def test_missing_return_rejected_when_expected_output_non_null(self):
        class Runner:
            blocked=False
            def run(self,source,payload):return {'value':None,'synthetic':True}
        self.reject(Runner(),"PROGRAM={'axis':'R'}\ndef run(p): pass\n")

    def test_ordinary_runtime_error_rejected_by_review_and_native(self):
        class Runner:
            blocked=False
            def run(self,source,payload):raise RuntimeError('Synthetic guest exception')
        self.reject(Runner(),"PROGRAM={'axis':'R'}\ndef run(p): return missing_name\n")


@unittest.skipUnless(os.environ.get('AUTHOR_HANDOFF_REAL_DOCKER')=='1','Explicit synthetic Docker check only')
class RealExecutionRejectionTests(ExecutionRejectionTests):
    def setUp(self):
        super().setUp()
        from earnings_open_code import DockerRunner
        self.runner=DockerRunner(self.f.root/'real-code',max_calls=1)

    def test_wrong_output_rejected_by_review_and_native(self):
        self.reject(self.runner,"PROGRAM={'axis':'R'}\ndef run(p): return 99\n")

    def test_missing_return_rejected_when_expected_output_non_null(self):
        self.reject(self.runner,"PROGRAM={'axis':'R'}\ndef run(p): pass\n")

    def test_ordinary_runtime_error_rejected_by_review_and_native(self):
        self.reject(self.runner,"PROGRAM={'axis':'R'}\ndef run(p): return missing_name\n")

    def test_correct_synthetic_code_passes_without_automatic_adoption(self):
        spec=reviewed(self.f,"PROGRAM={'axis':'R'}\ndef run(p): return sorted(p)[1]\n",self.runner)
        self.assertIsNone(spec['review_receipt'])
        cases=engine.read(engine.read(spec['static_review'])['program_cases'])
        self.assertTrue(cases['passed'])
        self.assertEqual(self.f.batch.snapshot()['micro_evolution']['active_pair'],self.f.micro['pair'])


@unittest.skipUnless(importlib.util.find_spec('earnings_population_services'),
                     'Population services not present on historical checkout')
class PopulationExecutionGateTests(unittest.TestCase):
    """Exercise the new actual services.review method without model transport."""
    def setUp(self):
        from earnings_population_services import Services
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.service=Services.__new__(Services)
        original=engine.save(self.root/'synthetic-original.json',{'synthetic':True})
        self.service.authored={'child':{'source':GOOD,'parsed':{
            'cases':[{'input':{},'expected':{'required':2}}]},'originals':[original]}}
        self.service.native_root=self.root
        self.service.case=Mock(return_value={})
        self.service.role=Mock(side_effect=AssertionError('Bad code must not reach paid reviewer'))
        self.service.forecast=Mock(side_effect=AssertionError('No prediction permitted'))

    def check_reject(self, value):
        runner=Mock();runner.run.return_value={'value':value,'synthetic':True}
        self.service.runner=runner
        result=self.service.review({'id':'child'},{},str(self.root/'review'))
        self.assertFalse(result['accepted_for_exploration'])
        self.service.role.assert_not_called();self.service.forecast.assert_not_called()
        runner.run.assert_called_once_with(GOOD,{})
        # New production review prepends a decision/rationale receipt. Inspect
        # the bound case receipt, not its position in the evidence list.
        receipts=[engine.read(bound) for bound in result['evidence']]
        cases=[value for value in receipts if 'results' in value]
        self.assertEqual(len(cases),1)
        self.assertFalse(cases[0]['results'][0]['passed'])

    def test_bad_value_stops_before_paid_review_or_prediction(self):
        self.check_reject({'required':99})

    def test_no_return_stops_before_paid_review_or_prediction(self):
        self.check_reject(None)

    def test_runtime_failure_stops_before_paid_review_or_prediction(self):
        runner=Mock();runner.run.side_effect=RuntimeError('Synthetic execution failure')
        self.service.runner=runner
        with self.assertRaises(RuntimeError):
            self.service.review({'id':'child'},{},str(self.root/'review'))
        self.service.role.assert_not_called();self.service.forecast.assert_not_called()
