"""Verified completed-campaign origin, never a new live grant.

Exact03 keeps its old verifier. Later complete windows inherit their actual
last reconcile; a failed/partial window is not accepted or reset to03.
"""
from contextlib import closing
from copy import deepcopy
import ast
import fcntl
import hashlib
import os
from pathlib import Path
import re
import sqlite3

import earnings_population as pool
import earnings_population_campaign as campaign
import earnings_population_campaign_context as context
import earnings_population_campaign_resume as bootstrap
import earnings_population_continuation as history
import earnings_population_tasks as tasks
from earnings_population_window import start_utc
from earnings_native_failure import _cleanup, _owned_requests
from earnings_night_budget import history_snapshot
from market_rsi import digest
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch

DEV = frozenset({'CIK0000003545', 'CIK0000004457', 'CIK0000017313'})


def _identity(binding, root, ledger, repo, seen):
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding['path']) is not str or type(binding['sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', binding['sha256']) is None):
        raise ValueError('Exact completed-result binding required before any read')
    path = Path(binding['path']); ident = path.parent.name
    if (root != bootstrap.OWNED or ledger != bootstrap.LEDGER or repo != bootstrap.REPO
            or any(p.resolve() != p for p in (root, ledger, repo, path))
            or path != root/'attempts'/ident/'population-run-result.json'
            or re.fullmatch('edgar-population-20261016-[0-9]{2}', ident) is None
            or ident in seen or len(seen) >= 50):
        raise ValueError('Canonical noncyclic owned completed window required')
    return path, ident


def _register(reader, inherited, *, training_scope=None):
    """Register only bindings already verified by the predecessor loader."""
    for bound in inherited['evidence']:
        path = Path(bound['path'])
        if path.parent == reader.root or training_scope is not None:
            reader.extra.add(path)
        for part in path.parts:
            if re.fullmatch('edgar-population-20261016-[0-9]{2}', part):
                reader.ids.add(part)
    recovery = inherited.get('recovery_context')
    if recovery is not None and recovery.get('independent_offline_observations') is not None:
        reader.extra.add(Path(recovery['independent_offline_observations']['receipt']['path']))
    companies = {row['company_id'] for row in inherited['population']['observations']}
    if training_scope is None:
        if not companies <= DEV:
            raise ValueError('Inherited observations may reference development companies only')
    else:
        from earnings_population_training25 import admit
        companies |= set(inherited['population']['exposed_companies'])
        companies |= {r['body']['company_id'] for r in inherited['population']['history'] if r.get('kind') == 'observe'}
        for cik in companies: admit(training_scope,cik)
    for cik in sorted(companies):
        qa = tasks.resident(cik)['kernel']['qa']
        reader.extra.add(Path(qa['path']))
        reader.read(qa, binary=True)  # Exact already-observed kernel bytes, never labels.


def _training(reader, runtime, study, *, inherited=None, preview=False):
    """Preview scope/metadata; full link checks require a replayed predecessor."""
    if 'training_policy' not in runtime:
        if 'training_state_link' in study or 'training_stage_attachment' in study:
            raise ValueError('Training link or stages need explicit original runtime policy')
        return None, []
    import earnings_population_training25 as training
    binding = study.get('training_state_link')
    if (type(runtime['training_policy']) is not str or runtime['training_policy'] != training.POLICY
            or type(runtime.get('companies')) is not list or len(runtime['companies']) != 1
            or type(binding) is not dict or set(binding) != {'path','sha256'}
            or binding.get('path') != str(reader.root/'inputs'/runtime['id']/'training-state-link.json')
            or runtime.get('model_budget_amendment') is None or study.get('continuation') is not None):
        raise ValueError('Exact original training runtime/link/current panel required before content')
    link = reader.read(binding)
    if (type(link) is not dict or set(link) != {'schema','policy','split','comparator',
            'previous_population','population_sha256','previous_feedback','last_scored_feedback','panel','completed_origin'}
            or link.get('schema') != 'earnings_training25_state_link_v1' or link.get('policy') != training.POLICY
            or type(link.get('completed_origin')) is not dict):
        raise ValueError('Exact completed training link metadata required before recursion')
    scope = training.load_scope(link.get('split'))
    if link.get('panel') != runtime['companies']: raise ValueError('Training link/current panel differs')
    training.admit(scope,runtime['companies'][0])
    for key,name in (('campaign','campaign.json'),('campaign_resume','campaign-resume.json')):
        if type(study.get(key)) is not dict or study[key].get('path') != str(reader.root/'inputs'/runtime['id']/name):
            raise ValueError('Canonical same-input training campaign/resume metadata required')
    manifest = reader.read(study['campaign'])
    if type(manifest) is not dict: raise ValueError('Exact training campaign metadata object required')
    plan = runtime['sources'].get(training.PLAN)
    expected = dict(schema='supervisor_bottleneck_plan_v1',id='earnings-population-training25-20261019',
        human_authorization=training.AUTHORIZATION,training_policy=training.POLICY,split=scope['split'],
        stage_authority=training.STAGE_AUTHORITY,max_decisions=1,scope=training.SCOPE)
    source_plan = reader.read(plan)
    stage_spec = None
    if type(source_plan) is dict and 'successful_stage_attachment' in source_plan:
        expected = training.entry_plan(plan,reader.repo,historical_reader=reader)
        stage_spec = training.stage_attachment_policy(plan,repo=reader.repo,attempt_id=runtime['id'],
            company_id=runtime['companies'][0],historical_reader=reader)
    if (manifest.get('training_state_link') != binding or manifest.get('source_plan') != plan
            or manifest.get('panel') != runtime['companies'] or manifest.get('max_decisions') != 1
            or digest(source_plan) != digest(expected)):
        raise ValueError('Original committed training authority/campaign link differs')
    stage_binding = study.get('training_stage_attachment')
    if stage_spec is None:
        if 'training_stage_attachment' in study:
            raise ValueError('Unselected training stage attachment cannot enter historical replay')
    elif (type(stage_binding) is not dict or set(stage_binding) != {'path','sha256'}
            or stage_binding.get('path') != str(reader.root/'inputs'/runtime['id']/'training-stage-attachment.json')):
        raise ValueError('Targeted training stages require their canonical sibling receipt')
    if (type(manifest.get('initial_feedback')) is not dict
            or manifest['initial_feedback'].get('path') != str(reader.root/'inputs'/runtime['id']/'rejection-feedback.json')):
        raise ValueError('Canonical current training feedback metadata required before read')
    resumed = reader.read(study['campaign_resume'])
    if (type(resumed) is not dict or set(resumed) != {'schema','previous_result','plan','repair'}
            or resumed.get('schema') != 'earnings_population_campaign_resume_v1'
            or resumed.get('plan') != plan or resumed.get('repair') is not None
            or resumed.get('previous_result') != link['completed_origin']):
        raise ValueError('Exact original completed predecessor metadata required before recursion')
    if preview:
        if inherited is not None: raise ValueError('Training preview is not full origin admission')
        return scope, []
    if inherited is None:
        raise ValueError('Verified original completed predecessor required before link recursion')
    original_final = reader.read(inherited['previous_result'])['result']['result']
    if (inherited['previous_result'] != resumed['previous_result']
            or reader.read(study['campaign_origin']) != inherited
            or reader.read(runtime['initial_population']) != inherited['population']
            or link['previous_population'] != original_final['artifacts'][0]
            or training._read(link['previous_population']) != inherited['population']
            or link['previous_feedback'] != inherited['feedback']
            or link['last_scored_feedback'] != inherited['last_scored_feedback']
            or manifest.get('last_scored_feedback') != inherited['last_scored_feedback']
            or reader.read(manifest['initial_feedback']) != inherited['research_feedback']):
        raise ValueError('Exact original training predecessor/initial population differs')
    training.validate_link(link)
    comparator = training.load_comparator(scope,link['comparator'])
    evidence = [binding,scope['split'],training.STAGE_AUTHORITY,link['comparator'],training.DRIVER]
    for row in comparator['rows']:
        evidence.extend(v for k,v in row['originals'].items() if k != 'cik')
        identity = training._read(row['originals']['window_identity'])
        evidence += [identity['review'],identity['checkpoint']]
    for bound in evidence:
        reader.extra.add(Path(bound['path']))
        reader.read(bound,binary=True)
    return scope, evidence


def _model_grant(db, reader, runtime, summary, maximum=None):
    """Historical grant/source identity, never current dispatch or deadline."""
    if 'additional_budget_amendment' in runtime:
        from earnings_population_additional_budget import historical_grant
        return historical_grant(db,reader,runtime,summary,maximum)
    if 'model_budget_amendment' not in runtime: return []
    import earnings_population_model_budget as model
    from earnings_population_budget import _encoded
    from earnings_population_panel_budget import ceiling
    from earnings_population_window import minutes
    bound = runtime['model_budget_amendment']
    grant = model.read_grant(db,required_binding=bound)
    if (type(bound) is not dict or set(bound) != {'path','sha256'} or grant is None
            or minutes(runtime) != 90 or type(runtime['additional_cap_nano_usd']) is not int
            or not 1 <= runtime['additional_cap_nano_usd'] <= ceiling(runtime,historical_reader=reader)
            or summary.get('model_budget_optin') != bound
            or _encoded(summary.get('dispatch_model_caps_usd')) != _encoded({model.MODEL:300,'other_models':100})
            or runtime['sources'].get(model.PLAN) != grant['authority']
            or runtime['baseline']['max_rowid'] < grant['prefix']['max_rowid']):
        raise ValueError('Exact historical model grant/summary/authority/window required')
    model._authority(grant['authority'],runtime['source_commit'])
    for name in model.IMPLEMENTATIONS:
        binding = runtime['sources'].get(name)
        if (type(binding) is not dict or binding.get('sha256') != grant['implementations'][name]
                or hashlib.sha256(reader.read(binding,binary=True)).hexdigest() != grant['implementations'][name]):
            raise ValueError('Original committed financial implementation differs')
    if maximum is not None:
        closed = history_snapshot(db,maximum)
        totals = db.execute('SELECT model,SUM(charged) FROM requests WHERE rowid<=? GROUP BY model',(maximum,)).fetchall()
        if (closed['charged_nano_usd'] > 400_000_000_000
                or closed['charged_nano_usd']-model.STAGE['charged_nano_usd'] > model.STAGE_CAP
                or any(amount > (model.NAMED if name == model.MODEL else model.OLD) for name,amount in totals)):
            raise ValueError('Original closed prefix exceeds model/global/stage ceiling')
    reader.extra.add(Path(bound['path']))
    reader.read(bound,binary=True)
    return [bound]


def _delivery_lessons(inherited):
    """Compact new capacity history only; preserve old replay return shapes."""
    mode = 'author_assembly_capacity_feedback_v1'
    base_mode = 'author_implementation_base_capacity_feedback_v1'
    modes = {mode,base_mode}
    schema = 'earnings_population_delivery_lesson_v1'
    input_schema = 'earnings_population_input_delivery_lesson_v1'
    input_mode = 'author_input_capacity_feedback_v1'
    forecast_mode = 'reviewed_candidate_forecast_deadline_failure_v1'
    forecast_schema = 'earnings_population_forecast_delivery_lesson_v1'
    forecast_fields = {'schema','mode','failed_attempt','audit','stage','error_type',
        'company_wall_seconds','observed_wall_seconds','completed_forecast_generations',
        'review_assessment','score_state','candidate_id','qualification'}
    forecast_qualification = ('Historical accepted-Review forecast deadline failure with no final predictions '
        'or score; operational diagnosis, not a financial rejection or predictive gain.')
    recovery = inherited.get('recovery_context', {})
    if inherited.get('author_stage_reuse') is not None and recovery.get('mode') != forecast_mode:
        return [deepcopy(inherited['recovery_context'])]  # Original completed11 shape.
    prior = inherited.get('delivery_lessons', [])
    marker = type(prior) is list and any(type(r) is dict and
        (r.get('schema') in {schema,input_schema,forecast_schema} or r.get('mode') in modes) for r in prior)
    if recovery.get('mode') not in modes|{forecast_mode} and not marker:
        return None  # Original ordinary history did not propagate legacy lessons.
    if type(prior) is not list or len(prior) > 50:
        raise ValueError('Bounded inherited delivery lessons required')
    fields = {'schema','mode','failed_attempt','audit','failed_parent','original_decision',
        'original_scientific_decision_sha256','raw_patch_response','public_failed_delta_sha256','capacity','qualification'}
    qualification = 'Historical source-capacity delivery failure, not a candidate, quality verdict, forecast score or demonstrated repair.'
    lessons = deepcopy(prior)
    if recovery.get('mode') in modes:
        if not fields-{'schema','mode','qualification'} <= set(recovery):
            raise ValueError('Exact already-verified capacity failure fields required')
        lesson=dict(schema=schema,mode=recovery['mode'],
            **{k:deepcopy(recovery[k]) for k in fields-{'schema','mode','qualification'}},
            qualification=qualification)
        if recovery['mode']==base_mode:
            base=recovery['implementation_base']
            lesson['implementation_base']=dict(version_id=base['version_id'],source=deepcopy(base['source']))
        lessons.append(lesson)
    if recovery.get('mode') == forecast_mode:
        lessons.append(dict(schema=forecast_schema, qualification=forecast_qualification,
            **{k:deepcopy(recovery[k]) for k in forecast_fields-{'schema','qualification'}}))
    input_diagnosis=recovery.get('input_delivery_diagnosis')
    input_fields={'schema','mode','failed_attempt','audit','original_decision','original_scientific_decision_sha256',
        'source_context','blocked_turn','completed_generations','input_limit','observed_input_tokens','qualification'}
    input_qualification='Historical input packing failure before a generation, not a new Delta, candidate, financial rejection, score or source-capacity failure.'
    if input_diagnosis is not None:
        if input_diagnosis.get('mode')!=input_mode:
            raise ValueError('Typed original input-delivery diagnosis required')
        lessons.append(dict(schema=input_schema,mode=input_mode,
            **{k:deepcopy(input_diagnosis[k])for k in input_fields-{'schema','mode','qualification'}},
            qualification=input_qualification))
    result, seen = [], {}
    for lesson in lessons:
        if type(lesson) is not dict:
            raise ValueError('Typed compact or original legacy delivery lesson required')
        if lesson.get('schema') == schema:
            capacity = lesson.get('capacity', {})
            is_base=lesson.get('mode')==base_mode
            size_fields = {'parent_utf8_bytes','append_utf8_bytes','assembled_utf8_bytes',
                           'source_limit_utf8_bytes','excess_utf8_bytes','test_text_utf8_bytes'}
            base_fields={'comparison_parent_utf8_bytes','implementation_base_utf8_bytes',
                'implementation_base_source_sha256','assembled_utf8_bytes','assembled_source_sha256',
                'source_limit_utf8_bytes','excess_utf8_bytes','edit_count','edits','test_text_utf8_bytes','test_text_sha256'}
            if (set(lesson) != fields|({'implementation_base'} if is_base else set())
                    or lesson.get('mode') not in modes or lesson.get('qualification') != qualification
                    or type(capacity) is not dict or set(capacity) != (base_fields if is_base else size_fields)
                    or any(type(capacity[k]) is not int or capacity[k] <= 0 for k in
                        ({'comparison_parent_utf8_bytes','implementation_base_utf8_bytes','assembled_utf8_bytes',
                          'source_limit_utf8_bytes','excess_utf8_bytes','edit_count','test_text_utf8_bytes'} if is_base else size_fields))
                    or capacity['source_limit_utf8_bytes'] != 65536
                    or not is_base and capacity['parent_utf8_bytes']+capacity['append_utf8_bytes'] != capacity['assembled_utf8_bytes']
                    or capacity['assembled_utf8_bytes']-65536 != capacity['excess_utf8_bytes']
                    or not is_base and (capacity['parent_utf8_bytes'] > 65536 or capacity['append_utf8_bytes'] > 65536)
                    or capacity['test_text_utf8_bytes'] > 32768
                    or type(lesson.get('failed_parent')) is not dict
                    or set(lesson['failed_parent']) != {'version_id','source'}):
                raise ValueError('Exact compact source-capacity lesson required')
            if is_base:
                base=lesson['implementation_base']; edits=capacity['edits']
                if (type(base)is not dict or set(base)!={'version_id','source'}
                        or type(edits)is not list or not 1<=len(edits)<=16 or capacity['edit_count']!=len(edits)
                        or capacity['comparison_parent_utf8_bytes']>65536 or capacity['implementation_base_utf8_bytes']>65536
                        or any(type(e)is not dict or set(e)!={'kind','old_text_utf8_bytes','new_text_utf8_bytes',
                            'old_text_sha256','new_text_sha256'} or e['kind'] not in {'replace','append'}
                            or any(type(e[k])is not int or not 0<=e[k]<=65536 for k in ('old_text_utf8_bytes','new_text_utf8_bytes'))
                            for e in edits)
                        or capacity['implementation_base_utf8_bytes']+sum(e['new_text_utf8_bytes']-e['old_text_utf8_bytes'] for e in edits)
                            != capacity['assembled_utf8_bytes']):
                    raise ValueError('Exact compact implementation-base capacity lesson required')
                for token in [base['version_id'],capacity['implementation_base_source_sha256'],
                              capacity['assembled_source_sha256'],capacity['test_text_sha256']]+[
                                  e[k] for e in edits for k in ('old_text_sha256','new_text_sha256')]:
                    campaign._sha(token)
                if base['source']['sha256']!=capacity['implementation_base_source_sha256']:
                    raise ValueError('Compact implementation-base identity differs')
            for token in (lesson['original_scientific_decision_sha256'],lesson['public_failed_delta_sha256'],
                          lesson['failed_parent']['version_id']):
                campaign._sha(token)
            for bound in [lesson[k] for k in ('failed_attempt','audit','original_decision','raw_patch_response')]+[lesson['failed_parent']['source']]+(
                    [lesson['implementation_base']['source']] if is_base else []):
                if (type(bound) is not dict or set(bound) != {'path','sha256'}
                        or type(bound['path']) is not str or not Path(bound['path']).is_absolute()
                        or str(Path(bound['path']).resolve()) != bound['path']):
                    raise ValueError('Canonical already-replayed lesson evidence binding required')
                campaign._sha(bound['sha256'])  # Original origin replay already checked bytes.
        elif lesson.get('schema')==input_schema:
            if (set(lesson)!=input_fields or lesson.get('mode')!=input_mode
                    or lesson.get('qualification')!=input_qualification
                    or any(type(lesson[k])is not int or lesson[k]<=0 for k in ('blocked_turn','completed_generations','input_limit'))
                    or not 2<=lesson['blocked_turn']<=8 or lesson['completed_generations']+1!=lesson['blocked_turn']
                    or type(lesson['observed_input_tokens'])is not list or not 1<=len(lesson['observed_input_tokens'])<=4
                    or any(type(v)is not int or v<=lesson['input_limit']for v in lesson['observed_input_tokens'])):
                raise ValueError('Exact compact input-delivery lesson required')
            campaign._sha(lesson['original_scientific_decision_sha256'])
            for bound in [lesson[k]for k in ('failed_attempt','audit','original_decision','source_context')]:
                if (type(bound)is not dict or set(bound)!={'path','sha256'}or type(bound['path'])is not str
                        or not Path(bound['path']).is_absolute()or str(Path(bound['path']).resolve())!=bound['path']):
                    raise ValueError('Canonical original input-delivery evidence required')
                campaign._sha(bound['sha256'])
        elif lesson.get('schema') == forecast_schema:
            import math
            if (set(lesson) != forecast_fields or lesson.get('mode') != forecast_mode
                    or lesson.get('qualification') != forecast_qualification
                    or lesson.get('stage') != 'execute' or lesson.get('error_type') != 'BudgetStop'
                    or type(lesson.get('company_wall_seconds')) is not int or lesson['company_wall_seconds'] != 1800
                    or type(lesson.get('observed_wall_seconds')) not in (int,float)
                    or not math.isfinite(lesson['observed_wall_seconds'])
                    or not 0 < lesson['observed_wall_seconds'] <= lesson['company_wall_seconds']
                    or type(lesson.get('completed_forecast_generations')) is not int
                    or not 1 <= lesson['completed_forecast_generations'] <= 24
                    or lesson.get('review_assessment') != 'accepted_for_exploration'
                    or lesson.get('score_state') != 'unscored'):
                raise ValueError('Exact compact accepted-Review forecast deadline lesson required')
            campaign._sha(lesson['candidate_id'])
            for bound in (lesson['failed_attempt'],lesson['audit']):
                if (type(bound) is not dict or set(bound) != {'path','sha256'}
                        or type(bound['path']) is not str or not Path(bound['path']).is_absolute()
                        or str(Path(bound['path']).resolve()) != bound['path']):
                    raise ValueError('Canonical already-replayed forecast failure evidence required')
                campaign._sha(bound['sha256'])
        elif (lesson.get('schema') != 'earnings_population_delivery_failure_v1'
                or lesson.get('stage') != 'source_review' or lesson.get('mode') in modes
                or set(lesson) & {'public_failed_delta','edits','test_text','source_text'}):
            raise ValueError('Only original legacy review lesson may accompany compact history')
        key = digest(lesson['failed_attempt'])
        if key in seen and seen[key] != lesson:
            raise ValueError('Conflicting duplicate delivery lesson for original failed attempt')
        if key not in seen:
            seen[key] = lesson; result.append(lesson)
    return result


def _budget(reader, runtime, owner, result):
    """Variable own request count/cost; preserve every old row and400 grant."""
    from earnings_population_budget import amendment_binding, validate_cap, CAP
    if runtime.get('budget_amendment') != amendment_binding():
        raise ValueError('Exact existing cumulative400 amendment required')
    requests = _owned_requests(runtime)
    summary = owner['budget_summary']
    expected_cap=500 if 'additional_budget_amendment' in runtime else 400
    if (summary != result['budget'] or summary.get('cap_usd') != expected_cap
            or summary.get('model_cap_usd') != 100 or summary.get('blocked') is not False
            or summary.get('unresolved_reserved_usd') != 0
            or summary.get('night_cap_usd') != runtime['additional_cap_nano_usd']/1e9
            or summary.get('prior_history_sha256') != runtime['baseline']['rows_sha256']):
        raise ValueError('Completed owner/result accounting differs')
    with closing(sqlite3.connect(reader.ledger.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        if validate_cap(db, amendment=runtime['budget_amendment']) != CAP:
            raise ValueError('Original400 grant/configuration differs')
        baseline = runtime['baseline']
        if (history_snapshot(db, history.EXTRA_BASELINE['max_rowid']) != history.EXTRA_BASELINE
                or history_snapshot(db, baseline['max_rowid']) != baseline):
            raise ValueError('Consumed historical prefix changed')
        ids = [row['request_id'] for row in requests]
        positions = [db.execute('SELECT rowid FROM requests WHERE id=?', (ident,)).fetchone()[0]
                     for ident in ids]
        maximum = max(positions, default=baseline['max_rowid'])
        own = db.execute('SELECT id FROM requests WHERE rowid>? AND rowid<=?',
                         (baseline['max_rowid'], maximum)).fetchall()
        closed = history_snapshot(db, maximum)
        if (len(ids) != len(set(ids)) or {row[0] for row in own} != set(ids)
                or maximum != baseline['max_rowid']+len(ids)
                or closed['charged_nano_usd'] != baseline['charged_nano_usd']+
                    sum(row['charged_nano_usd'] for row in requests)
                or round(summary['charged_upper_bound_usd']*1e9) != closed['charged_nano_usd']
                or round(summary['night_charged_upper_bound_usd']*1e9) !=
                    sum(row['charged_nano_usd'] for row in requests)):
            raise ValueError('Exact original owned settled prefix differs')
        grant_evidence = _model_grant(db,reader,runtime,summary,maximum)
    return [row['request'] for row in requests] + grant_evidence


def _literal(reader, binding, name):
    nodes = [node.value for node in ast.parse(reader.read(binding, binary=True)).body
             if isinstance(node, ast.Assign) and len(node.targets) == 1
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    if len(nodes) != 1:
        raise ValueError('One original source-bound literal declaration required')
    return ast.literal_eval(nodes[0])  # Human engineering metadata only, never candidate execution.


def _native_identity(reader, path, value, selected, runtime_binding, runtime, resident, python, *, training_scope=None):
    from earnings_research_state import sha as state_sha
    from supervisor_harness import capacity_feedback_engine as engine
    if training_scope is None:
        if selected['company_id'] != bootstrap.COMPANY or resident['company']['cik'] != bootstrap.COMPANY:
            raise ValueError('Only exact allowlisted Capital resident identity is supported')
    else:
        from earnings_population_training25 import admit
        admit(training_scope,selected['company_id'])
        if resident['company']['cik'] != selected['company_id']:
            raise ValueError('Exact admitted training Native resident required')
    task = 'population-case-'+digest([str(path.parent), selected['company_id'], selected['version']['id']])[:24]
    empty = dict(schema='earnings_research_state_v1', task_id=task, cik=selected['company_id'],
                 cutoff=resident['company']['cutoff'], records=[])
    initial = dict(path=str(path.parent/'initial-state'/(state_sha(empty)+'.json')), sha256=state_sha(empty))
    if (value.get('company') != resident['company'] or value.get('data') != resident['data_binding']
            or value.get('kernel') != resident['kernel'] or value.get('case') != resident['case']
            or value.get('runtime') != resident['runtime'] or value.get('python') != python
            or value.get('initial_state') != initial or reader.read(initial) != empty):
        raise ValueError('Exact original Native financial/kernel/case/runtime/empty-state identity differs')
    sources = {'researcher_v0.py':selected['version']['R']['sha256'],
        'harness_v0.py':selected['version']['H']['sha256'],
        'evaluation_scorer.py':resident['kernel']['scorer']['sha256'],
        'evaluation_qa.json':resident['kernel']['qa']['sha256'],
        'predictor.py':runtime['sources']['forecaster']['sha256']}
    for name, token in sources.items():
        if reader.pin(path.parent/'source'/name)['sha256'] != token:
            raise ValueError('Protected Native source-copy identity differs')
    component = lambda names, config:dict(sources={name:sources[name] for name in names},
                                        configuration_sha256=digest(config))
    expected = engine.identity.manifest(
        kernel=component(['evaluation_scorer.py','evaluation_qa.json'],
            dict(kernel=resident['kernel'],case=resident['case'],data=resident['data_binding'])),
        predictor=component(['predictor.py'],dict(output='original_five_numeric_predictions')),
        harness=component(['harness_v0.py'],dict(population_component='H')),
        researcher=component(['researcher_v0.py'],dict(population_component='R')),
        memory=initial['sha256'], model=dict(requested_model='gpt-6.1-sol',serving_snapshot='unknown',
            serving_snapshot_verified=False), runtime=dict(python=python,dependencies={}))
    if value.get('manifest') != expected:
        raise ValueError('Protected Native manifest/model/runtime/kernel/predictor identity differs')
    return dict(model_sha256=expected['M'],evaluation_sha256=expected['K'],
        data_scope_sha256=digest(dict(company=resident['case'],data=resident['data_binding'])),
        authority_sha256=digest(runtime_binding),resource_policy_sha256=digest(resident['runtime']))


def _native_work(reader, path, value, selected, runtime, replayed):
    from supervisor_harness import capacity_feedback_engine as engine
    works = replayed.get('capacity_work', [])
    if selected['role'] != 'forecast':
        if works:
            raise ValueError('Nonforecast Native role must have no capacity work')
        return
    row = selected['forecast_result']; slot = Path(runtime['root'])/'roles'/path.parent.name
    pair = digest(engine.activation.pair(value['manifest']))
    names = ('population-public-feedback.json','result.json','score.json','effective-capacity.json','research-state-output.json')
    bound = {name:reader.pin(slot/name) for name in names}
    if (not row['evidence'] or row['evidence'][0] != bound[names[0]]
            or any(row['evidence'].count(bound[name]) != 1 for name in names)):
        raise ValueError('Forecast completion lacks exact owned output/evidence bindings')
    public = reader.read(bound[names[0]])
    effective, terminal = reader.read(bound[names[3]]), reader.read(bound[names[4]])
    initial = dict(path=str(path.parent/'forecast-state'/(value['initial_state']['sha256']+'.json')),
                   sha256=value['initial_state']['sha256'])
    if (public.get('native_pair_sha256') != pair or public.get('effective_input') != bound[names[3]]
            or public.get('pool_sources') != {a:selected['version'][a]['sha256'] for a in ('R','H')}
            or public.get('version_id') != selected['version']['id']
            or public.get('company_id') != selected['company_id'] or public.get('points') != row['points']
            or effective.get('initial_state') != initial
            or reader.read(initial) != reader.read(value['initial_state'])
            or row['evidence'].count(terminal['state']) != 1):
        raise ValueError('Forecast public result/Native pair/state/case differs')
    verified = dict(result=bound[names[1]],score=bound[names[2]],state=terminal['state'],
        consumed=dict(pair_sha256=pair,state_sha256=effective['initial_state']['sha256']),artifacts=row['evidence'][1:])
    expected = dict(work_id='capacity-'+digest([str(slot),selected['version']['id'],selected['company_id']])[:32],
        pair_sha256=pair,evidence_sha256=digest(dict(context=reader.pin(path),slot=str(slot),version=selected['version'])),
        status='completed',output_evidence_sha256=digest(verified))
    if (len(works) != 1 or any(works[0].get(key) != item for key,item in expected.items())):
        raise ValueError('Exact owned forecast claim/completion ID/pair/evidence required')


def _native(reader, native, runtime_binding, runtime, expected, resident, python, *, training_scope=None):
    """Pure metadata replay, not snapshot() (which can repair/write a cache)."""
    evidence = []
    contexts = sorted(native.glob('*/context.json'))
    if {path.parent.name for path in contexts} != set(expected):
        raise ValueError('Exact completed round/role Native context set required')
    start = start_utc(runtime)
    for path in contexts:
        selected = expected[path.parent.name]
        value = reader.read(reader.pin(path))
        if (value.get('schema') != 'earnings_population_native_case_v1'
                or value.get('company', {}).get('cik') not in (DEV if training_scope is None else training_scope['training'])
                or value.get('company', {}).get('cik') != selected['company_id']
                or value.get('authority') != runtime_binding
                or value.get('source_commit') != runtime['source_commit']
                or value.get('pool_version') != selected['version']
                or value.get('window') != dict(start_utc=start, deadline_utc=runtime['deadline_utc'])
                or str(Path(runtime['root'])/'roles'/path.parent.name) not in runtime['slots'][selected['role']]):
            raise ValueError('Original Native round/role/company/version/window differs')
        selected_resident=resident
        if 'clean_company_concurrency' in runtime:
            from earnings_population_company_batch import enabled
            if not enabled(runtime):raise ValueError('Exact clean company batch required')
            selected_resident=tasks.resident(selected['company_id'])
            reader.extra.add(Path(selected_resident['kernel']['qa']['path']))
        fixed = _native_identity(reader,path,value,selected,runtime_binding,runtime,selected_resident,python,
            **({} if training_scope is None else {'training_scope':training_scope}))
        batch = ContinuousDiscoveryBatch(path.parent/'batch', allow_temporary=True)
        descriptor = os.open(batch.lock_path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
            records = batch._read_records()
            replayed, saved = batch._replay(records), batch._read_snapshot()
            from supervisor_harness import capacity_feedback_engine as engine
            if (saved != replayed or not replayed['initialized'] or replayed['attempts_claimed'] != 0
                    or replayed['active_attempt_ids'] or replayed['active_attempt_id'] is not None
                    or replayed['micro_evolution']['pending'] is not None
                    or replayed['micro_evolution']['active_pair'] != engine.activation.pair(value['manifest'])
                    or replayed['micro_evolution']['fixed_context'] != fixed):
                raise ValueError('Original Native metadata is not durably idle/completed')
            _native_work(reader,path,value,selected,runtime,replayed)
        evidence += [reader.pin(path), reader.pin(batch.snapshot_path)]
    return evidence


def _rounds(reader, attempt, runtime, study, manifest, seed, *, training_scope=None, routing_origin=None):
    """Rebuild actual parent/axis/review/selection and both feedback pointers."""
    previous = deepcopy(seed); expected = {}
    origin = routing_origin
    if origin is None:
        origin = {} if study.get('campaign_origin') is None else reader.read(study['campaign_origin'])
    for index in range(1, len(runtime['companies'])+1):
        rows = {stage: reader.pair(attempt/'loop'/f'round-{index:04d}-{stage}.done.json')['output']
                for stage in history.STAGES}
        if origin.get('controller_stage_import') is not None and index == 1:
            from earnings_population_controller_delivery import verify
            verify(reader,attempt,rows,origin,runtime)
        if origin.get('author_stage_reuse') is not None:
            if index != 1 or len(runtime['companies']) != 1:
                raise ValueError('Successful-stage reuse is one explicit round only')
            from earnings_population_recovery import verify_reused_stages
            verify_reused_stages(reader,attempt,rows,origin)
        packet = reader.read(rows['input']['packet'])
        chosen = reader.read(rows['controller']['decision'])
        state = pool.validate(previous['population']); child = rows['implement']['candidate']
        parent = chosen['parent_pair_sha256']; reviewed = rows['source_review']
        if (packet['population'] != state or packet['feedback'] != previous['feedback']
                or packet.get('round_index') != index or packet.get('company_id') != runtime['companies'][index-1]
                or chosen['feedback_sha256'] != digest(previous['feedback'])
                or parent not in [state['stable_id'], *state['explorers']]
                or chosen['axis'] not in {'R', 'H', 'continue'}
                or (child is None) != (chosen['axis'] == 'continue')
                or child is not None and (child['parent'] != parent or child['axis'] != chosen['axis'])):
            raise ValueError('Actual completed parent/feedback/axis differs')
        company = runtime['companies'][index-1]
        expected[f'controller-{index:02d}'] = dict(role='controller', round_index=index,
            company_id=company, version=deepcopy(state['versions'][state['stable_id']]))
        if child is not None:
            expected[f'author-{index:02d}'] = dict(role='author', round_index=index,
                company_id=company, version=deepcopy(state['versions'][parent]))
            expected[f'review-{index:02d}'] = dict(role='review', round_index=index,
                company_id=company, version=deepcopy(child))
            if training_scope is None and child['axis'] == 'H' and not reviewed['accepted_for_exploration']:
                raise ValueError('Rejected inactive H reference paging is unsupported; do not silently drop it')
        selected = deepcopy(state)
        retiring = chosen.get('retire_branch_id')
        if child is not None and reviewed['accepted_for_exploration']:
            if retiring is not None:
                selected = pool.retire(selected, retiring, reason=chosen['hypothesis'],
                                       evidence=[rows['controller']['decision']])
            selected = pool.retain(selected, child, reason=chosen['hypothesis'], evidence=reviewed['evidence'])
        measured = rows['execute']
        if reader.read(measured['frozen']) != selected:
            raise ValueError('Frozen pool differs from actual accepted single-axis transition')
        for arm, row in enumerate(measured['results']):
            expected[f'forecast-{index:02d}-{arm:02d}'] = dict(role='forecast', round_index=index,
                company_id=company, version=deepcopy(selected['versions'][row['version_id']]),forecast_result=deepcopy(row))
            required = str(attempt/'roles'/f'forecast-{index:02d}-{arm:02d}'/'program-executions.json')
            if [b.get('path') for b in row['evidence']].count(required) != 1:
                raise ValueError('Completed new forecast lacks exact original program-execution evidence')
        value = campaign.feedback(manifest, previous, chosen, child, reviewed, measured,
                                  index, rows['controller']['decision'])
        actual = rows['reconcile']; bound = actual['feedback']
        last = bound if value['score_state'] == 'scored' else previous['last_scored_feedback']
        if (reader.read(bound) != value or actual['latest_feedback'] != bound
                or actual['last_scored_feedback'] != last or actual['population'] != selected
                or rows['result_review']['feedback'] != bound
                or rows['result_review']['last_scored_feedback'] != last
                or reader.read(reader.pin(attempt/f'population-{index:02d}.json')) != selected):
            raise ValueError('Latest feedback/last scored pointer/final pool differs')
        # Verifies public awards/outcomes against original source-bound receipts;
        # it neither decodes raw QA nor recomputes the original scorer.
        from earnings_population_broker import public_feedback
        from earnings_population_public_predictions import runtime_policy
        public_feedback(bound, selected['versions'], policy=runtime_policy(runtime, study, historical_reader=reader),
            **({} if training_scope is None else {'training_scope':training_scope}))
        previous = actual
    return previous, expected


def _load(binding, root, ledger, repo, seen):
    path, ident = _identity(binding, root, ledger, repo, seen)
    if ident == bootstrap.IDENT:
        return bootstrap.load(binding, root=root, ledger=ledger, repo=repo)
    reader = history._Reader(root, ledger, repo, ident); attempt = path.parent
    result = reader.read(binding)
    if (result.get('status') != 'COMPLETED_DISCOVERY_PILOT' or result.get('retry_allowed') is not False
            or result.get('improvement_proven') is not False or (attempt/'population-run-failure.json').exists()):
        raise ValueError('Only a fully completed original window may transfer')
    token = hashlib.sha256(ident.encode()).hexdigest(); registry = ledger.parent/'.capacity-runtime-claims'
    claim_binding = reader.pin(registry/(token+'.json')); owner_binding = reader.pin(registry/(token+'.result.json'))
    reader.extra.update(Path(b['path']) for b in (claim_binding, owner_binding, tasks.FULL_PLAN, tasks.SCORER))
    claim, owner = reader.read(claim_binding), reader.read(owner_binding)
    runtime_binding = owner['runtime']; runtime = reader.read(runtime_binding)
    if (owner.get('status') != 'COMPLETED_COMPONENT_CONTEXT' or owner.get('error_type') is not None
            or owner.get('retry_allowed') is not False or claim.get('retry_allowed') is not False
            or claim.get('runtime') != runtime_binding or claim.get('id') != ident
            or runtime.get('schema') != 'earnings_population_runtime_v1' or runtime.get('id') != ident
            or runtime.get('root') != str(attempt) or runtime.get('ledger') != str(ledger)
            or claim.get('source_commit') != runtime.get('source_commit')
            or 'training_policy' not in runtime and runtime.get('companies') not in ([bootstrap.COMPANY], [bootstrap.COMPANY]*2)):
        raise ValueError('Exact completed campaign owner/runtime/development panel required')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[key]['path']) for key in ('review', 'budget_amendment'))
    if 'training_policy' in runtime:
        from earnings_population_training25 import POLICY
        if (type(runtime['training_policy']) is not str or runtime['training_policy'] != POLICY
                or any(type(runtime.get(key)) is not dict or runtime[key].get('path') != str(root/'inputs'/ident/name)
                    for key,name in (('forecast_study','study.json'),('initial_population','initial-population.json')))):
            raise ValueError('Exact canonical training study/state required before metadata read')
    study = reader.read(runtime['forecast_study'])
    scope, training_evidence = _training(reader,runtime,study,preview=True)
    resumed = reader.read(study['campaign_resume'])
    if scope is not None and (set(resumed) != {'schema','previous_result','plan','repair'}
            or resumed.get('repair') is not None or resumed.get('plan') != runtime['sources'].get(
                'configs/earnings_coevolution/population_training25_plan.json')):
        raise ValueError('Training inherits only an exact completed predecessor')
    if 'model_budget_amendment' in runtime:
        with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)) as db:
            db.execute('BEGIN')
            _model_grant(db,reader,runtime,owner['budget_summary'])
    if resumed.get('prior_failed_attempt') is not None:
        from earnings_population_recovery import load as recover
        inherited = recover(resumed['prior_failed_attempt'], root=root, ledger=ledger, repo=repo,
                            plan_binding=resumed['plan'],historical_reader=reader)
    else:
        inherited = _load(resumed['previous_result'], root, ledger, repo, {*seen, ident})
    _register(reader, inherited, **({} if scope is None else {'training_scope':scope}))
    if reader.read(study['campaign_origin']) != inherited:
        raise ValueError('Exact prior verified origin changed')
    if scope is not None:
        scope, training_evidence = _training(reader,runtime,study,inherited=inherited)
    routing_origin = None
    if 'training_stage_attachment' in study:
        from earnings_population_training25 import PLAN, stage_attachment_policy, stage_routing_origin
        from earnings_population_recovery import _verify_training_stage_attachment
        spec = stage_attachment_policy(runtime['sources'][PLAN],repo=repo,attempt_id=ident,
            company_id=runtime['companies'][0],historical_reader=reader)
        receipt = _verify_training_stage_attachment(spec['input'],base_origin=inherited,
            training_scope=scope,company_id=runtime['companies'][0],attempt_id=ident,
            root=root,ledger=ledger,repo=repo,plan_binding=runtime['sources'][PLAN],historical_reader=reader)
        if reader.read(study['training_stage_attachment']) != receipt:
            raise ValueError('Completed training stage receipt differs from authenticated originals')
        routing_origin = stage_routing_origin(inherited,receipt)
        _register(reader,routing_origin,training_scope=scope)
        training_evidence += [study['training_stage_attachment'],*receipt['evidence']]
    resident = tasks.resident(bootstrap.COMPANY if scope is None else runtime['companies'][0])
    reader.extra.add(Path(resident['kernel']['qa']['path']))
    if (study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER
            or study.get('cases') != [resident['case']]*len(runtime['companies'])
            or study.get('sole_ledger') != str(ledger) or study.get('runtime_config') != resident['runtime']
            or runtime.get('rates') != resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Original financial task/model/scorer differs')
    reader.scan(runtime); reader.scan(study); reader.scan(result)
    review = reader.read(runtime['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
            or review.get('blocking_findings') != [] or review.get('source_commit') != reader.commit
            or str(review.get('reviewer', '')).strip().lower() in ('', 'root', '/root')
            or review.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items() if k != 'review'})):
        raise ValueError('Original distinct configuration/source review differs')
    clock = reader.pair(attempt/'clock.json')
    if (clock != reader.read(owner['clock']) or clock.get('source_commit') != reader.commit
            or clock.get('cutoff_utc') != runtime['cutoff_utc'] or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Original sealed owner clock differs')
    manifest = reader.read(study['campaign'])
    with history._journal_lock(attempt/'loop'):
        replay, seed = history._replay(attempt/'loop', reader, runtime)
        journal = reader.pair(attempt/'loop/manifest.json')
        for stage, identity in journal['handler_identity'].items():
            if identity.get('campaign_policy') != runtime['sources']['tools/earnings_population_campaign.py'] or identity.get('campaign') != study['campaign']:
                raise ValueError('Original campaign handler differs')
        final, expected_native = _rounds(reader, attempt, runtime, study, manifest, seed,
            **({} if scope is None else {'training_scope':scope}),
            **({} if routing_origin is None else {'routing_origin':routing_origin}))
    if (replay != result['result'] or final != replay['result']
            or seed['population'] != inherited['population']
            or reader.read(seed['feedback']) != inherited['research_feedback']
            or seed['last_scored_feedback'] != inherited['last_scored_feedback']):
        raise ValueError('Full seven-stage closure/final reconcile differs')
    state = pool.validate(final['population'])
    if (state['protected'] != inherited['population']['protected']
            or state['observations'] != inherited['population']['observations']
            or state['exposed_companies'] != inherited['population']['exposed_companies']):
        raise ValueError('Repeated development campaign changed protected/exposure history')
    evidence = training_evidence + _budget(reader, runtime, owner, result)
    evidence += [row['result'] for row in _cleanup(attempt)]
    python = _literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON')
    evidence += _native(reader, Path('/private/tmp')/('market-rsi-'+ident), runtime_binding, runtime, expected_native, resident, python,
        **({} if scope is None else {'training_scope':scope}))
    feedback = reader.read(final['feedback'])
    reference = context._reference(final['feedback'], inherited.get('pre_recovery_reference_candidate', inherited['reference_candidate']))
    lessons = _delivery_lessons(inherited)
    return dict(population=deepcopy(state), feedback=deepcopy(final['feedback']), research_feedback=deepcopy(feedback),
        last_scored_feedback=deepcopy(final['last_scored_feedback']), reference_candidate=reference,
        original_research_feedback=deepcopy(inherited['original_research_feedback']), previous_result=deepcopy(binding),
        **({'delivery_lessons': lessons} if lessons is not None else {}),
        evidence=[binding, runtime_binding, claim_binding, owner_binding, runtime['review'], final['feedback'],
                  final['last_scored_feedback'], reader.pin(attempt/'loop/manifest.json'), *evidence, *inherited['evidence']])


def load(result_binding, *, root, ledger, repo):
    return _load(result_binding, *map(Path, (root, ledger, repo)), set())
