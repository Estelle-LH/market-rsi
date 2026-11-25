"""Public Q12 provenance references without exposing local file locations."""

import json
from pathlib import Path
import re


_TOKEN = re.compile(r'[0-9a-f]{64}')
_LOCAL = re.compile(r'(?<![\w:/.])/(?:Users|home|private/tmp|tmp|var/folders)/|file://|api-budget\.sqlite3')
_PRIVATE_LEAF = {'score.json', 'evaluation_qa.json', 'RESEARCH-MEMORY.json', 'api-budget.sqlite3'}


_AUTHOR_LOCAL_LOCATIONS = {
    'TRAIN25-CLEAN152-PUBLIC-SUCCESS-R-READONLY-OBSERVATION.json': (
        'bindings.attempt_root',),
    'TRAIN25-CLEAN155-FIRST8-R-MECHANISM-READONLY.json': ('root',),
    'TRAIN25-CLEAN155-FIXED-NEGATIVE-SOURCE-READONLY.json': (
        'bindings.call_directory', 'source.path'),
    'TRAIN25-CLEAN155-LAST2-R-MECHANISM-READONLY.json': (
        'bindings.forecast-01-08.call_directory', 'bindings.forecast-01-08.role_directory',
        'bindings.forecast-01-09.call_directory', 'bindings.forecast-01-09.role_directory'),
    'TRAIN25-CLEAN156-FIRST8-R-MECHANISM-READONLY.json': ('bindings.root',),
    'TRAIN25-CLEAN156-ROOT-SAVED-NEW2-OUTCOMES-LAST3-R-READONLY.json': ('binding_paths.root',),
    'TRAIN25-CLEAN156-ROOT-SAVED155-NAPCO-SOURCE-AUDIT.json': (
        'actual_parent_comparison.parent_call_directory', 'source_root'),
    'TRAIN25-CLEAN158-FOUR-R-MECHANISM-READONLY.json': ('bindings.root',),
    'TRAIN25-CLEAN158-OPENTEXT-FIXED-ORIGIN-FINANCIAL-READONLY.json': (
        'acquisition_and_parent_comparison.parent_R_receipt.directory',
        'acquisition_and_parent_comparison.parent_public_report.path',
        'later_literal_delivery.path', 'public_source_bindings.root'),
}


def project_author_negatives(prompt):
    """Withhold only exact local location fields in the admitted historical Author records."""
    from copy import deepcopy
    from earnings_population_independent_q12 import positive_public_material
    from earnings_population_memory_delta import typed_equal

    expected = positive_public_material()['mandatory_negative_evidence_bodies']
    records = prompt['research_context']['feedback']['mandatory_negative_evidence_bodies']
    if not typed_equal(records, expected):
        raise ValueError('Exact Source-qualified Author negative records required')
    projected = deepcopy(prompt)
    for record in projected['research_context']['feedback']['mandatory_negative_evidence_bodies']:
        for location in _AUTHOR_LOCAL_LOCATIONS.get(record['name'], ()):
            node = record['literal_saved_public_evidence']
            parts = location.split('.')
            for step in parts[:-1]:
                node = node[step]
            leaf = parts[-1]
            path = node[leaf]
            if type(path) is not str or not Path(path).is_absolute() or not _LOCAL.search(path):
                raise ValueError('Exact historical location field required')
            if leaf == 'path':
                sha = node.get('sha256')
                if type(sha) is not str or _TOKEN.fullmatch(sha) is None:
                    raise ValueError('Exact historical path must retain its existing source digest')
                node[leaf] = 'urn:sha256:' + sha
            else:
                node[leaf] = '[local location withheld]'
    return projected


def project(value):
    """Keep original digest associations; only recognized local bound paths lose location."""
    if type(value) is dict:
        if (set(value) == {'path','sha256'} and type(value['path']) is str
                and Path(value['path']).is_absolute()):
            from earnings_population_independent_q12 import ARTIFACTS, ID
            path = Path(value['path'])
            native = Path('/private/tmp') / ('market-rsi-'+ID)
            if (not (path.is_relative_to(ARTIFACTS) or path.is_relative_to(native))
                    or '..' in path.parts or str(path) != value['path']
                    or path.name in _PRIVATE_LEAF
                    or type(value['sha256']) is not str or _TOKEN.fullmatch(value['sha256']) is None):
                raise ValueError('Q12 external provenance cannot identify an unqualified local artifact')
            return dict(path='urn:sha256:'+value['sha256'], sha256=value['sha256'])
        return {key:project(item) for key,item in value.items()}
    if type(value) is list:
        return [project(item) for item in value]
    if type(value) is str and _LOCAL.search(value):
        raise ValueError('Q12 unqualified local path is not admissible for external delivery')
    return value


def tool_output(rendered, *, tool):
    """Project receipt descriptors from an already admitted tool observation."""
    result = json.loads(rendered)
    if type(result) is not dict:
        raise ValueError('Exact Q12 tool observation object required')
    if 'research_receipt' in result:
        result['research_receipt'] = _receipt_reference(result['research_receipt'])
    if tool == 'record_research_memory' and 'value' in result:
        value = result['value']
        if (type(value) is not dict or set(value) != {'recorded', 'delta', 'learning_claim'}
                or value['recorded'] is not True or value['learning_claim'] is not False):
            raise ValueError('Exact Q12 completed memory acknowledgement required')
        value['delta'] = _receipt_reference(value['delta'])
    projected = json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)
    _reject_local(projected)
    return projected


def _receipt_reference(binding):
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding['path']) is not str or not Path(binding['path']).is_absolute()):
        raise ValueError('Original Q12 local receipt descriptor required')
    return project(binding)


def check_request(request):
    """Last veto for local paths in locally generated user/tool inputs, not opaque model items."""
    _reject_local({key:value for key,value in request.items() if key!='input'})
    for item in request['input']:
        if type(item) is not dict:
            continue  # Original role envelope validation controls all formats.
        if item.get('role')=='user' or item.get('type')=='function_call_output':
            for key in ('content','output'):
                if key in item:
                    _reject_local(item[key])


def _reject_local(value):
    if type(value) is str and _LOCAL.search(value):
        raise ValueError('Q12 request contains an unqualified local provenance path')
    if type(value) is dict:
        for key,item in value.items():
            _reject_local(key)
            _reject_local(item)
    if type(value) is list:
        for item in value:
            _reject_local(item)
