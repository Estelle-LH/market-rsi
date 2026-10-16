import json
from pathlib import Path
import tempfile
import unittest

from earnings_open_program import program, candidate, arguments, schema, run_cases
from market_rsi import digest


R = "PROGRAM={'axis':'R'}\nimport statistics\ndef helper(xs): return statistics.median(xs)\ndef run(payload): return helper(payload)\n"
SPEC = {'type':'object','properties':{'xs':{'type':'array','items':{'type':'number'}}},
        'required':['xs'],'additionalProperties':False}
H = "PROGRAM="+repr({'axis':'H','tools':[{'name':'median_estimate','description':'New algorithm', 'parameters':SPEC}]})+"\n"+R.split('\n',1)[1]


class ProgramTests(unittest.TestCase):
    def choice(self, axis='R'):
        return {'schema':'earnings_capacity_decision_v1','axis':axis,
                'component':'research_policy' if axis=='R' else 'tool_interface',
                'parent_pair_sha256':'1'*64,'feedback_sha256':'2'*64,
                'hypothesis':'Test a different algorithm','expected_effect':'One predeclared same-input test'}

    def test_arbitrary_functions_imports_algorithms_are_admitted(self):
        self.assertEqual(program(R.encode(),'R'), {'axis':'R'})
        self.assertEqual(program(H.encode(),'H')['tools'][0]['name'], 'median_estimate')

    def test_committed_empty_program_baselines_have_original_tool_surface(self):
        root=Path(__file__).resolve().parents[1]/'configs/earnings_coevolution'
        self.assertEqual(program((root/'program_R0.py').read_bytes(),'R'),{'axis':'R'})
        self.assertEqual(program((root/'program_H0.py').read_bytes(),'H'),{'axis':'H','tools':[]})

    def test_malformed_metadata_types_produce_explicit_validation_failure(self):
        with self.assertRaises(ValueError):schema({'type':[]})
        with self.assertRaises(ValueError):program(H.replace(repr(SPEC),repr('not-a-schema')).encode(),'H')

    def test_host_does_not_execute_candidate(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'should-not-exist'
            source=R+f'open({str(path)!r},"w").write("bad")\n'
            program(source.encode(),'R')
            self.assertFalse(path.exists())

    def test_exact_author_source_and_tests_bound(self):
        choice=self.choice()
        value={'decision_sha256':digest(choice),'source_text':R,'test_text':"CASES=[{'input':[1,3,8],'expected':3}]"}
        result=candidate(value, {'axis':'R'}, choice)
        self.assertEqual(result['cases'][0]['expected'],3)
        self.assertFalse(result['tests_executed'])
        value['decision_sha256']='0'*64
        with self.assertRaises(ValueError): candidate(value, {'axis':'R'}, choice)

    def test_literal_metadata_duplicates_axis_and_missing_entry_rejected(self):
        for source in (R.replace("'R'", "'H'"), R.replace('PROGRAM=', 'OTHER='),
                       R.replace('def run(', 'def different('), R+"PROGRAM={'axis':'R'}\n",
                       R.replace("{'axis':'R'}", "{'axis':'R','axis':'R'}")):
            with self.assertRaises(ValueError): program(source.encode(),'R')

    def test_broker_and_state_tool_names_protected(self):
        for name in ('save_research_record','run_python','inspect_trace'):
            with self.assertRaises(ValueError): program(H.replace('median_estimate',name).encode(),'H')

    def test_schema_no_external_reference_and_exact_fields(self):
        self.assertEqual(schema(SPEC), SPEC)
        with self.assertRaises(ValueError): schema(dict(SPEC, **{'$ref':'file:///secret'}))
        with self.assertRaises(ValueError): schema(dict(SPEC, additionalProperties=True))
        for value in ({'xs':[1,2.5]}, {'xs':[]}): arguments(value,SPEC)
        for value in ({'xs':[True]}, {'xs':[float('nan')]}, {'xs':[],'extra':1}, {'xs':'x'}):
            with self.assertRaises(ValueError): arguments(value,SPEC)

    def test_cases_are_executed_by_supplied_runner_not_self_asserted(self):
        class Runner:
            def run(self, source, payload): return {'value':payload[0], 'receipt':{'fixture':True}}
        results=run_cases(Runner(),R,[{'input':[3],'expected':3},{'input':[2],'expected':9}])
        self.assertEqual([row['passed'] for row in results],[True,False])


if __name__=='__main__': unittest.main()
