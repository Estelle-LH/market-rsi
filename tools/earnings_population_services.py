"""Source-bound real roles; borrow the existing sole runtime owner and budget.

No keys, alternate scorer, mutable source adoption or candidate host execution.
Case roots are owned temporary Native execution forks, not stable promotions.
"""
from copy import deepcopy
from pathlib import Path
import re

from earnings_capacity_adapter import author_payload
from earnings_entry import checked
from earnings_http import save_bytes
from earnings_open_broker import program_references
from earnings_open_code import DockerRunner
from earnings_open_literature import LiteratureBroker
from earnings_open_program import candidate, program, run_cases
from earnings_open_roles import OpenAuthor
import earnings_open_researcher as researcher
from earnings_population import version as describe
from earnings_population_case import prepare_case
from earnings_population_execution import execute
from earnings_population_roles import PopulationController, PopulationReviewer, scientific
from earnings_population_broker import PopulationBroker, public_feedback
from earnings_population_tasks import resident
from earnings_population_diagnostics import project
from edgar_forecast_tools import FilingTools
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class Services:
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

    def case(self, version, slot):
        research = getattr(self, 'repair_company', None)
        company_id = research if research is not None and not Path(slot).name.startswith('forecast-') else self.current
        return prepare_case(self.native_root/Path(slot).name, resident(company_id), version,
            source_commit=self.runtime['source_commit'], authority_binding=self.binding,
            python_binding=self.python, start_utc=self.start_utc,
            deadline_utc=self.runtime['deadline_utc'])

    def broker(self, case, slot):
        feedback = getattr(self, 'prior_feedback', {})
        previous = resident(feedback['company_id'])['company'] if 'company_id' in feedback else None
        return PopulationBroker(self.native_root/(Path(slot).name+'-actions'),
            company=case['company'], capacity=case['capacity'], runner=self.runner,
            literature=self.literature, trace_slots=self.traces, versions=self.role_versions,
            prior_company=previous, population_context_binding=
                getattr(self, 'author_context', None) if Path(slot).name.startswith('author-') else None)

    def role(self, name, kind, case, slot):
        context, dependencies = self.contexts[name]
        return kind(context, broker=self.broker(case, slot), **dependencies,
                    **({'socket_timeout_seconds': 900} if name == 'author' else {}))

    def controller(self, packet, slot):
        self.current = packet['company_id']
        state = packet['population']
        self.role_versions = {ident: state['versions'][ident] for ident in [state['stable_id'], *state['explorers']]}
        stable = state['versions'][state['stable_id']]
        feedback = public_feedback(packet['feedback'], state['versions'])
        self.prior_feedback = feedback
        continuation = engine.read(self.runtime['forecast_study']).get('continuation') if hasattr(self, 'runtime') else None
        brief = None if continuation is None else engine.read(continuation)
        assigned = brief is not None and brief.get('repair') is not None and packet['round_index'] == 1
        self.repair_company = feedback['company_id'] if assigned else None
        case = self.case(stable, slot)
        role = self.role('controller', PopulationController, case, slot)
        active = [state['stable_id'], *state['explorers']]
        prompt = dict(company_id=self.current, questions=case['state_api'].tools.files['questions.md'],
            feedback=feedback, feedback_sha256=packet['parent_feedback_sha256'],
            feedback_binding=packet['feedback'], stable_id=state['stable_id'], active_versions=active,
            explorers=state['explorers'], current_programs=program_references(role.broker.current_sources()),
            explorer_programs=role.broker.references(), available_traces=role.broker.available_traces())
        if assigned:
            prompt['repair_assignment'] = deepcopy(brief['repair'])
            prompt['company_id'] = feedback['company_id']
            prompt['validation_company_id'] = self.current
            prompt['scope'] = 'Repair only on prior-company public data; validation-company questions/files remain unavailable to Controller/Author/review until frozen forecasts.'
        original = role.propose(prompt, slot)
        decoded = engine.read(engine.pin(Path(slot)/'decision.json'))
        if decoded['original'] != original:
            raise ValueError('Controller projection lost its actual response')
        return engine.save(Path(slot)/'population-decision.json', decoded['decision'])

    def author(self, chosen, state, slot):
        self.role_versions = {ident: state['versions'][ident] for ident in [state['stable_id'], *state['explorers']]}
        parent = state['versions'][chosen['parent_pair_sha256']]
        case = self.case(parent, slot)
        if hasattr(self, 'prior_feedback'):
            references = {axis: {'sha256': parent[axis]['sha256'],
                'read_tool': 'read_population_program', 'arguments': {
                    'version_id': parent['id'], 'axis': axis, 'offset': 0, 'characters': 4000}}
                for axis in ('R', 'H')}
            self.author_context = engine.save(self.native_root/(Path(slot).name+'-context.json'), {
                'schema': 'earnings_population_author_context_v1', 'parent_version_id': parent['id'],
                'parent_programs': references, 'feedback': deepcopy(self.prior_feedback),
                'feedback_sha256': chosen['feedback_sha256'],
                'task': 'Implement the Controller decision. Diagnose the verified prior program failure using its exact source and read_prior_file for original prior-company tables. Reported counts are not independent correctness. Preserve scorer/data/model/budget; no forced adoption or gain.'})
        role = self.role('author', OpenAuthor, case, slot)
        selected = scientific(chosen)
        before = program(checked(parent[chosen['axis']]), chosen['axis'])
        original = role.author(selected, before, slot)
        raw = engine.read(original)
        parsed, authored = candidate(raw, before, selected), author_payload(raw)
        projection = engine.save(Path(slot)/'scientific-decision-projection.json', {
            'population_decision': chosen, 'scientific_decision': selected,
            'scientific_decision_sha256': digest(selected),
            'scope': 'Explicitly removed retirement field only; no parent or feedback rewrite'})
        for name, value in [('candidate.py', authored['source_text']), ('cases.py', authored['test_text'])]:
            save_bytes(Path(slot)/name, value.encode())
        sources = {axis: parent[axis] for axis in ('R', 'H')}
        sources[chosen['axis']] = engine.pin(Path(slot)/'candidate.py')
        child = describe(**sources, parent=parent['id'], axis=chosen['axis'],
            method=chosen['hypothesis'], author='model:OpenAuthor', evidence=[original, projection])
        if child['id'] == parent['id']:
            raise ValueError('No source change; no false candidate or automatic retry')
        self.authored[child['id']] = dict(parsed=parsed, decision=selected,
            source=authored['source_text'], originals=[original, projection, engine.pin(Path(slot)/'cases.py')])
        return child

    def review(self, child, state, slot):
        authored = self.authored[child['id']]
        self.role_versions = {child['id']: child}
        case = self.case(child, slot)
        results = run_cases(self.runner, authored['source'], authored['parsed']['cases'])
        evidence = engine.save(self.native_root/(Path(slot).name+'-cases.json'), {
            'candidate_id': child['id'], 'results': results,
            'scope': 'Actual model-authored test cases in Docker, not independent financial proof'})
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
                                   research_objective='Improve original financial forecasting on this company')
                run = researcher.run(self.runner, authored['source'], payload, case['state_api'].tools)
                value = researcher.verify(run, authored['source'], payload, case['company'])
                diagnostics = project(value, source_sha256=child['R']['sha256'],
                    execution_sha256=run['receipt']['sha256'],
                    target_ids=re.findall(r'^### (T[0-9]+) \|', payload['questions'], re.M))
                probes.append(engine.save(self.native_root/(Path(slot).name+'-'+stage+'-probe.json'), {
                    'input': payload, 'execution': run, 'diagnostics': diagnostics,
                    'scope': 'Real public-data empty-state interface probe, not financial correctness'}))
            feedback = getattr(self, 'prior_feedback', {})
            if 'company_id' in feedback and feedback['company_id'] != case['company']['cik']:
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
        role = self.role('review', PopulationReviewer, case, slot)
        original = role.review(dict(candidate_id=child['id'], decision=authored['decision'],
            company_id=case['company']['cik'], tests={'passed': len(results), 'failed': 0},
            original_public_empty_state_probes=[{'stage': stage, 'completed': True, 'receipt': bound,
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
            current_programs=role.broker.references()), slot)
        reviewed = engine.read(engine.pin(Path(slot)/'review.json'))
        if reviewed['original'] != original:
            raise ValueError('Exploration review differs from original response')
        return self.review_outcome(child, slot, reviewed['review']['accepted_for_exploration'],
            reviewed['review']['rationale'], [original, evidence, *probes, *authored['originals']])

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
