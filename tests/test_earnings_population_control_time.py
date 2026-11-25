"""Prospective wall policy: synthetic clocks/HTTP, never a real13 completion.

Only the unknown-fee test uses an original ledger, privately created in temp.
No production ledger, credentials, financial data or candidate code is opened.
"""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
from earnings_controller import CapacityAuthor, _CapacityDeadlineHTTP
from earnings_loop_policy import LIMITS
import earnings_open_resources as resources
import earnings_open_roles as roles
from earnings_population_roles import PopulationReviewer
import test_earnings_open_roles as old


class ControlTimeTests(unittest.TestCase):
    def fixture(self):
        fixture = old.OpenRoleTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_declared_role_resources_and_generic_policy_stay_explicit(self):
        self.assertEqual(resources.role_limits(), {
            'controller': {'max_input_tokens': 32000, 'max_output_tokens': 16384, 'wall_seconds': 900},
            'review': {'max_input_tokens': 32000, 'max_output_tokens': 16384, 'wall_seconds': 900},
            'author': {'max_input_tokens': 96000, 'max_output_tokens': 49152, 'wall_seconds': 1200}})
        self.assertEqual(LIMITS, {'max_input_tokens': 10000, 'max_output_tokens': 16384, 'wall_seconds': 600})
        self.assertEqual(resources.ROLE_EFFORTS, {'controller': 'max', 'author': 'high', 'review': 'max', 'forecast': 'max'})

    def test_author_socket900_accepts_exact_old900_and_new1200_bound_walls(self):
        for wall in (900, 1200):
            with self.subTest(wall=wall):
                f = self.fixture()
                service = f.service(author=True, limits=dict(resources.role_limits()['author'], wall_seconds=wall),
                                    socket_timeout_seconds=900)
                self.assertEqual(service.socket_timeout_seconds, 900)
                self.assertEqual(service.context['limits']['wall_seconds'], wall)
                f.factory.assert_not_called()

    def test_socket_or_wall_types_and_arbitrary_expansions_refused_before_factory(self):
        for socket, wall in ((1200,1200),(901,1200),(True,1200),(900.0,1200),
                             (900,899),(900,1201),(900,True),(900,1200.0)):
            with self.subTest(socket=socket, wall=wall):
                f = self.fixture()
                with self.assertRaises(ValueError):
                    f.service(author=True, limits=dict(resources.role_limits()['author'], wall_seconds=wall),
                              socket_timeout_seconds=socket)
                f.factory.assert_not_called()

    def test_non_author_socket_and_generic_capacity_author_cannot_inherit_opt_in(self):
        f = self.fixture()
        with self.assertRaises(ValueError):
            f.service(limits=resources.role_limits()['controller'], socket_timeout_seconds=900)
        f = self.fixture(); service = f.service(author=True, limits=resources.role_limits()['author'])
        with self.assertRaises(ValueError):
            CapacityAuthor(service.binding, budget=f.budget, client_factory=f.factory)
        f.factory.assert_not_called()

    def test_all_role_ceilings_refuse_bool_and_smallest_above_wall(self):
        for role, ceiling in resources.role_limits().items():
            for wall in (True, ceiling['wall_seconds']+1):
                with self.subTest(role=role, wall=wall):
                    f = self.fixture()
                    if role == 'review':
                        # Construct the original receiving class with an exact review context.
                        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
                        root = Path(temp.name).resolve(); slot = root/'roles'/'review-01'
                        context = {'schema':'earnings_capacity_review_transport_v1','source_commit':'a'*40,
                            'root':str(root),'rates':{'api_model':'gpt-6.1-sol','effort':'max',
                                'input':'2','cached':'.1','write':'2.5','output':'10'},
                            'limits':dict(ceiling,wall_seconds=wall),'slots':[str(slot)],
                            'cutoff_utc':'2099-01-01T00:00:00Z','cutoff_monotonic':time.monotonic()+7200}
                        path=root/'context.json'; roles.e.durable_json(path,context)
                        with self.assertRaises(ValueError):
                            PopulationReviewer({'path':str(path),'sha256':roles.e.digest(path.read_bytes())},
                                budget=f.budget,client_factory=f.factory,broker=f.broker)
                    else:
                        with self.assertRaises(ValueError):
                            f.service(author=role=='author',limits=dict(ceiling,wall_seconds=wall))
                    f.factory.assert_not_called()

    def timed_controller(self, wall, advance, *, budget_remaining=2000, context_remaining=1200):
        f = self.fixture(); now = [time.monotonic()]
        f.budget.monotonic_deadline = now[0]+budget_remaining
        with patch.object(roles.time, 'monotonic', side_effect=lambda:now[0]):
            service = f.service(limits=dict(resources.role_limits()['controller'],wall_seconds=wall),max_turns=1)
            # Context's immutable 1200-second global bound is generated by the fixture.
            self.assertEqual(service.context['cutoff_monotonic'],now[0]+context_remaining)
            f.generations = [f.message(f.choice('continue'))]
            def advance_once(*args):
                now[0] += advance
                return f.fake_paid(*args)
            with patch.object(roles,'budgeted_response',side_effect=advance_once):
                if advance >= min(wall,budget_remaining,context_remaining):
                    with self.assertRaisesRegex(RuntimeError,'BudgetStop'):
                        service.propose(f.prompt,str(f.slot))
                else:
                    service.propose(f.prompt,str(f.slot))
        result=f.failure()
        self.assertFalse(result['retry_allowed'])
        self.assertEqual(len(f.requests),1)
        self.assertEqual(result['wall_seconds'],advance)
        return f,service,result

    def test_original_role_accepts_synthetic650s_only_with_new900s_wall(self):
        _,_,old_result=self.timed_controller(600,650)
        _,_,new_result=self.timed_controller(900,650)
        self.assertEqual(old_result['status'],'FAILED_NO_RETRY')
        self.assertEqual(new_result['status'],'COMPLETED_DECISION')

    def test_original_author_uses1200_role_wall_but900_request_socket(self):
        for wall in (900,1200):
            with self.subTest(wall=wall):
                f=self.fixture(); now=[time.monotonic()]
                f.budget.monotonic_deadline=now[0]+2000
                chosen=f.choice()
                source='PROGRAM = {"axis":"R"}\ndef run(payload):\n    return {"synthetic": True}\n'
                f.generations=[f.message({'decision_sha256':roles.digest(chosen),'source_text':source,
                    'test_text':"CASES = [{'input': {}, 'expected': {'synthetic': True}}]"})]
                with patch.object(roles.time,'monotonic',side_effect=lambda:now[0]):
                    service=f.service(author=True,limits=dict(resources.role_limits()['author'],wall_seconds=wall),
                                      socket_timeout_seconds=900,max_turns=1)
                    def advance_once(*args):
                        now[0]+=1000
                        return f.fake_paid(*args)
                    with patch.object(roles,'budgeted_response',side_effect=advance_once):
                        if wall==900:
                            with self.assertRaisesRegex(RuntimeError,'BudgetStop'):
                                service.author(chosen,{'axis':'R'},str(f.slot))
                        else:service.author(chosen,{'axis':'R'},str(f.slot))
                result=f.failure()
                self.assertEqual(result['status'],'FAILED_NO_RETRY' if wall==900 else 'COMPLETED_CANDIDATE')
                self.assertFalse(result['retry_allowed'])
                self.assertEqual(f.factory.return_value.timeout,900)
                self.assertEqual(len(f.requests),1)

    def test_exact_role_wall_and_global_budget_deadline_still_stop_no_retry(self):
        for wall,advance,remaining in ((900,900,2000),(900,6,5)):
            with self.subTest(wall=wall,advance=advance,remaining=remaining):
                f,service,result=self.timed_controller(wall,advance,budget_remaining=remaining)
                self.assertEqual(result['status'],'FAILED_NO_RETRY')
                self.assertEqual(result['error_type'],'BudgetStop')
                with self.assertRaises(FileExistsError):service.propose(f.prompt,str(f.slot))
                self.assertEqual(len(f.requests),1)

    def test_expired_original_global_cutoff_stops_before_factory(self):
        f=self.fixture(); f.budget.monotonic_deadline=time.monotonic()-1
        service=f.service(limits=resources.role_limits()['controller'])
        with self.assertRaises(BudgetStop):service.propose(f.prompt,str(f.slot))
        f.factory.assert_not_called();self.assertFalse(f.slot.exists())

    def test_original_http_clips900socket_to_global_remaining_not1200(self):
        client=Mock(timeout=900); now=[100.0]
        transport=_CapacityDeadlineHTTP(client,lambda:None,deadline_utc='2099-01-01T00:00:00Z',
            rollout_seconds=1200,captured_deadline=105,clock=lambda:0,monotonic=lambda:now[0])
        transport.post('/synthetic',{})
        self.assertEqual(client.timeout,5)
        now[0]=105
        with self.assertRaises(BudgetStop):transport.post('/synthetic',{})
        client.post.assert_called_once()

    def test_unknown_generation_failure_is_preserved_on_private_ledger_without_retry(self):
        from test_earnings_capacity_controller_transport import _TransportFixture, _wire
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        f=_TransportFixture(self,Path(temp.name)/'private-ledger')
        # Exact existing temporary-ledger path, only HTTPS bytes are synthetic.
        f.context['limits']=dict(resources.role_limits()['controller'])
        path=f.root/'open-context.json';roles.e.durable_json(path,f.context)
        binding={'path':str(path),'sha256':roles.e.digest(path.read_bytes())}
        calls=[]
        class Connection:
            def __init__(inner,host,timeout):self.assertEqual(host,'api.openai.com')
            def request(inner,method,endpoint,body,headers):
                inner.endpoint=endpoint;calls.append(endpoint)
            def getresponse(inner):
                if inner.endpoint=='/v1/responses':raise TimeoutError('synthetic unknown invoice')
                raw=_wire({'input_tokens':20})
                return Mock(status=200,getheader=Mock(return_value='synthetic'),read=Mock(side_effect=lambda n:raw[:n]))
            def close(inner):pass
        service=roles.OpenController(binding,budget=f.budget,client_factory=f.factory,broker=self.fixture().broker)
        with patch('earnings_http.http.client.HTTPSConnection',Connection):
            with self.assertRaisesRegex(RuntimeError,'TimeoutError'):
                service.propose(f.prompt,f.slots[0])
        self.assertEqual(calls.count('/v1/responses'),1)
        self.assertEqual(f.budget.db.execute("SELECT charged,status FROM requests WHERE id!='fixture-prior'").fetchall(),[(0,'uncertain')])
        slot=Path(f.slots[0]);result=json.loads((slot/'result.json').read_bytes())
        self.assertEqual(result['status'],'FAILED_NO_RETRY');self.assertFalse(result['retry_allowed'])
        self.assertFalse((slot/'01-response.json').exists())
        self.assertTrue(json.loads((slot/'budget-summary.json').read_bytes())['blocked'])
        with self.assertRaises(FileExistsError):service.propose(f.prompt,f.slots[0])
        self.assertEqual(calls.count('/v1/responses'),1)


if __name__=='__main__':unittest.main()
