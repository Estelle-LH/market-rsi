"""Explicit frozen TRAIN25 identities, not execution, progress or paid authority."""
from copy import deepcopy
from pathlib import Path
import re

from earnings_entry import checked, strict_json
import earnings_population_completed as completed
import earnings_population_tasks as tasks
import earnings_population_training25 as training
from market_rsi import digest

POLICY = 'frozen_training25_panel_v1'
SCHEMA = 'earnings_training25_frozen_panel_v1'
ARMS = ('control', 'parent', 'candidate')
AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-DIRECT-FULL-PANEL-AUTHORITY.json'),
    sha256='2033e1586552d8dd6e2dc797bee19b1841f2a298cefffc48bf988b771c6cb417')
ORIGIN = dict(path=str(training.ROOT/'attempts/edgar-population-20261016-36/population-run-result.json'),
    sha256='15f7081a3463219c4fdd1ad9b79d0dfb4fb99953d56d8df4ba7354e12e8aa82b')
ROUND0 = dict(path=str(training.ROOT/'TRAIN25-PLAIN-COMPARATOR-MANIFEST.json'),
    sha256='7a43ee9cac7204ef664d134c2e5effac14e2422aa9cedc207f66fcfe55ef07a3')
CONTROL_ID = '11cebd96927bc57b5a8800769d5e6dfbaeb0ace8f6b8715456c6daabb7e1a127'
CONTROL_R = 'da832217bbe5f872d7e8cfd3200dd8a6bafbff1751548432f84b6e18e95a179a'
SCOPE = ('Frozen identities only; zero measured panel coverage. Original35 Review is Clorox-only; '
         'company-specific Native execution, outcomes, fees and next-model use remain unproved.')
FIELDS = {'schema','policy','authority','split','round0','origin','members','companies','financial_policy','scope'}
NEW_AUTHORITY = dict(path=str(training.ROOT/'TRAIN25-DIRECT-NEW-CANDIDATE-AUTHORITY.json'),
    sha256='4aa5c123d6ab86c65673abd9502d7e59a9cd88cb5e6031016d9192c1b71933df')


def _prelude(completed_result, split_binding, comparator_binding, authority_binding, root, ids=None):
    if (Path(root) != training.ROOT or completed_result != ORIGIN
            or authority_binding != AUTHORITY or comparator_binding != ROUND0):
        raise ValueError('Exact completed36, direct authority and plain Round0 required')
    authority = training._read(authority_binding)
    if (authority.get('schema') != 'earnings_training25_direct_full_candidate_panel_authority_v1'
            or authority.get('Round0',{}).get('manifest_sha256') != ROUND0['sha256']):
        raise ValueError('Original direct frozen-panel authority differs')
    scope = training.load_scope(split_binding)
    if ids is not None and (type(ids) is not list or ids != scope['training']):
        raise ValueError('Exact unique ordered training25 required before task/origin bodies')
    for cik in scope['training']: training.admit(scope,cik)
    return scope, authority


def _task(cik, runtime):
    resident = tasks.resident(cik)
    company, case, kernel = resident['company'], resident['case'], resident['kernel']
    qa = kernel.get('qa'); parts = Path(qa.get('path','')).parts if type(qa) is dict else ()
    if (company.get('cik') != cik or case.get('cik') != cik or resident.get('runtime') != runtime
            or resident.get('data_binding') != tasks.FULL_PLAN or kernel.get('scorer') != tasks.SCORER
            or case.get('evaluation_kernel') != kernel
            or any(case.get(k) != company.get(k) for k in ('cutoff','target_accession','visible_root'))
            or cik not in parts or case.get('target_accession') not in parts
            or type(qa.get('sha256') if type(qa) is dict else None) is not str
            or re.fullmatch('[0-9a-f]{64}',qa['sha256']) is None):
        raise ValueError('Original admitted company-specific case/kernel/runtime required')
    files = {}
    for name in ('questions.md','filing_index.tsv'):
        rows = [r for r in company['allowed_files'] if r.get('path') == name]
        if len(rows) != 1: raise ValueError('Unique original public question/index identity required')
        files[name] = dict(path=str(Path(company['visible_root'])/name),sha256=rows[0]['sha256'])
    return dict(company_id=cik,case=deepcopy(case),kernel=deepcopy(kernel),
        questions=files['questions.md'],filing_index=files['filing_index.tsv'],
        initial_state_template=dict(policy='fresh_native_task_per_window_company_arm',
            schema='earnings_research_state_v1',cik=cik,cutoff=case['cutoff'],records=[]))


def _descriptor(base, scope, authority, *, root):
    if base.get('previous_result') != ORIGIN:
        raise ValueError('Original completed loader must authenticate exactly36')
    original = training._read(ORIGIN)
    final = original['result']['result']; state = base['population']; pool = final['artifacts'][0]
    if (pool.get('path') != str(Path(ORIGIN['path']).parent/'population-01.json')
            or final['population'] != state or training._read(pool) != state
            or final['feedback'] != base['feedback'] or final['latest_feedback'] != base['feedback']
            or final['last_scored_feedback'] != base['last_scored_feedback']):
        raise ValueError('Preserved completed pool/latest/last-scored joins differ')
    spec = authority['first_panel_candidate']
    ids = dict(control=CONTROL_ID,parent=spec['actual_parent'],candidate=spec['id'])
    sources = dict(control=CONTROL_R,parent=spec['parent_R'],candidate=spec['R'])
    if len(set(ids.values())) != 3 or base['research_feedback'].get('baseline_version_id') != CONTROL_ID:
        raise ValueError('Distinct original control/actual parent/candidate required')
    members = {arm:deepcopy(state['versions'][ids[arm]]) for arm in ARMS}
    for arm, version in members.items():
        if (version['id'] != ids[arm] or version['id'] != digest({a:version[a]['sha256'] for a in ('R','H')})
                or version['R']['sha256'] != sources[arm] or version['H']['sha256'] != spec['H']
                or version['H'] != members['control']['H']):
            raise ValueError('Exact original frozen R/H versions required')
        checked(version['R']); checked(version['H'])  # Hash inert sources; never execute/import them.
    if members['candidate']['axis'] != 'R' or members['candidate']['parent'] != members['parent']['id']:
        raise ValueError('Original single-axis candidate ancestry required')
    runtime_path = str(Path(root)/'inputs'/Path(ORIGIN['path']).parent.name/'runtime-reviewed.json')
    bindings = [b for b in base['evidence'] if b.get('path') == runtime_path]
    if len(bindings) != 1: raise ValueError('One original authenticated runtime binding required')
    runtime = training._read(bindings[0]); fixed = strict_json(tasks._read(tasks.RUNTIME))
    if (runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('id') != Path(ORIGIN['path']).parent.name
            or runtime.get('rates') != fixed['models'][training.MODEL]
            or runtime.get('role_efforts',{}).get('forecast') != fixed['models'][training.MODEL]['effort']):
        raise ValueError('Original fixed model/inference policy required')
    comparator = training.load_comparator(scope,ROUND0)
    if [r['company_id'] for r in comparator['rows']] != scope['training']:
        raise ValueError('Complete original plain25 comparator required')
    companies = [_task(cik,fixed) for cik in scope['training']]
    if len({r['kernel']['qa']['path'] for r in companies}) != 25:
        raise ValueError('Independent company-specific kernel identities required')
    names = ('forecaster','tools/earnings_entry.py','tools/earnings_open_worker.py',
             'tools/earnings_population_execution.py')
    return dict(schema=SCHEMA,policy=POLICY,authority=deepcopy(AUTHORITY),split=deepcopy(scope['split']),
        round0=dict(manifest=deepcopy(ROUND0),kind='plain_original_forecast_comparator',companies=25,targets=125),
        origin=dict(completed_result=deepcopy(ORIGIN),population=deepcopy(pool),
            latest_feedback=deepcopy(base['feedback']),last_scored_feedback=deepcopy(base['last_scored_feedback']),
            population_sha256=digest(state)),members=members,companies=companies,
        financial_policy=dict(data=deepcopy(tasks.FULL_PLAN),scorer=deepcopy(tasks.SCORER),runtime=deepcopy(tasks.RUNTIME),
            original_runtime=deepcopy(bindings[0]),original_source_commit=runtime['source_commit'],
            forecast_limits=deepcopy(runtime['limits']['forecast']),model_rates=deepcopy(runtime['rates']),
            forecast_sources={k:deepcopy(runtime['sources'][k]) for k in names}),scope=SCOPE)


def _produce(completed_result, *, split_binding, comparator_binding, authority_binding, root, ledger, repo, ids=None):
    scope, authority = _prelude(completed_result,split_binding,comparator_binding,authority_binding,root,ids)
    base = completed.load(completed_result,root=root,ledger=ledger,repo=repo)
    value = _descriptor(base,scope,authority,root=root)
    return dict(descriptor=value,base_origin=base)


def freeze_descriptor(completed_result, *, split_binding, comparator_binding, authority_binding, root, ledger, repo):
    """Authenticate the original completed origin once; return metadata plus its verified base."""
    return _produce(completed_result,split_binding=split_binding,comparator_binding=comparator_binding,
        authority_binding=authority_binding,root=root,ledger=ledger,repo=repo)


def freeze_proposal_descriptor(proposal_binding, *, split_binding, comparator_binding, authority_binding,
                               root, ledger, repo):
    """Freeze a genuinely new accepted proposal, not the old R35 selection."""
    # Old36 authenticates ancestry and the original task/resource template only.
    # Its single-company child is never relabelled as this fresh proposal.
    scope,old_authority=_prelude(ORIGIN,split_binding,comparator_binding,AUTHORITY,root)
    if authority_binding != NEW_AUTHORITY:
        raise ValueError('Exact direct new-Author authority required')
    authority=training._read(NEW_AUTHORITY)
    if authority.get('human_answer') != '让 Author 根据完整25家公司 Round0反馈提出新候选，旧34–36仅归档参考':
        raise ValueError('Original new-candidate scope differs')
    from earnings_population_proposal_completed import load_proposal
    verified=load_proposal(proposal_binding,root=root,ledger=ledger,repo=repo)
    if (type(verified) is not dict or verified.get('schema') != 'earnings_training25_verified_proposal_v1'
            or verified.get('accepted') is not True or verified.get('proposal') != proposal_binding
            or type(verified.get('task')) is not dict or verified['task'].get('authority') != NEW_AUTHORITY
            or verified['task'].get('split') != scope['split']
            or verified['task'].get('round0_manifest') != ROUND0
            or verified['task'].get('training_companies') != scope['training']
            or verified['task'].get('smoke_only') is not True):
        raise ValueError('Genuine accepted fresh whole25 proposal required')
    base=verified['base_origin'];state=base['population']
    child,parent,chosen=verified['candidate'],verified['parent'],verified['decision']
    from earnings_population import version as make_version
    from earnings_population_runtime import PROPOSAL_ARCHIVES
    if (type(child) is not dict or type(parent) is not dict or type(chosen) is not dict
            or parent.get('id') not in [state['stable_id'],*state['explorers']]
            or parent['id'] in PROPOSAL_ARCHIVES or state['versions'][parent['id']] != parent
            or child.get('id') in state['versions'] or child.get('parent') != parent['id']
            or child.get('axis') not in ('R','H') or chosen.get('axis') != child['axis']
            or chosen.get('parent_pair_sha256') != parent['id']):
        raise ValueError('Actual permitted implementation parent and fresh R/H code required')
    for member in (child,parent):
        if make_version(**{k:member[k] for k in ('R','H')})['id'] != member['id']:
            raise ValueError('Frozen proposal R/H source identity differs')
        for axis in ('R','H'):checked(member[axis])
    changed=child['axis'];other='H' if changed=='R' else 'R'
    if child[other] != parent[other] or child[changed]['sha256'] == parent[changed]['sha256']:
        raise ValueError('Exactly one actual R/H component must change')
    value=_descriptor(base,scope,old_authority,root=root)
    original=verified['runtime'];financial=value['financial_policy']
    if (original.get('rates') != financial['model_rates']
            or original.get('limits',{}).get('forecast') != financial['forecast_limits']
            or any(original.get('sources',{}).get(k) != b for k,b in financial['forecast_sources'].items())
            or original.get('role_efforts',{}).get('forecast') != financial['model_rates']['effort']):
        raise ValueError('New proposal changed the original frozen forecasting policy')
    value.update(authority=deepcopy(NEW_AUTHORITY),proposal=deepcopy(proposal_binding),
        members=dict(control=value['members']['control'],parent=deepcopy(parent),candidate=deepcopy(child)),
        scope='Fresh accepted whole25 proposal; zero measured panel coverage. Implementation parent is ancestry, '
            'not a full25 champion. Current-company Review is integration smoke only; all25 outcomes remain unmeasured.')
    financial.update(original_runtime=deepcopy(verified['runtime_binding']),
        original_source_commit=original['source_commit'])
    if len({v['id'] for v in value['members'].values()}) != 3:
        raise ValueError('Distinct declared control, actual parent and fresh candidate required')
    return dict(descriptor=value,base_origin=base,proposal=verified)


def load_descriptor(binding, *, policy=None, root, ledger, repo):
    """Explicit receiving boundary; no-policy legacy means no descriptor, not implicit activation."""
    if policy is None and binding is None: return None
    if type(policy) is not str or policy != POLICY or binding is None:
        raise ValueError('Explicit exact frozen-panel policy and binding required')
    value = training._read(binding)
    if (type(value) is not dict or set(value) not in (FIELDS,FIELDS|{'proposal'}) or value.get('schema') != SCHEMA
            or value.get('policy') != POLICY or type(value.get('companies')) is not list
            or any(type(r) is not dict for r in value['companies'])
            or type(value.get('origin')) is not dict or type(value.get('round0')) is not dict):
        raise ValueError('Exact typed frozen-panel descriptor metadata required')
    if 'proposal' in value:
        scope=training.load_scope(value['split'])
        if [r.get('company_id') for r in value['companies']] != scope['training']:
            raise ValueError('Exact ordered25 required before proposal or task body')
        result=freeze_proposal_descriptor(value['proposal'],split_binding=value['split'],
            comparator_binding=value['round0'].get('manifest'),authority_binding=value['authority'],
            root=root,ledger=ledger,repo=repo)
    else:
        result = _produce(value['origin'].get('completed_result'),split_binding=value['split'],
        comparator_binding=value['round0'].get('manifest'),authority_binding=value['authority'],
        root=root,ledger=ledger,repo=repo,ids=[r.get('company_id') for r in value['companies']])
    if value != result['descriptor']:
        raise ValueError('Frozen panel differs from authenticated original identities')
    return result
