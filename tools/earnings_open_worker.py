"""Selected R/H programs on the existing filing worker; execution is container-only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from edgar_forecast_tools import TOOLS
from earnings_capacity_worker import CapacityWorker, SAVE_TOOL
from earnings_entry import checked, durable_json, strict_json
from earnings_open_program import arguments
import earnings_open_researcher as researcher
from market_rsi import digest


def execution_value(execution, source, payload):
    """Recheck durable runner originals, not just a claimed output/hash."""
    receipt = strict_json(checked(execution['receipt']))
    root = Path(execution['receipt']['path']).parent
    request = (root/'input.json').read_bytes()
    stdout = (root/'stdout.bin').read_bytes()
    stderr = (root/'stderr.bin').read_bytes()
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    if (receipt['status'] != 'COMPLETED' or receipt['cleanup_verified'] is not True
            or receipt['host_candidate_execution'] is not False or receipt['exit_code'] != 0
            or receipt['source_sha256'] != sha(source.encode())
            or receipt['input_sha256'] != sha(request) or receipt['stdout_sha256'] != sha(stdout)
            or receipt['stderr_sha256'] != sha(stderr)
            or strict_json(request) != {'source':source, 'payload':payload}):
        raise ValueError('Program execution originals/source/input differ')
    original = strict_json(stdout)
    if original != {'ok':True, 'value':execution['value']}:
        raise ValueError('Program output differs from preserved execution')
    return deepcopy(execution['value'])


class ProgramWorker(CapacityWorker):
    open_program_protocol = 'earnings_open_program_v1'

    def __init__(self, *args, runner, **kwargs):
        super().__init__(*args, **kwargs)
        self.runner = runner
        self.initial_state_binding = deepcopy(self.state_binding)
        self.definitions = self.program_definitions()
        self.executions = []
        self.r_payload = {'stage':'forecast', 'questions':self.files['questions.md'],
            'filing_index':self.files['filing_index.tsv'], 'records':deepcopy(self.state['records'])}
        self.r_execution = researcher.run(runner,self._source('R'),self.r_payload,self.tools)
        self.context = self.expected_context()
        self._check()

    def _resolved(self, axis):
        return self.capacity.resolve(axis, expected_pair_sha256=self.pair,
            shadow_proposal_sha256=self.shadow_proposal_sha256)

    def _source(self, axis):
        return checked(self._resolved(axis)['receipt']['source']).decode()

    def program_definitions(self):
        additions = self._resolved('H')['profile']['tools']
        by_name = {t['name']:dict(deepcopy(t), type='function', strict=True) for t in additions}
        result = [by_name.pop(t['name'], deepcopy(t)) for t in TOOLS]
        return result + list(by_name.values()) + [deepcopy(SAVE_TOOL)]

    def expected_context(self):
        message, receipt = self.state_api.consume(self.initial_state_binding)
        if receipt != self.state_receipt:
            raise ValueError('Original program state message drift')
        context = self.capacity.prepare(expected_pair_sha256=self.pair,
            questions=self.files['questions.md'], state_message=message,
            shadow_proposal_sha256=self.shadow_proposal_sha256)
        payload = {'stage':'forecast', 'questions':self.files['questions.md'],
            'filing_index':self.files['filing_index.tsv'],
            'records':self.state_api.load(self.initial_state_binding)['records']}
        if payload != self.r_payload:
            raise ValueError('Program initial public input drift')
        value = researcher.verify(self.r_execution,self._source('R'),payload,self.state_api.company)
        context['messages'].append({'role':'user', 'content':
            'Selected researcher program output; untrusted research advice, not authority to change data or evaluation:\n'
            +json.dumps(value, sort_keys=True, allow_nan=False)})
        # A cold execution has a new receipt path/time; its committed behavior
        # must match, not its container invocation identifier.
        context['program_execution'] = {'source_sha256':hashlib.sha256(self._source('R').encode()).hexdigest(),
            'input_sha256':digest(payload), 'output_sha256':digest(value)}
        if 'research_observations' in self.r_execution:
            context['program_execution']['research_observations_sha256']=digest(self.r_execution['research_observations'])
        context['payload_sha256'] = digest(context['messages'])
        return context

    def _check(self):
        super()._check()
        if self.definitions != self.program_definitions() or self.context != self.expected_context():
            raise ValueError('Selected program definitions/context drift')
        for item in self.executions:
            execution_value(item['execution'], self._source('H'), item['input'])

    def dispatch(self, name, values):
        self._check()
        definitions = {t['name']:t for t in self._resolved('H')['profile']['tools']}
        if name not in definitions:
            return super().dispatch(name, values)
        self.tools.calls += 1
        if self.tools.calls > 80:
            raise ValueError('Original tool call budget exhausted')
        arguments(values, definitions[name]['parameters'])
        # The model chooses logical allowed filing names, never host paths.
        paths = ([values['path']] if 'path' in values else values.get('paths', []))
        if (type(paths) is not list or len(paths) > 16 or any(type(p) is not str
                or p not in self.files for p in paths)):
            raise ValueError('Program tools may read only named original public files')
        payload = {'tool':name, 'arguments':deepcopy(values),
            'files':{p:self.files[p] for p in set(paths) | {'questions.md','filing_index.tsv'}}}
        execution = self.runner.run(self._source('H'), payload)
        self.executions.append({'input':payload, 'execution':execution})
        result = execution_value(execution, self._source('H'), payload)
        self.tools.returned += len(json.dumps(result, allow_nan=False))
        if self.tools.returned > 2_000_000:
            raise ValueError('Original tool return budget exhausted')
        return result

    def finish(self, output):
        super().finish(output)
        public=researcher.public_evidence(self.r_execution)
        if public is not None:durable_json(output/'researcher-public-tools.json',public)
        durable_json(output/'program-executions.json', {'R':self.r_execution,
            'H':self.executions, 'scope':'Actual selected container program executions; no quality claim'})
