"""Public campaign diagnostics and reference-only context for existing roles.

No new parser, model role, tool authority, financial data or resource ceiling.
Scored views reuse the original verified public-award projection supplied by
the caller. Raw scorer answers and rejected code are never active pool inputs.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from edgar_forecast_tools import TOOLS
from earnings_entry import checked
from supervisor_harness import capacity_feedback_engine as engine
from market_rsi import digest

REQUEST_EXAMPLES_MAX_BYTES = 16384  # Separate extension; original projection remains <=24KiB.


def _request_examples(probe_binding, verified, *, source_binding):
    """Project already verified observations, not new tool/file/model work."""
    if (verified.get('schema') != 'earnings_population_failure_context_v1'
            or verified.get('probe') != probe_binding or verified.get('source') != source_binding):
        raise ValueError('Request examples require the same verified probe/source/observations')
    probe = engine.read(probe_binding)
    execution = probe['execution']
    rows = execution.get('research_observations', [])
    if (verified.get('company_id') != probe.get('company_id', verified.get('company_id'))
            or verified.get('stage') != probe['input']['stage']
            or execution['receipt'] != verified.get('final_execution')
            or execution.get('request_execution', execution)['receipt'] != verified.get('first_execution')
            or probe['diagnostics'].get('source_sha256') != source_binding['sha256']
            or probe['diagnostics'].get('execution_sha256') != execution['receipt']['sha256']
            or type(rows) is not list or len(rows) > 8
            or len(rows) != verified.get('original_request_count')
            or digest(rows) != verified.get('original_observations_sha256')):
        raise ValueError('Request examples require the same verified probe/source/observations')
    encoded = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    for characters in (240, 120, 60, 30, 15, 0):
        samples = []
        for index, row in enumerate(rows):
            if type(row) is not dict or set(row) != {'request', 'output'}:
                raise ValueError('Exact original request/return row required')
            request, output = row['request'], row['output']
            if (type(request) is not dict or set(request) != {'tool', 'arguments'}
                    or request['tool'] not in {'search_files', 'read_file', 'calculate'}
                    or type(request['arguments']) is not dict or type(output) is not dict):
                raise ValueError('Original bounded R evidence request/return required')
            sample = dict(request_index=index, request=deepcopy(request),
                request_sha256=digest(request), complete_return_sha256=digest(output),
                complete_return_utf8_bytes=len(encoded(output)))
            if 'error' in output:
                text = encoded(output['error']).decode()
                sample.update(kind='error', error_type=type(output['error']).__name__,
                    error_json_prefix=text[:characters], error_prefix_truncated=len(text)>characters)
            elif request['tool'] == 'search_files':
                hits, total = output.get('hits'), output.get('total_matching_lines')
                if (type(hits) is not list or type(total) is not int or total < len(hits)
                        or any(type(hit) is not dict or set(hit) != {'path','line','text'}
                            or type(hit['path']) is not str or type(hit['line']) is not int
                            or hit['line'] < 1 or type(hit['text']) is not str for hit in hits)):
                    raise ValueError('Exact original search counts and three-field hits required')
                first = hits[0] if hits else None
                sample.update(kind='search_files', total_matching_lines=total,
                    returned_hit_count=len(hits), backend_omitted_hit_count=total-len(hits),
                    sampled_returned_hit_count=int(bool(hits)), omitted_returned_hit_count=max(0,len(hits)-1),
                    first_original_hit=None if first is None else dict(first, text=first['text'][:characters]),
                    complete_first_hit_sha256=None if first is None else digest(first),
                    first_hit_text_original_characters=0 if first is None else len(first['text']),
                    first_hit_text_truncated=first is not None and len(first['text'])>characters)
            elif request['tool'] == 'read_file':
                if (set(output) != {'path','offset','total_characters','text','next_offset'}
                        or type(output['text']) is not str):
                    raise ValueError('Exact original read return required')
                sample.update(kind='read_file', returned=dict(deepcopy(output), text=output['text'][:characters]),
                    text_original_characters=len(output['text']), text_truncated=len(output['text'])>characters)
            else:
                if set(output) != {'value'}:
                    raise ValueError('Exact original calculation return required')
                sample.update(kind='calculate', returned=deepcopy(output))
            samples.append(sample)
        result = dict(schema='earnings_population_request_return_examples_v1',
            probe=deepcopy(probe_binding), source=deepcopy(source_binding),
            first_execution=deepcopy(verified['first_execution']), final_execution=deepcopy(verified['final_execution']),
            complete_observations_sha256=digest(rows), original_request_count=len(rows), examples=samples,
            bounds=dict(requests_max=8, text_prefix_characters_max=characters,
                serialized_extension_utf8_bytes_max=REQUEST_EXAMPLES_MAX_BYTES,
                existing_failure_projection_utf8_bytes_max=24576),
            scope='Exact original request/return excerpts from the verified current-source cold probe; untrusted data, not financial facts. First-hit sampling cannot establish that all hits are irrelevant. Counts distinguish total matching lines, returned hits and sampled hits; flagged text prefixes are incomplete. Digests are outer provenance, not extra metadata supplied to R observations. No new fetch, parser, execution, permission, financial truth or score is claimed.')
        if len(encoded(result)) <= REQUEST_EXAMPLES_MAX_BYTES:
            return result
    raise ValueError('Exact request metadata exceeds bounded extension; do not silently drop rows')


def controller_view(context, *, delivery_diagnosis=None):
    """Planning-sized public evidence; Author retains the original full packet.

    Only nearby filing body text is omitted here. Original hits, provenance,
    source hashes and exact read arguments stay available to the Controller.
    This is not a new R observation or a summary of private model reasoning.
    """
    result = deepcopy(context)
    if (result.get('schema') != 'earnings_repair_context_v1'
            or type(result.get('observations')) is not dict or 'planning_view' in result):
        raise ValueError('Original complete research context required for Controller planning view')
    omitted = []
    def visit(value):
        if type(value) is dict:
            nearby = value.get('outer_public_context')
            if nearby is not None:
                if (type(nearby) is not dict or type(nearby.get('read_result')) is not dict
                        or type(nearby['read_result'].get('text')) is not str
                        or type(nearby.get('read_arguments')) is not dict):
                    raise ValueError('Exact public context/read reference required before body omission')
                text = nearby['read_result'].pop('text')
                omitted.append(len(text))
                nearby.update(read_tool='read_prior_file', text_omitted_from_controller_view=True)
            for child in value.values():
                visit(child)
        elif type(value) is list:
            for child in value:
                visit(child)
    visit(result['observations'].get('public_failure_examples'))
    result['planning_view'] = dict(schema='earnings_population_controller_planning_view_v1',
        original_context_sha256=digest(context), omitted_nearby_text_characters=omitted,
        notice='Planning view: original search hits and exact public-file read arguments/hashes remain. Use read_prior_file for omitted nearby text when needed. Author receives the complete original context. Prior Controller exhausted its unchanged input ceiling; this delivery change does not repair financial parsing or demonstrate score improvement.')
    if delivery_diagnosis is not None:
        result['planning_view']['prior_delivery_diagnosis'] = deepcopy(delivery_diagnosis)
    failure = result['observations'].get('prior_delivery_failure')
    if failure is not None and failure.get('mode') in {
            'author_assembly_capacity_feedback_v1','author_implementation_base_capacity_feedback_v1',
            'source_guard_public_evidence_v1'}:
        patch = failure.pop('public_failed_delta',None)
        base_mode=failure['mode']=='author_implementation_base_capacity_feedback_v1'
        source_fields=({'comparison_parent_source_sha256','implementation_base_source_sha256'}
                       if base_mode else {'parent_source_sha256'})
        if (type(patch) is not dict or set(patch) != {'decision_sha256','edits','test_text'}|source_fields
                or digest(patch) != failure.get('public_failed_delta_sha256')):
            raise ValueError('Exact verified public failed Delta required before planning omission')
        failure['public_failed_delta_summary'] = dict(decision_sha256=patch['decision_sha256'],
            **{key:patch[key] for key in source_fields}, edits=[dict(kind=edit['kind'],
                **{key+'_utf8_bytes':len(edit[key].encode()) for key in ('old_text','new_text')},
                **{key+'_sha256':hashlib.sha256(edit[key].encode()).hexdigest() for key in ('old_text','new_text')})
                for edit in patch['edits']], test_text_utf8_bytes=len(patch['test_text'].encode()),
            test_text_sha256=hashlib.sha256(patch['test_text'].encode()).hexdigest())
        failure['public_failed_delta_omitted_from_controller_view'] = True
        failure['planning_notice'] = ('Full exact public edits/test strings go to Author; these hashes/bindings '
            'are provenance, not a generic host-file read capability. Diagnose capacity without inventing a candidate or quality verdict.')
    return result


def _review(original, *, training_scope=None):
    child, reviewed = original['candidate'], original['exploration_review']
    public = dict(candidate_id=None if child is None else child['id'],
                  accepted_for_exploration=reviewed['accepted_for_exploration'])
    if child is None:
        if reviewed != {'accepted_for_exploration': False, 'evidence': []}:
            raise ValueError('No-change has no independent candidate review')
        return public, []
    outcomes = [b for b in reviewed['evidence'] if Path(b['path']).name.endswith('-outcome.json')]
    if len(outcomes) != 1:
        raise ValueError('One actual campaign candidate outcome required')
    actual = engine.read(outcomes[0])
    if (actual.get('schema') != 'earnings_population_exploration_review_v1'
            or actual.get('candidate_id') != child['id']
            or actual.get('accepted_for_exploration') is not reviewed['accepted_for_exploration']
            or type(actual.get('rationale')) is not str or not 1 <= len(actual['rationale']) <= 1000):
        raise ValueError('Campaign outcome differs from its actual review')
    public.update(binding=deepcopy(outcomes[0]), rationale=actual['rationale'])
    probes = []
    for bound in reviewed['evidence']:
        if Path(bound['path']).name.endswith('-probe.json'):
            expected_company = original['company_id']
            if training_scope is not None:
                from earnings_population_training25 import admit
                if Path(bound['path']).name.endswith('-prior-probe.json'):
                    expected_company = engine.read(original['previous_feedback'])['company_id']
                admit(training_scope, expected_company)
            probe = engine.read(bound)
            if probe.get('company_id') != expected_company:
                raise ValueError('Campaign cold-probe company must be labeled exactly')
            probes.append(dict(company_id=probe['company_id'], stage=probe['input']['stage'],
                receipt=deepcopy(bound), diagnostics=deepcopy(probe['diagnostics'])))
        elif Path(bound['path']).name.endswith('-cases.json'):
            cases = engine.read(bound)
            rows = cases.get('results')
            if (cases.get('candidate_id') != child['id'] or type(rows) is not list
                    or not 1 <= len(rows) <= 8
                    or any(type(row) is not dict or type(row.get('passed')) is not bool for row in rows)):
                raise ValueError('Exact bounded authored-case results required')
            public['authored_cases'] = dict(receipt=deepcopy(bound),
                passed=[row['passed'] for row in rows],
                qualification='Model-authored cases, not independent correctness; inspect exact receipt for executions.')
    return public, probes


def _research_question(original):
    """The declared public question, not hidden reasoning or an inferred intent."""
    from earnings_population_roles import scientific
    chosen = scientific(engine.read(original['decision']))
    child = original['candidate']
    if (chosen['parent_pair_sha256'] != original['chosen_parent_id']
            or chosen['feedback_sha256'] != digest(original['previous_feedback'])
            or (chosen['axis'] == 'continue') != (child is None)
            or child is not None and (child.get('axis') != chosen['axis']
                                     or child.get('parent') != chosen['parent_pair_sha256'])):
        raise ValueError('Public research question differs from actual feedback/parent/candidate')
    return dict(decision=deepcopy(original['decision']), **{key: chosen[key] for key in
        ('axis','component','parent_pair_sha256','hypothesis','expected_effect')})


def project(original, versions, project_scored, *, training_scope=None):
    """Typed unscored views never contain results; real scores keep old checks."""
    scoped = {} if training_scope is None else {'training_scope': training_scope}
    if training_scope is not None:
        from earnings_population_training25 import admit
        admit(training_scope, original.get('company_id'))
    if original['schema'] == 'earnings_population_rejection_feedback_v1':
        if (original.get('kind') != 'review_rejected' or original.get('score_state') != 'unscored'
                or 'results' in original or 'points' in original
                or original['review']['accepted_for_exploration'] is not False):
            raise ValueError('Exact unscored original rejection required')
        public = {k: deepcopy(original[k]) for k in ('schema', 'kind', 'score_state', 'company_id',
            'population_sha256', 'active_parent_id', 'last_scored_feedback', 'rejected_candidate',
            'probes', 'original_questions', 'tool_abi', 'qualifications', 'scope')}
        public['review'] = {k: deepcopy(original['review'][k])
                            for k in ('binding', 'accepted_for_exploration', 'rationale')}
        public['last_scored_observation'] = _last_scored(
            original['last_scored_feedback'], original['company_id'], versions, project_scored, **scoped)
        return public
    if original.get('schema') != 'earnings_population_campaign_feedback_v1':
        raise ValueError('Typed campaign feedback required')
    public = {k: deepcopy(original[k]) for k in ('schema', 'kind', 'score_state', 'company_id',
        'round_index', 'decision', 'chosen_parent_id', 'baseline_version_id', 'previous_feedback',
        'campaign_contract_sha256', 'last_scored_feedback', 'scope')}
    public['exploration_review'], public['probes'] = _review(original, **scoped)
    if training_scope is not None:
        public['research_question'] = _research_question(original)
    if original['kind'] == 'scored_dev' and original['score_state'] == 'scored':
        # The comparator occupies this projection-only envelope; no stable
        # selection is changed or inferred by the original award verifier.
        measured = project_scored(dict(schema='earnings_population_feedback_v1',
            company_id=original['company_id'], round_index=original['round_index'],
            stable_id=original['baseline_version_id'], scope=original['scope'], results=original['results']), versions)
        public['results'] = measured['results']
        if 'original_questions' in measured:
            public['original_questions'] = measured['original_questions']
    elif (original['kind'] not in {'review_rejected', 'no_change'}
            or original['score_state'] != 'unscored' or original['results']):
        raise ValueError('Campaign rejection/no-change cannot carry a forecast score')
    else:
        public['last_scored_observation'] = _last_scored(
            original['last_scored_feedback'], original['company_id'], versions, project_scored, **scoped)
    return public


def _last_scored(binding, company, versions, project_scored, *, training_scope=None):
    """One bounded prior observation; never recursively unfold feedback history."""
    original = engine.read(binding)
    if training_scope is not None:
        from earnings_population_training25 import admit
        admit(training_scope, original.get('company_id'))
        company = original['company_id']  # Separate original score; never relabel it as latest.
    if original.get('schema') == 'earnings_population_campaign_feedback_v1':
        if original.get('kind') != 'scored_dev' or original.get('score_state') != 'scored':
            raise ValueError('Last scored observation cannot be another unscored decision')
        original = dict(schema='earnings_population_feedback_v1',
            company_id=original['company_id'], round_index=original['round_index'],
            stable_id=original['baseline_version_id'], scope=original['scope'], results=original['results'])
    measured = project_scored(original, versions)
    if measured['company_id'] != company or not measured['results']:
        raise ValueError('Last scored observation must match the development panel')
    return dict(binding=deepcopy(binding), company_id=company,
        results=[{k: deepcopy(row[k]) for k in ('version_id', 'points', 'target_scores') +
                  (('public_predictions',) if 'public_predictions' in row else ())}
                 for row in measured['results']])


def _reference(feedback_binding, fallback):
    seen = set()
    for _ in range(50):
        token = (feedback_binding['path'], feedback_binding['sha256'])
        if token in seen:
            raise ValueError('Campaign feedback reference cycle')
        seen.add(token)
        current = engine.read(feedback_binding)
        if current.get('schema') == 'earnings_population_rejection_feedback_v1':
            return deepcopy(current['rejected_candidate'])
        if current.get('schema') != 'earnings_population_campaign_feedback_v1':
            break
        child = current['candidate']
        if current['kind'] == 'review_rejected' and child is not None and child['axis'] == 'R':
            return dict(axis='R', source=deepcopy(child['R']), source_delivery='paged_reference',
                        reference_only=True, id=child['id'], parent=child['parent'])
        feedback_binding = current['previous_feedback']
    else:
        raise ValueError('Campaign reference lineage exceeds bounded verification')
    return deepcopy(fallback)


def _failure_context(reference, public, original, *, training_scope=None):
    """One exact-source probe, not two copies of forecast/controller bodies."""
    rows = public.get('probes') or original['probes']
    matches = [row for row in rows if row.get('stage') == 'forecast'
        and row.get('source_sha256', row.get('diagnostics', {}).get('source_sha256'))
            == reference['source']['sha256']]
    if not matches:
        return None  # No current-source probe is not permission to invent one.
    company_id = original['company_id']
    if training_scope is not None:
        from earnings_population_training25 import admit
        company_id = public.get('company_id') if public.get('probes') else company_id
        admit(training_scope, company_id)
        matches = [row for row in matches if row.get('company_id') == company_id]
        if not matches:
            return None  # A labelled prior-company probe is not the current failure.
    if len(matches) != 1 or matches[0]['company_id'] != company_id:
        raise ValueError('One exact-source prior-company forecast probe required')
    from earnings_population_failure_context import project
    from earnings_population_tasks import resident
    verified = project(matches[0]['receipt'], source_binding=reference['source'],
                       company=resident(company_id)['company'])
    # Keep the original <=24KiB projection intact. This independently bounded
    # extension follows the same existing Controller/Author receiving path.
    samples = _request_examples(matches[0]['receipt'], verified, source_binding=reference['source'])
    return dict(verified, request_return_examples=samples)


def _training_context(study, packet, scope):
    """Compact complete public baseline, never a Native trial or target answer."""
    from earnings_population_training25 import admit, load_comparator
    link = engine.read(study['training_state_link'])
    if packet['company_id'] not in link['panel'] or packet['round_index'] != 1:
        raise ValueError('Actual single training round must match admitted link')
    latest = engine.read(link['previous_feedback']); scored = engine.read(link['last_scored_feedback'])
    for cik in (packet['company_id'], latest.get('company_id'), scored.get('company_id')):
        admit(scope, cik)
    if engine.read(packet['feedback']) != latest:
        raise ValueError('Training packet must retain its actual prior feedback')
    last = (link['previous_feedback'] if latest.get('schema') == 'earnings_population_feedback_v1'
            or latest.get('score_state') == 'scored' else latest.get('last_scored_feedback'))
    if last != link['last_scored_feedback']:
        raise ValueError('Training state must retain its actual separate last-score pointer')
    baseline = load_comparator(scope, link['comparator'])
    rows = []
    for row in baseline['rows']:
        values = {v['target_id']: v['predicted_value'] for v in row['predictions']}
        rows.append(dict(company_id=row['company_id'], points=row['points'], targets=[dict(
            target_id=v['target_id'], predicted_value=values[v['target_id']], points_awarded=v['points_awarded'])
            for v in row['target_scores']]))
    return dict(training_comparator=dict(schema='earnings_training25_public_summary_v1',
        policy=baseline['policy'], split=deepcopy(scope['split']), manifest=deepcopy(link['comparator']),
        target_order=[f'T{i:03d}' for i in range(1, 6)], rows=rows,
        attribution='Plain fixed-model public training baseline, not Native R32 results or hidden answers.'),
        training_state=dict(link=deepcopy(study['training_state_link']), current_company_id=packet['company_id'],
            previous_feedback=deepcopy(link['previous_feedback']), previous_company_id=latest['company_id'],
            last_scored_feedback=deepcopy(link['last_scored_feedback']), last_scored_company_id=scored['company_id']))


def prepare(runtime, packet, public_feedback):
    """Build a bounded, original-broker-compatible reference without dispatch."""
    study = engine.read(runtime['forecast_study'])
    from earnings_population_public_predictions import runtime_scope
    scope = runtime_scope(runtime, study)
    scoped = {} if scope is None else {'training_scope': scope}
    campaign = study.get('campaign')
    if campaign is None:
        return None
    if packet.get('campaign') != campaign:
        raise ValueError('Actual Controller packet must bind the admitted campaign')
    origin = engine.read(study['campaign_origin'])
    original = origin.get('original_research_feedback', origin['research_feedback'])
    training = {}
    if scope is not None:
        from earnings_population_training25 import admit
        for cik in (original.get('company_id'), public_feedback.get('company_id')):
            admit(scope, cik)
        training = _training_context(study, packet, scope)
    abi = original['tool_abi']
    if (original.get('schema') != 'earnings_population_rejection_feedback_v1'
            or abi.get('schema') != 'earnings_original_R_evidence_abi_v1'
            or abi.get('tools') != TOOLS or abi.get('request_phases') != 1 or abi.get('max_requests') != 8
            or abi.get('second_request_phase_allowed') is not False
            or abi.get('search_hit_fields') != ['path', 'line', 'text']
            or abi.get('read_result_fields') != ['path', 'offset', 'total_characters', 'text', 'next_offset']
            or abi.get('search_has_source_sha256') is not False
            or abi.get('search_has_character_offset') is not False
            or abi.get('read_has_source_sha256') is not False):
        raise ValueError('Exact original R evidence ABI required; no synthesized metadata')
    recovery = origin.get('recovery_context') if packet['round_index'] == 1 else None
    reference = (deepcopy(origin['reference_candidate']) if recovery is not None else
                 _reference(packet['feedback'], origin['reference_candidate']))
    if (reference.get('axis') != 'R' or reference.get('source_delivery') != 'paged_reference'
            or reference.get('reference_only') is not True or 'source_text' in reference
            or len(checked(reference['source'])) > 65536):
        raise ValueError('Bounded exact rejected R is a read-only reference')
    observed = (public_feedback if recovery is None or recovery.get('mode') in {
                    'author_assembly_capacity_feedback_v1','author_implementation_base_capacity_feedback_v1'}
                else dict(probes=recovery['probes']))
    failed_examples = _failure_context(reference, observed, original, **scoped)
    context = dict(schema='earnings_repair_context_v1',
        human_task='Diagnose the actual public research failure and implement the chosen testable R/H idea. Algorithms, literature and tools remain available; no forced mutation, acceptance or gain.',
        prior_candidate=reference,
        observations=dict(feedback_binding=deepcopy(packet['feedback']),
            prior_company_id=original['company_id'], original_R_evidence_abi=deepcopy(abi),
            original_rejection_probes=deepcopy(original['probes']),
            current_public_diagnostics=deepcopy(observed.get('probes', [])),
            current_authored_cases=deepcopy(public_feedback.get('exploration_review', {}).get('authored_cases')),
            public_failure_examples=deepcopy(failed_examples),
            qualifications=deepcopy(original['qualifications'])),
        verification='Exact source/feedback bindings; old Capital public tables remain readable. Original ABI has one phase of at most eight requests: search has no hash or character offset, read has no hash. Author read_prior_file adds a hash for that outer read only; R never receives it implicitly. R final output may be compact arbitrary JSON advice, not state fact records requiring metadata absent from its observations. Choose the algorithm and support claims with actual available evidence, never manufactured hashes or offsets.',
        non_claims='Reference is not an active parent, adopted version, financial correctness or a demonstrated score gain; original financial data/scorer/model and forecast limits remain fixed.')
    if recovery is not None:
        context['observations']['prior_delivery_failure'] = deepcopy(recovery)
    resumed = None if study.get('campaign_resume') is None else engine.read(study['campaign_resume'])
    if scope is not None:
        if recovery is not None or resumed is None or resumed.get('repair') is not None or resumed.get('reuse_mode') is not None:
            raise ValueError('Training research requires ordinary completed origin, not forced repair/reuse')
        context['human_task'] = ('Improve transferable financial research across the frozen training25. '
            'Use public baseline and actual feedback to choose one testable R/H/continue question; '
            'literature, new algorithms and tools are available. Old failures are evidence, not a mandatory parser repair. '
            'No forced mutation, adoption or score gain; never hardcode exposed answers.')
        context['observations'].update(deepcopy(training), prior_company_id=public_feedback['company_id'],
            original_R_evidence_abi_company_id=original['company_id'])
        context['verification'] = context['verification'].replace('old Capital public tables remain readable',
            'current and prior public tables require their own admitted training company; original ABI provenance remains separate')
    from earnings_population_source_guard_repair import repair_evidence
    public_repair = None if scope is not None else repair_evidence(runtime, packet)
    if public_repair is not None:
        if recovery is not None:
            raise ValueError('Public annotation cannot replace a recovered origin')
        context['observations']['prior_delivery_failure'] = deepcopy(public_repair['delivery'])
    return dict(campaign=deepcopy(campaign), origin=deepcopy(study['campaign_origin']),
        feedback_binding=deepcopy(packet['feedback']), original_R_evidence_abi=deepcopy(abi),
        prior_candidate=reference, failure_evidence_context=failed_examples, research_context=context,
        **({} if scope is None else dict(training_scope=scope, **deepcopy(training))),
        **({'repair_assignment': deepcopy(public_repair['repair_assignment'])} if public_repair is not None else
           {} if scope is not None or resumed is None or packet['round_index'] != 1
           else {'repair_assignment': deepcopy(resumed['repair'])}))
