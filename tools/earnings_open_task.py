"""Opt-in open-program task on the existing feedback engine and financial task."""
from copy import deepcopy
from pathlib import Path

from earnings_capacity_task import EarningsTask
from earnings_open_admission import admit, sources
from earnings_open_program import candidate
from earnings_open_broker import program_references
from earnings_open_worker import ProgramWorker
from earnings_open_feedback import project_target_scores
import earnings_open_researcher as researcher
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


def controller_packet_view(packet):
    """Reference source, deduplicate advice; never summarize actual feedback."""
    result=deepcopy(packet)
    result['program_sources']=program_references(result['program_sources'])
    execution=result['guidance_execution']
    if type(execution) is not dict:
        raise ValueError('Exact public researcher execution required')
    if 'value' in execution:
        if digest(execution.pop('value'))!=digest(result['researcher_guidance']):
            raise ValueError('Verified researcher value differs from execution')
        execution['value_sha256']=digest(result['researcher_guidance'])
    return result


class OpenTask(EarningsTask):
    worker_type=ProgramWorker
    def __init__(self):
        self.capacity=self.runner=self.broker=None
        self.baseline_score=None

    def admit_live(self,envelope):
        admit(envelope)
        return True

    def preflight(self,envelope):
        self.company,self.state_api=admit(envelope)
        self.kernel=envelope['evaluation_kernel']
        from earnings_execution_receipt import kernel
        kernel(self.kernel,self.state_api.tools.files['questions.md'])

    def sources(self):
        from earnings_entry import REPO
        return {name:engine.pin(REPO/name) for name in sources()}

    def bootstrap_control(self,envelope,prompt,index):
        if index!=1:return None
        self.admit_live(envelope)
        if ('program_lineage' in engine.read(envelope['study'])
                and engine.read(envelope['grant'])['bootstrap_no_model_call'] is False):return None
        return {'schema':'earnings_capacity_decision_v1','axis':'continue','component':'none',
            'parent_pair_sha256':prompt['parent_pair_sha256'],'feedback_sha256':prompt['feedback_sha256'],
            'hypothesis':'Human-declared executable baseline; no model decision claimed',
            'expected_effect':'Score the unchanged financial task and deliver actual feedback'}

    def seed(self,envelope):
        result=super().seed(envelope)
        study=engine.read(envelope['study'])
        if 'program_lineage' in study:
            from earnings_open_continuation import verify
            lineage=verify(study['program_lineage'])
            result['feedback']['inherited_research']={
                'prior_pair_sha256':lineage['prior_pair_sha256'],
                'feedback':deepcopy(lineage['feedback']),'scope':lineage['scope']}
            result['artifacts'].append(study['program_lineage'])
        return result

    def packet(self,envelope,ctx,profiles,pair):
        if self.capacity is None or self.runner is None or self.broker is None:
            raise ValueError('Program task must be attached to its admitted owned assembly')
        previous=ctx['previous_result']
        state=self.load_state(previous['state'])
        objective={
            'primary':'Improve financial prediction methods and the process that generates them, using the unchanged original scorer.',
            'diagnosis':'Use per-target awarded points and original public evidence to compare method-level and tooling explanations. Points are feedback, not the hidden answers.',
            'selection':'Choose the most informative next research question. A tool repair is a means to research, not the default end objective.',
            'literature':'Search and read relevant primary methods when needed; no reward for paper counts or tool calls.',
            'attribution':'Prediction algorithms change the predictor semantically; distinguish that from a stronger researcher and keep composite effects explicit.'}
        payload={'stage':'controller','questions':self.state_api.tools.files['questions.md'],
            'filing_index':self.state_api.tools.files['filing_index.tsv'],'records':deepcopy(state['records']),
            'feedback':deepcopy(previous['feedback']),'research_objective':deepcopy(objective)}
        source=self.broker.current_sources()
        execution=researcher.run(self.runner,source['R'],payload,self.broker.files)
        value=researcher.verify(execution,source['R'],payload,self.company)
        public_execution=deepcopy(execution)
        if 'research_observations' in public_execution:
            observations=public_execution.pop('research_observations')
            public_execution.update(research_observations_sha256=digest(observations),
                research_observation_count=len(observations))
        packet={'task_id':envelope['id'],'questions':payload['questions'],
            'parent_pair_sha256':pair,'parent_feedback_sha256':ctx['previous_feedback_sha256'],
            'feedback_sha256':ctx['previous_feedback_sha256'],'feedback':deepcopy(previous['feedback']),
            'profiles':deepcopy(profiles),'program_sources':source,
            'registered_traces':self.broker.available_traces(),
            'researcher_guidance':value,'guidance_execution':public_execution,
            'research_objective':objective,
            'scope':'Discovery; financial data/scorer unchanged. Method literature is an extra observation channel.'}
        context_reader=getattr(type(self.broker),'research_context',None)
        if callable(context_reader):
            context=context_reader(self.broker)
            if context is not None:packet['research_context']=context
        return controller_packet_view(packet)

    def candidate(self,original,before,choice):return candidate(original,before,choice)

    def make_worker(self,task_id,capacity,pair,state_root,state,*,shadow_proposal_sha256=None):
        return ProgramWorker(self.company,task_id,capacity,pair,state_root,state,
            shadow_proposal_sha256=shadow_proposal_sha256,runner=self.runner)

    def execution(self,output,worker,slot):
        worker._check()
        result=super().execution(output,worker,slot)
        saved=engine.pin(Path(slot)/'program-executions.json')
        if engine.read(saved)!={'R':worker.r_execution,'H':worker.executions,
                'scope':'Actual selected container program executions; no quality claim'}:
            raise ValueError('Program execution summary differs from actual worker')
        originals=[saved]
        public=researcher.public_evidence(worker.r_execution)
        if public is not None:
            bound=engine.pin(Path(slot)/'researcher-public-tools.json')
            if engine.read(bound)!=public:raise ValueError('Public R evidence differs from actual worker originals')
            originals.append(bound)
        for run in [*researcher.originals(worker.r_execution),*[item['execution'] for item in worker.executions]]:
            root=Path(run['receipt']['path']).parent
            originals.extend(engine.pin(root/name) for name in ('result.json','intent.json','input.json',
                'stdout.bin','stderr.bin','create.stdout','create.stderr'))
        return dict(result,artifacts=[*result['artifacts'],*originals])

    def feedback(self,output,envelope):
        result=super().feedback(output,envelope)
        score=result['observation']['prediction']['score_out_of_5']
        if self.baseline_score is None:self.baseline_score=score
        result['baseline_score_out_of_5']=self.baseline_score
        result['target_scores']=project_target_scores(engine.read(output['score']),
            self.state_api.tools.files['questions.md'])
        from earnings_open_evidence import project_trace
        slot=Path(output['result']['path']).parent
        trace=project_trace(slot,max_events=8,max_output_chars=500)
        result['public_trace']={'slot':slot.name,**trace}
        return result
