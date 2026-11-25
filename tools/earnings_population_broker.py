"""Paged exact pool sources and label-free original feedback projections."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from edgar_forecast_tools import function
from earnings_entry import checked
from earnings_open_broker import ResearchBroker
from earnings_open_program import arguments
from earnings_population_diagnostics import from_trial
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class PopulationBroker(ResearchBroker):
    def _frontier_paging(self):
        binding=getattr(self,'clean_slate_runtime_binding',None)
        if binding is None:return False
        from earnings_population_coevolution import frontier_round
        value=engine.read(binding)
        return value.get('clean_slate_policy')=='round0_clean_slate_v1' and frontier_round(value.get('clean_learning_round'))

    def __init__(self, *args, versions, population_context_binding=None, prior_company=None,
                 training_scope=None, clean_slate_runtime_binding=None, **kwargs):
        self.clean_slate_runtime_binding = deepcopy(clean_slate_runtime_binding)
        from edgar_forecast_tools import FilingTools
        self.training_scope = deepcopy(training_scope)
        if training_scope is not None:
            from earnings_population_training25 import admit
            from earnings_population_public_predictions import company as descriptor
            admit(training_scope, kwargs.get('company', {}).get('cik'))
            if prior_company is not None:
                admit(training_scope, prior_company.get('cik'))
            for company in [kwargs['company'], *([] if prior_company is None else [prior_company])]:
                if company != descriptor(company['cik'], training_scope=training_scope):
                    raise ValueError('Training broker descriptor differs from original metadata')
        self.population_context_binding = deepcopy(population_context_binding)
        self.prior_company = deepcopy(prior_company)
        self.prior_files = None if prior_company is None else FilingTools(prior_company)
        self.versions = deepcopy(versions)
        for row in self.versions.values():
            for axis in ('R', 'H'):
                checked(row[axis])
        super().__init__(*args, **kwargs)

    def research_context(self, *, include_source=False):
        if self.population_context_binding is None:
            return super().research_context(include_source=include_source)
        value = engine.read(self.population_context_binding)
        if (type(include_source) is not bool
                or value.get('schema') != 'earnings_population_author_context_v1'
                or value.get('parent_version_id') not in self.versions):
            raise ValueError('Exact feedback-bound population Author context required')
        parent = self.versions[value['parent_version_id']]
        expected = self.references()[value['parent_version_id']]
        if value.get('campaign') is not None:
            current = self.current_programs()
            if any(current[axis]['source_sha256'] != parent[axis]['sha256'] for axis in ('R', 'H')):
                raise ValueError('Current Native pair differs from actual chosen Author parent')
            if value.get('parent_programs') == current:
                expected = current
        if value.get('parent_programs') != expected:
            raise ValueError('Exact feedback-bound population Author context required')
        clean_binding = getattr(self,'clean_slate_runtime_binding',None)
        if clean_binding is not None:
            from earnings_population_clean_slate import enabled, read_task, POLICY, round2_origin
            from earnings_population_coevolution import selected_parent, frontier_round
            runtime = engine.read(clean_binding)
            if not enabled(runtime): raise ValueError('Explicit clean Author runtime required')
            task, scope = read_task(runtime)
            state=task['scaffold'];origin=round2_origin(runtime) if frontier_round(runtime.get('clean_learning_round')) else None
            parent=selected_parent(state,origin)
            active={ident:state['versions'][ident] for ident in [state['stable_id'],*state.get('explorers',[])]}
            feedback = engine.read(task['feedback'])
            if (task['mode'] != 'proposal' or self.training_scope != scope
                    or self.research_context_binding is not None
                    or value.get('clean_slate_policy') != POLICY
                    or self.versions != active
                    or value['parent_version_id'] != parent['id']
                    or value.get('feedback_binding') != task['feedback']
                    or value.get('feedback_sha256') != digest(task['feedback'])
                    or value.get('feedback') != feedback or value.get('training_comparator') != feedback
                    or set(value) & {'campaign','prior_candidate','implementation_base','training_state',
                        'prior_delivery_failure','failure_evidence_context','delivery_lessons'}):
                raise ValueError('Clean Author must consume only exact Round0 feedback and scaffold')
            return value
        if self.research_context_binding is not None:
            reference = super().research_context(include_source=include_source)
            observations = reference['observations']
            if (value.get('prior_candidate') != reference['prior_candidate']
                    or value.get('feedback_binding') != observations['feedback_binding']
                    or value.get('feedback_sha256') != digest(observations['feedback_binding'])
                    or value.get('original_R_evidence_abi') != observations['original_R_evidence_abi']
                    or value.get('failure_evidence_context') != observations.get('public_failure_examples')
                    or value.get('prior_delivery_failure') != observations.get('prior_delivery_failure')
                    or value.get('evidence_abi_guidance') != reference['verification']):
                raise ValueError('Author rejected-source reference differs from exact broker context')
        training = {'training_comparator', 'training_state'}
        if self.training_scope is not None:
            if self.research_context_binding is None or any(
                    key not in value or value[key] != observations.get(key) for key in training):
                raise ValueError('Author training inputs differ from exact reference context')
            if value['training_comparator'].get('split') != self.training_scope['split']:
                raise ValueError('Author comparator differs from admitted frozen scope')
        elif training & set(value):
            raise ValueError('Training inputs require explicit frozen scope')
        if ('implementation_base' in value) != ('implementation_base_decision' in value):
            raise ValueError('Implementation base and exact scientific decision must travel together')
        if 'implementation_base' in value:
            from earnings_population_delta_author import implementation_base
            expected_base = implementation_base(value['implementation_base_decision'], parent,
                value['feedback_binding'], value['prior_candidate'])
            if expected_base is None or digest(expected_base) != digest(value['implementation_base']):
                raise ValueError('Author implementation base differs from exact current rejected-source proof')
        return value

    def _definitions(self):
        result = super()._definitions() + [function('read_population_program',
            'Read an exact page of a registered pool version, never execute it. Use supplied change/function character offsets to inspect relevant code; offset0 starts the whole source and next_offset continues a page.',
            {'version_id': {'type': 'string', 'enum': sorted(self.versions)},
             'axis': {'type': 'string', 'enum': ['R', 'H']},
             'offset': {'type': 'integer', 'minimum': 0, 'maximum': 65536},
             'characters': {'type': 'integer', 'minimum': 1, 'maximum': 4000}})]
        if self._frontier_paging():
            for spec in result:
                if spec['name']=='read_current_program':
                    spec['description']='Read the first exact4000-character page of the current selected R/H source, never execute it. This is not the whole source. Continue via returned read_population_program arguments and next_offset; full hash/length retained.'
        if self.prior_files is not None:
            result.append(function('read_prior_file',
                'Read exact prior-company public evidence to diagnose the reported failure. Same original cutoff/files/read bounds; not hidden answers. Use prior feedback original_questions and filing_index.tsv to locate filings.',
                {'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
                 'characters': {'type': 'integer', 'minimum': 1, 'maximum': 20000}}))
        return result

    def references(self):
        return {ident: {axis: {'sha256': row[axis]['sha256'],
            'read_tool': 'read_population_program', 'arguments': {
                'version_id': ident, 'axis': axis, 'offset': 0, 'characters': 4000}}
                for axis in ('R', 'H')} for ident, row in self.versions.items()}

    def dispatch(self, name, args):
        current_page=name=='read_current_program' and self._frontier_paging()
        if name not in {'read_population_program', 'read_prior_file'} and not current_page:
            return super().dispatch(name, args)
        if (self.root.resolve() != self.root or self.root.is_symlink()
                or (self.root.stat().st_dev, self.root.stat().st_ino) != self.identity
                or self.definitions != self._definitions() or self.calls >= 64):
            raise ValueError('Original research action identity/budget drift')
        definition = next((t for t in self.definitions if t['name'] == name), None)
        if definition is None:
            raise ValueError('Prior public evidence is not registered in this role')
        arguments(args, definition['parameters'])
        key = digest({'name': name, 'arguments': args})
        if key in self.failed:
            raise ValueError('Failed source page stays closed; no automatic retry')
        slot = self.root/f'{self.calls + 1:04d}'
        slot.mkdir(mode=0o700)
        self.calls += 1
        engine.save(slot/'intent.json', {'name': name, 'arguments': args, 'retry_allowed': False})
        try:
            if current_page:
                sources=self.current_sources()
                pair=digest({axis:hashlib.sha256(sources[axis].encode()).hexdigest() for axis in ('R','H')})
                row=self.versions.get(pair)
                if row is None or any(checked(row[axis]).decode()!=sources[axis] for axis in ('R','H')):
                    raise ValueError('Current Native pair differs from exact registered source page')
                axis=args['axis'];text=sources[axis];end=min(4000,len(text))
                value=dict(version_id=pair,axis=axis,source_sha256=row[axis]['sha256'],
                    source_utf8_bytes=len(text.encode()),offset=0,next_offset=end,total_characters=len(text),
                    source_text=text[:end],complete_source=end==len(text),
                    read_tool='read_population_program',arguments=dict(version_id=pair,axis=axis,offset=end,characters=4000),
                    notice='Exact bounded first page; not the whole source. Continue with the existing paged tool; original full source remains unchanged.')
            elif name == 'read_prior_file':
                value = self.prior_files.dispatch('read_file', deepcopy(args))
                value = dict(value, prior_company_id=self.prior_company['cik'],
                    source_sha256=hashlib.sha256(self.prior_files.files[args['path']].encode()).hexdigest())
            else:
                bound = self.versions[args['version_id']][args['axis']]
                text = checked(bound).decode()
                offset, count = args['offset'], args['characters']
                if offset > len(text):
                    raise ValueError('Source page starts beyond exact source')
                end = min(offset + count, len(text))
                value = dict(version_id=args['version_id'], axis=args['axis'], source_sha256=bound['sha256'],
                    offset=offset, next_offset=end, total_characters=len(text), text=text[offset:end])
            self.returned += len(json.dumps(value, allow_nan=False).encode())
            if self.returned > 2_000_000:
                raise ValueError('Original research return budget exhausted')
            receipt = engine.save(slot/'result.json', {'value': value, 'untrusted_evidence': True})
            return dict(value=value, research_receipt=receipt)
        except Exception as error:
            self.failed.add(key)
            engine.save(slot/'failure.json', {'error_type': type(error).__name__, 'retry_allowed': False})
            raise


def public_feedback(feedback, versions, *, policy=None, training_scope=None):
    """Copy only verified original public trial awards, never raw scorer JSON."""
    from earnings_population_public_predictions import policy as validate_policy
    validate_policy(policy)
    if feedback.get('schema') == 'earnings_population_seed_v1':
        return deepcopy(feedback)
    original = engine.read(feedback)
    scoped = {} if training_scope is None else {'training_scope': training_scope}
    if training_scope is not None:
        from earnings_population_training25 import admit
        admit(training_scope, original.get('company_id'))
    if original.get('schema') in {'earnings_population_rejection_feedback_v1',
                                  'earnings_population_campaign_feedback_v1'}:
        from earnings_population_campaign_context import project
        return project(original, versions, lambda value, pool: _public_scored(value, pool, policy=policy, **scoped), **scoped)
    return _public_scored(original, versions, policy=policy, **scoped)


def _public_scored(original, versions, *, policy=None, training_scope=None):
    from earnings_population_public_predictions import policy as validate_policy
    validate_policy(policy)
    if original.get('schema') != 'earnings_population_feedback_v1':
        raise ValueError('Actual preceding population feedback required')
    scoped = {} if training_scope is None else {'training_scope': training_scope}
    if training_scope is not None:
        from earnings_population_training25 import admit
        admit(training_scope, original.get('company_id'))
    result = {k: original[k] for k in ('schema', 'company_id', 'round_index', 'stable_id', 'scope')}
    reviewed = original.get('exploration_review')
    if reviewed is not None:
        result['exploration_review'] = {key: reviewed[key] for key in ('candidate_id', 'accepted_for_exploration')}
        outcomes = [b for b in reviewed['evidence'] if Path(b['path']).name.endswith('-outcome.json')]
        if reviewed['candidate_id'] is not None:
            if len(outcomes) != 1:
                raise ValueError('Actual proposal outcome required, including rejection')
            outcome = engine.read(outcomes[0])
            if (outcome.get('schema') != 'earnings_population_exploration_review_v1'
                    or outcome.get('candidate_id') != reviewed['candidate_id']
                    or outcome.get('accepted_for_exploration') is not reviewed['accepted_for_exploration']
                    or type(outcome.get('rationale')) is not str or not 1 <= len(outcome['rationale']) <= 1000):
                raise ValueError('Exploration outcome differs from actual review')
            result['exploration_review']['rationale'] = outcome['rationale']
    result['results'] = []
    for row in original['results']:
        rows = [b for b in row['evidence'] if Path(b['path']).name == 'population-public-feedback.json']
        if len(rows) != 1:
            raise ValueError('Exactly one verified public forecast projection required')
        public = engine.read(rows[0])
        if (public.get('schema') != 'earnings_population_public_trial_v1'
                or public.get('version_id') != row['version_id'] or public.get('points') != row['points']
                or public.get('company_id') != original['company_id']
                or public.get('pool_sources') != {axis: versions[row['version_id']][axis]['sha256'] for axis in ('R', 'H')}):
            raise ValueError('Public feedback does not join actual original trial/source')
        targets = public['target_scores']
        if (type(targets) is not list or len(targets) != 5
                or any(type(t) is not dict or set(t) != {'target_id', 'points_awarded'}
                    or type(t['target_id']) is not str or type(t['points_awarded']) not in (int, float)
                    or t['points_awarded'] not in (0, .5, 1) for t in targets)
                or len({t['target_id'] for t in targets}) != 5
                or sum(t['points_awarded'] for t in targets) != row['points']):
            raise ValueError('Exact original five-target public awards required')
        projected = dict(version_id=row['version_id'], points=row['points'], target_scores=deepcopy(targets))
        program = [b for b in row['evidence'] if b.get('path') ==
                   str(Path(rows[0]['path']).parent/'program-executions.json')]
        if program:
            from edgar_forecast_tools import FilingTools
            if policy is None:
                from earnings_population_tasks import resident
                company = resident(original['company_id'])['company']
                projected['research_diagnostics'] = from_trial(rows[0], row['evidence'],
                    versions[row['version_id']], company)
            else:
                from earnings_population_public_predictions import company as descriptor, project
                company = descriptor(original['company_id'], **scoped)
                diagnostics, comparison = project(rows[0], row['evidence'], versions[row['version_id']], company, **scoped)
                projected.update(research_diagnostics=diagnostics, public_predictions=comparison)
            result['original_questions'] = FilingTools(company).files['questions.md']
        else:
            projected['research_diagnostics'] = {'availability': 'unavailable_missing_execution_evidence'}
        result['results'].append(projected)
    return result
