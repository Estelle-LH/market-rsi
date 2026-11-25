"""Inactive typed training boundary/comparator links; no execution or authority."""
from copy import deepcopy
import math
from pathlib import Path
import re

from earnings_entry import checked, strict_json, strict_predictions
from earnings_open_feedback import project_target_scores
from earnings_population import validate as validate_population
from earnings_population_tasks import ARTIFACTS, FULL_PLAN, SCORER, RUNTIME
from market_rsi import digest

POLICY = 'frozen_training25_v1'
PLAN = 'configs/earnings_coevolution/population_training25_plan.json'
AUTHORIZATION = '切换到25/25训练方案，新增本阶段$200上限。允许历史固定基线评测；核实held-out结果未用于当前研究者调参后，冻结划分，直接跑25家training基线并连续迭代。held-out先不看，不扩展工程，每轮保留学习轨迹和Git checkpoint。'
SCOPE = ('Prospectively frozen retrospective TRAIN25 Discovery; all25 plain baseline rows are '
         'separate comparator evidence, not Native trials or untouched holdout. Current-company '
         'Native scores compare actual frozen arms only; prior-company scores remain research memory.')
ROOT = ARTIFACTS/'edgar-population-20261016'
SPLIT = ROOT/'TRAIN25-FROZEN-SPLIT.json'
SPLIT_SHA = '124f5ddf328675399633c34b0a0f81eebf2d592b95dc515591025982060b76c7'
DRIVER = {'path':str(ROOT/'TRAIN25-PLAIN-BASELINE.py'),
          'sha256':'5689bffb4c834338c5f12b136cc1d91e9a014d5e88213a139ad88df24ecc24ce'}
SOURCE = '8918aad4dc4d2e1bcbeb63d13b9196082c356b6b'
MODEL = 'gpt-6.1-sol'
KNOWN3 = {'CIK0000003545','CIK0000004457','CIK0000017313'}
TARGETS = ['T%03d'%n for n in range(1,6)]
HEADERS = '\n'.join('### '+target+' |' for target in TARGETS)
STAGE_AUTHORITY = dict(path=str(ROOT/'TRAIN25-STAGE-AUTHORITY.json'),
    sha256='2ca94e70596fca3364bb09297781caa8f39dbce4c2e02707aef1d8945bdac8e7')
ROW_FIELDS = {'cik','window_config','window_identity','identity','result','predictions',
              'final_request','final_response','score','public_feedback'}
STAGE_ATTACHMENT_MODE = 'training25_reviewed_candidate_preclaim_deadline_v1'
STAGE_ATTACHMENT_SCHEMA = 'earnings_training25_successful_stage_attachment_v1'
STAGE_ATTACHMENT_RECEIPT = 'earnings_training25_verified_stage_attachment_v1'
STAGE_ATTACHMENT_AUTHORITY = dict(path=str(ROOT/'TRAIN25-DIRECT-R35-REUSE-AUTHORITY.json'),
    sha256='0e6339ac9650b8e56b55c9aa1c74854f7b9add00cd3747fe6fb66eb0066efac5')


def _stage_attachment_spec(spec):
    if (type(spec) is not dict or set(spec) != {'mode','apply_to_attempt','company_id','input','authority'}
            or spec['mode'] != STAGE_ATTACHMENT_MODE or spec['company_id'] != 'CIK0000021076'
            or type(spec['apply_to_attempt']) is not str
            or re.fullmatch('edgar-population-20261016-[0-9]{2}',spec['apply_to_attempt']) is None
            or spec['apply_to_attempt'] == 'edgar-population-20261016-35'
            or spec['authority'] != STAGE_ATTACHMENT_AUTHORITY):
        raise ValueError('Exact same-task targeted successful-stage policy required')
    bound = spec['input']
    if (type(bound) is not dict or set(bound) != {'path','sha256'}
            or type(bound.get('path')) is not str or Path(bound['path']).parent != ROOT
            or 'qa' in Path(bound['path']).name.lower() or Path(bound['path']).suffix != '.json'
            or type(bound.get('sha256')) is not str or re.fullmatch('[0-9a-f]{64}',bound['sha256']) is None):
        raise ValueError('Exact owned attachment metadata binding required')
    return deepcopy(spec)


def _bytes(bound):
    if (type(bound) is not dict or set(bound) != {'path','sha256'}
            or type(bound['path']) is not str or type(bound['sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}',bound['sha256'])):
        raise ValueError('Exact immutable binding required')
    path = Path(bound['path'])
    if (not path.is_absolute() or not path.is_relative_to(ROOT) or 'qa' in path.name.lower()
            or str(path.resolve()) != bound['path'] or path.is_symlink()
            or not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 16000000):
        raise ValueError('Canonical bounded single-link original required before read')
    return checked(bound)


def _read(bound):
    return strict_json(_bytes(bound))


def load_scope(binding):
    if binding != {'path':str(SPLIT),'sha256':SPLIT_SHA}:
        raise ValueError('Exact frozen TRAIN25 split required before read')
    value = _read(binding)
    training, heldout = value['training'], value['heldout']
    if (value.get('schema') != 'edgar_retrospective_prospectively_sealed_split_v1'
            or value.get('status') != 'FROZEN_RETROSPECTIVE_PROSPECTIVE_SEAL'
            or value.get('historical_isolation_certified') is not False
            or type(training) is not list or type(heldout) is not list
            or len(training) != 25 or len(heldout) != 25
            or any(type(cik) is not str or not re.fullmatch('CIK[0-9]{10}',cik) for cik in training+heldout)
            or len(set(training+heldout)) != 50 or not KNOWN3 <= set(training)):
        raise ValueError('Exact disjoint25/25 prospective boundary required')
    return dict(schema='earnings_training25_scope_v1',split=deepcopy(binding),
                training=deepcopy(training),heldout=deepcopy(heldout))


def admit(scope, cik):
    if type(scope) is not dict or scope != load_scope(scope.get('split')):
        raise ValueError('Verified unchanged training scope required')
    if type(cik) is not str or cik not in scope['training'] or cik in scope['heldout']:
        raise ValueError('Training admission required before any task content')
    return cik


def _window(scope, row):
    config, identity = _read(row['window_config']), _read(row['window_identity'])
    if (config.get('schema') != 'edgar_train25_plain_baseline_window_v1'
            or config.get('split') != scope['split'] or config.get('driver') != DRIVER
            or config.get('source_commit') != SOURCE or config.get('model') != MODEL
            or config.get('runtime') != RUNTIME or config.get('data') != FULL_PLAN
            or config.get('scorer') != SCORER or config.get('retries') is not False
            or config.get('execution') != 'plain_original_forecast_no_capacity_worker_no_recipe'
            or type(config.get('companies')) is not list or not config['companies']
            or len(config['companies']) != len(set(config['companies']))
            or row['cik'] not in config['companies'] or identity.get('config') != row['window_config']):
        raise ValueError('Original plain window/source/split identity differs')
    for cik in config['companies']:admit(scope,cik)
    _bytes(DRIVER)
    review, checkpoint = _read(identity['review']), _read(identity['checkpoint'])
    if (review.get('status') != 'PASS' or review.get('config') != row['window_config']
            or review.get('driver') != DRIVER or checkpoint.get('driver') != DRIVER
            or checkpoint.get('config') != row['window_config']
            or checkpoint.get('review') != identity['review']
            or type(checkpoint.get('commit')) is not str or not re.fullmatch('[0-9a-f]{40}',checkpoint['commit'])):
        raise ValueError('Original reviewed checkpoint bindings differ')
    root = ROOT/'training-baseline'/config['identifier']
    index = config['companies'].index(row['cik'])+1
    slot = root/('%02d-'%index+row['cik'])
    if (config.get('output') != str(root) or row['window_identity']['path'] != str(root/'identity.json')
            or row['window_config']['path'] != str(ROOT/(config['identifier']+'.config.json'))):
        raise ValueError('Original owned window paths differ')
    return config, slot


def _row(scope, row):
    admit(scope,row.get('cik') if type(row) is dict else None)
    if set(row) != ROW_FIELDS:raise ValueError('Exact comparator row bindings required')
    config, slot = _window(scope,row)
    for key,name in [('identity','identity.json'),('result','result.json'),('predictions','predictions.json'),
                     ('score','score.json'),('public_feedback','public-feedback.json')]:
        if row[key].get('path') != str(slot/name):raise ValueError('Original sibling binding differs')
    identity, result = _read(row['identity']), _read(row['result'])
    turn = result.get('turns')
    if (result.get('status') != 'COMPLETED_SCORED' or result.get('cik') != row['cik']
            or type(result.get('scored_targets')) is not int or result['scored_targets'] != 5
            or type(turn) is not int or not 1 <= turn <= 99
            or result.get('public_feedback') != row['public_feedback']
            or identity.get('cik') != row['cik'] or identity.get('case',{}).get('cik') != row['cik']
            or identity.get('config') != row['window_config'] or identity.get('model') != MODEL
            or identity.get('runtime') != RUNTIME or identity.get('source_commit') != SOURCE
            or identity.get('researcher_capacity_worker','missing') is not None
            or identity.get('research_recipe','missing') is not None):
        raise ValueError('Completed five-target plain result/identity required')
    for key,suffix in [('final_request','request'),('final_response','response')]:
        if row[key].get('path') != str(slot/('%02d-'%turn+suffix+'.json')):
            raise ValueError('Original final numbered binding required')
    request, response = _read(row['final_request']), _read(row['final_response'])
    if (request.get('payload',{}).get('model') != MODEL or response.get('model') != MODEL
            or response.get('service_tier') != 'default' or type(request.get('request_id')) is not str
            or not request['request_id'] or type(request.get('reserved_nano_usd')) is not int
            or request['reserved_nano_usd'] <= 0):raise ValueError('Original counted final/model differs')
    predictions = strict_predictions(response,TARGETS)
    if _read(row['predictions']) != predictions:raise ValueError('Saved predictions differ from strict final')
    score, public = _read(row['score']), _read(row['public_feedback'])
    awards = project_target_scores(score,HEADERS)  # IDs only; no question/QA load or re-score.
    expected_public = dict(cik=row['cik'],score_out_of_5=score['score_out_of_5'],per_target=awards)
    if (digest(public) != digest(expected_public)
            or type(result.get('points')) not in (int,float) or not math.isfinite(result['points'])
            or result['points'] != score['score_out_of_5']):raise ValueError('Original public award projection differs')
    return dict(company_id=row['cik'],predictions=deepcopy(predictions['predictions']),
                target_scores=awards,points=score['score_out_of_5'],originals=deepcopy(row))


def load_comparator(scope, binding):
    value = _read(binding)
    if (type(value) is not dict or set(value) != {'schema','split','rows'}
            or value['schema'] != 'earnings_plain_training_comparator_manifest_v1'
            or value['split'] != scope['split'] or type(value['rows']) is not list
            or len(value['rows']) != 25):raise ValueError('Complete25 comparator manifest required')
    ids = [r.get('cik') if type(r) is dict else None for r in value['rows']]
    for cik in ids:admit(scope,cik)  # All membership checked BEFORE row/body reads.
    if len(set(ids)) != 25 or set(ids) != set(scope['training']):raise ValueError('Exact unique training25 rows required')
    rows = {r['cik']:_row(scope,r) for r in value['rows']}
    return dict(schema='earnings_plain_training_comparator_v1',policy=POLICY,split=deepcopy(scope['split']),
        manifest=deepcopy(binding),rows=[rows[cik] for cik in scope['training']],
        attribution='Plain fixed-model baseline; no NativeR32 trial, adoption or co-evolution claim.')


def _campaign_origin(binding, state, pool_binding, feedback_binding, feedback):
    """Join original completion receipts; full historical admission stays external."""
    path = Path(binding['path'])
    if (path.parent.parent != ROOT/'attempts' or path.name != 'population-run-result.json'
            or not re.fullmatch('edgar-population-20261016-[0-9]{2}',path.parent.name)):
        raise ValueError('Canonical original completed campaign required before read')
    result = _read(binding); loop = result.get('result',{}); final = loop.get('result',{})
    count = loop.get('completed_rounds')
    if (result.get('status') != 'COMPLETED_DISCOVERY_PILOT' or result.get('retry_allowed') is not False
            or loop.get('status') != 'completed' or type(count) is not int or not 1 <= count <= 2
            or set(final) != {'artifacts','company_id','decision_record','feedback',
                              'last_scored_feedback','latest_feedback','population'}
            or digest(final['population']) != digest(state) or final['feedback'] != feedback_binding
            or final['latest_feedback'] != feedback_binding or final['company_id'] != feedback.get('company_id')
            or pool_binding['path'] != str(path.parent/('population-%02d.json'%count))
            or feedback_binding['path'] != str(path.parent/('feedback-%02d.json'%count))
            or final['decision_record']['path'] != str(path.parent/('decision-%02d.json'%count))
            or final['artifacts'] != [pool_binding,feedback_binding,final['decision_record']]):
        raise ValueError('Original completed reconcile/pool/latest feedback differs')
    record = _read(final['decision_record'])
    campaign_path = ROOT/'inputs'/path.parent.name/'campaign.json'
    if (feedback.get('schema') != 'earnings_population_campaign_feedback_v1'
            or feedback.get('round_index') != count or record.get('schema') != 'earnings_population_campaign_decision_v1'
            or record.get('round_index') != count or record.get('feedback') != feedback_binding
            or record.get('population_sha256') != digest(state)
            or record.get('frozen',{}).get('path') != str(path.parent/('frozen-pool-%02d.json'%count))
            or digest(_read(record['frozen'])) != digest(state)
            or record.get('campaign',{}).get('path') != str(campaign_path)
            or any(record.get(a) != feedback.get(b) for a,b in (
                ('kind','kind'),('score_state','score_state'),('parent_id','chosen_parent_id'),
                ('baseline_version_id','baseline_version_id')))
            or record.get('candidate_id') != (None if feedback.get('candidate') is None else feedback['candidate']['id'])):
        raise ValueError('Original campaign decision/frozen feedback join differs')
    campaign = _read(record['campaign'])
    scored = feedback.get('kind') == 'scored_dev'
    if (campaign.get('schema') != 'earnings_population_campaign_v1' or campaign.get('max_decisions') != count
            or campaign.get('panel') != [feedback['company_id']]
            or campaign.get('baseline_version_id') != feedback.get('baseline_version_id')
            or digest(campaign.get('contract')) != feedback.get('campaign_contract_sha256')
            or feedback.get('kind') not in {'scored_dev','review_rejected','no_change'}
            or feedback.get('score_state') != ('scored' if scored else 'unscored')
            or type(feedback.get('results')) is not list or bool(feedback['results']) != scored
            or final['last_scored_feedback'] != (feedback_binding if scored else feedback.get('last_scored_feedback'))):
        raise ValueError('Original campaign contract/latest versus last-score differs')
    return final['last_scored_feedback']


def link_state(policy, split_binding, comparator_binding, pool_binding, feedback_binding, *, panel, completed_origin=None):
    if policy is None:return None  # Legacy paths do not read or gain fields.
    if type(policy) is not str or policy != POLICY:raise ValueError('Exact forward training policy required')
    scope = load_scope(split_binding)
    if type(panel) is not list or not 1 <= len(panel) <= 2 or len(set(panel)) != len(panel):
        raise ValueError('One/two unique training panel IDs required')
    for cik in panel:admit(scope,cik)
    load_comparator(scope,comparator_binding)
    state = _read(pool_binding)
    observed = state.get('exposed_companies',[]) + [r['company_id'] for r in state.get('observations',[])]
    observed += [r['body']['company_id'] for r in state.get('history',[]) if r.get('kind') == 'observe']
    for cik in observed:admit(scope,cik)  # Before original validation hashes referenced artifacts.
    # Metadata must join the original completion before any recursive artifact
    # validation. A self-consistent file hash alone does not establish origin.
    feedback = _read(feedback_binding)
    if completed_origin is not None:
        last = _campaign_origin(completed_origin,state,pool_binding,feedback_binding,feedback)
    elif (not state['observations'] or state['observations'][-1]['feedback'] != feedback_binding
            or any(feedback.get(k) != state['observations'][-1][k] for k in ('company_id','results','stable_id'))
            or feedback.get('schema') not in {'earnings_population_feedback_v1','earnings_population_campaign_feedback_v1'}):
        raise ValueError('Exact immutable prior pool/latest feedback link required')
    admit(scope,feedback['company_id'])
    if completed_origin is None:
        last = feedback['last_scored_feedback'] if feedback.get('score_state') == 'unscored' else feedback_binding
    scored = _read(last)
    admit(scope,scored.get('company_id'))
    if not scored.get('results') or scored.get('score_state','scored') != 'scored':
        raise ValueError('Separate real last-scored feedback required')
    state = validate_population(state)
    return dict(schema='earnings_training25_state_link_v1',policy=POLICY,split=deepcopy(split_binding),
        comparator=deepcopy(comparator_binding),previous_population=deepcopy(pool_binding),
        population_sha256=digest(state),previous_feedback=deepcopy(feedback_binding),
        last_scored_feedback=deepcopy(last),panel=deepcopy(panel),
        **({} if completed_origin is None else {'completed_origin':deepcopy(completed_origin)}))


def validate_link(value):
    if value is None:return None
    origin = value.get('completed_origin') if type(value) is dict else None
    if (type(origin) is not dict or set(origin) != {'path','sha256'}
            or type(origin['path']) is not str or type(origin['sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}',origin['sha256']) is None):
        raise ValueError('Training transfer requires an original completed origin before artifact validation')
    expected = link_state(value.get('policy'),value.get('split'),value.get('comparator'),
        value.get('previous_population'),value.get('previous_feedback'),panel=value.get('panel'),
        completed_origin=value.get('completed_origin'))
    if value != expected:raise ValueError('Training state envelope drift')
    return deepcopy(value)


def entry_plan(binding, repo, *, historical_reader=None):
    """Exact source-bound task authority; financial activation remains external."""
    path = Path(repo)/PLAN
    if (type(binding) is not dict or set(binding) != {'path','sha256'}):
        raise ValueError('Exact committed training source-plan path required')
    if historical_reader is None:
        if binding.get('path') != str(path) or path.resolve() != path:
            raise ValueError('Exact committed training source-plan path required')
        value = strict_json(checked(binding))
    else:
        import earnings_population_continuation as history
        if (type(historical_reader) is not history._Reader or historical_reader.repo != Path(repo)
                or historical_reader.root != ROOT or history.source_name(binding.get('path'),Path(repo)) != PLAN
                or (binding.get('path'),binding.get('sha256')) not in historical_reader.sources):
            raise ValueError('Exact registered historical training source plan required')
        value = historical_reader.read(binding)
    expected = dict(schema='supervisor_bottleneck_plan_v1',id='earnings-population-training25-20261019',
        human_authorization=AUTHORIZATION,training_policy=POLICY,
        split=dict(path=str(SPLIT),sha256=SPLIT_SHA),stage_authority=STAGE_AUTHORITY,
        max_decisions=1,scope=SCOPE)
    if type(value) is dict and 'successful_stage_attachment' in value:
        expected['successful_stage_attachment'] = _stage_attachment_spec(value['successful_stage_attachment'])
    if digest(value) != digest(expected):
        raise ValueError('Exact forward training25 task authority required')
    stage = _read(STAGE_AUTHORITY)
    if (stage.get('schema') != 'edgar_training_stage_authority_record_v1'
            or stage.get('direct_human_instruction') != AUTHORIZATION
            or stage.get('stage_start') != dict(ledger_rows=6401,booked_nano_usd=187429960800,
                ledger_prefix_sha256='0c343c36c21c496b7f6263ba4ec9afb8ffb5dcb347b0e4195e63349112ce252a',
                pending_requests=0,fixed_model_booked_nano_usd=79944786300)):
        raise ValueError('Original stage authority/prefix differs; no reset')
    return value


def stage_attachment_policy(plan_binding, *, repo, attempt_id, company_id,
                            attachment_binding=None, historical_reader=None):
    """Source-owned target lookup; the producer separately requires explicit opt-in."""
    plan = entry_plan(plan_binding,repo,historical_reader=historical_reader)
    spec = plan.get('successful_stage_attachment')
    if spec is None or attempt_id != spec['apply_to_attempt']:
        if attachment_binding is not None:raise ValueError('Attachment is not authorized for this new attempt')
        return None
    if company_id != spec['company_id'] or attachment_binding is not None and attachment_binding != spec['input']:
        raise ValueError('Successful stages require the exact input and same company')
    return deepcopy(spec)


def stage_routing_origin(base_origin, authenticated_receipt):
    """Ephemeral receiver view only; this is not an independent admission API."""
    value = authenticated_receipt
    fields = {'schema','mode','input','authority','completed_origin','company_id','candidate_id',
              'author_stage_reuse','review_stage_reuse','delivery_diagnosis','evidence'}
    if (type(value) is not dict or set(value) != fields or value['schema'] != STAGE_ATTACHMENT_RECEIPT
            or value['mode'] != STAGE_ATTACHMENT_MODE or value['authority'] != STAGE_ATTACHMENT_AUTHORITY
            or value['completed_origin'] != base_origin['previous_result']
            or value['company_id'] != 'CIK0000021076'
            or value['author_stage_reuse']['candidate']['id'] != value['candidate_id']
            or value['review_stage_reuse']['candidate'] != value['author_stage_reuse']['candidate']
            or any(base_origin.get(k) is not None for k in ('author_stage_reuse','review_stage_reuse','controller_stage_import'))):
        raise ValueError('Exact verified stage attachment beside the completed base required')
    result = deepcopy(base_origin)
    result.update(author_stage_reuse=deepcopy(value['author_stage_reuse']),
                  review_stage_reuse=deepcopy(value['review_stage_reuse']),
                  training_stage_attachment=deepcopy(value['input']))
    result['evidence'] += deepcopy(value['evidence'])
    return result


def feedback_contracts(origin, scope):
    """Own original companies/contracts, not a cross-company equality bridge."""
    latest = origin['research_feedback']; scored = _read(origin['last_scored_feedback'])
    for row in (latest,scored):admit(scope,row.get('company_id'))
    if latest.get('schema') != 'earnings_population_campaign_feedback_v1':
        raise ValueError('Completed original campaign feedback required')
    fields = dict(initial_feedback_contract_sha256=latest['campaign_contract_sha256'])
    if scored.get('schema') == 'earnings_population_campaign_feedback_v1':
        if scored.get('kind') != 'scored_dev' or scored.get('score_state') != 'scored':
            raise ValueError('Original last scored campaign required')
        fields['last_scored_contract_sha256'] = scored['campaign_contract_sha256']
    for token in fields.values():
        if type(token) is not str or not re.fullmatch('[0-9a-f]{64}',token):
            raise ValueError('Exact original feedback contract hash required')
    return fields
