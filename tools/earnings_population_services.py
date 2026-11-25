"""Source-bound real roles; borrow the existing sole runtime owner and budget.

No keys, alternate scorer, mutable source adoption or candidate host execution.
Case roots are owned temporary Native execution forks, not stable promotions.
"""
from copy import deepcopy
from pathlib import Path
import json
import re

from earnings_entry import checked, REPO
from earnings_http import save_bytes
from earnings_open_broker import program_references
from earnings_open_code import DockerRunner
from earnings_open_literature import LiteratureBroker
from earnings_open_program import candidate, program, run_cases
import earnings_open_researcher as researcher
from earnings_population import version as describe
from earnings_population_case import prepare_case
from earnings_population_execution import execute
from earnings_population_roles import PopulationController, PopulationReviewer, scientific
from earnings_population_broker import PopulationBroker, public_feedback
from earnings_population_tasks import resident
from earnings_population_diagnostics import project
from earnings_population_delta_author import DeltaAuthor, assemble, implementation_base
from edgar_forecast_tools import FilingTools
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


def review_probe_output(value, *, maximum_characters=12000):
    """Expose verified public R output, not merely its opaque receipt path.

    This projection never supplies protected scorer fields. A long output is
    visibly incomplete, not a financial correctness certificate.
    """
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    result = dict(schema='earnings_population_verified_public_R_output_v1',
        value_sha256=digest(value), complete=len(raw) <= maximum_characters,
        total_characters=len(raw))
    if result['complete']:
        result['value'] = deepcopy(value)
    else:
        result['json_prefix'] = raw[:maximum_characters]
        result['qualification'] = 'Truncated exact public output; do not infer unseen evidence or accept an unverified extraction claim.'
    return result


class Services:
    @classmethod
    def company_worker(cls, runtime_binding, *, native_root, python_binding, company, slot,
                       contexts, clock_binding, transport_policy, budget, client_factory, register_case):
        """Attach one declared company to the ALREADY owned shared clock, not a new owner."""
        from earnings_population_company_batch import enabled
        value=engine.read(runtime_binding)
        if (not enabled(value) or dict(zip(value['slots']['forecast'],value['companies'])).get(slot)!=company
                or native_root!=Path('/private/tmp')/('market-rsi-'+value['id'])
                or not native_root.is_dir() or native_root.resolve()!=native_root):
            raise ValueError('Existing exact batch Native root and declared company required')
        self=cls.__new__(cls)
        self.binding,self.runtime,self.root=runtime_binding,value,Path(value['root'])
        self.native_root,self.python,self.current=native_root,python_binding,company
        self.contexts={'forecast':(contexts['forecast'],dict(budget=budget,client_factory=client_factory))}
        self.traces,self.authored,self.pending={},{},[]
        self.clock,self.transport_policy=clock_binding,transport_policy
        self.dependencies=dict(register_case=register_case)
        self.runner=DockerRunner(self.root/'code'/Path(slot).name)
        return self

    def __init__(self, runtime_binding, *, native_root, python_binding):
        self.binding, self.runtime = runtime_binding, engine.read(runtime_binding)
        self.root = Path(self.runtime['root'])
        self.native_root, self.python = Path(native_root), python_binding
        if (self.native_root.resolve() != self.native_root or self.native_root.exists()
                or not self.native_root.is_relative_to(Path('/private/tmp'))):
            raise ValueError('Fresh owned temporary Native root required')
        self.contexts, self.traces, self.authored, self.pending = {}, {}, {}, []
        self.current = None

    def start_execution(self):
        # The original shared owner must create/seal its clock before any
        # nonempty attempt root. Factories alone perform no execution setup.
        if set(self.contexts) != {'controller', 'author', 'review', 'forecast'}:
            raise ValueError('All original owner contexts required before execution setup')
        engine.read(self.clock)
        self.native_root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.runner = DockerRunner(self.root/'code')
        self.literature = LiteratureBroker(self.native_root/'literature', max_requests=8)

    def factories(self):
        # Source-file identities are checked by open_capacity_runtime before
        # contexts, credentials or paid dispatch; these closures are intentional.
        def controller(context, **dependencies):
            self.contexts['controller'] = (context, dependencies)
            return self.controller
        def author(context, **dependencies):
            self.contexts['author'] = (context, dependencies)
            return self.author
        def review(context, **dependencies):
            self.contexts['review'] = (context, dependencies)
            return self.review
        def forecast(context, **dependencies):
            self.contexts['forecast'] = (context, dependencies)
            return self.forecast
        return dict(controller=controller, author=author, review=review, forecast=forecast)

    def _training_scope(self):
        from earnings_population_public_predictions import runtime_scope
        return runtime_scope(self.runtime) if hasattr(self, 'runtime') else None

    def _proposal_task(self, *, scope=None):
        if not hasattr(self, 'runtime') or 'training_proposal_policy' not in self.runtime:
            return None  # Legacy fixtures and historical runtimes gain no field or import.
        from earnings_population_runtime import proposal_task
        from earnings_population_training25 import ROOT
        task = proposal_task(self.runtime)  # Original full runtime admission remains authoritative.
        scope = self._training_scope() if scope is None else scope
        fields = {'schema','policy','authority','split','round0_manifest','training_companies',
                  'primary_task','smoke_company_id','smoke_only','archive_only_version_ids'}
        if (type(task) is not dict or set(task) != fields or scope is None
                or self.runtime['training_proposal_policy'] != 'round0_new_panel_candidate_v1'
                or task.get('schema') != 'earnings_training25_new_panel_proposal_task_v1'
                or task.get('policy') != self.runtime['training_proposal_policy']
                or task.get('authority') != dict(path=str(ROOT/'TRAIN25-DIRECT-NEW-CANDIDATE-AUTHORITY.json'),
                    sha256='4aa5c123d6ab86c65673abd9502d7e59a9cd88cb5e6031016d9192c1b71933df')
                or task.get('round0_manifest') != dict(path=str(ROOT/'TRAIN25-PLAIN-COMPARATOR-MANIFEST.json'),
                    sha256='7a43ee9cac7204ef664d134c2e5effac14e2422aa9cedc207f66fcfe55ef07a3')
                or task.get('split') != scope['split'] or task.get('training_companies') != scope['training']
                or len(scope['training']) != 25 or task.get('smoke_only') is not True
                or self.runtime.get('companies') != [task.get('smoke_company_id')]
                or task.get('smoke_company_id') not in scope['training']
                or type(task.get('primary_task')) is not str or not task['primary_task'].strip()
                or task.get('archive_only_version_ids') != [
                    '1167a7efab99330677db3a80690bd44a6f17d1e77120f90f2b182771ad2f3b33',
                    '3392fd6008ee9dd1ce779d3c27a8cd0283209659b664d25db3681767211bd6b9']):
            raise ValueError('Exact admitted whole-panel proposal task required')
        return deepcopy(task)

    def _proposal_context(self, task):
        if task is None: return
        context = self.campaign_context
        if context is None: raise ValueError('Whole-panel proposal requires original full training context')
        summary = context.get('training_comparator'); research = context['research_context']
        if (type(summary) is not dict or summary.get('schema') != 'earnings_training25_public_summary_v1'
                or summary.get('manifest') != task['round0_manifest'] or summary.get('split') != task['split']
                or type(summary.get('rows')) is not list
                or [r.get('company_id') for r in summary['rows']] != task['training_companies']
                or any([v.get('target_id') for v in r.get('targets',[])] != ['T%03d'%i for i in range(1,6)]
                    for r in summary['rows'])
                or research['observations'].get('training_comparator') != summary):
            raise ValueError('Exact complete125 original Round0 pairs required for proposal')
        research['human_task'] = task['primary_task'] + (
            ' Plain Round0 is comparator evidence only, never a Native R/H parent. Select actual pool '
            'implementation ancestry without treating it as a full25 champion. Old34–36 are archive-only '
            'references. Current-company questions, tests and cold probes are integration smoke only; '
            'freeze one fresh method for all25 before another mutation, with no promised adoption or gain.')
        research['observations']['proposal_task'] = deepcopy(task)

    def case(self, version, slot):
        research = getattr(self, 'repair_company', None)
        company_id = research if research is not None and not Path(slot).name.startswith('forecast-') else self.current
        scope = self._training_scope()
        if scope is not None:
            from earnings_population_training25 import admit
            admit(scope, company_id)
            if company_id != self.current:
                raise ValueError('Training Native case must remain the actual current company')
        result = prepare_case(self.native_root/Path(slot).name, resident(company_id), version,
            source_commit=self.runtime['source_commit'], authority_binding=self.binding,
            python_binding=self.python, start_utc=self.start_utc,
            deadline_utc=self.runtime['deadline_utc'])
        register = getattr(self, 'dependencies', {}).get('register_case')
        if register is not None:
            register(result)
        return result

    def broker(self, case, slot):
        feedback = getattr(self, 'prior_feedback', {})
        scope = self._training_scope()
        if scope is not None and 'company_id' in feedback:
            from earnings_population_training25 import admit
            admit(scope, feedback['company_id'])
        previous = resident(feedback['company_id'])['company'] if 'company_id' in feedback else None
        reference = ({'research_context_binding': self.reference_context_binding}
                     if getattr(self, 'campaign_context', None) is not None else {})
        return PopulationBroker(self.native_root/(Path(slot).name+'-actions'),
            company=case['company'], capacity=case['capacity'], runner=self.runner,
            literature=self.literature, trace_slots=self.traces, versions=self.role_versions,
            prior_company=previous, population_context_binding=
                getattr(self, 'author_context', None) if Path(slot).name.startswith('author-') else None,
            **reference, **({} if scope is None else {'training_scope': scope}),
            **({'clean_slate_runtime_binding':self.binding} if 'clean_slate_policy' in getattr(self,'runtime',{}) else {}))

    def role(self, name, kind, case, slot):
        context, dependencies = self.contexts[name]
        review_runtime = ({'population_runtime_binding': self.binding}
                          if name == 'review' and 'review_input_policy' in getattr(self,'runtime',{}) else {})
        return kind(context, broker=self.broker(case, slot), **dependencies,
                    **({'socket_timeout_seconds': 900} if name == 'author' else {}), **review_runtime)

    def _reuse_origin(self, study):
        origin = engine.read(study['campaign_origin'])
        prefix=None
        if 'proposal_prefix_reuse' in self.runtime or 'proposal_prefix_reuse' in study:
            from earnings_population_runtime import _proposal_prefix_metadata
            prefix=_proposal_prefix_metadata(self.runtime,study,company_id=self.runtime['companies'][0])
        if prefix is not None:
            if prefix['base_origin']!=origin or any(origin.get(k) is not None for k in ('author_stage_reuse','review_stage_reuse')):
                raise ValueError('Failed37 research must retain plain completed36 ancestry')
            return dict(origin,author_stage_reuse=deepcopy(prefix['author_stage_reuse']))
        if 'training_stage_attachment' not in study:
            return origin
        import earnings_population_training25 as training
        scope = self._training_scope()
        if scope is None:
            raise ValueError('Successful training stages require admitted training scope')
        company = training.admit(scope, self.runtime['companies'][0])
        bound = study['training_stage_attachment']
        expected = training.ROOT/'inputs'/self.runtime['id']/'training-stage-attachment.json'
        if (type(bound) is not dict or set(bound) != {'path','sha256'}
                or bound.get('path') != str(expected) or expected.resolve() != expected):
            raise ValueError('Canonical admitted successful-stage receipt required')
        receipt = engine.read(bound)
        spec = training.stage_attachment_policy(self.runtime['sources'][training.PLAN],
            repo=REPO,attempt_id=self.runtime['id'],
            company_id=company,attachment_binding=receipt.get('input'))
        if spec is None or receipt.get('input') != spec['input']:
            raise ValueError('Successful stages require the exact current Source-plan target')
        return training.stage_routing_origin(origin,receipt)

    def reused_author(self):
        if getattr(self, 'campaign_context', None) is None:
            return None
        study = engine.read(self.runtime['forecast_study'])
        if 'training_proposal_policy' in self.runtime and (
                'training_stage_attachment' in study or study.get('campaign_origin') is not None
                and engine.read(study['campaign_origin']).get('author_stage_reuse') is not None):
            raise ValueError('New whole-panel proposal cannot reuse old Controller/Author/Review stages')
        if study.get('campaign_origin') is None:
            return None
        origin = self._reuse_origin(study)
        bundle = origin.get('author_stage_reuse')
        training_reuse = 'training_stage_attachment' in study or 'proposal_prefix_reuse' in study
        if self._training_scope() is not None and bundle is not None and not training_reuse:
            raise ValueError('Training research requires genuine new Controller and Author')
        if bundle is not None:
            resumed = engine.read(study['campaign_resume'])
            if (bundle.get('mode') != 'review_existing_candidate_v1'
                    or not training_reuse and resumed.get('reuse_mode') != bundle['mode']
                    or len(self.runtime['companies']) != 1):
                raise ValueError('Admitted one-round explicit successful Author reuse required')
        return bundle

    def controller(self, packet, slot):
        if 'clean_slate_policy' in getattr(self,'runtime',{}):
            from earnings_population_clean_slate import controller
            return controller(self,packet,slot)
        self.current = packet['company_id']
        scope = self._training_scope()
        if scope is not None:
            from earnings_population_training25 import admit
            admit(scope, self.current)
        task = self._proposal_task(scope=scope)
        state = packet['population']
        self.role_versions = {ident: state['versions'][ident] for ident in [state['stable_id'], *state['explorers']]}
        stable = state['versions'][state['stable_id']]
        from earnings_population_public_predictions import runtime_policy
        policy = runtime_policy(self.runtime) if hasattr(self, 'runtime') else None
        feedback = public_feedback(packet['feedback'], state['versions'], policy=policy,
            **({} if scope is None else {'training_scope': scope}))
        self.prior_feedback = feedback
        self.campaign_context = None
        if hasattr(self, 'runtime'):
            from earnings_population_campaign_context import prepare
            self.campaign_context = prepare(self.runtime, packet, feedback)
        self._proposal_context(task)
        if self.campaign_context is not None:
            self.reference_context_binding = engine.save(
                self.native_root/(Path(slot).name+'-reference-context.json'),
                self.campaign_context['research_context'])
        continuation = engine.read(self.runtime['forecast_study']).get('continuation') if hasattr(self, 'runtime') else None
        brief = None if continuation is None else engine.read(continuation)
        assignment = None if brief is None else brief.get('repair')
        if self.campaign_context is not None:
            assignment = self.campaign_context.get('repair_assignment', assignment)
        assigned = assignment is not None and packet['round_index'] == 1
        if scope is not None and assigned:
            raise ValueError('Training research cannot inherit a forced parser repair')
        self.repair_company = feedback['company_id'] if assigned else None
        case = self.case(stable, slot)
        role = self.role('controller', PopulationController, case, slot)
        active = [state['stable_id'], *state['explorers']]
        if task is not None:
            active = [ident for ident in active if ident not in task['archive_only_version_ids']]
        prompt = dict(company_id=self.current, questions=case['state_api'].tools.files['questions.md'],
            feedback=feedback, feedback_sha256=packet['parent_feedback_sha256'],
            feedback_binding=packet['feedback'], stable_id=state['stable_id'], active_versions=active,
            explorers=state['explorers'], current_programs=program_references(role.broker.current_sources()),
            explorer_programs=role.broker.references(), available_traces=role.broker.available_traces())
        if assigned:
            prompt['repair_assignment'] = deepcopy(assignment)
            prompt['company_id'] = feedback['company_id']
            prompt['validation_company_id'] = self.current
            prompt['scope'] = 'Repair only on prior-company public data; validation-company questions/files remain unavailable to Controller/Author/review until frozen forecasts.'
            if self.campaign_context is not None:
                prompt['scope'] = 'One explicit R repair on the exposed fixed development company; fresh matched actual-parent comparison, not new-company validation. Diagnose exact real failure snippets and preserve useful parent behavior.'
        if self.campaign_context is not None:
            from earnings_population_campaign_context import controller_view
            from earnings_population_runtime import AFTER04_PLAN
            plan = self.runtime.get('sources', {}).get(AFTER04_PLAN)
            diagnosis = None if plan is None else engine.read(plan)['delivery_diagnosis']
            prompt.update(campaign=self.campaign_context['campaign'],
                research_context=controller_view(self.campaign_context['research_context'],
                                                 delivery_diagnosis=diagnosis),
                original_R_evidence_abi=self.campaign_context['original_R_evidence_abi'],
                scope=packet['scope'])
            inherited_origin = engine.read(self.campaign_context['origin'])
            if inherited_origin.get('delivery_lessons') is not None:
                prompt['prior_delivery_lessons'] = deepcopy(inherited_origin['delivery_lessons'])
        if task is not None:
            prompt.update(proposal_task=deepcopy(task), active_versions=active,
                research_objective=self.campaign_context['research_context']['human_task'],
                scope='Whole25 method proposal; current-company evidence is smoke only. No full-panel score or adoption.')
        if hasattr(self, 'runtime') and scope is None:
            from earnings_population_controller_delivery import route
            imported = route(self.runtime, self.campaign_context, prompt, packet, slot)
            if imported is not None:
                return imported
        reuse = self.reused_author()
        if reuse is not None:
            if packet['round_index'] != 1 or Path(slot).name != 'controller-01':
                raise ValueError('Controller reuse is first-round-only, not automatic replay')
            chosen = engine.read(reuse['decision'])
            parent = chosen['parent_pair_sha256']
            if parent not in active or reuse['candidate']['id'] in state['versions']:
                raise ValueError('Reused selection must preserve active parent and unadopted candidate')
            chosen['feedback_sha256'] = packet['parent_feedback_sha256']
            Path(slot).mkdir(parents=True, exist_ok=False)
            routed = engine.save(Path(slot)/'population-decision.json', chosen)
            engine.save(Path(slot)/'controller-stage-reuse.json', dict(
                schema='earnings_population_Controller_stage_reuse_v1', mode=reuse['mode'],
                routing_author='trusted_recovery_adapter', new_model_called=False,
                original_decision=reuse['decision'], decision=routed,
                packet=engine.pin(Path(slot).parent.parent/'packet-01.json'),
                source_attempt=reuse['failed_attempt'], research_context=prompt.get('research_context')))
            return routed
        original = role.propose(prompt, slot)
        decoded = engine.read(engine.pin(Path(slot)/'decision.json'))
        if decoded['original'] != original:
            raise ValueError('Controller projection lost its actual response')
        if task is not None and decoded['decision']['parent_pair_sha256'] not in active:
            raise ValueError('Archive-only version cannot be the new proposal parent')
        return engine.save(Path(slot)/'population-decision.json', decoded['decision'])

    def author(self, chosen, state, slot):
        scope = self._training_scope()
        task = self._proposal_task(scope=scope)
        if task is not None:
            self._proposal_context(task)
            if chosen['parent_pair_sha256'] in task['archive_only_version_ids']:
                raise ValueError('Archive-only version cannot be the new Author parent')
        self.role_versions = {ident: state['versions'][ident] for ident in [state['stable_id'], *state['explorers']]}
        parent = state['versions'][chosen['parent_pair_sha256']]
        selected = scientific(chosen)
        campaign = getattr(self, 'campaign_context', None)
        reuse = self.reused_author()
        base = (None if campaign is None or reuse is not None else implementation_base(selected, parent,
            campaign['feedback_binding'], campaign['prior_candidate']))
        case = self.case(parent, slot)
        if hasattr(self, 'prior_feedback'):
            references = {axis: {'sha256': parent[axis]['sha256'],
                'read_tool': 'read_population_program', 'arguments': {
                    'version_id': parent['id'], 'axis': axis, 'offset': 0, 'characters': 4000}}
                for axis in ('R', 'H')}
            if campaign is not None:
                references = program_references({axis: checked(parent[axis]).decode() for axis in ('R', 'H')})
            context = {
                'schema': 'earnings_population_author_context_v1', 'parent_version_id': parent['id'],
                'parent_programs': references, 'feedback': deepcopy(self.prior_feedback),
                'feedback_sha256': chosen['feedback_sha256'],
                'task': 'Implement the Controller decision. Diagnose the verified prior program failure using its exact source and read_prior_file for original prior-company tables. Reported counts are not independent correctness. Preserve scorer/data/model/budget; no forced adoption or gain.'}
            if campaign is not None:
                context.update(feedback_binding=campaign['feedback_binding'],
                    campaign=campaign['campaign'], prior_candidate=campaign['prior_candidate'],
                    original_R_evidence_abi=campaign['original_R_evidence_abi'],
                    failure_evidence_context=deepcopy(campaign.get('failure_evidence_context')),
                    evidence_abi_guidance=campaign['research_context']['verification'])
                if base is not None:
                    context.update(implementation_base=deepcopy(base), implementation_base_decision=deepcopy(selected))
                delivery = campaign['research_context']['observations'].get('prior_delivery_failure')
                if delivery is not None:
                    context['prior_delivery_failure'] = deepcopy(delivery)
                if campaign.get('repair_assignment') is not None:
                    context['task'] += (' This human-assigned repair must be narrow and justified by the real failed excerpts. '
                        'Preserve working parent behavior; inspect real date/unit/value context. Avoid a wholesale parser rewrite, '
                        'hardcoded target answers, manufactured source metadata or an unavailable extra R evidence phase. '
                        'Report the specific changed functions and test the actual acquisition path, not only constructed complete excerpts.')
                if scope is not None:
                    if campaign.get('training_scope') != scope or campaign.get('repair_assignment') is not None:
                        raise ValueError('Author training context differs from actual admitted scope')
                    context.update(**{key: deepcopy(campaign[key]) for key in
                        ('training_comparator', 'training_state')})
                    context['task'] = ('Implement the actual Controller hypothesis to improve transferable financial '
                        'research across training25. Literature, algorithms and tools remain available under the '
                        'existing one-axis/source/feedback limits. Preserve useful actual-parent behavior, '
                        'use old failures as evidence rather than a mandatory parser repair, and test available '
                        'period/unit/source evidence. No answer hardcoding, forced adoption or promised score gain.')
                if task is not None:
                    context.update(proposal_task=deepcopy(task),task=campaign['research_context']['human_task'])
            if 'clean_slate_policy' in getattr(self,'runtime',{}):
                from earnings_population_clean_slate import read_task, research_task, second_round, POLICY
                clean_task, _ = read_task(self.runtime)
                context.update(task=research_task(self.runtime),training_comparator=engine.read(clean_task['feedback']),
                    feedback_binding=clean_task['feedback'],clean_slate_policy=POLICY,
                    scaffold_semantics=('Selected actual complete25 code parent R/H, not necessarily prediction incumbent; full pool/genealogy and distinct feedback sources retained in the round origin.'
                        if second_round(self.runtime) else 'Unscored empty code adapter only; actual comparator is saved plain Round0.'))
            self.author_context = engine.save(self.native_root/(Path(slot).name+'-context.json'), context)
        if reuse is not None:
            expected = engine.read(reuse['decision'])
            expected['feedback_sha256'] = chosen['feedback_sha256']
            if chosen != expected or Path(slot).name != 'author-01' or parent['id'] != reuse['candidate']['parent']:
                raise ValueError('Reuse cannot silently change science/parent or re-author')
            selected = reuse['scientific_decision']
            base_option = ({} if reuse.get('implementation_base') is None
                           else {'implementation_base': reuse['implementation_base']})
            authored = assemble(parent[chosen['axis']], selected, engine.read(reuse['raw_patch_response']), **base_option)
            parsed = candidate(authored, program(checked(parent[chosen['axis']]), chosen['axis']), selected)
            child = deepcopy(reuse['candidate'])
            if (checked(child[chosen['axis']]) != authored['source_text'].encode()
                    or checked(reuse['tests']) != authored['test_text'].encode()
                    or child['H'] != parent['H']):
                raise ValueError('Exact reused assembled source/tests/unchanged H required')
            Path(slot).mkdir(parents=True, exist_ok=False)
            receipt = engine.save(Path(slot)/'author-stage-reuse.json', dict(
                schema='earnings_population_Author_stage_reuse_v1', mode=reuse['mode'],
                new_model_called=False, source_attempt=reuse['failed_attempt'], candidate_id=child['id'],
                original_decision=reuse['decision'], scientific_decision_sha256=digest(selected),
                raw_patch_response=reuse['raw_patch_response'], assembly=reuse['assembly'],
                source=reuse['source'], tests=reuse['tests'],
                **{k: deepcopy(reuse[k]) for k in ('implementation_base','original_controller_import') if k in reuse},
                attribution=('Original10 model Delta/tests; no new model call or source authorship.'
                    if Path(reuse['failed_attempt']['path']).parent.name == 'edgar-population-20261016-10' else
                    Path(reuse['failed_attempt']['path']).parent.name+
                    ' original model Delta/tests; no new model call or source authorship.')))
            self.authored[child['id']] = dict(parsed=parsed, decision=selected, source=authored['source_text'],
                originals=[receipt,reuse['raw_patch_response'],reuse['assembly'],reuse['source'],reuse['tests']],
                review_index_inputs=dict(parent_binding=reuse['parent_source'], chosen=selected,
                    original_binding=reuse['raw_patch_response'], source_binding=reuse['source'],
                    version_id=child['id'], assembly_binding=reuse['assembly']),
                reused_stage=receipt)
            return child
        role = self.role('author', DeltaAuthor, case, slot)
        before = program(checked(parent[chosen['axis']]), chosen['axis'])
        base_option = {} if base is None else {'implementation_base': base}
        original = role.author(selected, before, slot, parent_binding=parent[chosen['axis']], **base_option)
        raw = engine.read(original)
        authored = assemble(parent[chosen['axis']], selected, raw, **base_option)
        parsed = candidate(authored, before, selected)
        projection = engine.save(Path(slot)/'scientific-decision-projection.json', {
            'population_decision': chosen, 'scientific_decision': selected,
            'scientific_decision_sha256': digest(selected),
            'scope': 'Explicitly removed retirement field only; no parent or feedback rewrite'})
        for name, value in [('candidate.py', authored['source_text']), ('cases.py', authored['test_text'])]:
            save_bytes(Path(slot)/name, value.encode())
        source_binding, test_binding = (engine.pin(Path(slot)/name) for name in ('candidate.py', 'cases.py'))
        assembly = engine.save(Path(slot)/'delta-assembly.json', {
            'schema': 'earnings_population_delta_assembly_v1' if base is None else 'earnings_population_delta_assembly_v2', 'axis': chosen['axis'],
            'parent_version_id': parent['id'], 'parent_source': deepcopy(parent[chosen['axis']]),
            'raw_patch_response': original, 'scientific_decision': projection,
            'scientific_decision_sha256': digest(selected), 'assembled_business_sha256': digest(authored),
            'assembly_source': engine.source_of(assemble), 'source': source_binding, 'tests': test_binding,
            'model_authorship': ('Delta edits and test_text only; unchanged parent code is mechanically inherited.' if base is None else
                                'Delta edits and test_text only; unchanged rejected implementation-base code is mechanically inherited, not newly authored or adopted.'),
            'host_candidate_execution': False,
            **({} if base is None else dict(implementation_base=deepcopy(base),
                comparison_parent_source=deepcopy(parent[chosen['axis']]),
                comparison_parent_version_id=parent['id'],
                genetic_scope='Delta edits/tests are newly authored; unchanged rejected implementation-base bytes are inherited. Child parent remains active comparison parent; a paired trial measures accumulated repairs, not just latest edits.'))})
        sources = {axis: parent[axis] for axis in ('R', 'H')}
        sources[chosen['axis']] = source_binding
        child = describe(**sources, parent=parent['id'], axis=chosen['axis'],
            method=chosen['hypothesis'], author='model:DeltaAuthor', evidence=[original, projection, assembly])
        if child['id'] == parent['id']:
            raise ValueError('No source change; no false candidate or automatic retry')
        if task is not None and child['id'] in state['versions']:
            raise ValueError('New Author proposal must not substitute any archived existing version')
        self.authored[child['id']] = dict(parsed=parsed, decision=selected,
            source=authored['source_text'], originals=[original, projection, assembly, source_binding, test_binding],
            review_index_inputs=dict(parent_binding=parent[chosen['axis']], chosen=selected,
                original_binding=original, source_binding=source_binding, version_id=child['id'], assembly_binding=assembly))
        return child

    def matched_parent_probes(self, parent, child, case, probes, slot):
        """Fresh R-only comparisons, not parent adoption or a financial score."""
        rows, evidence = [], []
        if len(probes) < 2:
            raise ValueError('Both original child stages required for matched parent comparison')
        source = checked(parent['R']).decode()
        for stage, child_binding in zip(('forecast', 'controller'), probes[:2]):
            child_probe = engine.read(child_binding)
            payload = deepcopy(child_probe['input'])
            tools = FilingTools(case['company'])
            if (child_probe.get('company_id') != case['company']['cik']
                    or child_probe['diagnostics']['source_sha256'] != child['R']['sha256']
                    or payload.get('stage') != stage or payload.get('records') != []
                    or payload.get('questions') != tools.files['questions.md']
                    or payload.get('filing_index') != tools.files['filing_index.tsv']):
                raise ValueError('Parent comparison requires exact original child initial input/data')
            run = researcher.run(self.runner, source, payload, tools)
            value = researcher.verify(run, source, payload, case['company'])
            diagnostics = project(value, source_sha256=parent['R']['sha256'],
                execution_sha256=run['receipt']['sha256'],
                target_ids=re.findall(r'^### (T[0-9]+) \|', payload['questions'], re.M))
            public = review_probe_output(value, maximum_characters=3000)
            bound = engine.save(self.native_root/(Path(slot).name+'-parent-'+stage+'-comparison.json'), {
                'schema': 'earnings_population_matched_parent_probe_v1',
                'parent_version_id': parent['id'], 'parent_programs': {axis: parent[axis] for axis in ('R', 'H')},
                'child_version_id': child['id'], 'company_id': case['company']['cik'],
                'matched_child_probe': child_binding, 'initial_input_sha256': digest(payload),
                'input': payload, 'execution': run, 'diagnostics': diagnostics,
                'verified_public_R_output': public,
                'scope': 'Fresh selected active-parent R, same initial public input/data/runner; query lists/results may differ. No H execution, score, adoption or financial-correctness certificate.'})
            evidence.append(bound)
            rows.append(dict(stage=stage, completed=True, receipt=bound,
                parent_version_id=parent['id'], matched_child_probe=deepcopy(child_binding),
                initial_input_sha256=digest(payload), company_id=case['company']['cik'],
                diagnostics=diagnostics, verified_public_R_output=public))
        if len(rows) != 2:
            raise ValueError('Both original child stages required for matched parent comparison')
        return rows, evidence

    def review(self, child, state, slot):
        task = self._proposal_task()
        prefix=None
        if 'proposal_prefix_reuse' in getattr(self,'runtime',{}):
            from earnings_population_runtime import _proposal_prefix_metadata
            prefix=_proposal_prefix_metadata(self.runtime,engine.read(self.runtime['forecast_study']),
                company_id=self.runtime['companies'][0])
        if task is not None and (child.get('parent') in task['archive_only_version_ids']
                or child['id'] in state['versions']):
            raise ValueError('Review requires the fresh proposal and actual permitted implementation parent')
        authored = self.authored[child['id']]
        if task is not None and authored.get('reused_stage') is not None and prefix is None:
            raise ValueError('Fresh proposal Review cannot reuse an old Author receipt')
        parent = None
        if getattr(self, 'campaign_context', None) is not None:
            parent_id = child.get('parent')
            parent = state['versions'].get(parent_id)
            other = 'H' if child['axis'] == 'R' else 'R'
            if (parent_id not in [state['stable_id'], *state['explorers']] or parent is None
                    or parent.get('id') != parent_id or child[other] != parent[other]
                    or parent_id != digest({axis: parent[axis]['sha256'] for axis in ('R', 'H')})):
                raise ValueError('Review comparison requires exact selected active parent/other axis')
            for axis in ('R', 'H'):
                checked(parent[axis])
        self.role_versions = {child['id']: child, **({} if parent is None else {parent['id']: parent})}
        frontier_test=None
        if 'clean_slate_policy' in getattr(self,'runtime',{}) and self.runtime.get('clean_learning_round',0)>=9:
            from earnings_population_clean_slate import round2_origin
            from earnings_population_coevolution import declared_test, selected_parent
            origin=round2_origin(self.runtime);frontier_parent=selected_parent(state,origin)
            if child['parent']!=frontier_parent['id']:raise ValueError('Review replaced the declared frontier parent')
            self.role_versions[frontier_parent['id']]=frontier_parent
            frontier_test=declared_test(origin)
        case = self.case(child, slot)
        reuse = self.reused_author() if hasattr(self, 'runtime') else None
        if reuse is not None:
            study = engine.read(self.runtime['forecast_study'])
            reviewed = self._reuse_origin(study).get('review_stage_reuse')
            if reviewed is not None:
                from earnings_population_forecast_failure import reuse_receipt
                receipt = reuse_receipt(reviewed, reuse, child, slot)
                if Path(slot).exists() and any(Path(slot).iterdir()):
                    raise ValueError('Accepted Review reuse requires a fresh empty role slot')
                Path(slot).mkdir(parents=True, exist_ok=True)
                marker = engine.save(Path(slot)/'review-stage-reuse.json', receipt)
                return dict(accepted_for_exploration=True, evidence=[marker, *deepcopy(reviewed['evidence'])])
        results = run_cases(self.runner, authored['source'], authored['parsed']['cases'])
        evidence = engine.save(self.native_root/(Path(slot).name+'-cases.json'), {
            'candidate_id': child['id'], 'results': results,
            'scope': ('Human-authorized acquisition expectation repair plus original model examples in Docker; not financial proof'
                if authored.get('human_interface_repair') is not None else
                'Actual model-authored test cases in Docker, not independent financial proof')})
        if not all(row['passed'] for row in results):
            return self.review_outcome(child, slot, False, 'MODEL_CASES_FAILED; inspect preserved case evidence',
                                       [evidence, *authored['originals']])
        probes = []
        if child['axis'] == 'R':
            for stage in ('forecast', 'controller'):
                payload = dict(stage=stage, questions=case['state_api'].tools.files['questions.md'],
                    filing_index=case['state_api'].tools.files['filing_index.tsv'], records=[])
                if stage == 'controller':
                    payload.update(feedback={'scope': 'Cold admission probe; no new score'},
                                   research_objective=('Improve original financial forecasting on this company' if task is None
                                       else task['primary_task']+' Current-company integration smoke only, not whole25 validation.'))
                run = researcher.run(self.runner, authored['source'], payload, case['state_api'].tools)
                value = researcher.verify(run, authored['source'], payload, case['company'])
                diagnostics = project(value, source_sha256=child['R']['sha256'],
                    execution_sha256=run['receipt']['sha256'],
                    target_ids=re.findall(r'^### (T[0-9]+) \|', payload['questions'], re.M))
                probe = {
                    'input': payload, 'execution': run, 'diagnostics': diagnostics,
                    'scope': 'Real public-data empty-state interface probe, not financial correctness'}
                if getattr(self, 'campaign_context', None) is not None or authored.get('human_interface_repair') is not None:
                    probe['company_id'] = case['company']['cik']
                    probe['verified_public_R_output'] = review_probe_output(value)
                probes.append(engine.save(self.native_root/(Path(slot).name+'-'+stage+'-probe.json'), probe))
            feedback = getattr(self, 'prior_feedback', {})
            if 'company_id' in feedback and feedback['company_id'] != case['company']['cik']:
                scope = self._training_scope()
                if scope is not None:
                    from earnings_population_training25 import admit
                    admit(scope, feedback['company_id'])
                prior = resident(feedback['company_id'])['company']
                tools = FilingTools(prior)
                payload = dict(stage='forecast', questions=tools.files['questions.md'],
                    filing_index=tools.files['filing_index.tsv'], records=[])
                run = researcher.run(self.runner, authored['source'], payload, tools)
                value = researcher.verify(run, authored['source'], payload, prior)
                diagnostics = project(value, source_sha256=child['R']['sha256'],
                    execution_sha256=run['receipt']['sha256'],
                    target_ids=re.findall(r'^### (T[0-9]+) \|', payload['questions'], re.M))
                probes.append(engine.save(self.native_root/(Path(slot).name+'-prior-probe.json'), {
                    'company_id': prior['cik'], 'input': payload, 'execution': run,
                    'diagnostics': diagnostics, 'scope': 'Original previous-company repair test; no scorer or hidden labels'}))
        navigation = {}
        if authored.get('human_interface_repair') is not None:
            navigation['human_authorized_minimal_interface_repair']=deepcopy(authored['human_interface_repair'])
        parent_probes = []
        if parent is not None:
            matched, parent_probes = (self.matched_parent_probes(parent, child, case, probes, slot)
                                     if child['axis'] == 'R' else ([], []))
            navigation.update(matched_active_parent_empty_state_probes=matched,
                active_parent_comparison=dict(parent_version_id=parent['id'],
                    parent_programs={axis: deepcopy(parent[axis]) for axis in ('R', 'H')},
                    child_version_id=child['id'], changed_axis=child['axis'],
                    status='matched_R_probes_completed' if matched else 'not_run_H_candidate',
                    scope='R advice/execution comparison only, not H behavior or financial truth; original independent Review and forecast admission remain unchanged.'))
        role = self.role('review', PopulationReviewer, case, slot)
        if authored.get('review_index_inputs') is not None:
            from earnings_population_delta_author import review_index
            navigation['candidate_change_index'] = review_index(**authored['review_index_inputs'])
        if authored.get('reused_stage') is not None:
            navigation['successful_Author_stage_reuse'] = engine.read(authored['reused_stage'])
            if prefix is not None:
                navigation['prior_Review_delivery_failure']=dict(failed_attempt=prefix['failed_attempt'],
                    authority=prefix['authority'],stage='source_review',error_type='BudgetStop',
                    observed_input_tokens=[32976,33290],prior_input_limit=32000,
                    review_assessment=prefix['review_assessment'],
                    completed_Review_generations=prefix['original_completed_generations']['review'],score_state='unscored',
                    scope='Closed37 delivery failure, no scientific verdict or prediction. Original code/tests imported; assess current source and matched probes independently.')
            else:
                recovery = self.campaign_context['research_context']['observations']['prior_delivery_failure']
                navigation['prior_Review_delivery_failure'] = {key: deepcopy(recovery[key]) for key in (
                    'failed_attempt','audit','stage','error_type','observed_input_tokens','prior_input_limit',
                    'review_assessment','completed_Review_generations','score_state','scope')}
                navigation['known_public_tradeoff'] = 'Prior public cold audit reported improved T005 evidence but T002 acquisition regression. Inspect the actual current probes and source; this is not acceptance or a financial-correctness certificate.'
        review_prompt = dict(candidate_id=child['id'], decision=authored['decision'], **navigation,
            company_id=case['company']['cik'], tests={'passed': len(results), 'failed': 0},
            **({'human_repair_acceptance': 'Before a forecast trial, the real empty-state original-data tests must demonstrate usable source-backed period/unit/value evidence for the claimed repair. Inspect the exact saved probe output, not only synthetic cases or program-reported counts. Reject unresolved real extraction failure; no score gain is required before the trial.'}
                if getattr(self, 'campaign_context', None) is not None
                    and self.campaign_context.get('repair_assignment') is not None else {}),
            **({'campaign_research_context': dict(
                feedback_binding=self.campaign_context['feedback_binding'],
                original_R_evidence_abi=self.campaign_context['original_R_evidence_abi'],
                cold_probe_company_id=case['company']['cik'],
                prior_feedback_company_id=self.prior_feedback['company_id'],
                scope='R cold probes below already use the labeled development company. If it equals the feedback company, an extra duplicate prior-company probe is unnecessary; H candidates do not create R cold probes.')}
                if getattr(self, 'campaign_context', None) is not None else {}),
            original_public_empty_state_probes=[{'stage': stage, 'completed': True, 'receipt': bound,
                                                **({'company_id': case['company']['cik']}
                                                   if getattr(self, 'campaign_context', None) is not None else {}),
                                                **({'verified_public_R_output': engine.read(bound)['verified_public_R_output']}
                                                   if 'verified_public_R_output' in engine.read(bound) else {}),
                                                'diagnostics': engine.read(bound)['diagnostics']}
                for stage, bound in zip(('forecast', 'controller'), probes)],
            original_questions=case['state_api'].tools.files['questions.md'],
            prior_company_repair_probe=None if len(probes) < 3 else {
                'receipt': probes[2], 'company_id': engine.read(probes[2])['company_id'],
                'diagnostics': engine.read(probes[2])['diagnostics'],
                'original_questions': engine.read(probes[2])['input']['questions'],
                'previous_feedback': getattr(self, 'prior_feedback', {})},
            repair_objective=None if getattr(self, 'repair_company', None) is None else {
                'task': 'Assess whether this implementation addresses the actual previous-company parsing failure. Completed execution and passing Author examples alone do not demonstrate repair. A parser still producing zero extracted cells and all targets incomplete has not demonstrated the requested extraction benefit; inspect exact source/public tables when needed.',
                'previous_feedback': self.prior_feedback},
            current_programs=role.broker.references())
        if task is not None:
            review_prompt.update(proposal_task=deepcopy(task),research_objective=task['primary_task'],
                evaluation_scope='Current-company cases/cold probes are integration and safety smoke only; accepted Review is not full25 suitability, predictive gain or adoption. The same fresh code must be frozen for all25 before another mutation.')
        if frontier_test is not None:
            review_prompt.update(declared_frontier_test=frontier_test,
                frontier_parent_programs={axis:deepcopy(frontier_parent[axis]) for axis in ('R','H')},
                frontier_scope='Verify this actual-parent hypothesis against source/test/public evidence. Criteria are not assumed gain. No additional paid role, probe phase or resources; same candidate must complete25 before selection.')
        from earnings_population_review_context import share_probe_prefixes
        original = role.review(share_probe_prefixes(review_prompt), slot)
        reviewed = engine.read(engine.pin(Path(slot)/'review.json'))
        if reviewed['original'] != original:
            raise ValueError('Exploration review differs from original response')
        return self.review_outcome(child, slot, reviewed['review']['accepted_for_exploration'],
            reviewed['review']['rationale'], [original, evidence, *probes, *parent_probes, *authored['originals']])

    def review_outcome(self, child, slot, accepted, rationale, evidence):
        public = engine.save(self.native_root/(Path(slot).name+'-outcome.json'), {
            'schema': 'earnings_population_exploration_review_v1', 'candidate_id': child['id'],
            'accepted_for_exploration': accepted, 'rationale': rationale})
        return dict(accepted_for_exploration=accepted, evidence=[public, *evidence])

    def forecast(self, version, company_id, slot):
        if company_id != self.current:
            raise ValueError('Forecast company differs from actual Controller round')
        case = self.case(version, slot)
        context, dependencies = self.contexts['forecast']
        def claim(case, work_id):
            self.pending.append((case, work_id))
        result = execute(case, version, slot, runner=self.runner, context=context,
            study=self.runtime['forecast_study'], clock=self.clock,
            transport_policy=self.transport_policy, before_claim=claim, **dependencies)
        self.pending.pop()
        self.traces[Path(slot).name] = str(slot)
        return result
