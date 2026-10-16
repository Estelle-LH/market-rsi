"""Opt-in original-full50 company bindings; no labels, inference or state reuse."""
from copy import deepcopy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from edgar_forecast_audit import git_blob
from edgar_forecast_model_pilot import safe_file
from edgar_forecast_tools import FilingTools

ARTIFACTS = Path('/Users/estelle/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts')
RECOVERY = ARTIFACTS / 'earnings-benchmark-recovery-20261014'
DATASET = RECOVERY / 'upstream-git-01'
REVISION = '6b406d516802d91f2c987390aac837e1a546602f'
FULL_PLAN = {'path': str(ARTIFACTS / 'edgar-model-scoring-20261007/pilot-01/full-openai-20261008-02/full-plan.json'),
             'sha256': 'd9d301980815170556cbc5cd24a582d423d4e5764e7fef1012a3be7e29418209'}
METADATA = {'path': str(RECOVERY / 'upstream-metadata-v2.json'),
            'sha256': 'eecac6c070d8e1e9fa910035279dcac2fed6338959684c9d6bc2a88ed6e8e2b9'}
MANIFEST = {'path': str(DATASET / 'benchmark_manifest.json'),
            'sha256': 'd1dbf1ced4b70e4621d85c422ef9ae9858199414f4282bc1773d7745f2e0fa2c'}
SCORER = {'path': str(DATASET / 'scripts/edgar_forecast_bench.py'),
          'sha256': '00283f8dec7565ebf22d3fb232ca4e956d23c76ef2c2e3f40b8f8f65dc23b563'}
RUNTIME = {'path': str(Path(__file__).resolve().parents[1] / 'benchmarks/edgar_forecast/openai_runtime.json'),
           'sha256': '6327387abaeea7ecf3d2f86a3f5be8a7f300b0056d784206284defc8d24bce8b'}
CIK = re.compile(r'CIK[0-9]{10}')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(binding):
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding['path']) is not str or type(binding['sha256']) is not str
            or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])):
        raise ValueError('Exact file binding required')
    path = Path(binding['path'])
    if not path.is_absolute() or path.resolve() != path or not path.is_file():
        raise ValueError('Original regular non-symlink absolute file required')
    data = path.read_bytes()
    if _sha(data) != binding['sha256']:
        raise ValueError('Original resident source hash differs')
    return data


def _upstream(name, metadata):
    data = safe_file(DATASET, name).read_bytes()
    matches = [row for row in metadata['siblings'] if row['rfilename'] == name]
    if len(matches) != 1:
        raise ValueError('Unique original upstream metadata required')
    row = matches[0]
    expected = row.get('lfs', {}).get('sha256')
    valid = _sha(data) == expected if expected else git_blob(data) == row['blobId']
    if len(data) != row['size'] or not valid:
        raise ValueError('Original upstream file differs')
    return data


def _universe():
    plan, metadata = json.loads(_read(FULL_PLAN)), json.loads(_read(METADATA))
    manifest_data = _read(MANIFEST)
    if _upstream('benchmark_manifest.json', metadata) != manifest_data:
        raise ValueError('Original manifest metadata differs')
    manifest = json.loads(manifest_data)
    ordered = [row['cik'] for row in plan['companies']]
    original = [row['cik'] for row in manifest['instances']]
    if (metadata['sha'] != REVISION or plan['dataset_revision'] != REVISION
            or plan['original_manifest_sha256'] != MANIFEST['sha256']
            or plan['scorer_sha256'] != SCORER['sha256']
            or plan['selection'] != 'all_original_CIKs_sorted' or plan['target_count'] != 250
            or len(ordered) != 50 or len(set(ordered)) != 50 or ordered != sorted(ordered)
            or len(original) != 50 or set(ordered) != set(original)
            or any(type(cik) is not str or not CIK.fullmatch(cik) for cik in ordered)):
        raise ValueError('Exact original full50 universe and resident order required')
    return plan, manifest, metadata


def _choose(ordered, excluded, count):
    if (type(excluded) not in {list, tuple, set, frozenset}
            or any(type(cik) is not str or not CIK.fullmatch(cik) for cik in excluded)
            or len(excluded) != len(set(excluded)) or not set(excluded) <= set(ordered)
            or type(count) is not int or not 1 <= count <= len(ordered)):
        raise ValueError('Exact known exclusions and bounded positive company count required')
    available = [cik for cik in ordered if cik not in excluded]
    if len(available) < count:
        raise ValueError('Insufficient unexposed original companies; no substitution')
    return available[:count]


def select_companies(excluded, count):
    """Deterministic resident-plan order; caller supplies logged exposure only."""
    plan, _, _ = _universe()
    return _choose([row['cik'] for row in plan['companies']], excluded, count)


def _cutoff(value):
    date = dt.datetime.strptime(str(value).replace('-', ''), '%Y%m%d').date()
    return min(dt.date(2026, 2, 1), date - dt.timedelta(days=1)).isoformat()


def _company(cik, plan, manifest, metadata):
    if type(cik) is not str or not CIK.fullmatch(cik):
        raise ValueError('Exact original company CIK required')
    companies = [row for row in plan['companies'] if row['cik'] == cik]
    instances = [row for row in manifest['instances'] if row['cik'] == cik]
    if len(companies) != 1 or len(instances) != 1:
        raise ValueError('Company absent or duplicated in original universe')
    company, instance = companies[0], instances[0]
    if company['target_accession'] != instance['target_accession'] or instance['target_count'] != 5:
        raise ValueError('Original five-target company accession required')
    bundle = instance['staged_bundle_path']
    bm = json.loads(_upstream(bundle + '/bundle_manifest.json', metadata))
    if company['cutoff'] != _cutoff(bm['target_date_filed']):
        raise ValueError('Original company public-information cutoff differs')
    tools = FilingTools(company)
    if (len(tools.files) != company['filing_count'] + 2
            or re.findall(r'^### (T\d+) \|', tools.files['questions.md'], re.M)
            != ['T001', 'T002', 'T003', 'T004', 'T005']
            or tools.files['questions.md'].encode() != _upstream(bundle + '/forecast_benchmark_doc.md', metadata)):
        raise ValueError('Original public question/index/filing snapshot differs')
    # Opaque protected bytes are verified, never JSON-decoded or model-visible.
    name = bundle + '/forecast_benchmark_qa.json'
    qa = {'path': str(safe_file(DATASET, name)), 'sha256': _sha(_upstream(name, metadata))}
    return deepcopy(company), qa


def resident(cik):
    """Load exact original task bindings; execution/budget admission is separate."""
    plan, manifest, metadata = _universe()
    company, qa = _company(cik, plan, manifest, metadata)
    scorer = _read(SCORER)
    if _upstream('scripts/edgar_forecast_bench.py', metadata) != scorer:
        raise ValueError('Original scorer metadata differs')
    runtime = json.loads(_read(RUNTIME))
    kernel = {'scorer': deepcopy(SCORER), 'qa': qa}
    case = {key: company[key] for key in ('cik', 'cutoff', 'target_accession', 'visible_root')}
    case.update(allowed_manifest_sha256=_sha(json.dumps(company['allowed_files'],
        sort_keys=True, separators=(',', ':')).encode()), evaluation_kernel=deepcopy(kernel))
    return {'company': company, 'runtime': runtime, 'kernel': kernel,
            'data_binding': deepcopy(FULL_PLAN), 'case': case}
