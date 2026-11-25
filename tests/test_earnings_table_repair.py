"""Independent synthetic repair-authority/context/round tests; no live resources.

The role generation and R execution fixtures are explicitly invented. Passing
these checks establishes interface delivery, never an autonomous repair or gain.
"""
import ast
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import earnings_open_admission as live
import earnings_open_fresh_grant as fresh
import earnings_open_roles as roles
from earnings_open_broker import ResearchBroker
from earnings_open_task import OpenTask
from edgar_forecast_tools import FilingTools
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_fresh_grant as authority_fixture
import test_earnings_open_roles as role_fixture
import test_earnings_open_worker as worker_fixture
import test_earnings_research_state as state_fixture


AUTHORIZATION = '先查清这 $0.34 的未决费用，再给我具体计划，开新的 90 分钟窗口，让 Author 自己诊断并修复真实财报表格解析，验证新版本被下一轮实际使用。数据、scorer 和原 $200 累计预算不变，每个改动单独提交，失败先诊断，不自动重试。'


class Authority(unittest.TestCase):
    def setUp(self):
        self.f = authority_fixture.FreshGrantTests()
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def continuation(self):
        return {'human_authorization': AUTHORIZATION,
                'cumulative_cap_nano_usd': 10_000_000_000, 'rounds': 1,
                'research_context': {'path': str(self.f.home/'context.json'), 'sha256': 'a'*64}}

    def test_legacy_default_caps_rounds_baseline_and_window_are_unchanged(self):
        body = self.f.policy()
        self.assertEqual(fresh.pilot_cap(body), 5_000_000_000)
        self.assertEqual(fresh.requested_rounds(body), 2)
        self.assertEqual(self.f.validate(), body)
        self.assertEqual(body['original_total_cap_nano_usd'], 200_000_000_000)
        self.assertEqual(body['original_per_model_cap_nano_usd'], 100_000_000_000)
        self.assertEqual(body['new_subgrant_nano_usd'], 50_000_000_000)
        self.assertEqual(body['baseline']['max_rowid'], 4283)
        self.assertEqual(body['baseline']['request_count'], 4283)
        self.assertEqual(body['baseline']['charged_nano_usd'], 137_542_765_000)
        self.assertEqual(body['window'], self.f.body['window'])

    def test_continuation_cumulative_ten_never_rebases_consumed_charges(self):
        self.assertEqual(fresh.TABLE_REPAIR_AUTHORIZATION, AUTHORIZATION)
        self.f.body['continuation'] = self.continuation()
        body = self.f.policy()
        self.assertEqual(fresh.pilot_cap(body), 10_000_000_000)
        self.assertEqual(fresh.requested_rounds(body), 1)
        self.assertEqual(body['baseline'], fresh.BASELINE)
        self.assertEqual(fresh.pilot_cap(body)-4_102_310_300, 5_897_689_700)
        self.f.grant['additional_cap_nano_usd'] = 10_000_000_000
        self.assertEqual(self.f.validate(), body)
        for update in ({'additional_cap_nano_usd': 5_000_000_000},
                       {'baseline': dict(fresh.BASELINE, charged_nano_usd=141_645_075_300)},
                       {'cutoff_utc': '2026-10-15T02:30:01Z'}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.f.validate(dict(self.f.grant, **update))

    def test_continuation_requires_exact_human_scope_and_strict_values(self):
        good = self.continuation()
        variants = [dict(good, human_authorization='+50 dollar more'),
                    dict(good, cumulative_cap_nano_usd=10_000_000_001),
                    dict(good, cumulative_cap_nano_usd=10_000_000_000.0),
                    dict(good, cumulative_cap_nano_usd=True),
                    dict(good, rounds=2), dict(good, rounds=True), dict(good, rounds=1.0),
                    dict(good, retry_allowed=True),
                    dict(good, research_context={'path':'relative.json','sha256':'a'*64}),
                    dict(good, research_context={'path':str(self.f.home/'context.json'),'sha256':'bad'})]
        for changed in variants:
            body = dict(self.f.body, continuation=changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.f.policy(body)


class Context(unittest.TestCase):
    def setUp(self):
        self.data = state_fixture.ResearchStateTests()
        self.data.setUp(); self.addCleanup(self.data.doCleanups)
        self.root = self.data.root
        self.source_text = "PROGRAM={'axis':'R'}\n# invented failed source, never executed\ndef run(p):\n    return {'comparables': []}\n"
        source = self.root/'rejected-R.py'
        source.write_text(self.source_text)
        self.context = {'schema':'earnings_repair_context_v1',
            'human_task':'Diagnose invented empty table extraction; no answers supplied.',
            'prior_candidate': {'source':engine.pin(source), 'axis':'R', 'status':'rejected',
                                'parent_score_out_of_5':1.5, 'score_out_of_5':1.0},
            'observations':['Invented table extractor returned no comparables.'],
            'verification':['Preserve public input; use original scorer.'],
            'non_claims':['No predictive improvement or autonomous repair established.']}
        self.binding = engine.save(self.root/'context.json', self.context)
        self.runner = worker_fixture.ReceiptFixtureRunner(self.root/'synthetic-runner')
        self.broker = self.make_broker('with-context', self.binding)

    def make_broker(self, name, binding=None):
        return ResearchBroker(self.root/name, company=self.data.company,
            capacity=mock.Mock(), runner=self.runner, literature=mock.Mock(), trace_slots={},
            research_context_binding=binding)

    def test_immutable_summary_and_full_source_views_are_distinct_and_detached(self):
        summary = self.broker.research_context()
        self.assertEqual(summary, self.context)
        self.assertNotIn('source_text', summary['prior_candidate'])
        full = self.broker.research_context(include_source=True)
        self.assertEqual(full, dict(self.context, prior_candidate=dict(
            self.context['prior_candidate'], source_text=self.source_text)))
        full['prior_candidate']['source']['sha256'] = '0'*64
        self.assertEqual(self.broker.research_context(), self.context)
        self.assertIsNone(self.make_broker('no-context').research_context())

    def test_changed_context_or_failed_source_is_rejected_without_running(self):
        source = Path(self.context['prior_candidate']['source']['path'])
        original = source.read_bytes()
        source.write_bytes(original+b'# drift\n')
        with self.assertRaises(ValueError):
            self.broker.research_context(include_source=True)
        source.write_bytes(original)
        Path(self.binding['path']).write_bytes(b'{}')
        with self.assertRaises(ValueError):
            self.broker.research_context()
        self.assertEqual(self.runner.calls, 0)

    def test_unknown_context_schema_and_top_fields_rejected(self):
        for i, changed in enumerate((dict(self.context, schema='other'),
                                     dict(self.context, source_text='undeclared'),
                                     {k:v for k,v in self.context.items() if k!='non_claims'})):
            bound = engine.save(self.root/f'invalid-{i}.json', changed)
            broker = self.make_broker(f'invalid-broker-{i}', bound)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                broker.research_context(include_source=True)

    def packet(self, broker):
        task = OpenTask()
        task.capacity, task.runner, task.broker = object(), self.runner, broker
        task.company = self.data.company
        task.state_api = SimpleNamespace(tools=FilingTools(self.data.company))
        task.load_state = mock.Mock(return_value={'records':[]})
        sources = {'R':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
                   'H':"PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {}\n"}
        with mock.patch.object(broker, 'current_sources', return_value=sources):
            return task.packet({'id':'invented-task'},
                {'previous_result':{'state':{}, 'feedback':{'synthetic':True}},
                 'previous_feedback_sha256':'a'*64},
                {'R':{'axis':'R'},'H':{'axis':'H','tools':[]}}, 'b'*64)

    def test_actual_controller_packet_gets_summary_and_legacy_broker_stays_unchanged(self):
        packet = self.packet(self.broker)
        self.assertEqual(packet['research_context'], self.context)
        self.assertNotIn(self.source_text, json.dumps(packet['research_context']))
        # Older synthetic brokers have no optional method at all.
        old = SimpleNamespace(files=FilingTools(self.data.company),
                              current_sources=lambda: {}, available_traces=lambda: [])
        self.assertNotIn('research_context', self.packet(old))

    def test_actual_author_effective_input_gets_exact_failed_code_default_unchanged(self):
        for enabled in (True, False):
            f = role_fixture.OpenRoleTests(); f.setUp(); self.addCleanup(f.doCleanups)
            if enabled:
                f.broker = self.broker
            service = f.service(author=True, max_turns=1)
            choice = f.choice('R')
            authored = {'decision_sha256':digest(choice),
                'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return 1\n",
                'test_text':"CASES=[{'input':{},'expected':1}]"}
            f.generations = [f.message(authored)]
            with mock.patch.object(roles, 'budgeted_response', side_effect=f.fake_paid):
                service.author(choice, {'axis':'R'}, str(f.slot))
            effective = json.loads((f.slot/'effective-input.json').read_bytes())
            physical = json.loads(f.requests[0]['input'][0]['content'])
            self.assertEqual(physical, effective)
            if enabled:
                self.assertEqual(effective['research_context'], self.broker.research_context(include_source=True))
                self.assertEqual(effective['research_context']['prior_candidate']['source_text'], self.source_text)
            else:
                self.assertEqual(set(effective), {'decision','before_profile','decision_sha256'})


class Rounds(unittest.TestCase):
    def plan(self, count):
        # Only canonical prospective path strings; none are opened or created.
        root = Path('/private/tmp/invented-table-repair-episode')
        rows, matched = [], []
        for i in range(1, count+1):
            row = {role:str(root/'roles'/f'{role}-{i:02d}')
                   for role in ('controller','author','review','forecast')}
            rows.append(row)
            matched.append({'parent':str(root/'roles'/f'parent-{i:02d}'),
                'candidate':str(root/'roles'/f'candidate-{i:02d}'), 'downstream':row['forecast']})
        return {'root':str(root), 'max_rounds':count, 'slots':rows}, {
            'schema':'earnings_matched_plan_v1', 'rounds':matched}

    def test_one_and_two_rounds_have_all_triples_and_terminal_controller(self):
        for n in (1, 2):
            envelope, matched = self.plan(n)
            actual = live.slots(envelope, matched)
            with self.subTest(n=n):
                for role in ('author','review'):
                    self.assertEqual(actual[role], [row[role] for row in envelope['slots']])
                self.assertEqual(actual['controller'], [row['controller'] for row in envelope['slots']]+[
                    str(Path(envelope['root'])/'roles/controller-terminal')])
                self.assertEqual(actual['forecast'], [row[key] for row in matched['rounds']
                    for key in ('parent','candidate','downstream')])
                self.assertEqual(len(actual['forecast']), 3*n)

    def test_invalid_round_types_counts_mismatches_and_collisions_fail_closed(self):
        for count in (0, 3, True, False, 1.0):
            envelope, matched = self.plan(1)
            envelope['max_rounds'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                live.slots(envelope, matched)
        for axis in ('slots','rounds'):
            envelope, matched = self.plan(1)
            (envelope if axis=='slots' else matched)[axis].append(deepcopy(
                (envelope if axis=='slots' else matched)[axis][0]))
            with self.subTest(axis=axis), self.assertRaises(ValueError):
                live.slots(envelope, matched)
        for change in ('duplicate','terminal','outside','downstream'):
            envelope, matched = self.plan(1)
            if change=='duplicate': matched['rounds'][0]['candidate'] = matched['rounds'][0]['parent']
            elif change=='terminal': envelope['slots'][0]['author'] = str(Path(envelope['root'])/'roles/controller-terminal')
            elif change=='outside': matched['rounds'][0]['parent'] = '/private/tmp/outside-role'
            else: matched['rounds'][0]['downstream'] = matched['rounds'][0]['parent']
            with self.subTest(change=change), self.assertRaises(ValueError):
                live.slots(envelope, matched)

    def test_preparer_and_admission_derive_requested_rounds_from_validated_authority(self):
        # Static consumer checks avoid preparing IDs, running Git, or opening
        # the actual source/data/ledger admission path.
        tools = Path(live.__file__).resolve().parent
        for name in ('prepare_earnings_open.py','earnings_open_admission.py'):
            tree = ast.parse((tools/name).read_text())
            calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
            found = any((isinstance(node, ast.Attribute) and node.attr=='requested_rounds')
                        or (isinstance(node, ast.Name) and node.id=='requested_rounds') for node in calls)
            with self.subTest(name=name): self.assertTrue(found)


if __name__ == '__main__':
    unittest.main()
