"""Train-only GLM objective research over the audited recorded-quote grid.

No fit, execution, Dev or Test capability. Every objective query and the first
decision are retained. Quiet/missing rows stay in full-population diagnostics.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

import numpy as np

from controller_activity_log import append_activity, read_activity_events, verify_activity_log
from historical_grid_objectives import FAMILIES, SPEC_FIELDS, GridPanel, profile, validate_spec
from historical_ingest_controller import _signed, _tool, load
from market_rsi import canonical, digest, file_hash, fresh_json, identifier


BASE_INSTRUCTIONS=(
    'You are the GLM researcher in the existing Codex harness. Choose a defensible forecasting '
    'objective using only the audited open Train recorded-quote grid and public literature. '
    'The data-use decision is already yours and is now executed: six open dates, a minute grid, '
    'a five-minute source-age cap and broad observed-arrival scope, with phase/quality annotations. '
    'Do not silently change these upstream parameters. You choose objective horizon, smoothing, '
    'label freshness/coverage and primary metric, or defer for a concrete extension. Inspect the '
    'data and definitions before requesting profiles. Each query defines its parameters BEFORE '
    'its Train-only result is opened. Smaller target variance or persistence MSE is NOT predictive '
    'skill or proof of denoising; explain what is being predicted and why. Report full population, '
    'missing labels, per-date and nominal-phase coverage; do not select rows by future movement. '
    'Our grid quotes are not a verified executable tape, PM trades or settlement outcomes. '
    'Basis points here are ABSOLUTE probability units, not relative financial returns. '
    'Forward averages/medians/EWMA are future LABELS only, never causal input features. '
    'The supported functions are a library, not a requirement that one is scientifically useful. '
    'A literature tool searches runner-frozen primary-source notes, NOT live web/full-paper access. '
    'No learned model, Dev, Test, download or PnL scoring is available. These dates are already '
    'opened and never fresh holdout. Select one primary objective and optional diagnostics, '
    'or defer with exact missing functionality. Submit the first valid decision and exit. '
    'This is an objective contract, not automatic authorization of a formal experiment.'
)

PAPERS=[
    {'paper_id':'deeplob-v6','title':'DeepLOB: Deep Convolutional Neural Networks for Limit Order Books',
     'url':'https://arxiv.org/html/1808.03668v6','section':'III-C; primary full-text section inspected 2026-09-10 UTC',
     'synopsis':'Compares future-average-minus-current and future-average-minus-past-average relative midpoint labels. '
        'Uses event-indexed windows and a direction threshold; the LSE experiment uses the latter construction. '
        'The paper warns that ten days alone is insufficient for robust generalization claims.',
     'transfer_limit':'Our minute grid, absolute probability delta and missing-data rules are adaptations, not the paper recipe. '
        'Past-average anchoring and direction thresholds are not implemented in the current registry.'},
    {'paper_id':'hyndman-koehler-2006','title':'Another look at measures of forecast accuracy',
     'url':'https://robjhyndman.com/publications/another-look-at-measures-of-forecast-accuracy/',
     'section':'Author publication page and synopsis inspected 2026-09-10 UTC',
     'synopsis':'Discusses degeneracies in commonly used forecast metrics and proposes mean absolute scaled error for comparing series.',
     'transfer_limit':'A same-row persistence skill ratio is not identical to MASE. Scaling cannot create predictability; '
        'a zero baseline error makes a ratio undefined. No universal horizon is supplied.'},
    {'paper_id':'jacod-et-al-2009','title':'Microstructure noise in the continuous case: The pre-averaging approach',
     'url':'https://galton.uchicago.edu/~mykland/paperlinks/preaveraging.pdf',
     'section':'Author-hosted published paper abstract inspected 2026-09-10 UTC',
     'synopsis':'Develops pre-averaging estimators of integrated volatility in a noisy continuous-price setting.',
     'transfer_limit':'This is not evidence that a simple forward moving average is an unbiased efficient-price label '
        'for sampled binary-contract quotes. Noise estimation and the paper estimator are not implemented.'},
]

METRICS={
    'mse_skill_vs_persistence':'1 - model same-row MSE / zero-delta same-row MSE; undefined when baseline MSE is zero',
    'mae_skill_vs_persistence':'1 - model same-row MAE / zero-delta same-row MAE; undefined when baseline MAE is zero',
    'mse_probability':'mean squared error in absolute probability units; report persistence alongside',
    'mae_probability_bps':'mean absolute error times10000; absolute probability basis points, not relative returns',
}


def read_panel(root):
    result=load(root/'panel-result.json');_signed(result,'result_sha256')
    path=root/'unlabelled-grid.npz'
    if (result.get('schema')!='historical_unlabelled_grid_panel_v1' or result.get('complete') is not True
            or result.get('target_computed') is not False or result.get('target_selected') is not False
            or result.get('training_admitted') is not False or result.get('fresh_holdout') is not False
            or result.get('all_grid_rows_retained') is not True or file_hash(path)!=result['panel_sha256']):
        raise ValueError('intact complete unlabelled open-Train panel required')
    expected={'entity','time_ms','midpoint','quote_age_ms','date','phase','row_id','cadence_ms','max_age_ms'}
    with zipfile.ZipFile(path) as archive:
        if set(archive.namelist())!={name+'.npy' for name in expected} or sum(x.file_size for x in archive.infolist())>300000000:
            raise ValueError('bounded numeric panel archive required')
    with np.load(path,allow_pickle=False) as archive:
        arrays={name:archive[name] for name in expected}
    panel=GridPanel(**{name:arrays[name] for name in ['entity','time_ms','midpoint','quote_age_ms','date','phase']},
        cadence_ms=int(arrays['cadence_ms']),max_age_ms=int(arrays['max_age_ms']))
    panel.validate();summary=result['summary'];n=len(panel.time_ms)
    if (n!=summary['rows'] or len(arrays['row_id'])!=n or len(set(arrays['row_id']))!=n
            or dict(Counter(panel.date))!=summary['by_open_train_date']
            or dict(Counter(panel.phase))!=summary['by_nominal_phase']
            or int(np.isfinite(panel.midpoint).sum())!=summary['finite_midpoint_rows']
            or len(set(panel.entity))!=summary['entities']):raise ValueError('cached panel population mismatch')
    return panel,arrays['row_id'],result


def numerical_feedback(audit_directory,previous_controller,panel_result):
    audit=load(audit_directory/'audit.json');_signed(audit,'audit_sha256')
    claim=load(audit_directory/'claim.json')
    chosen_path=previous_controller/'workspace/frozen-grid-objective-proposal.json'
    chosen=load(chosen_path);_signed(chosen,'proposal_sha256')
    assessment=load(previous_controller/'session/assessment.json')
    input_hashes={(Path(path) if Path(path).is_absolute() else Path(__file__).resolve().parents[2]/path).resolve():sha
        for path,sha in claim['input_hashes'].items()}
    if (audit.get('audit_pass') is not True or assessment.get('valid') is not True or assessment.get('process_reaped') is not True
            or audit['claim_sha256']!=file_hash(audit_directory/'claim.json')
            or audit['proposal_sha256']!=chosen['proposal_sha256']
            or claim['panel_sha256']!=panel_result['panel_sha256']
            or claim['new_engine_sha256']!=file_hash(Path(__file__).with_name('historical_grid_objectives.py'))
            or chosen_path.resolve() not in input_hashes):
        raise ValueError('matching corrected evidence and original first decision required')
    for path,sha in input_hashes.items():
        if previous_controller.resolve() not in path.parents or file_hash(path)!=sha:
            raise ValueError('original numerical-audit input changed or escaped the prior controller')
    corrections=[]
    for item in audit['corrections']:
        identifier(item['query_id']);correction=load(audit_directory/(item['query_id']+'.json'));_signed(correction,'correction_sha256')
        if correction['correction_sha256']!=item['correction_sha256']:raise ValueError('correction hash changed')
        corrections.append(correction)
    return {'new_evidence_not_a_score_retry':True,'audit':audit,'corrections':corrections,
        'original_first_decision':chosen,'original_assessment_harness_valid':True,
        'original_choice_not_executed_for_training':True,
        'instruction':'Inspect corrected unchanged/constant-path fractions and named-horizon corrections before revising or retaining your objective. '
            'Data, query specs and coverage did not change. Do not defend the old incorrect statistics or treat smaller variance as prediction skill.'}


def prepare_workspace(output,*,panel_directory,proposal,annotations,session_id,experiment_id,
                      numerical_audit=None,previous_controller=None,prior_failed_session=None):
    identifier(session_id);identifier(experiment_id)
    result=load(panel_directory/'result.json');_signed(result,'result_sha256')
    chosen=load(proposal);_signed(chosen,'proposal_sha256')
    side=load(annotations/'result.json');_signed(side,'result_sha256')
    if (result['input_hashes']['proposal']!=file_hash(proposal)
            or result['input_hashes']['annotations']!=file_hash(annotations/'result.json')
            or side['proposal_sha256']!=chosen['proposal_sha256']):raise ValueError('matched data-use lineage required')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name in ['queries','proposals']: (output/name).mkdir()
    shutil.copyfile(panel_directory/'unlabelled-grid.npz',output/'unlabelled-grid.npz')
    fresh_json(output/'panel-result.json',result);fresh_json(output/'data-use-proposal.json',chosen)
    fresh_json(output/'annotations-result.json',side)
    fresh_json(output/'literature.json',{'mode':'frozen_primary_source_notes_not_live_search','papers':PAPERS})
    fresh_json(output/'constraints.json',{
        'stage':'open_train_objective_discovery','max_profile_queries':24,
        'no_dev_or_test':True,'no_model_fit':True,'no_new_download':True,'no_training_admission':True,
        'dates_already_opened':sorted(set(chosen['plan']['open_train_utc_dates']+['2026-02-22','2026-05-14'])),
        'full_population_diagnostics_required':True,'no_future_movement_filter':True,
        'nonzero_variance_is_not_noise_or_learnability_proof':True,'fresh_holdout':False})
    visible=['panel-result.json','unlabelled-grid.npz','data-use-proposal.json','annotations-result.json','literature.json','constraints.json']
    if (numerical_audit is None)!=(previous_controller is None):raise ValueError('both correction audit and previous controller required')
    if numerical_audit is not None:
        fresh_json(output/'numerical-feedback.json',numerical_feedback(numerical_audit,previous_controller,result))
        visible.append('numerical-feedback.json')
    if prior_failed_session is not None:
        failed=load(prior_failed_session/'session/assessment.json')
        events=read_activity_events(prior_failed_session/'workspace/objective-activity.jsonl')
        errors=[e for e in events if e['tool']=='propose_objective' and e['status']=='error']
        if (numerical_audit is None or failed.get('valid') is not False or failed.get('process_reaped') is not True
                or failed.get('unresolved_accounting') or len(errors)<3
                or any(e['error']!='bounded regular JSON input required' for e in errors)
                or (prior_failed_session/'workspace/submitted-grid-objective-decision.json').exists()):
            raise ValueError('exact completed missing-prior-query interface failure required')
        fresh_json(output/'interface-repair.json',{'failed_session_id':prior_failed_session.name,
            'assessment_sha256':file_hash(prior_failed_session/'session/assessment.json'),
            'activity_sha256':file_hash(prior_failed_session/'workspace/objective-activity.jsonl'),
            'repeated_failures':len(errors),'valid_prior_decision_imported':False,
            'cause':'Audited prior query IDs were visible in feedback but not registered as new-session query IDs.',
            'fix':'Explicit reuse_corrected_objective_query preserves audited target specs/results under fresh IDs; '
                'missing references now return actionable errors instead of a generic bounded-JSON error.',
            'purpose':'infrastructure repair continuation; not a retry to seek a higher score'})
        visible.append('interface-repair.json')
    fresh_json(output/'workspace.json',{'schema':'historical_grid_objective_workspace_v1','session_id':session_id,
        'experiment_id':experiment_id,'files':{name:file_hash(output/name) for name in visible},'dev_present':False,'test_present':False})
    validate_workspace(output);read_panel(output)
    return load(output/'workspace.json')


def validate_workspace(root):
    value=load(root/'workspace.json')
    expected={'panel-result.json','unlabelled-grid.npz','data-use-proposal.json','annotations-result.json','literature.json','constraints.json'}
    allowed=(expected,expected|{'numerical-feedback.json'},expected|{'numerical-feedback.json','interface-repair.json'})
    if (value.get('schema')!='historical_grid_objective_workspace_v1' or set(value['files']) not in allowed
            or value.get('dev_present') is not False or value.get('test_present') is not False):
        raise ValueError('isolated objective workspace required')
    for name,sha in value['files'].items():
        path=root/name
        if path.is_symlink() or not path.is_file() or file_hash(path)!=sha:raise ValueError('frozen objective input changed')
    return value


TEXT={'type':'string','minLength':1,'maxLength':12000}
SPEC_SCHEMA={'type':'object','description':'Exact fields and supported families returned by inspect_objective_registry.'}
TOOLS=[
    _tool('inspect_train_inventory','Read full population, missingness and clock/source limitations.'),
    _tool('inspect_objective_registry','Read supported objective specs, formulas, units, metrics and unavailable methods.'),
    _tool('inspect_numerical_correction','Read new arithmetic correction and the preserved prior objective decision when present.'),
    _tool('search_public_literature','Search frozen primary-source notes, not live web.',{'query':TEXT}),
    _tool('inspect_train_rows','Read bounded existing unlabelled Train rows in immutable order.',
        {'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':100}}),
    _tool('profile_objective','Freeze a complete query BEFORE computing Train-only coverage and persistence diagnostics.',
        {'query_id':TEXT,'spec':SPEC_SCHEMA,'rationale':TEXT}),
    _tool('reuse_corrected_objective_query','Reference an audited prior controller query under a fresh current-session ID; no recomputation.',
        {'source_query_id':TEXT,'query_id':TEXT,'rationale':TEXT}),
    _tool('propose_objective','Archive a proposed primary metric/target and optional diagnostic queries; no model fit.',
        {'proposal_id':TEXT,'primary_query_id':TEXT,'diagnostic_query_ids':{'type':'array','items':{'type':'string'},'maxItems':3},
         'primary_metric':{'type':'string','enum':list(METRICS)},'rationale':TEXT,'limitations':TEXT}),
    _tool('submit_grid_objective_decision','Submit first valid select/defer decision and exit.',
        {'action':{'type':'string','enum':['select','defer']},'proposal_id':{'type':'string'},'reason':TEXT})]
ALLOWED_TOOLS=tuple(tool['name'] for tool in TOOLS)


class Broker:
    def __init__(self,root):
        self.root=root;validate_workspace(root);self.panel,self.ids,self.result=read_panel(root)

    def call(self,name,arguments):
        validate_workspace(self.root)
        if (self.root/'submitted-grid-objective-decision.json').exists():raise ValueError('decision already submitted; stop')
        if name not in ALLOWED_TOOLS or not isinstance(arguments,dict):raise ValueError('unknown objective tool')
        try:
            fields=next(tool['inputSchema']['properties'] for tool in TOOLS if tool['name']==name)
            if set(arguments)!=set(fields) or len(canonical(arguments).encode())>40000:
                raise ValueError('exact bounded tool arguments required; no hidden filters or scope changes')
            value=self._call(name,arguments)
        except Exception as exc:
            append_activity(self.root/'objective-activity.jsonl',{'tool':name,'arguments':arguments,'status':'error','error':str(exc)})
            raise
        append_activity(self.root/'objective-activity.jsonl',{'tool':name,'arguments':arguments,'status':'ok','result':value})
        return value

    def _query(self,name):
        identifier(name)
        path=self.root/'queries'/name/'result.json'
        if not path.is_file():
            raise ValueError('No current-session query '+name+'. Call profile_objective with a fresh query_id, '
                'or reuse_corrected_objective_query to reference an audited prior query under a fresh ID.')
        value=load(path);_signed(value,'result_sha256')
        claim=load(self.root/'queries'/name/'query.json')
        if (value['query_sha256']!=file_hash(self.root/'queries'/name/'query.json') or value['profile']['spec']!=claim['spec']
                or claim['panel_sha256']!=self.result['panel_sha256'] or claim.get('open_train_only') is not True):
            raise ValueError('query/profile binding changed')
        if claim.get('profile_origin')=='audited_correction_of_prior_controller_query':
            correction=self._correction(claim['source_query_id'])
            if (claim.get('frozen_before_profile') is not False
                    or claim['correction_sha256']!=correction['correction_sha256']
                    or digest(value['profile'])!=digest(correction['corrected_profile'])):
                raise ValueError('reused correction/profile binding changed')
        elif claim.get('frozen_before_profile') is not True:raise ValueError('new query must be frozen before computation')
        return value

    def _correction(self,name):
        identifier(name);path=self.root/'numerical-feedback.json'
        if not path.is_file():raise ValueError('no independently audited correction to reuse')
        matches=[value for value in load(path)['corrections'] if value['query_id']==name]
        if len(matches)!=1:raise ValueError('source query is not among the audited corrections')
        _signed(matches[0],'correction_sha256')
        return matches[0]

    def _call(self,name,a):
        if name=='inspect_numerical_correction':
            path=self.root/'numerical-feedback.json'
            if not path.exists():return {'correction_present':False}
            feedback=load(path)
            repair=self.root/'interface-repair.json'
            return {**feedback,'interface_repair':load(repair) if repair.exists() else None,
                'reusable_source_query_ids':[v['query_id'] for v in feedback['corrections']],
                'reuse_instructions':'Previous IDs are not current-session queries. Use reuse_corrected_objective_query '
                    '(source_query_id, fresh query_id, rationale) before propose_objective. No recalculation is needed.'}
        if name=='inspect_train_inventory':
            return {'panel':{k:v for k,v in self.result.items() if k!='summary'},
                'summary':{k:v for k,v in self.result['summary'].items() if k!='entity_mapping'},
                'data_use':load(self.root/'data-use-proposal.json'),'annotations':load(self.root/'annotations-result.json'),
                'constraints':load(self.root/'constraints.json')}
        if name=='inspect_objective_registry':
            return {'families':sorted(FAMILIES),'required_spec_fields':sorted(SPEC_FIELDS),
                'cadence_ms':self.panel.cadence_ms,'source_max_age_ms':self.panel.max_age_ms,
                'rules':'Positive future endpoints aligned to cadence; at most128 grid points and one day. '
                    'point_delta needs equal endpoints/minimum_observations1; other families combine the inclusive grid window. '
                    'minimum_window_coverage in(0,1]; count and coverage requirements BOTH apply; '
                    'label_max_age_ms<=source_max_age_ms. half_life_ms=null except explicit positive EWMA half life.',
                'formulas':{'point_delta':'p(t+h)-p(t)','forward_mean_delta':'mean valid p(t+offset) - p(t)',
                    'forward_median_delta':'median valid p(t+offset) - p(t)',
                    'forward_ewma_delta':'weighted mean valid future p; weights2**((offset-end)/half_life); minus p(t)'},
                'metrics':METRICS,'units':'absolute probability delta; multiply by10000 for probability bps',
                'unavailable':'No trade-price/VWAP, settlement/Brier, dense sub-grid labels, estimated latent efficient-price '
                    'filter, past-average anchor or PnL. Request an extension by deferring, never silently approximate.',
                'risk':'Missing labels are retained with reasons; variance, smoothness or low baseline error does not prove predictability.'}
        if name=='search_public_literature':
            terms=set(a['query'].lower().split());papers=load(self.root/'literature.json')['papers']
            return {'mode':'frozen_primary_source_notes_not_live_search',
                'papers':sorted(papers,key=lambda p:-sum(t in canonical(p).lower() for t in terms))}
        if name=='inspect_train_rows':
            offset,limit=a['offset'],a['limit']
            if type(offset) is not int or not 0<=offset<len(self.ids) or type(limit) is not int or not 1<=limit<=100:
                raise ValueError('bounded Train-only slice required')
            rows=[]
            for i in range(offset,min(offset+limit,len(self.ids))):
                mid=self.panel.midpoint[i];age=self.panel.quote_age_ms[i]
                rows.append({'row_id':str(self.ids[i]),'entity_code':int(self.panel.entity[i]),'decision_ms':int(self.panel.time_ms[i]),
                    'date':str(self.panel.date[i]),'nominal_phase':str(self.panel.phase[i]),
                    'midpoint':float(mid) if np.isfinite(mid) else None,'source_age_ms':float(age) if np.isfinite(age) else None})
            return {'offset':offset,'rows':rows,'total_rows':len(self.ids),'unlabelled':True}
        if name=='profile_objective':
            events=read_activity_events(self.root/'objective-activity.jsonl');seen={e['tool'] for e in events if e['status']=='ok'}
            if not {'inspect_train_inventory','inspect_objective_registry'}<=seen:raise ValueError('inspect data and registry first')
            if (self.root/'numerical-feedback.json').exists() and 'inspect_numerical_correction' not in seen:
                raise ValueError('inspect new numerical correction before querying')
            identifier(a['query_id']);validate_spec(a['spec'],self.panel.cadence_ms,self.panel.max_age_ms)
            if not isinstance(a['rationale'],str) or not a['rationale'].strip():raise ValueError('query rationale required')
            if len(list((self.root/'queries').iterdir()))>=24:raise ValueError('bounded24 profile-query limit reached')
            root=self.root/'queries'/a['query_id'];root.mkdir(exist_ok=False)
            fresh_json(root/'query.json',{'spec':a['spec'],'rationale':a['rationale'],
                'panel_sha256':self.result['panel_sha256'],'frozen_before_profile':True,'open_train_only':True})
            value={'profile':profile(self.panel,a['spec']),'query_id':a['query_id'],
                'query_sha256':file_hash(root/'query.json'),'engine_sha256':file_hash(Path(__file__).with_name('historical_grid_objectives.py'))}
            value['result_sha256']=digest(value);fresh_json(root/'result.json',value)
            return value
        if name=='reuse_corrected_objective_query':
            events=read_activity_events(self.root/'objective-activity.jsonl');seen={e['tool'] for e in events if e['status']=='ok'}
            if not {'inspect_train_inventory','inspect_objective_registry','inspect_numerical_correction'}<=seen:
                raise ValueError('inspect source, registry and numerical correction before reuse')
            identifier(a['query_id']);correction=self._correction(a['source_query_id'])
            if not isinstance(a['rationale'],str) or not a['rationale'].strip():raise ValueError('reuse rationale required')
            if len(list((self.root/'queries').iterdir()))>=24:raise ValueError('bounded24 query limit reached')
            root=self.root/'queries'/a['query_id'];root.mkdir(exist_ok=False)
            fresh_json(root/'query.json',{'spec':correction['corrected_profile']['spec'],'rationale':a['rationale'],
                'panel_sha256':self.result['panel_sha256'],'open_train_only':True,
                'frozen_before_profile':False,'profile_origin':'audited_correction_of_prior_controller_query',
                'source_query_id':a['source_query_id'],'correction_sha256':correction['correction_sha256']})
            value={'query_id':a['query_id'],'profile':correction['corrected_profile'],
                'query_sha256':file_hash(root/'query.json'),'engine_sha256':file_hash(Path(__file__).with_name('historical_grid_objectives.py')),
                'reused_prior_query_id':a['source_query_id'],'new_target_computation':False}
            value['result_sha256']=digest(value);fresh_json(root/'result.json',value)
            return value
        if name=='propose_objective':
            identifier(a['proposal_id']);diagnostics=a['diagnostic_query_ids'];primary=self._query(a['primary_query_id'])
            if (not isinstance(diagnostics,list) or len(diagnostics)>3 or len(set(diagnostics))!=len(diagnostics)
                    or a['primary_query_id'] in diagnostics or a['primary_metric'] not in METRICS):raise ValueError('distinct diagnostic IDs and supported primary metric required')
            if not all(isinstance(a[k],str) and a[k].strip() for k in ['rationale','limitations']):raise ValueError('explain objective and limitations')
            if primary['profile']['all_rows']['covered_rows']==0:raise ValueError('no observed primary labels; defer instead')
            queries={name:self._query(name) for name in [a['primary_query_id'],*diagnostics]}
            if len({digest(q['profile']['spec']) for q in queries.values()})!=len(queries):raise ValueError('diagnostic objectives must be distinct')
            if (a['primary_metric'].endswith('_skill_vs_persistence')
                    and primary['profile']['all_rows']['persistence_mse_probability']==0):raise ValueError('zero baseline makes skill ratio undefined; defer or choose a defined metric')
            value={**a,'queries':{k:{'spec':v['profile']['spec'],'result_sha256':v['result_sha256']} for k,v in queries.items()},
                'panel_sha256':self.result['panel_sha256'],'training_admitted':False,'formal_experiment_ready':False}
            value['proposal_sha256']=digest(value);fresh_json(self.root/'proposals'/(a['proposal_id']+'.json'),value)
            return value
        if name=='submit_grid_objective_decision':
            events=read_activity_events(self.root/'objective-activity.jsonl');seen={e['tool'] for e in events if e['status']=='ok'}
            if not {'inspect_train_inventory','inspect_objective_registry'}<=seen:raise ValueError('inspect before deciding')
            if (self.root/'numerical-feedback.json').exists() and 'inspect_numerical_correction' not in seen:
                raise ValueError('inspect new numerical correction before deciding')
            if not isinstance(a['reason'],str) or not a['reason'].strip():raise ValueError('decision reason required')
            if a['action']=='select':
                identifier(a['proposal_id']);value=load(self.root/'proposals'/(a['proposal_id']+'.json'));_signed(value,'proposal_sha256')
                for key,q in value['queries'].items():
                    if self._query(key)['result_sha256']!=q['result_sha256']:raise ValueError('selected profile changed')
                fresh_json(self.root/'frozen-grid-objective-proposal.json',value)
            elif a['action']!='defer':raise ValueError('select or defer required')
            fresh_json(self.root/'submitted-grid-objective-decision.json',a)
            return {'submitted':True,'bytes':len(canonical(a).encode()),'action':a['action'],'training_admitted':False}
        raise ValueError('unknown tool')


def assess_activity(root):
    validate_workspace(root);log=verify_activity_log(root/'objective-activity.jsonl')
    events=read_activity_events(root/'objective-activity.jsonl')
    decisions=[e for e in events if e['tool']=='submit_grid_objective_decision' and e['status']=='ok']
    if (len(decisions)!=1 or events[-1]!=decisions[0]
            or load(root/'submitted-grid-objective-decision.json')!=decisions[0]['arguments']):raise ValueError('exact first terminal decision required')
    if decisions[0]['arguments']['action']=='select':
        chosen=load(root/'frozen-grid-objective-proposal.json');_signed(chosen,'proposal_sha256')
        if len([e for e in events if e['tool']=='propose_objective' and e['status']=='ok' and e['result']==chosen])!=1:
            raise ValueError('selected proposal must match the logged proposal')
        broker=Broker(root)
        for key,value in chosen['queries'].items():
            query=broker._query(key)
            if query['result_sha256']!=value['result_sha256']:raise ValueError('selected query changed')
            if len([e for e in events if e['tool'] in {'profile_objective','reuse_corrected_objective_query'} and e['status']=='ok' and e['result']==query])!=1:
                raise ValueError('selected profile must have one logged execution or verified reuse')
    return {'valid':True,'log':log,'action':decisions[0]['arguments']['action'],'training_admitted':False}


def serve(broker):
    from data_discovery_tools_mcp import reply
    for line in sys.stdin:
        request=None
        try:
            request=json.loads(line);method=request.get('method');rid=request.get('id')
            if method=='initialize':reply(rid,{'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'historical-grid-objective','version':'1'}})
            elif method=='ping':reply(rid,{})
            elif method=='tools/list':reply(rid,{'tools':TOOLS})
            elif method=='tools/call':
                p=request.get('params',{})
                try:result=broker.call(p.get('name'),p.get('arguments',{}));failed=False
                except (ValueError,FileExistsError,KeyError,TypeError) as exc:result={'accepted':False,'message':str(exc)};failed=True
                reply(rid,{'content':[{'type':'text','text':canonical(result)}],'isError':failed})
        except Exception as exc:
            if isinstance(request,dict) and request.get('id') is not None:reply(request['id'],error=exc)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args();os.environ.clear();serve(Broker(args.workspace))
