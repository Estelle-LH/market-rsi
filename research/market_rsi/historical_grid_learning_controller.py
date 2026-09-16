"""Codex/GLM broker for archived, opened-Train feature/model diagnostics."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np

from controller_activity_log import append_activity, read_activity_events, verify_activity_log
from historical_delta_evaluation import raw_feature_diagnostic
from historical_grid_features import FIELDS, TRANSFORMS
from historical_feature_composition import COMPOSITION_FIELDS, OPERATORS, MAX_DEPTH, MAX_LEAVES
from historical_recorded_features import derive, validate_feature, feature_engine_sha256, contains_recorded
from historical_trade_windows import (SPEC_FIELDS as RECORDED_FIELDS, SOURCE as RECORDED_SOURCE,
    STATISTICS as RECORDED_STATISTICS, load_audited_index)
from historical_grid_learning import MODEL_FIELDS, PLAN_FIELDS, evaluate, read_inputs, validate_plan
from historical_grid_objective_controller import PAPERS, assess_activity as assess_objective
from historical_ingest_controller import _signed, _tool, load
from historical_input_compatibility import require_compatible_inputs
from historical_learning_diagnostics import diagnose, missing_profiles
from historical_learning_recovery import inspection_failure_evidence, verify_recovery_files
from historical_conditional_diagnostics import diagnose_conditional, validate_selection
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from materialize_selected_grid_objective import write_archive


BASE_INSTRUCTIONS = (
    'You are the GLM researcher in the existing Codex harness. Continue from your archived '
    'historical source and corrected objective decisions. The primary recorded-quote '
    'probability DELTA target is frozen; do not change its horizon, labels or population. '
    'Select causal feature formulas and model/training parameters using only already-open '
    'Train. You have seven causal primitives, bounded researcher-selected field composition, '
    'and four executable statistical models; this '
    'is an implementation library, not a recommendation that one is correct. Defer for '
    'specific missing capabilities instead of inventing a source field or silent default. '
    'Inspect contract/library and literature notes first. Profile each selected feature '
    'before fitting. Explicitly partition all six opened Train dates into earlier fit and '
    'later diagnostic check dates. Once the first trial is frozen, keep the split and metric '
    'aggregation fixed. Later trials must reference a completed parent and change only '
    'features OR prediction/training, not both. All check dates are already opened Train, '
    'never fresh Dev/Test: repeated use is adaptive in-sample research, not RSI improvement. '
    'Missing inputs use explicitly declared persistence or native_nan with HistGB and no '
    'normalizer; no source price is filled. Quiet rows stay in evaluation. Fit/normalization use earlier-day labels '
    'only, with whole-market isolation from check. Models output signed probability changes, '
    'not price levels. You choose optional known probability-bound projection. Report baseline '
    'and candidate MSE, absolute-probability bps, coverage and failures, not just a delta. '
    'The literature tool searches frozen primary-source notes, not live web or full papers. '
    'This initial cache has no signed flow, order-book depth, settlement or tradable PnL. '
    'CPU diagnostics execute trusted bounded library code, not arbitrary generated Python '
    'and not E2B; LLM calls alone use the existing metered research budget. Each feature '
    'query and model trial is frozen before execution; no duplicate trial for a better score. '
    'Distinct hypothesis-driven feature or model comparisons within the declared trial limit '
    'are allowed on opened Train; that is research, not a forbidden retry of an identical plan. '
    'Choose a defensible completed trial or defer, submit the first valid decision and exit. '
    'A prose final answer is NOT a committed decision: you MUST invoke '
    'submit_grid_learning_decision to finish, including when deferring. Never invent an API '
    'or claim a tool was executed when its actual successful receipt is absent.'
)
FILES = {'input-result.json','current-inputs.npz','label-result.json','primary-labels.npz',
         'panel-result.json','objective-proposal.json','data-use-proposal.json','archive.json','literature.json'}
RECORDED_FILES = {'recorded-trades/result.json', 'recorded-trades/claim.json', 'recorded-trades/events.npz',
                  'recorded-trades/audit/audit.json', 'recorded-trades/audit/claim.json',
                  'recorded-trades/window-canary.json', 'recorded-trades/window-canary-claim.json'}
TEXT = {'type':'string','minLength':1,'maxLength':12000}
IDENTIFIER = {'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$','minLength':1,'maxLength':100}
PRIMITIVE_SCHEMA = {'type':'object','additionalProperties':False,'required':sorted(FIELDS),
    'properties':{'name':IDENTIFIER,'source':TEXT,
        'transform':{'type':'string','enum':sorted(TRANSFORMS)},
        'lookback_ms':{'type':'integer','minimum':0,'maximum':86400000},
        'minimum_observations':{'type':'integer','minimum':1,'maximum':256},
        'minimum_window_coverage':{'type':'number','exclusiveMinimum':0,'maximum':1}}}
RECORDED_SCHEMA = {'type':'object','additionalProperties':False,'required':sorted(RECORDED_FIELDS),
    'properties':{'name':IDENTIFIER,'source':{'type':'string','enum':[RECORDED_SOURCE]},
        'statistic':{'type':'string','enum':sorted(RECORDED_STATISTICS)},
        'window_ms':{'type':'integer','minimum':1,'maximum':86400000},
        'minimum_records':{'type':'integer','minimum':1,'maximum':8000000},
        'maximum_recorded_gap_ms':{'type':'integer','minimum':1,'maximum':86400000}}}
FEATURE_SCHEMA = {'anyOf':[PRIMITIVE_SCHEMA, RECORDED_SCHEMA]}
for _depth in range(MAX_DEPTH):
    FEATURE_SCHEMA = {'anyOf':[PRIMITIVE_SCHEMA, RECORDED_SCHEMA, {
        'type':'object','additionalProperties':False,'required':sorted(COMPOSITION_FIELDS),
        'properties':{'name':IDENTIFIER,'operator':{'type':'string','enum':sorted(OPERATORS)},
            'operands':{'type':'array','minItems':2,'maxItems':4,'items':FEATURE_SCHEMA}}}]}
MODEL_SCHEMA = {'type':'object','additionalProperties':False,'required':['algorithm','parameters'],
    'properties':{'algorithm':{'type':'string','enum':list(MODEL_FIELDS)},
        'parameters':{'type':'object','description':'Exactly model_fields[algorithm]; every value researcher-chosen.'}}}
PLAN_SCHEMA = {'type':'object','additionalProperties':False,'required':sorted(PLAN_FIELDS),
    'properties':{'features':{'type':'array','minItems':1,'maxItems':24,'items':FEATURE_SCHEMA},
        'model':MODEL_SCHEMA,
        'normalizer':{'type':'string','enum':['none','fit_mean_std']},
        'train_utc_dates':{'type':'array','minItems':1,'uniqueItems':True,'items':TEXT},
        'check_utc_dates':{'type':'array','minItems':1,'uniqueItems':True,'items':TEXT},
        'train_weighting':{'type':'string','enum':['equal_row','equal_day','equal_market']},
        'score_aggregation':{'type':'string','enum':['equal_row','equal_day','equal_group']},
        'missing_input_action':{'type':'string','enum':['persistence','native_nan']},
        'output_transform':{'type':'string','enum':['none','clip_to_probability_delta_bounds']},
        'seed':{'type':'integer','enum':[23]},'rationale':TEXT}}
PARENT_SCHEMA = {'type':'string','description':
    'Only when NO frozen protocol/completed parent exists: exactly the empty string "" '
    '(not "none", "null", or a guessed ID). Otherwise name an available completed trial ID, '
    'including an archived parent carried from a prior session; do not rerun that parent.'}
TOOLS = [
    _tool('inspect_learning_contract','Read fixed target, source coverage, archive and all opened Train dates.'),
    _tool('inspect_learning_library','Read executable feature/model formulas, exact schemas, limits and unimplemented capabilities.'),
    _tool('search_public_literature','Search fixed primary-source notes, not live browsing.',{'query':TEXT}),
    _tool('profile_feature','Freeze one explicit causal feature, then report its full-population Train association.',
        {'query_id':IDENTIFIER,'spec':FEATURE_SCHEMA,'rationale':TEXT}),
    _tool('evaluate_learning_plan','Freeze and execute one bounded CPU Train/check diagnostic; no new Dev/Test.',
        {'trial_id':IDENTIFIER,'parent_trial_id':PARENT_SCHEMA,'plan':PLAN_SCHEMA}),
    _tool('inspect_learning_trial','Explain a completed trial: actual parent diff, feature missingness and exact denominators. No refit or new score.',
        {'trial_id':IDENTIFIER}),
    _tool('diagnose_feature_controls','Freeze a diagnostic for one existing trial feature against your chosen other trial features. Earlier-only nuisance fits; no new prediction model or holdout.',
        {'query_id':IDENTIFIER,'trial_id':IDENTIFIER,'feature_name':IDENTIFIER,
         'control_names':{'type':'array','maxItems':12,'uniqueItems':True,'items':IDENTIFIER},'rationale':TEXT}),
    _tool('submit_grid_learning_decision','Select a completed diagnostic or defer, then exit.',
        {'action':{'type':'string','enum':['select','defer']},'trial_id':{'type':'string'},'reason':TEXT})]
ALLOWED_TOOLS = tuple(t['name'] for t in TOOLS)


def failed_pre_fit_evidence(session, current, seen=()):
    """Verify the entire preserved interface-failure chain, without dropping old evidence."""
    identifier(session.name)
    if session.name in seen or len(seen)>=8:raise ValueError('cyclic or excessive failed-session ancestry')
    oldroot=session/'workspace';validate_workspace(oldroot)
    assessment=load(session/'session/assessment.json')
    verify_activity_log(oldroot/'learning-activity.jsonl')
    events=read_activity_events(oldroot/'learning-activity.jsonl')
    failures=[e for e in events if e['tool']=='evaluate_learning_plan' and e['status']=='error']
    if (assessment.get('valid') is not False or assessment.get('process_reaped') is not True
            or len(failures)<3 or list((oldroot/'trials').iterdir())
            or any(e['tool']=='evaluate_learning_plan' and e['status']=='ok' for e in events)
            or (oldroot/'submitted-grid-learning-decision.json').exists()
            or any(file_hash(oldroot/n)!=file_hash(current/n) for n in
                   ['objective-proposal.json','primary-labels.npz'])):
        raise ValueError('exact completed pre-fit interface failure with identical inputs required')
    require_compatible_inputs(oldroot,current)
    require_recorded_compatibility(oldroot,current)
    preparation=load(session/'preparation.json')
    if any(file_hash(session/'source-snapshot'/n)!=sha for n,sha in preparation['source_hashes'].items()):
        raise ValueError('failed-session source snapshot changed')
    profiles=[];history=[]
    prior=load(oldroot/'archive.json').get('interface_repair')
    if prior:
        identifier(prior['failed_session_id']);ancestor=session.parent/prior['failed_session_id']
        if (file_hash(ancestor/'session/assessment.json')!=prior['assessment_sha256']
                or file_hash(ancestor/'workspace/learning-activity.jsonl')!=prior['activity_sha256']):
            raise ValueError('inherited interface evidence changed')
        inherited=failed_pre_fit_evidence(ancestor,current,seen+(session.name,))
        if inherited['profiles']!=prior['successful_feature_profiles_reused_without_recomputation']:
            raise ValueError('inherited feature evidence does not match its original artifacts')
        profiles.extend(inherited['profiles']);history.extend(inherited['history'])
    for event in events:
        if event['tool']=='profile_feature' and event['status']=='ok':
            result=event['result'];identifier(event['arguments']['query_id'])
            p=oldroot/'features'/event['arguments']['query_id'];_signed(result,'result_sha256')
            if (load(p/'result.json')!=result or file_hash(p/'claim.json')!=result['claim_sha256']
                    or result['feature_engine_sha256']!=feature_engine_sha256(result['spec'])):
                raise ValueError('prior successful feature evidence changed')
            if result not in profiles:profiles.append(result)
    history.append({'session_id':session.name,'assessment_sha256':file_hash(session/'session/assessment.json'),
        'activity_sha256':file_hash(oldroot/'learning-activity.jsonl'),
        'preparation_sha256':file_hash(session/'preparation.json'),
        'errors':[{'arguments':e['arguments'],'error':e['error']} for e in failures],
        'model_trials_started':0,'successful_fits':0})
    return {'profiles':profiles,'history':history,'first_unexecuted_request':failures[0]['arguments']}


def completed_profile_evidence(session, current, seen=()):
    """Verify profiles back through EVERY completed/failed ancestor without refitting."""
    identifier(session.name)
    if session.name in seen or len(seen)>=16:raise ValueError('cyclic or excessive completed ancestry')
    old=session/'workspace';validate_workspace(old);assessment=load(session/'session/assessment.json')
    if assessment.get('valid') is not True or assessment.get('process_reaped') is not True:
        raise ValueError('completed ancestor must be valid and reaped')
    prep=load(session/'preparation.json')
    if (prep.get('workspace_sha256',file_hash(old/'workspace.json'))!=file_hash(old/'workspace.json')
            or any(file_hash(session/'source-snapshot'/n)!=sha for n,sha in prep['source_hashes'].items())
            or any(file_hash(old/n)!=file_hash(current/n) for n in
                   ['objective-proposal.json','primary-labels.npz'])):
        raise ValueError('completed ancestor source/input binding changed')
    require_compatible_inputs(old,current)
    require_recorded_compatibility(old,current)
    assess_activity(old);archive=load(old/'archive.json');profiles=[];failures=[];completed=[]
    parent=archive.get('completed_diagnostic')
    if parent:
        identifier(parent['completed_session_id']);ancestor=session.parent/parent['completed_session_id']
        for name,key in [('session/assessment.json','assessment_sha256'),
                         ('workspace/learning-activity.jsonl','activity_sha256'),
                         ('preparation.json','source_preparation_sha256')]:
            if file_hash(ancestor/name)!=parent[key]:raise ValueError('completed parent reference changed')
        evidence=completed_profile_evidence(ancestor,current,seen+(session.name,))
        if (evidence['profiles']!=parent['successful_feature_profiles_reused_without_recomputation']
                or evidence['failures']!=parent['verified_failure_history']):
            raise ValueError('completed carryover lost or changed inherited evidence')
        profiles.extend(evidence['profiles']);failures.extend(evidence['failures']);completed.extend(evidence['completed'])
    inherited=archive.get('interface_repair')
    if inherited:
        identifier(inherited['failed_session_id']);ancestor=session.parent/inherited['failed_session_id']
        if (file_hash(ancestor/'session/assessment.json')!=inherited['assessment_sha256']
                or file_hash(ancestor/'workspace/learning-activity.jsonl')!=inherited['activity_sha256']):
            raise ValueError('failed parent reference changed')
        evidence=failed_pre_fit_evidence(ancestor,current)
        if evidence['profiles']!=inherited['successful_feature_profiles_reused_without_recomputation']:
            raise ValueError('completed session feature ancestry changed')
        for profile in evidence['profiles']:
            if profile not in profiles:profiles.append(profile)
        for failure in evidence['history']:
            if failure not in failures:failures.append(failure)
    for e in read_activity_events(old/'learning-activity.jsonl'):
        if e['tool']=='profile_feature' and e['status']=='ok':
            result=e['result'];_signed(result,'result_sha256');path=old/'features'/e['arguments']['query_id']
            if (file_hash(path/'claim.json')!=result['claim_sha256'] or load(path/'result.json')!=result
                    or result['feature_engine_sha256']!=feature_engine_sha256(result['spec'])):
                raise ValueError('completed feature source or result changed')
            if result not in profiles:profiles.append(result)
    completed.append({'session_id':session.name,'assessment_sha256':file_hash(session/'session/assessment.json'),
        'activity_sha256':file_hash(old/'learning-activity.jsonl'),'preparation_sha256':file_hash(session/'preparation.json'),
        'decision':load(old/'submitted-grid-learning-decision.json'),
        'terminal_protocol_recovery':load(old/'archive.json').get('terminal_protocol_recovery'),
        'prediction_error_balance':load(old/'archive.json').get('prediction_error_balance'),
        'trial_ids':sorted(p.name for p in (old/'trials').iterdir())})
    return {'profiles':profiles,'failures':failures,'completed':completed}


def carry_completed_diagnostic(session, audit_path, output):
    """Carry all audited hypotheses/results after a capability request, not a score reset."""
    audit=load(audit_path);_signed(audit,'result_sha256')
    old=session/'workspace';assessment=load(session/'session/assessment.json')
    activity=assess_activity(old);decision=load(old/'submitted-grid-learning-decision.json')
    if (not audit.get('passed') or audit.get('session_id')!=session.name
            or audit['assessment_sha256']!=file_hash(session/'session/assessment.json')
            or audit.get('decision')!=decision or audit.get('activity')!=activity
            or assessment.get('valid') is not True or assessment.get('process_reaped') is not True
            or decision['action']!='defer' or not audit['trials']
            or any(file_hash(old/n)!=file_hash(output/n) for n in
                   ['objective-proposal.json','primary-labels.npz'])):
        raise ValueError('exact audited completed capability deferral with identical inputs required')
    compatibility=require_compatible_inputs(old,output)
    require_recorded_compatibility(old,output)
    prep=load(session/'preparation.json')
    if any(file_hash(session/'source-snapshot'/n)!=sha for n,sha in prep['source_hashes'].items()):
        raise ValueError('completed source snapshot changed')
    audited={v['trial_id']:v for v in audit['trials']}
    evidence=completed_profile_evidence(session,output)
    roots=list((old/'trials').iterdir())
    if {p.name for p in roots}!=set(audited):raise ValueError('every existing trial must be audited/carried, including any failure')
    for path in roots:
        result=load(path/'result.json')
        if result['result_sha256']!=audited[path.name]['result_sha256']:
            raise ValueError('audited trial result changed')
        shutil.copytree(path,output/'trials'/path.name)
    shutil.copyfile(old/'protocol.json',output/'protocol.json')
    diagnostic_history = verify_conditional_queries(old)
    for query in diagnostic_history:
        target = output/'conditional-diagnostics'/query['query_id']
        target.parent.mkdir(exist_ok=True)
        shutil.copytree(old/'conditional-diagnostics'/query['query_id'], target)
    return {'completed_session_id':session.name,'assessment_sha256':file_hash(session/'session/assessment.json'),
        'activity_sha256':file_hash(old/'learning-activity.jsonl'),'result_audit_sha256':file_hash(audit_path),
        'source_preparation_sha256':file_hash(session/'preparation.json'),'decision':decision,
        'all_prior_trials':audited,'frozen_protocol':load(old/'protocol.json'),
        'successful_feature_profiles_reused_without_recomputation':evidence['profiles'],
        'verified_failure_history':evidence['failures'],
        'verified_completed_history':evidence['completed'],
        'prior_conditional_diagnostics':diagnostic_history,
        'input_compatibility':compatibility,
        'capability_added':('Four additive source-reported direction/amount/token-role fields; every old column/NaN is byte-identical.'
            if compatibility['kind']=='additive_reported_direction_only'
            else 'No input fields changed. Inspect the current library for supported capabilities.'),
        'hypothesis_not_selection':'Available capabilities are not a prescribed next signal, method, or selected model.',
        'prior_scores_and_decision_unchanged':True,'previous_trial_slots_still_count':True,
        'same_scientific_plan_must_not_be_reexecuted':True}


def archived_profiles(archive):
    profiles=[]
    for key in ['interface_repair','completed_diagnostic']:
        for p in archive.get(key,{}).get('successful_feature_profiles_reused_without_recomputation',[]):
            if p not in profiles:profiles.append(p)
    return profiles


def error_balance_evidence(path, session, current):
    """Attach ALL audited old scores, not a hand-selected successful subgroup."""
    audit=load(path);_signed(audit,'result_sha256')
    if (session is None or audit.get('schema')!='historical_prediction_error_balance_v1'
            or audit.get('passed') is not True or audit.get('session_id')!=session.name
            or any(audit.get(k)!=0 for k in ('new_prediction_fits','new_nuisance_fits','new_provider_calls','rows_removed'))
            or audit.get('prediction_values_changed') is not False or audit.get('fresh_holdout') is not False
            or audit.get('claim_sha256')!=file_hash(path.parent/'claim.json')):
        raise ValueError('exact zero-fit completed-parent error-balance audit required')
    claim=load(path.parent/'claim.json');old=session/'workspace'
    expected={str((old/n).resolve()):file_hash(old/n) for n in
        ('current-inputs.npz','primary-labels.npz','workspace.json')}
    for trial in sorted((old/'trials').iterdir()):
        for source in trial.iterdir():
            if source.is_file():expected[str(source.resolve())]=file_hash(source)
    if (claim.get('input_hashes')!=expected or any(file_hash(current/n)!=file_hash(old/n)
            for n in ('current-inputs.npz','primary-labels.npz'))):
        raise ValueError('error-balance original inputs changed')
    reported={r['trial_id']:r for r in audit['trials']}
    if (len(reported)!=len(audit['trials']) or set(reported)!={p.name for p in (old/'trials').iterdir()}
            or set(reported)!={p.name for p in (current/'trials').iterdir()}):
        raise ValueError('all original trial error balances required')
    for name, report in reported.items():
        trial=load(current/'trials'/name/'result.json')
        if report['trial_result_sha256']!=trial['result_sha256']:
            raise ValueError('error-balance trial binding changed')
        for metric in ('model_mse_probability','persistence_mse_probability'):
            if not np.isclose(report['all'][metric],trial['report']['score'][metric],rtol=1e-10,atol=1e-15):
                raise ValueError('error-balance score changed')
    return {'audit_sha256':file_hash(path),'evidence':audit,
        'runner_note':'This is an algebraic decomposition of ALL existing scores, not a suggested model. '
            'MSE minus persistence MSE equals prediction energy minus twice target alignment, with original '
            'score weights. Quiet/moving groups explain contributions but are NOT selection filters. '
            'No check-selected scale or rescaled score was fitted. Excess energy is not proof of its cause '
            'or that calibration will generalize. You choose any further hypothesis. '
            'Do not claim one algorithm/support change uniquely disentangles both causes.'}


def pairing_audit_evidence(path, session, current):
    """Bind observational QA to the exact prior and current inputs; no scientific selection."""
    audit=load(path);_signed(audit,'result_sha256')
    if (audit.get('schema')!='historical_open_train_pairing_audit_v1'
            or session is None or audit.get('session_id')!=session.name
            or audit.get('assessment_sha256')!=file_hash(session/'session/assessment.json')
            or audit.get('fits')!=0 or audit.get('provider_calls')!=0
            or audit.get('rows_removed')!=0 or audit.get('labels_changed') is not False
            or audit.get('fresh_holdout_opened') is not False):
        raise ValueError('exact prior zero-fit opened-Train pairing audit required')
    files=['current-inputs.npz','primary-labels.npz','panel-result.json']
    expected={str((session/'workspace'/n).resolve()):file_hash(session/'workspace'/n) for n in files}
    if audit.get('input_hashes')!=expected or any(file_hash(current/n)!=expected[str((session/'workspace'/n).resolve())] for n in files):
        raise ValueError('pairing audit inputs differ from current or prior artifacts')
    return {'audit_sha256':file_hash(path),'evidence':audit,
        'runner_note':'These are measured row symmetries, not a selected feature. Pooled zero association can arise by cancellation; '
            'it does not falsify every role-conditioned hypothesis. Choose and justify your own next step. '
            'The existing three model scores and their limitations remain unchanged.'}


def attach_recorded_events(output, index, audit, canary, prior):
    """Freeze a completed, independently audited capability requested by this parent."""
    if prior is None: raise ValueError('recorded-event extension requires an audited completed parent')
    arrays, dates, binding = load_audited_index(index, audit)
    del arrays
    index_claim = load(index/'claim.json'); check = load(canary/'result.json'); _signed(check,'result_sha256')
    if (not check.get('passed') or check.get('bindings') != binding
            or check.get('labels_read') is not False or check.get('features_selected_for_learning') is not False
            or check.get('provider_calls') != 0 or check.get('fits') != 0
            or check.get('claim_sha256') != file_hash(canary/'claim.json')
            or index_claim['controller_assessment_sha256'] != file_hash(prior/'session/assessment.json')
            or index_claim['controller_decision_sha256'] != file_hash(prior/'workspace/submitted-grid-learning-decision.json')
            or dates != load(output/'data-use-proposal.json')['plan']['open_train_utc_dates']):
        raise ValueError('exact parent-requested real-byte window canary required')
    frozen_canary = load(canary/'claim.json')
    for name, sha in frozen_canary['input_hashes'].items():
        if file_hash(Path(name)) != sha: raise ValueError('canary implementation/input changed')
    copies = {'recorded-trades/result.json':index/'result.json', 'recorded-trades/claim.json':index/'claim.json',
              'recorded-trades/events.npz':index/'events.npz', 'recorded-trades/audit/audit.json':audit,
              'recorded-trades/audit/claim.json':audit.parent/'claim.json',
              'recorded-trades/window-canary.json':canary/'result.json',
              'recorded-trades/window-canary-claim.json':canary/'claim.json'}
    for name, path in copies.items():
        target = output/name; target.parent.mkdir(parents=True,exist_ok=True)
        before = file_hash(path); shutil.copyfile(path,target)
        if file_hash(path) != before or file_hash(target) != before:
            raise ValueError('recorded-event source changed during freeze')
    return {'bindings':binding, 'canary_sha256':file_hash(canary/'result.json'),
            'independent_window_comparisons':check['independent_window_comparisons'],
            'researcher_selects_all_parameters':True, 'new_dates_or_labels':False,
            'limits':load(index/'result.json')['limits'],
            'attachment_note':'The stored-event index is now available to the feature library. Prior index text saying not connected describes its build time, not this attachment. Only recorded flow, not depth or complete exchange tape.'}


def require_recorded_compatibility(old, current):
    if (old/'recorded-trades').exists():
        if any(not (current/n).is_file() or file_hash(old/n)!=file_hash(current/n) for n in RECORDED_FILES):
            raise ValueError('prior recorded-event context changed or disappeared')


def prepare_workspace(output, *, controller, input_cache, labels, session_id, experiment_id, prior_failed_session=None,
                      prior_completed_session=None, prior_result_audit=None, prior_pairing_audit=None,
                      recorded_index=None, recorded_audit=None, recorded_canary=None, prior_unsubmitted_session=None,
                      prior_error_balance_audit=None):
    if (prior_failed_session is not None and prior_completed_session is not None
            or (prior_completed_session is None)!=(prior_result_audit is None)):
        raise ValueError('choose a failed-interface continuation OR an audited completed diagnostic')
    identifier(session_id); identifier(experiment_id)
    prior = controller/'workspace'; assessment = load(controller/'session/assessment.json')
    if assessment.get('valid') is not True or assessment.get('process_reaped') is not True or not assess_objective(prior)['valid']:
        raise ValueError('completed valid prior objective controller required')
    label_result = load(labels/'result.json'); _signed(label_result,'result_sha256')
    query = label_result['primary_query_id']; identifier(query)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name in ['features','trials']: (output/name).mkdir()
    copies = {'input-result.json':input_cache/'result.json','current-inputs.npz':input_cache/'current-inputs.npz',
        'label-result.json':labels/'result.json','primary-labels.npz':labels/(query+'.npz'),
        'panel-result.json':prior/'panel-result.json','objective-proposal.json':prior/'frozen-grid-objective-proposal.json',
        'data-use-proposal.json':prior/'data-use-proposal.json'}
    for name,path in copies.items():
        sha=file_hash(path); shutil.copyfile(path,output/name)
        if file_hash(path)!=sha or file_hash(output/name)!=sha:raise ValueError('source changed during input freeze')
    recorded = None
    if any(v is not None for v in (recorded_index,recorded_audit,recorded_canary)):
        if any(v is None for v in (recorded_index,recorded_audit,recorded_canary)):
            raise ValueError('all recorded-index/audit/canary arguments required')
        recorded = attach_recorded_events(output,recorded_index,recorded_audit,recorded_canary,prior_completed_session)
    elif prior_completed_session is not None and (prior_completed_session/'workspace/recorded-trades').exists():
        for name in RECORDED_FILES:
            target=output/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(prior_completed_session/'workspace'/name,target)
        require_recorded_compatibility(prior_completed_session/'workspace',output)
        recorded=load(prior_completed_session/'workspace/archive.json')['recorded_event_extension']
    archive={'prior_controller_id':controller.name,
        'objective_assessment_sha256':file_hash(controller/'session/assessment.json'),
        'objective_activity_sha256':file_hash(prior/'objective-activity.jsonl'),
        'first_valid_objective_decision':load(prior/'submitted-grid-objective-decision.json'),
        'source_limitations':load(prior/'data-use-proposal.json')['plan'].get('limitations',''),
        'prior_feature_ideas':load(prior/'data-use-proposal.json')['plan'].get('feature_ideas',[]),
        'code_adaptation':'New signed-delta learning adapter after completed labelled/current-input materialization; old runs preserved.',
        'fresh_holdout':False}
    if recorded is not None: archive['recorded_event_extension'] = recorded
    if prior_failed_session is not None:
        evidence=failed_pre_fit_evidence(prior_failed_session,output)
        oldroot=prior_failed_session/'workspace'
        archive['interface_repair']={'failed_session_id':prior_failed_session.name,
            'assessment_sha256':file_hash(prior_failed_session/'session/assessment.json'),
            'activity_sha256':file_hash(oldroot/'learning-activity.jsonl'),
            'cause':'Underdocumented tool arguments caused repeated pre-fit failures; exact requests/errors are preserved in verified history.',
            'fix':'Full plan/feature schema, exact initial parent empty string and field-specific errors are now visible. No scientific value substituted.',
            'first_unexecuted_request':evidence['first_unexecuted_request'],
            'verified_failure_history':evidence['history'],
            'successful_feature_profiles_reused_without_recomputation':evidence['profiles'],
            'prior_trial_or_selection_imported':False,'new_evidence_is_interface_repair_not_score_retry':True}
    if prior_completed_session is not None:
        archive['completed_diagnostic']=carry_completed_diagnostic(prior_completed_session,prior_result_audit,output)
        # Recompute sign counts from verified saved profiles, not controller prose.
        archive['numeric_profile_sign_counts'] = [
            {'query_id':p['query_id'],'result_sha256':p['result_sha256'],
             'date_count':len(p['diagnostic']['by_date']),
             'negative_dates':{metric:sum(v.get(metric) is not None and v[metric]<0
                  for v in p['diagnostic']['by_date'].values()) for metric in ('pearson_ic','rank_ic')}}
            for p in archive['completed_diagnostic']['successful_feature_profiles_reused_without_recomputation']]
        archive['reporting_guardrail'] = 'Use original numeric per-date profiles. Negative Pearson and rank counts can differ. Use inspect_learning_trial for the actual parent feature diff, missingness and quiet-row denominators. Tested candidates do not falsify all models or all data. Pre-projection predictions were not saved, so never claim clipping changed zero values from the scorer alone.'
    if prior_pairing_audit is not None:
        archive['pairing_audit']=pairing_audit_evidence(prior_pairing_audit,prior_completed_session,output)
    if prior_error_balance_audit is not None:
        archive['prediction_error_balance']=error_balance_evidence(prior_error_balance_audit,prior_completed_session,output)
    if prior_unsubmitted_session is not None:
        if prior_completed_session is None:raise ValueError('protocol closure requires the last audited valid parent')
        archive['terminal_protocol_recovery']=inspection_failure_evidence(prior_unsubmitted_session,prior_completed_session)
    input_result=load(output/'input-result.json')
    if input_result.get('schema')=='historical_direction_input_extension_v1':
        archive['input_extension']={
            'result_sha256':input_result['result_sha256'],
            'proof':input_result['compatibility'],
            'source_semantics':input_result['source_extension']['direction_contract'],
            'limitations':input_result['limitations'],
            'reason':'Raw source fields omitted by the earlier projection were independently verified and exposed additively.',
            'scientific_choices_not_overridden':True,
            'previous_conclusion_correction':'Two particular models, one with changed algorithm/normalizer/support, do not prove no learnable content or isolate missingness as the cause. No new score was used to choose these raw fields.'}
    fresh_json(output/'archive.json',archive)
    papers = PAPERS + [
        {'paper_id':'sklearn16-ridge','title':'Ridge — scikit-learn1.6.1 API documentation',
         'url':'https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.Ridge.html',
         'synopsis':'Squared-error linear regression plus alpha times squared coefficient norm. SVD solver does not use tolerance.',
         'transfer_limit':'Regularization and normalizer must be specified; a linear model may miss nonlinear relations.'},
        {'paper_id':'sklearn16-elasticnet','title':'ElasticNet — scikit-learn1.6.1 API documentation',
         'url':'https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.ElasticNet.html',
         'synopsis':'Linear squared-error regression with mixed L1/L2 penalty. Alpha and l1_ratio jointly define the penalties.',
         'transfer_limit':'Feature scaling affects penalty strength; alpha0/l1_ratio near0 have documented solver caveats.'},
        {'paper_id':'sklearn16-histgb','title':'HistGradientBoostingRegressor — scikit-learn1.6.1 API documentation',
         'url':'https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html',
         'synopsis':'Histogram-based gradient boosting regressor learns routing for missing values (NaN) from the training data. If a feature has no missing training values, unseen missing values follow the child with more samples. Automatic early stopping can reserve a validation subset.',
         'transfer_limit':'This adapter disables automatic early stopping/random validation. Native-NaN mode is explicitly researcher-selected with normalizer none; it does not repair source data or prove missingness is informative.'}]
    fresh_json(output/'literature.json',{'mode':'frozen_primary_source_notes_not_live_search','papers':papers})
    fresh_json(output/'workspace.json',{'schema':'historical_grid_learning_workspace_v1',
        'session_id':session_id,'experiment_id':experiment_id,
        'files':{name:file_hash(output/name) for name in FILES | (RECORDED_FILES if recorded is not None else set())},'dev_present':False,'test_present':False})
    validate_workspace(output); read_inputs(output)
    return load(output/'workspace.json')


def validate_workspace(root):
    manifest=load(root/'workspace.json')
    if (manifest.get('schema')!='historical_grid_learning_workspace_v1' or set(manifest['files']) not in (FILES,FILES|RECORDED_FILES)
            or manifest.get('dev_present') is not False or manifest.get('test_present') is not False):
        raise ValueError('isolated opened-Train workspace required')
    for name,sha in manifest['files'].items():
        if (root/name).is_symlink() or any((root/p).is_symlink() for p in Path(name).parents if p!=Path('.')) or file_hash(root/name)!=sha:raise ValueError('frozen learning input changed')
    if (root/'recorded-trades').exists() != (RECORDED_FILES <= set(manifest['files'])):
        raise ValueError('unmanifested or missing recorded-event capability')
    return manifest


def verify_conditional_queries(root):
    """Keep successful and failed query claims across sessions; never reset slots."""
    parent = root/'conditional-diagnostics'
    if not parent.exists(): return []
    if parent.is_symlink(): raise ValueError('conditional directory may not be a symlink')
    results = []
    for path in sorted(parent.iterdir()):
        identifier(path.name)
        if path.is_symlink() or not path.is_dir(): raise ValueError('invalid conditional query path')
        claim = load(path/'claim.json')
        trial = load(root/'trials'/claim['arguments']['trial_id']/'result.json')
        _signed(trial,'result_sha256')
        if (claim['trial_result_sha256'] != trial['result_sha256']
                or claim['input_hashes'] != {n:file_hash(root/n) for n in ('current-inputs.npz','primary-labels.npz')}
                or claim['arguments']['query_id'] != path.name):
            raise ValueError('conditional query binding changed')
        entry = {'query_id':path.name,'claim_sha256':file_hash(path/'claim.json')}
        if (path/'result.json').exists():
            result = load(path/'result.json'); _signed(result,'result_sha256')
            if (result['claim_sha256'] != entry['claim_sha256']
                    or result['trial_result_sha256'] != claim['trial_result_sha256']):
                raise ValueError('conditional diagnostic result changed')
            entry['result'] = result
        elif (path/'failure.json').exists():
            entry['failure'] = load(path/'failure.json')
        else:
            raise ValueError('conditional query is incomplete')
        results.append(entry)
    return results


class Broker:
    def __init__(self,root):
        self.root=root; validate_workspace(root); self.inputs=read_inputs(root)

    def call(self,name,args):
        validate_workspace(self.root)
        if (self.root/'submitted-grid-learning-decision.json').exists():raise ValueError('decision already submitted; stop')
        if name not in ALLOWED_TOOLS:raise ValueError('unknown learning tool')
        try:
            recovery=load(self.root/'archive.json').get('terminal_protocol_recovery')
            if recovery:
                verify_recovery_files(recovery)
                if name in {'profile_feature','evaluate_learning_plan','diagnose_feature_controls'}:
                    raise ValueError('protocol closure only: no new feature profiles or model fits; inspect existing artifacts and submit your decision')
            fields=next(t['inputSchema']['properties'] for t in TOOLS if t['name']==name)
            if not isinstance(args,dict) or set(args)!=set(fields) or len(canonical(args).encode())>40000:
                raise ValueError('exact bounded tool arguments required')
            result=self._call(name,args)
        except Exception as exc:
            append_activity(self.root/'learning-activity.jsonl',{'tool':name,'arguments':args,'status':'error','error':str(exc)})
            raise
        append_activity(self.root/'learning-activity.jsonl',{'tool':name,'arguments':args,'status':'ok','result':result})
        return result

    def _inspected(self):
        events=read_activity_events(self.root/'learning-activity.jsonl')
        seen={e['tool'] for e in events if e['status']=='ok'}
        if not {'inspect_learning_contract','inspect_learning_library'}<=seen:
            raise ValueError('inspect contract and library before research')
        return events

    def _trial(self,name):
        identifier(name);path=self.root/'trials'/name
        result=load(path/'result.json');_signed(result,'result_sha256')
        if (result['claim_sha256']!=file_hash(path/'claim.json')
                or result['predictions_sha256']!=file_hash(path/'predictions.npz')):
            raise ValueError('trial result or prediction artifact changed')
        return result

    def _call(self,name,a):
        i=self.inputs;x=i['x'];y=i['y']
        if name=='inspect_learning_contract':
            return {'objective':i['objective'],'population_rows':len(x['row_id']),
                'opened_train_dates':sorted(set(x['date'])),'source_inputs':i['input_result'],
                'archive':load(self.root/'archive.json'),'new_dev_test_available':False,
                'raw_feature_stats_include_all_opened_train':True,'check_scores_are_not_fresh_holdout':True,
                'recorded_event_binding':i.get('recorded_event_binding'),
                'available_parent_trial_ids':[p.name for p in sorted((self.root/'trials').iterdir()) if (p/'result.json').exists()],
                'frozen_protocol':load(self.root/'protocol.json') if (self.root/'protocol.json').exists() else None}
        if name=='inspect_learning_library':
            return {'feature_fields':sorted(FIELDS),'transforms':sorted(TRANSFORMS),
                'composition':{'fields':sorted(COMPOSITION_FIELDS),'operators':sorted(OPERATORS),
                    'max_depth':MAX_DEPTH,'max_primitive_leaves':MAX_LEAVES,
                    'sum':'sum2..4 chosen operands','difference':'first minus second of exactly2 operands',
                    'product':'multiply2..4 chosen operands',
                    'operands':'Each operand is a primitive spec or bounded nested composition; no hidden formula or coefficient.',
                    'missing':'Every operand must be present; zero times missing remains missing.',
                    'timing':'Compose already-causal same-row primitives. This is not all-trade window aggregation.'},
                'recorded_event_windows':{'attached':'recorded_events' in i,'fields':sorted(RECORDED_FIELDS),
                    'source':RECORDED_SOURCE,'statistics':RECORDED_STATISTICS,'schema':RECORDED_SCHEMA,
                    'parameters':'Choose every parameter yourself: window1ms..1day, minimum_records1..8000000, maximum_recorded_gap_ms1..window. No defaults.',
                    'timing':'ALL recorded rows in receipt interval(t-window,t]; every event must already be available; all same-ms ties retained. May compose with existing grid features.',
                    'missing':'Whole window unknown for unopened context, unobserved beginning, insufficient count, excessive recorded gap or invalid record. Zero denominators unknown. Empty is not zero.',
                    'limits':'Recorded-feed gap proxy is not exchange completeness. Maker0 may include publisher defaults. No book depth, PnL or new dates.'},
                'formulas':{'identity':'current source value','log1p':'log(1+x), x>=0 else unknown',
                    'square':'current source squared','lag_delta':'current minus exact same-entity value at t-lookback',
                    'lag_log_return':'log(current)-log(exact past), both positive else unknown',
                    'trailing_mean_delta':'current minus uniform mean of observed points t-lookback..t',
                    'trailing_std':'population std of observed points t-lookback..t, centred before aggregation'},
                'feature_requirements':'point lookback0/count1/coverage1; lag positive/count2/coverage1; trailing positive aligned lookback, explicit mincount/coverage; max256 gridpoints/1day',
                'model_fields':{k:sorted(v) for k,v in MODEL_FIELDS.items()},'plan_fields':sorted(PLAN_FIELDS),
                'model_schema':MODEL_SCHEMA,'feature_schema':FEATURE_SCHEMA,'plan_schema':PLAN_SCHEMA,
                'evaluate_learning_plan_arguments':next(t['inputSchema'] for t in TOOLS if t['name']=='evaluate_learning_plan'),
                'initial_parent_trial_id':'' if not (self.root/'protocol.json').exists() else None,
                'initial_parent_rule':PARENT_SCHEMA['description'],
                'available_parent_trial_ids':[p.name for p in sorted((self.root/'trials').iterdir()) if (p/'result.json').exists()],
                'rationale_rule':'plan.rationale must be a nonempty explanation; empty text is invalid, independently of model hyperparameters.',
                'fixed_implementation_settings':{'ridge':'SVD solver; squared error plus L2; no coefficient sign constraint',
                    'elastic_net':'cyclic coordinate selection; no warm start; L1/L2 squared-error regression',
                    'random_forest':'single worker, squared_error criterion, bootstrap=True; no warm start',
                    'hist_gradient_boosting':'squared_error loss, max_bins255, no early stopping or random validation, no warm start',
                    'all':'sklearn1.6.1 defaults for remaining library mechanics are recorded in effective_estimator_parameters; request an extension to vary unsupported settings'},
                'model_limits':'alpha0..1e6; l1_ratio0..1; elastic max_iter1..10000,tol1e-12..1; forest trees1..128,depth1..12,minleaf1..10000,max_features(0,1]; hist lr(0,1],iter1..256,leaves2..64,l2 0..1e6,minleaf1..10000',
                'normalizer':['none','fit_mean_std'],'train_weighting':['equal_row','equal_day','equal_market'],
                'score_aggregation':['equal_row','equal_day','equal_group'],'missing_input_action':['persistence','native_nan'],
                'native_nan_requirements':'Only hist_gradient_boosting with normalizer none. All eligible Train/check rows enter the model, including unknown inputs. NaNs remain NaN; no source filling. Report missing-input fit/check counts. Native handling is an available capability, not a selected algorithm.',
                'trial_explanations':'inspect_learning_trial reads original artifacts and derives feature availability only: actual parent additions/removals, per-feature missingness, exact quiet-row denominators, and projection evidence limits. No fit, new score, imputation, or automatic feature selection.',
                'conditional_diagnostics':{'tool':'diagnose_feature_controls',
                    'selection':'Choose a feature and zero to twelve other controls by exact names from one completed trial. No automatic subset or model choice.',
                    'method':'Four equal-row nuisance regressions, candidate and target in raw and prior-midpoint-ECDF spaces, fit on earlier causal complete cases only. Check uses fixed fits.',
                    'reports':'Paired-support raw Pearson/rank and prior-fit residual correlations, residual variance, prior collinearity, date/market breadth and all missing-support counts.',
                    'limits':'Not classical same-check partial Spearman, no fitted prediction score, uncertainty interval or causal verdict. All six dates remain opened Train. Existing model slots and scores do not change.',
                    'claimed_queries':verify_conditional_queries(self.root),'total_query_limit':16},
                'output_transform':['none','clip_to_probability_delta_bounds'],'seed':23,
                'protocol':'partition ALL opened Train dates chronologically; purge labels at/after first check UTC day and any whole market spanning check; no random validation/early stopping',
                'comparisons':'freeze split/aggregation at first trial; change only features OR prediction/training relative to a completed parent',
                'limits':{'feature_queries':32,'model_trials':8,'features_per_model':24,
                    'session_total_tool_calls':32,'reserve_at_least_one_call_for_terminal_submission':True},
                'additional_raw_fields':i['input_result'].get('compatibility',{}).get('added_fields',[]),
                'raw_direction_limit':'If present, the new fields are latest source-reported maker/amount/token roles, not window-aggregated signed flow; maker0 can be publisher default. Inspect the input contract.',
                'unimplemented':['arbitrary generated Python','neural learner training','full book depth','new Dev/Test','Train subsampling/curriculum']
                    + ([] if 'recorded_events' in i else ['all-recorded-trade windows are not attached to this workspace'])}
        if name=='search_public_literature':
            if not isinstance(a['query'],str) or not a['query'].strip():raise ValueError('search query required')
            catalog=load(self.root/'literature.json');terms=a['query'].lower().split()
            papers=sorted(catalog['papers'],key=lambda p:-sum(t in canonical(p).lower() for t in terms))
            return {'mode':catalog['mode'],'papers':papers[:5]}
        if name=='profile_feature':
            self._inspected();identifier(a['query_id']);validate_feature(a['spec'],i['names'],i['cadence_ms'])
            if not isinstance(a['rationale'],str) or not a['rationale'].strip():raise ValueError('feature rationale required')
            if len(list((self.root/'features').iterdir()))>=32:raise ValueError('feature query budget reached')
            root=self.root/'features'/a['query_id'];root.mkdir(exist_ok=False)
            fresh_json(root/'claim.json',{'spec':a['spec'],'rationale':a['rationale'],
                'objective_sha256':i['objective']['proposal_sha256'],'frozen_before_execution':True})
            derived=derive(x['entity'],x['decision_ms'],x['values'],i['names'],spec=a['spec'],cadence_ms=i['cadence_ms'],recorded_events=i.get('recorded_events'))
            report=raw_feature_diagnostic(derived['values'],y['delta_probability'],y['available'],x['date'])
            result={'query_id':a['query_id'],'claim_sha256':file_hash(root/'claim.json'),
                'spec':a['spec'],'diagnostic':report,'feature_engine_sha256':feature_engine_sha256(a['spec'])}
            if contains_recorded(a['spec']):
                result['recorded_event_binding'] = i['recorded_event_binding']
                result['missing_reason_counts'] = ({name:int(np.count_nonzero(derived['reason']==code))
                    for name,code in derived['reason_codes'].items()} if 'reason' in derived else 'all composed operands required')
            result['result_sha256']=digest(result);fresh_json(root/'result.json',result);return result
        if name=='evaluate_learning_plan':
            events=self._inspected();identifier(a['trial_id']);validate_plan(a['plan'],i)
            current_profiles=[e['result'] for e in events if e['tool']=='profile_feature' and e['status']=='ok']
            prior_profiles=archived_profiles(load(self.root/'archive.json'))
            missing=missing_profiles(a['plan']['features'],current_profiles+prior_profiles)
            if missing:raise ValueError('profile every selected feature before fitting; exact missing specs: '+canonical(missing)+
                '. Cosmetic names are part of the frozen spec. Reuse the original exact profiled spec or explicitly profile your new spec; no automatic rewrite or fit occurred.')
            roots=list((self.root/'trials').iterdir())
            if len(roots)>=8:raise ValueError('model trial budget reached')
            fingerprint=digest({k:v for k,v in a['plan'].items() if k!='rationale'})
            for path in roots:
                claim=load(path/'claim.json')
                if claim['semantic_plan_sha256']==fingerprint:raise ValueError('duplicate scientific trial; never retry for score')
            protocol={k:a['plan'][k] for k in ['train_utc_dates','check_utc_dates','score_aggregation']}
            if (self.root/'protocol.json').exists():
                if load(self.root/'protocol.json')!=protocol:raise ValueError('Train/check boundary or metric changed after first trial')
                parent=self._trial(a['parent_trial_id']);old=parent['plan']
                feature_changed=old['features']!=a['plan']['features']
                predictor_changed=any(old[k]!=a['plan'][k] for k in ['model','normalizer','train_weighting','missing_input_action','output_transform'])
                if feature_changed and predictor_changed:raise ValueError('change one stage only relative to the declared parent')
                stage='raw_features' if feature_changed else 'prediction_training'
            else:
                if a['parent_trial_id']!='':
                    raise ValueError('First trial requires parent_trial_id="" (the EMPTY STRING). '
                                     'Do not send "none", "null", or a guessed trial ID: no completed parent exists yet.')
                stage='initial_reference';fresh_json(self.root/'protocol.json',protocol)
            root=self.root/'trials'/a['trial_id'];root.mkdir(exist_ok=False)
            fresh_json(root/'claim.json',{'plan':a['plan'],'semantic_plan_sha256':fingerprint,
                'parent_trial_id':a['parent_trial_id'],'stage_changed':stage,'frozen_before_execution':True,
                'prior_feature_evidence':{p['query_id']:p['result_sha256'] for p in prior_profiles if any(p['spec']==f for f in a['plan']['features'])},
                'objective_sha256':i['objective']['proposal_sha256']})
            try:
                from threadpoolctl import threadpool_limits
                with threadpool_limits(limits=1):report,arrays=evaluate(i,a['plan'])
                write_archive(root/'predictions.npz',arrays)
                result={'trial_id':a['trial_id'],'plan':a['plan'],'report':report,
                    'claim_sha256':file_hash(root/'claim.json'),'predictions_sha256':file_hash(root/'predictions.npz'),
                    'new_provider_calls_for_cpu_fit':0,'fresh_holdout':False}
                result['result_sha256']=digest(result);fresh_json(root/'result.json',result);return result
            except Exception as exc:
                fresh_json(root/'failure.json',{'error':str(exc),'no_automatic_retry':True});raise
        if name=='inspect_learning_trial':
            self._inspected();trial=self._trial(a['trial_id'])
            root=self.root/'trials'/a['trial_id'];claim=load(root/'claim.json')
            parent=self._trial(claim['parent_trial_id']) if claim['parent_trial_id'] else None
            with np.load(root/'predictions.npz',allow_pickle=False) as saved:
                arrays={k:saved[k] for k in saved.files}
            return diagnose(i,trial,arrays,parent)
        if name=='diagnose_feature_controls':
            self._inspected(); identifier(a['query_id']); trial=self._trial(a['trial_id'])
            specs=validate_selection(trial,a['feature_name'],a['control_names'])
            if not isinstance(a['rationale'],str) or not a['rationale'].strip():
                raise ValueError('diagnostic rationale required')
            parent=self.root/'conditional-diagnostics'; parent.mkdir(exist_ok=True)
            prior=verify_conditional_queries(self.root)
            semantic=digest({'trial_result_sha256':trial['result_sha256'],
                'feature_name':a['feature_name'],'control_names':sorted(a['control_names'])})
            if len(prior)>=16:raise ValueError('conditional diagnostic query limit reached')
            if any(load(parent/p['query_id']/'claim.json')['semantic_sha256']==semantic for p in prior):
                raise ValueError('identical conditional diagnostic already claimed; reuse its result')
            root=parent/a['query_id']; root.mkdir(exist_ok=False)
            fresh_json(root/'claim.json',{'arguments':a,'semantic_sha256':semantic,
                'trial_result_sha256':trial['result_sha256'],'selected_specs_sha256':digest(specs),
                'input_hashes':{n:file_hash(self.root/n) for n in ('current-inputs.npz','primary-labels.npz')},
                'implementation_sha256':file_hash(Path(__file__).with_name('historical_conditional_diagnostics.py')),
                'frozen_before_execution':True})
            try:
                from threadpoolctl import threadpool_limits
                with threadpool_limits(limits=1):
                    result=diagnose_conditional(i,trial,a['feature_name'],a['control_names'])
                result.update({'query_id':a['query_id'],'claim_sha256':file_hash(root/'claim.json')})
                result['result_sha256']=digest(result);fresh_json(root/'result.json',result);return result
            except Exception as exc:
                fresh_json(root/'failure.json',{'error':str(exc),'no_automatic_retry':True});raise
        if name=='submit_grid_learning_decision':
            self._inspected()
            if not isinstance(a['reason'],str) or not a['reason'].strip():raise ValueError('decision reason required')
            if a['action']=='select':
                trial=self._trial(a['trial_id']);fresh_json(self.root/'frozen-grid-learning-plan.json',trial)
            elif a['action']!='defer':raise ValueError('select or defer required')
            fresh_json(self.root/'submitted-grid-learning-decision.json',a)
            return {'submitted':True,'bytes':len(canonical(a).encode()),'action':a['action'],'fresh_holdout':False}
        raise ValueError('unknown tool')


def assess_activity(root):
    validate_workspace(root);log=verify_activity_log(root/'learning-activity.jsonl')
    events=read_activity_events(root/'learning-activity.jsonl')
    decisions=[e for e in events if e['tool']=='submit_grid_learning_decision' and e['status']=='ok']
    if (len(decisions)!=1 or events[-1]!=decisions[0]
            or load(root/'submitted-grid-learning-decision.json')!=decisions[0]['arguments']):
        raise ValueError('exact first terminal learning decision required')
    broker=Broker(root)
    verify_conditional_queries(root)
    for event in events:
        if event['tool']=='evaluate_learning_plan' and event['status']=='ok':
            if broker._trial(event['arguments']['trial_id'])!=event['result']:raise ValueError('logged trial result changed')
        if event['tool']=='profile_feature' and event['status']=='ok':
            p=root/'features'/event['arguments']['query_id']
            if load(p/'result.json')!=event['result'] or file_hash(p/'claim.json')!=event['result']['claim_sha256']:
                raise ValueError('logged feature query changed')
        if event['tool']=='diagnose_feature_controls' and event['status']=='ok':
            p=root/'conditional-diagnostics'/event['arguments']['query_id']
            if load(p/'result.json')!=event['result']:
                raise ValueError('logged conditional diagnostic changed')
    if decisions[0]['arguments']['action']=='select':
        if load(root/'frozen-grid-learning-plan.json')!=broker._trial(decisions[0]['arguments']['trial_id']):
            raise ValueError('selected learning trial changed')
    return {'valid':True,'log':log,'action':decisions[0]['arguments']['action'],'fresh_holdout':False}


def serve(broker):
    from data_discovery_tools_mcp import reply
    for line in sys.stdin:
        request=None
        try:
            request=json.loads(line);method=request.get('method');rid=request.get('id')
            if method=='initialize':reply(rid,{'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'historical-grid-learning','version':'1'}})
            elif method=='ping':reply(rid,{})
            elif method=='tools/list':reply(rid,{'tools':TOOLS})
            elif method=='tools/call':
                p=request.get('params',{})
                try:value=broker.call(p.get('name'),p.get('arguments',{}));failed=False
                except Exception as exc:value={'accepted':False,'message':str(exc)};failed=True
                reply(rid,{'content':[{'type':'text','text':canonical(value)}],'isError':failed})
        except Exception as exc:
            if request and 'id' in request:reply(request['id'],error={'code':-32603,'message':str(exc)})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True)
    serve(Broker(p.parse_args().workspace))
