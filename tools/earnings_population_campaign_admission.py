"""Source-bound fixed-panel study checks; original owner and caps stay external."""
from copy import deepcopy
import hashlib
from pathlib import Path
import re

import earnings_population_campaign as campaign
import earnings_population_rejection as rejection
import earnings_population_tasks as tasks
from edgar_forecast_tools import FilingTools
from edgar_forecast_openai import capacity_forecast_closing_policy
from earnings_entry import checked, strict_json
from earnings_open_resources import ROLE_EFFORTS, role_limits, population_role_limits
from market_rsi import digest

ROOT, REPO = rejection.OWNED, rejection.REPO
PLAN = 'configs/earnings_coevolution/population_campaign_plan.json'
AUTHORIZATION = '授权准备并按剩余额度跑有界前缀'
RESUME_PLAN = 'configs/earnings_coevolution/population_resume03_plan.json'
RESUME_AUTHORIZATION = '允许，先补齐03→新ID的状态继承，测试和独立审查通过后，沿用剩余额度开新的90分钟窗口。让真实Author收到失败片段并交付最小修复，先过真实财报测试再预测，与父版逐项比较。数据、scorer、模型、上限和原$200总预算不变，不重置账本。每步单独Git提交，失败先诊断、不自动重试，不动其他Supervisor。'
MODEL = {'requested_model': 'gpt-6.1-sol', 'serving_snapshot': 'unknown', 'serving_snapshot_verified': False}


def scientific_contract(resident, *, training_scope=None, review_input_policy=None):
    """Identity of the original public task and comparable execution, no parser."""
    company = rejection.COMPANY
    if training_scope is not None:
        from earnings_population_training25 import admit
        company = admit(training_scope, resident['company']['cik'])
    if (resident['company']['cik'] != company or resident['case']['cik'] != company
            or resident['data_binding'] != tasks.FULL_PLAN or resident['kernel']['scorer'] != tasks.SCORER
            or resident['case']['evaluation_kernel'] != resident['kernel']):
        raise ValueError('Original Capital task/data/scorer bindings required')
    files, runtime = FilingTools(resident['company']).files, resident['runtime']
    review_fields = {} if review_input_policy is None else {'review_input_policy': review_input_policy}
    if review_fields and training_scope is None:
        raise ValueError('Review input opt-in requires an admitted training contract')
    return dict(schema='earnings_population_scientific_contract_v1', company_id=company,
        data=deepcopy(tasks.FULL_PLAN), scorer=deepcopy(tasks.SCORER), case=deepcopy(resident['case']),
        kernel=deepcopy(resident['kernel']), questions_sha256=hashlib.sha256(files['questions.md'].encode()).hexdigest(),
        filing_index_sha256=hashlib.sha256(files['filing_index.tsv'].encode()).hexdigest(),
        runtime=deepcopy(runtime), model=deepcopy(MODEL), role_efforts=deepcopy(ROLE_EFFORTS),
        limits=dict(population_role_limits(review_fields), forecast={'max_input_tokens': runtime['max_input_tokens'],
            'max_output_tokens': runtime['max_output_tokens'], 'wall_seconds': runtime['company_wall_seconds']}),
        initial_records=[], cache_policy='disabled', baseline_version_id=rejection.PARENT,
        forecast_closing_policy=capacity_forecast_closing_policy(), **review_fields)


def _local(binding, value, name):
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding.get('path')) is not str):
        raise ValueError('Exact immutable campaign input binding required')
    path = Path(binding['path'])
    if (str(path) != binding['path'] or path != ROOT/'inputs'/value['id']/name
            or not path.is_absolute() or path.resolve() != path or not path.is_file()):
        raise ValueError('Canonical current-ID campaign input file required before read')
    return strict_json(checked(binding))


def last_scored_contract_sha256(origin, current_contract):
    """Join a replay-verified score to its own original task/resource contract.

    Caller must first replay the origin. This is not caller-selected historical
    authority: the canonical score attempt selects its runtime in that replay's
    evidence, and its immutable study selects the original campaign contract.
    """
    binding = origin['last_scored_feedback']
    path = Path(binding['path'])
    if (not re.fullmatch(r'edgar-population-20261016-[0-9]{2}', path.parent.name)
            or path.parent.parent != ROOT/'attempts'
            or not re.fullmatch(r'feedback-[0-9]{2}\.json', path.name)
            or str(path) != binding['path'] or path.resolve() != path):
        raise ValueError('Canonical owned historical scored feedback required')
    score = campaign._read(binding)
    if score.get('schema') == 'earnings_population_feedback_v1':
        return None
    token = score.get('campaign_contract_sha256')
    campaign._sha(token)
    if (score.get('schema') != 'earnings_population_campaign_feedback_v1'
            or score.get('company_id') != campaign.PANEL[0]
            or score.get('kind') != 'scored_dev' or score.get('score_state') != 'scored'):
        raise ValueError('Actual original scored development ancestor required')
    inputs = ROOT/'inputs'/path.parent.name
    matches = [b for b in origin['evidence'] if b.get('path') == str(inputs/'runtime-reviewed.json')]
    if not matches or any(b != matches[0] for b in matches):
        raise ValueError('Historical score requires its unique verified runtime binding')
    def metadata(bound):
        # Origin replay already verified historical source bytes against Git.
        # Rechecking their nested old source bindings as current files is wrong.
        campaign._bindings([bound])
        value = strict_json(checked(bound))
        if type(value) is not dict: raise ValueError('Original historical metadata object required')
        return value
    runtime = metadata(matches[0])
    if runtime.get('id') != path.parent.name or runtime.get('root') != str(path.parent):
        raise ValueError('Historical score/runtime attempt mismatch')
    def original(bound, name):
        if type(bound) is not dict or bound.get('path') != str(inputs/name):
            raise ValueError('Canonical source-bound historical study/campaign required')
        return metadata(bound)
    study = original(runtime['forecast_study'], 'study.json')
    manifest = original(study['campaign'], 'campaign.json')
    historical = manifest.get('contract')
    if (type(historical) is not dict or digest(historical) != token
            or manifest.get('baseline_version_id') != score.get('baseline_version_id')
            or manifest.get('panel') != campaign.PANEL):
        raise ValueError('Historical scored feedback differs from its original contract')
    adjusted = deepcopy(historical)
    for role in ('controller','review','author'):
        if (type(historical.get('limits',{}).get(role,{}).get('wall_seconds')) is not int
                or type(current_contract.get('limits',{}).get(role,{}).get('wall_seconds')) is not int):
            raise ValueError('Exact integer historical/current role walls required')
    before_input = historical.get('limits',{}).get('author',{}).get('max_input_tokens')
    after_input = current_contract.get('limits',{}).get('author',{}).get('max_input_tokens')
    if type(before_input) is not int or type(after_input) is not int:
        raise ValueError('Exact integer historical/current Author input limits required')
    if any(historical['limits'][role]['wall_seconds'] != current_contract['limits'][role]['wall_seconds']
           for role in ('controller','review','author')):
        for role, before, after in (('controller',600,900),('review',600,900),('author',900,1200)):
            if (adjusted.get('limits',{}).get(role,{}).get('wall_seconds') != before
                    or current_contract.get('limits',{}).get(role,{}).get('wall_seconds') != after):
                raise ValueError('Only exact declared historical control-wall transition is permitted')
            adjusted['limits'][role]['wall_seconds'] = after
    if before_input != after_input:
        if (before_input, after_input) not in {(48000, 64000), (48000, 96000), (64000, 96000)}:
            raise ValueError('Only exact declared forward Author input48k/64k to64k/96k transitions are permitted')
        adjusted['limits']['author']['max_input_tokens'] = after_input
    before_review = historical.get('limits',{}).get('review',{}).get('max_input_tokens')
    after_review = current_contract.get('limits',{}).get('review',{}).get('max_input_tokens')
    if type(before_review) is not int or type(after_review) is not int:
        raise ValueError('Exact integer historical/current Review input limits required')
    if before_review != after_review:
        if (before_review, after_review) != (20000, 32000):
            raise ValueError('Only exact declared forward Review input20k to32k transition is permitted')
        adjusted['limits']['review']['max_input_tokens'] = after_review
    field = 'forecast_closing_policy'
    if field in historical or field in current_contract:
        expected = capacity_forecast_closing_policy()
        if (digest(current_contract.get(field)) != digest(expected)
                or field in historical and digest(historical[field]) != digest(expected)):
            raise ValueError('Only exact declared forward capacity finalization policy is permitted')
        adjusted[field] = expected
    if digest(adjusted) != digest(current_contract):
        raise ValueError('Historical fixed task/model/tokens/forecast contract changed')
    return token


def validate(value, study, state):
    """Return repeated original residents; common source/model/ledger checks remain."""
    if (type(value.get('id')) is not str or not re.fullmatch(r'edgar-population-20261016-[0-9]{2}', value['id'])
            or value['id'] in {rejection.IDENT, 'edgar-population-20261016-01'}
            or value.get('ledger') != str(rejection.LEDGER) or study.get('continuation') is not None):
        raise ValueError('Explicit fresh campaign ID, sole ledger and no mixed continuation required')
    if 'training_policy' in value:
        return _training_validate(value, study, state)
    manifest = _local(study['campaign'], value, 'campaign.json')
    origin = _local(study['campaign_origin'], value, 'campaign-origin.json')
    extra = set(manifest) & {'comparison_policy', 'initial_feedback_contract_sha256', 'last_scored_contract_sha256'} if type(manifest) is dict else set()
    if (type(manifest) is not dict or set(manifest) != campaign.FIELDS | extra
            or extra and (study.get('campaign_resume') is None
                          or manifest.get('comparison_policy') != campaign.PARENT_COMPARISON)):
        raise ValueError('Exact fixed-panel campaign fields required before recursive reads')
    if 'last_scored_contract_sha256' in manifest:
        campaign._sha(manifest['last_scored_contract_sha256'])
    initial_feedback = _local(manifest['initial_feedback'], value, 'rejection-feedback.json')
    plan_bound = value['sources'].get(PLAN)
    if (type(plan_bound) is not dict or set(plan_bound) != {'path', 'sha256'}
            or plan_bound.get('path') != str(REPO/PLAN) or (REPO/PLAN).resolve() != REPO/PLAN
            or manifest['source_plan'] != plan_bound):
        raise ValueError('Exact committed current campaign source-plan binding required')
    plan = strict_json(checked(plan_bound))
    if (plan.get('schema') != 'supervisor_bottleneck_plan_v1'
            or plan.get('id') != 'earnings-population-campaign-20261016'
            or plan.get('human_authorization') != AUTHORIZATION):
        raise ValueError('Exact current human campaign authorization required')
    resident = tasks.resident(rejection.COMPANY)
    contract = scientific_contract(resident)
    count = manifest['max_decisions']
    if (type(count) is not int or not 1 <= count <= 2 or manifest['panel'] != campaign.PANEL
            or value.get('companies') != campaign.PANEL*count or manifest['contract'] != contract
            or manifest['baseline_version_id'] != rejection.PARENT
            or manifest['initial_population_sha256'] != digest(state)
            or manifest['validation_company_id'] != campaign.VALIDATION_COMPANY):
        raise ValueError('Exact fixed original task/starting baseline/repeated panel contract required')
    if study.get('campaign_resume') is None:
        original = rejection.load_closed_review_rejection(
            {'path': str(ROOT/'attempts'/rejection.IDENT/'population-run-failure.json'), 'sha256': rejection.FAILURE_SHA},
            root=ROOT, ledger=rejection.LEDGER, repo=REPO)
    else:
        resumed = _local(study['campaign_resume'], value, 'campaign-resume.json')
        recovery = 'prior_failed_attempt' in resumed
        reuse = resumed.get('reuse_mode') == 'review_existing_candidate_v1'
        controller_import = 'controller_import_mode' in resumed
        from earnings_population_recovery import PLAN as RECOVERY_PLAN
        from earnings_population_budget import PLAN as BUDGET_PLAN, GRANT
        completed = not recovery and Path(resumed['previous_result']['path']).parent.name != 'edgar-population-20261016-03'
        plan_name = RECOVERY_PLAN if recovery else RESUME_PLAN
        if completed: plan_name = BUDGET_PLAN
        resume_plan = value['sources'].get(plan_name)
        if (set(resumed) != {'schema', 'previous_result', 'plan', 'repair'} | ({'prior_failed_attempt'} if recovery else set()) | ({'reuse_mode'} if reuse else set()) | ({'controller_import_mode'} if controller_import else set())
                or resumed['schema'] != 'earnings_population_campaign_resume_v1'
                or resumed['plan'] != resume_plan
                or resume_plan is None or resume_plan.get('path') != str(REPO/plan_name)):
            raise ValueError('Exact committed closed-campaign resume binding required')
        authorization = strict_json(checked(resume_plan))
        from earnings_population_budget import AUTHORIZATION as CURRENT_AUTHORIZATION
        if (authorization.get('schema') != 'supervisor_bottleneck_plan_v1'
                or authorization.get('id') != (GRANT if completed else 'earnings-population-review-recovery-20261016' if recovery else 'earnings-population-resume03-20261016')
                or authorization.get('human_authorization') != (CURRENT_AUTHORIZATION if recovery or completed else RESUME_AUTHORIZATION)):
            raise ValueError('Exact current human resume authorization required')
        if recovery:
            from earnings_population_recovery import load
            original = load(resumed['prior_failed_attempt'], root=ROOT, ledger=rejection.LEDGER,
                            repo=REPO, plan_binding=resume_plan)
            if resumed['previous_result'] != original['previous_result'] or resumed['repair'] is not None:
                raise ValueError('Recovery preserves completed seed and autonomous next R/H choice')
            if reuse != (original.get('author_stage_reuse') is not None) or reuse and count != 1:
                raise ValueError('Exact verified first-round-only successful Author reuse required')
            imported = original.get('controller_stage_import')
            if (controller_import != (imported is not None)
                    or imported is not None and (reuse or resumed['controller_import_mode'] != imported['mode'])):
                raise ValueError('Exact distinct verified Controller-public-proposal import required')
        else:
            if controller_import:
                raise ValueError('Controller proposal import requires exact closed-failure ancestry')
            from earnings_population_completed import load
            original = load(resumed['previous_result'], root=ROOT, ledger=rejection.LEDGER, repo=REPO)
        if manifest.get('comparison_policy') != campaign.PARENT_COMPARISON:
            raise ValueError('Resumed campaign must measure actual parent as well as frozen control')
        parent = original['reference_candidate']['parent']
        capacity = recovery and original.get('recovery_context',{}).get('mode') in {
            'author_assembly_capacity_feedback_v1','author_implementation_base_capacity_feedback_v1'}
        if capacity and (reuse or parent not in state['explorers']
                or parent != original['recovery_context']['failed_parent']['version_id']
                or state['versions'][parent]['R'] != original['recovery_context']['failed_parent']['source']):
            raise ValueError('Exact verified failed-parent/reference ancestry required')
        if (not completed and not reuse and not capacity and (parent not in state['explorers'] or parent != manifest['baseline_version_id'])
                or not recovery and not completed and resumed['repair'] != dict(schema='earnings_population_human_repair_v1',
                    parent_version_id=parent, human_authorization=RESUME_AUTHORIZATION)):
            raise ValueError('Actual inherited parent must be the fresh matched repair comparator')
        if completed and resumed['repair'] is not None:
            raise ValueError('Completed continuation must preserve autonomous active-parent/R/H choice')
    if (origin != original or state != original['population']
            or initial_feedback != original['research_feedback']
            or manifest['last_scored_feedback'] != original['last_scored_feedback']
            or ('initial_feedback_contract_sha256' in manifest) != (study.get('campaign_resume') is not None)
            or study.get('campaign_resume') is not None and manifest['initial_feedback_contract_sha256'] !=
                original['research_feedback'].get('campaign_contract_sha256')):
        raise ValueError('Exact unchanged verified origin/pool/latest feedback/last score required')
    if ('last_scored_contract_sha256' in manifest and manifest['last_scored_contract_sha256'] !=
            last_scored_contract_sha256(original, contract)):
        raise ValueError('Historical score contract must match the independently replayed original')
    # Only after all references are joined to the verified original may the
    # shared structural reader recursively check their immutable artifacts.
    campaign.load(study['campaign'], state, value['companies'], count)
    return [deepcopy(resident) for _ in range(count)]


def _training_validate(value, study, state):
    """Real original completed replay remains the authority for inherited state."""
    import earnings_population_training25 as training
    if (value['training_policy'] != training.POLICY or type(value['training_policy']) is not str
            or value.get('budget_amendment') is None or value.get('model_budget_amendment') is None
            or study.get('training_state_link') is None or study.get('campaign_resume') is None):
        raise ValueError('Explicit training/400/model-grant/completed task link required')
    link = _local(study['training_state_link'],value,'training-state-link.json')
    if (type(link) is not dict or set(link) != {'schema','policy','split','comparator',
            'previous_population','population_sha256','previous_feedback','last_scored_feedback','panel','completed_origin'}
            or link.get('schema') != 'earnings_training25_state_link_v1' or link.get('policy') != training.POLICY
            or type(link.get('completed_origin')) is not dict):
        raise ValueError('Exact completed training link metadata required before recursion')
    scope = training.load_scope(link['split'])
    if type(link['panel']) is not list or len(link['panel']) != 1 or value['companies'] != link['panel']:
        raise ValueError('Exactly one explicitly admitted training company required')
    company = training.admit(scope, link['panel'][0])  # BEFORE resident/body access.
    manifest = _local(study['campaign'],value,'campaign.json')
    if manifest.get('training_state_link') != study['training_state_link']:
        raise ValueError('Study and campaign must share exact training link')
    plan = value['sources'].get(training.PLAN)
    training.entry_plan(plan,REPO)
    resumed = _local(study['campaign_resume'],value,'campaign-resume.json')
    if (set(resumed) != {'schema','previous_result','plan','repair'}
            or resumed.get('schema') != 'earnings_population_campaign_resume_v1'
            or resumed['plan'] != plan or resumed['repair'] is not None
            or resumed['previous_result'] != link.get('completed_origin')):
        raise ValueError('Training requires an original completed origin, no reuse/recovery')
    stage_spec = training.stage_attachment_policy(plan,repo=REPO,attempt_id=value['id'],company_id=company)
    from earnings_population_runtime import _proposal_prefix_metadata
    prefix=_proposal_prefix_metadata(value,study,company_id=company)
    if prefix is not None:
        if stage_spec is not None:
            raise ValueError('Failed37 prefix cannot mix with old successful-stage attachments')
        from earnings_population_proposal_completed import load_failed37_prefix
        authenticated=load_failed37_prefix(prefix['failed_attempt'],consumer_attempt_id=value['id'],
            root=ROOT,ledger=rejection.LEDGER,repo=REPO)
        if prefix!=authenticated:
            raise ValueError('Saved failed37 receipt differs from original authenticated delivery')
        original=authenticated['base_origin']
    elif stage_spec is None:
        if 'training_stage_attachment' in study:
            raise ValueError('Unselected successful-stage attachment cannot enter ordinary training')
        from earnings_population_completed import load
        original = load(resumed['previous_result'],root=ROOT,ledger=rejection.LEDGER,repo=REPO)
    else:
        saved_stages = _local(study.get('training_stage_attachment'),value,'training-stage-attachment.json')
        from earnings_population_recovery import load_training_stage_attachment
        carried = load_training_stage_attachment(stage_spec['input'],completed_result=resumed['previous_result'],
            training_scope=scope,company_id=company,attempt_id=value['id'],root=ROOT,
            ledger=rejection.LEDGER,repo=REPO,plan_binding=plan)
        if saved_stages != carried['stage_attachment']:
            raise ValueError('Saved successful-stage receipt differs from original authenticated delivery')
        original = carried['base_origin']
    original_final = training._read(original['previous_result'])['result']['result']
    origin = _local(study['campaign_origin'],value,'campaign-origin.json')
    latest = _local(manifest['initial_feedback'],value,'rejection-feedback.json')
    if (origin != original or state != original['population']
            or original['previous_result'] != resumed['previous_result']
            or link['previous_population'] != original_final['artifacts'][0]
            or link['previous_feedback'] != original['feedback']
            or training._read(link['previous_population']) != state
            or link['last_scored_feedback'] != original['last_scored_feedback']
            or latest != original['research_feedback']
            or manifest['last_scored_feedback'] != original['last_scored_feedback']
            or manifest['baseline_version_id'] != latest['baseline_version_id']):
        raise ValueError('Exact verified training origin/pool/latest/last score/control required')
    training.validate_link(link)  # Only after the full original predecessor and exact bindings join.
    resident = tasks.resident(company)
    review_fields = ({'review_input_policy':value['review_input_policy']} if 'review_input_policy' in value else {})
    if (manifest['source_plan'] != plan or manifest['contract'] != scientific_contract(resident,training_scope=scope,**review_fields)
            or manifest['validation_company_id'] != company):
        raise ValueError('Original admitted training task/model/data/scorer contract differs')
    campaign.load(study['campaign'],state,value['companies'],1)
    return [deepcopy(resident)]
