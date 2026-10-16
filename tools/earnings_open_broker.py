"""Public research tools shared by outer roles; no authority, keys or labels."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from edgar_forecast_tools import FilingTools, TOOLS, function
from earnings_http import strict_json
from earnings_open_evidence import TraceReader
from earnings_open_literature import TOOLS as LITERATURE_TOOLS
from earnings_open_program import arguments
from earnings_open_code import CandidateExecutionFailure, encoded, start_marker
from earnings_open_guest import MAX_RESULT_BYTES
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

DEFINITIONS = [*deepcopy(TOOLS), *deepcopy(LITERATURE_TOOLS),
    function('inspect_trace','Inspect one bounded page of public tool actions/results from a registered prior forecast, never reasoning or hidden labels. Start offset=0, then use next_offset. Whole page<=6000 bytes; all originals remain retained.',
        {'label':{'type':'string'},'max_events':{'type':'integer','minimum':1,'maximum':40},
         'max_output_chars':{'type':'integer','minimum':1,'maximum':2000},
         'offset':{'type':'integer','minimum':0,'maximum':10000}}),
    function('read_current_program','Read exact current selected R or H program source; never run it on host.',
        {'axis':{'type':'string','enum':['R','H']}}),
    function('run_python',f'Run new Python code defining run(payload) in the isolated no-network container. Only explicitly supplied public input is available. Complete serialized {{ok:true,value:...}} result<={MAX_RESULT_BYTES} UTF-8 bytes; source size is a separate bound. Keep evidence quotes compact. Preserve failed attempts; no automatic retry.',
        {'source':{'type':'string'},'payload_json':{'type':'string'}})]
REFERENCE_TOOL = function('read_reference_program',
    'Read a page of the exact failed R development reference, not the selected program. Character offsets; use next_offset. Read-only hashed source, never executed by this tool.',
    {'offset':{'type':'integer','minimum':0,'maximum':64000},
     'characters':{'type':'integer','minimum':1,'maximum':6000}})
HUMAN_REPAIR_DISPATCH = {
    'schema':'earnings_human_repair_dispatch_v1',
    'human_authorization':'允许修正任务派发后测试',
    'axis':'R','component':'research_policy',
    'scope':'first_declared_controller_slot',
    'adoption':'unchanged_independent_selection'}


def program_references(sources):
    """Small public descriptors for exact current source, not truncated code."""
    if (type(sources) is not dict or set(sources)!={'R','H'}
            or any(type(value) is not str or not 1<=len(value.encode('utf-8'))<=65536
                   for value in sources.values())):
        raise ValueError('Exact bounded current R/H source text required')
    return {axis:{'source_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest(),
        'source_utf8_bytes':len(source.encode('utf-8')),
        'read_tool':'read_current_program','arguments':{'axis':axis}}
        for axis,source in sources.items()}


class ResearchBroker:
    def __init__(self, root, *, company, capacity, runner, literature, trace_slots,
                 research_context_binding=None):
        root=Path(root)
        if not root.is_absolute() or root.resolve()!=root or root.exists():
            raise ValueError('Fresh canonical research action root required')
        root.mkdir(parents=True,exist_ok=False,mode=0o700)
        self.root,self.identity=root,(root.stat().st_dev,root.stat().st_ino)
        self.files=FilingTools(company)
        self.capacity,self.runner,self.literature=capacity,runner,literature
        self.trace_slots=deepcopy(trace_slots)
        self.research_context_binding=deepcopy(research_context_binding)
        self.definitions=self._definitions()
        self.calls,self.returned,self.failed=0,0,set()
        self._author_evidence_attempted,self._author_evidence_cache=False,None

    def research_context(self, *, include_source=False):
        """Frozen human brief/optional task assignment, never execution authority."""
        if type(include_source) is not bool:raise ValueError('Explicit source-view flag required')
        if self.research_context_binding is None:return None
        value=engine.read(self.research_context_binding)
        keys={'schema','human_task','prior_candidate','observations','verification','non_claims'}
        if (type(value) is not dict or set(value) not in (keys,keys|{'dispatch'})
                or value['schema']!='earnings_repair_context_v1'
                or type(value['human_task']) is not str or not value['human_task'].strip()
                or type(value['prior_candidate']) is not dict
                or value['prior_candidate'].get('axis')!='R' or 'source_text' in value['prior_candidate']):
            raise ValueError('Exact source-bound public repair context required')
        if 'dispatch' in value and (type(value['dispatch']) is not dict
                or value['dispatch']!=HUMAN_REPAIR_DISPATCH):
            raise ValueError('Exact explicitly human-authorized initial R repair dispatch required')
        source=engine.activation._read(value['prior_candidate']['source']).decode('utf-8')
        if len(source.encode())>64_000:raise ValueError('Prior public source exceeds context bound')
        delivery=value['prior_candidate'].get('source_delivery','inline')
        if delivery not in ('inline','paged_reference') or ('source_delivery' in value['prior_candidate'] and delivery!='paged_reference'):
            raise ValueError('Only the explicit paged reference extension is supported')
        if include_source and delivery=='inline':value['prior_candidate']['source_text']=source
        observations=value.get('observations')
        locations=observations.get('actual_original_read_locations') if type(observations) is dict else None
        if include_source and locations is not None:
            value['initial_original_evidence']=self._author_original_evidence(locations)
        return value

    def _author_original_evidence(self, locations):
        """One declared public read, supplied by H, not a model exploration claim.

        Use the existing broker/filing boundary, counters and immutable receipt.
        Repeated context views verify/reuse this exact observation, never retry.
        No hint means legacy/autonomous packets are unchanged.
        """
        if type(locations) is not list or not 1<=len(locations)<=8 or type(locations[0]) is not dict:
            raise ValueError('Bounded explicit original-table read hints required')
        hint=locations[0]
        args=hint.get('arguments')
        path=args.get('path') if type(args) is dict else None
        if (hint.get('tool')!='read_file' or type(path) is not str
                or not path.startswith('filings/') or not path.endswith('.md')):
            raise ValueError('Only an existing allowed original filing read can seed Author evidence')
        request={'tool':'read_file','arguments':deepcopy(args)}
        if self._author_evidence_cache is None:
            if self._author_evidence_attempted:
                raise ValueError('Initial Author evidence failed once; no automatic retry')
            self._author_evidence_attempted=True
            result=self.dispatch('read_file',deepcopy(args))
            if not result['value'].get('text'):
                raise ValueError('Initial Author evidence has no original body; preserve receipt and stop')
            self._author_evidence_cache={'schema':'earnings_author_initial_original_evidence_v1',
                'provided_by':'harness_preparation_not_model_tool_choice',
                'request':request,'result':result,
                'source_sha256':hashlib.sha256(self.files.files[path].encode('utf-8')).hexdigest(),
                'untrusted_evidence':True}
        cached=self._author_evidence_cache
        if (cached['request']!=request
                or cached['source_sha256']!=hashlib.sha256(self.files.files[path].encode('utf-8')).hexdigest()
                or engine.read(cached['result']['research_receipt'])!=
                   {'value':cached['result']['value'],'untrusted_evidence':True}):
            raise ValueError('Initial Author evidence source/request/receipt drift')
        return deepcopy(cached)

    def _definitions(self):
        context=None if self.research_context_binding is None else engine.read(self.research_context_binding)
        paged=(type(context) is dict and type(context.get('prior_candidate')) is dict
            and context['prior_candidate'].get('source_delivery')=='paged_reference')
        if paged:self.research_context()
        return deepcopy(DEFINITIONS+([REFERENCE_TOOL] if paged else []))

    def available_traces(self):
        return sorted(label for label,slot in self.trace_slots.items() if Path(slot).is_dir())

    def current_sources(self):
        pair=digest(self.capacity.batch.snapshot()['micro_evolution']['active_pair'])
        return {axis:engine.activation._read(self.capacity.resolve(axis,
            expected_pair_sha256=pair)['receipt']['source']).decode() for axis in ('R','H')}

    def current_programs(self):
        return program_references(self.current_sources())

    def _candidate_failure(self,error,source,payload):
        """Only the exact runner classification plus original evidence recovers."""
        try:
            if type(error) is not CandidateExecutionFailure:
                raise ValueError('Exact runner-owned candidate failure required')
            bound=error.receipt
            if type(bound) is not dict or set(bound)!={'path','sha256'}:
                raise ValueError('Exact failure binding required')
            path=Path(bound['path'])
            if (path.resolve()!=path or str(path)!=bound['path'] or path.name!='result.json'
                    or path.parent.parent!=self.runner.root
                    or not re.fullmatch(r'call-[0-9a-f]{32}',path.parent.name)):
                raise ValueError('Original failure outside exact owned code root')
            def raw(name,limit):
                p=path.parent/name
                if p.resolve()!=p or not p.is_file() or p.stat().st_nlink!=1 or p.stat().st_size>limit:
                    raise ValueError('Nonregular, aliased or oversized code failure original')
                return p.read_bytes()
            receipt=strict_json(raw('result.json',100000))
            sha=lambda value:hashlib.sha256(value).hexdigest()
            if sha(raw('result.json',100000))!=bound['sha256']:
                raise ValueError('Failure receipt drift')
            intent=strict_json(raw('intent.json',100000))
            if type(intent) is not dict or set(intent)!={'source_sha256','input_sha256','image',
                    'guest_sha256','command','docker','timeout_seconds','container_name',
                    'container_token','retry_allowed','start_command'}:
                raise ValueError('Complete original execution intent required')
            request=raw('input.json',2200000);out=raw('stdout.bin',65536);err=raw('stderr.bin',65536)
            if (any(receipt.get(k)!=v for k,v in intent.items())
                    or request!=encoded({'source':source,'payload':payload})
                    or receipt.get('source_sha256')!=sha(source.encode()) or receipt.get('input_sha256')!=sha(request)
                    or receipt.get('stdout_sha256')!=sha(out) or receipt.get('stderr_sha256')!=sha(err)
                    or not err.startswith(start_marker(sha(source.encode())))
                    or receipt.get('status')!='FAILED_NO_RETRY' or receipt.get('retry_allowed') is not False
                    or receipt.get('failure_classification')!='RECOVERABLE_GUEST_EXCEPTION'
                    or receipt.get('execution_started') is not True or receipt.get('cleanup_verified') is not True
                    or receipt.get('source_integrity_verified') is not True
                    or receipt.get('host_candidate_execution') is not False or self.runner.blocked):
                raise ValueError('Unverified ordinary candidate failure')
            detail=receipt.get('candidate_diagnostic')
            if (receipt.get('exit_code')!=2 or type(receipt.get('exit_code')) is not int
                    or strict_json(out)!={'ok':False,'candidate_exception':detail}):
                raise ValueError('Guest failure bytes/exit do not establish the reported diagnostic')
            if (type(detail) is not dict or set(detail)!={'error_type','message','source_line'}
                    or type(detail['error_type']) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',detail['error_type'])
                    or type(detail['message']) is not str or len(detail['message'])>512
                    or not all(c.isprintable() for c in detail['message'])
                    or detail['source_line'] is not None and (type(detail['source_line']) is not int
                        or not 1<=detail['source_line']<=len(source.splitlines()))):
                raise ValueError('Bounded candidate-only diagnostic required')
            return {'status':'CANDIDATE_FAILED_NO_RETRY',**detail,
                'execution_receipt_sha256':bound['sha256'],'same_action_retry_allowed':False,
                'diagnostic_is_untrusted':True}
        except (ValueError,TypeError,KeyError,OSError) as invalid:
            raise RuntimeError('Candidate failure originals could not be verified') from invalid

    def dispatch(self, name, args):
        if (self.root.resolve()!=self.root or self.root.is_symlink()
                or (self.root.stat().st_dev,self.root.stat().st_ino)!=self.identity
                or self.definitions!=self._definitions() or self.calls>=64):
            raise ValueError('Research action identity/budget/definitions drift')
        specs={t['name']:t['parameters'] for t in self.definitions}
        if name not in specs:
            raise ValueError('Unknown research action')
        arguments(args,specs[name])
        key=digest({'name':name,'arguments':args})
        if name=='run_python':
            try:key=digest({'name':name,'source':args['source'],'payload':strict_json(args['payload_json'])})
            except (ValueError,TypeError):pass
        if key in self.failed:
            raise ValueError('Exact failed research action stays closed; diagnose before a different proposal')
        slot=self.root/f'{self.calls+1:04d}'
        slot.mkdir(mode=0o700);self.calls+=1
        engine.save(slot/'intent.json',{'name':name,'arguments':args,'retry_allowed':False})
        failed_execution=None
        try:
            if name in {t['name'] for t in TOOLS}:
                value=self.files.dispatch(name,args)
            elif name in {t['name'] for t in LITERATURE_TOOLS}:
                value=self.literature.dispatch(name,args)
            elif name=='inspect_trace':
                value=TraceReader({label:self.trace_slots[label] for label in self.available_traces()}).read(
                    args['label'],max_events=args['max_events'],max_output_chars=args['max_output_chars'],offset=args['offset'])
            elif name=='read_current_program':
                axis=args['axis'];sources=self.current_sources()
                value={'axis':axis,'source_text':sources[axis],**program_references(sources)[axis]}
            elif name=='read_reference_program':
                context=self.research_context()
                source=engine.activation._read(context['prior_candidate']['source']).decode('utf-8')
                offset=args['offset'];end=min(offset+args['characters'],len(source))
                if offset>len(source):raise ValueError('Reference offset beyond source')
                value={'source_sha256':context['prior_candidate']['source']['sha256'],
                    'offset':offset,'next_offset':end,'total_characters':len(source),
                    'text':source[offset:end],'read_only_reference':True}
            else:
                payload=strict_json(args['payload_json'])
                try:value=self.runner.run(args['source'],payload)
                except CandidateExecutionFailure as error:
                    value={'error':self._candidate_failure(error,args['source'],payload)}
                    failed_execution=dict(error.receipt)
                    self.failed.add(key)
            length=len(json.dumps(value,allow_nan=False).encode())
            self.returned+=length
            if length>180_000 or self.returned>2_000_000:
                raise ValueError('Public research output budget exceeded')
            if failed_execution is not None:
                bound=engine.save(slot/'failure.json',{'error_type':'CandidateExecutionFailure',
                    'execution':failed_execution,'candidate_failure':value['error'],'retry_allowed':False})
                return {**value,'research_receipt':bound}
            bound=engine.save(slot/'result.json',{'value':value,'untrusted_evidence':True})
            return {'value':value,'research_receipt':bound}
        except Exception as error:
            self.failed.add(key)
            engine.save(slot/'failure.json',{'error_type':type(error).__name__,'retry_allowed':False})
            raise
