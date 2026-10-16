"""Executable R/H candidates: parse metadata on host, execute only in Docker."""
import ast
from copy import deepcopy
import hashlib
import json
import re

from earnings_capacity_adapter import _literal_assignment, author_payload, decision
from market_rsi import digest

RESERVED = {'save_research_record', 'search_literature', 'read_literature', 'run_python', 'inspect_trace'}


def schema(value, depth=0):
    if type(value) is not dict or depth > 5 or set(value) - {
            'type', 'properties', 'required', 'additionalProperties', 'items',
            'description', 'enum', 'minimum', 'maximum'}:
        raise ValueError('Bounded local JSON schema required; no external references')
    kind = value.get('type')
    if type(kind) is not str or kind not in {'object', 'array', 'string', 'integer', 'number', 'boolean', 'null'}:
        raise ValueError('Supported explicit JSON type required')
    if kind == 'object':
        fields = value.get('properties')
        if (type(fields) is not dict or len(fields) > 16 or value.get('additionalProperties') is not False
                or type(value.get('required')) is not list or len(value['required']) != len(fields)
                or set(value['required']) != set(fields)):
            raise ValueError('Exact strict object properties required')
        for name, child in fields.items():
            if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name):
                raise ValueError('Bounded argument name required')
            schema(child, depth+1)
    elif kind == 'array':
        schema(value.get('items'), depth+1)
    json.dumps(value, allow_nan=False)
    return deepcopy(value)


def arguments(value, spec):
    kind = spec['type']
    admitted = {'object': (dict,), 'array': (list,), 'string': (str,), 'integer': (int,),
                'number': (int, float), 'boolean': (bool,), 'null': (type(None),)}
    if type(value) not in admitted[kind]:
        raise ValueError('Program tool argument type differs')
    if kind == 'object':
        if set(value) != set(spec['properties']):
            raise ValueError('Exact program argument fields required')
        for name, item in value.items():
            arguments(item, spec['properties'][name])
    elif kind == 'array':
        for item in value:
            arguments(item, spec['items'])
    elif kind in {'integer', 'number'}:
        if 'minimum' in spec and value < spec['minimum'] or 'maximum' in spec and value > spec['maximum']:
            raise ValueError('Program numeric bounds exceeded')
    if 'enum' in spec and not any(digest(value) == digest(item) for item in spec['enum']):
        raise ValueError('Program enum differs')
    json.dumps(value, allow_nan=False)


def program(data, axis):
    if axis not in {'R', 'H'} or type(data) is not bytes or not 1 <= len(data) <= 65_536:
        raise ValueError('Bounded Python program source required')
    text = data.decode()
    tree = ast.parse(text)
    declarations = [node for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'PROGRAM' for target in node.targets)]
    if len(declarations) != 1 or not any(isinstance(node, ast.FunctionDef) and node.name == 'run' for node in tree.body):
        raise ValueError('One literal PROGRAM declaration and run(payload) function required')
    meta = _literal_assignment(ast.get_source_segment(text, declarations[0]), 'PROGRAM')
    if type(meta) is not dict or meta.get('axis') != axis or set(meta) != ({'axis'} if axis == 'R' else {'axis', 'tools'}):
        raise ValueError('Exact program axis metadata required')
    if axis == 'H':
        tools = meta['tools']
        if type(tools) is not list or len(tools) > 8:
            raise ValueError('At most eight program tools required')
        names = set()
        for tool in tools:
            if (type(tool) is not dict or set(tool) != {'name', 'description', 'parameters'}
                    or type(tool['name']) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', tool['name'])
                    or tool['name'] in RESERVED or tool['name'] in names
                    or type(tool['description']) is not str or not 1 <= len(tool['description']) <= 1000
                    or type(tool['parameters']) is not dict
                    or tool['parameters'].get('type') != 'object'):
                raise ValueError('Unique typed program tool required; broker/state operations stay protected')
            names.add(tool['name']); schema(tool['parameters'])
    if len(json.dumps(meta).encode()) > 16_384:
        raise ValueError('Program metadata size exceeded')
    return deepcopy(meta)


def candidate(original, before, chosen):
    decision(chosen, parent_pair_sha256=chosen['parent_pair_sha256'], feedback_sha256=chosen['feedback_sha256'])
    if chosen['axis'] not in {'R', 'H'} or before.get('axis') != chosen['axis']:
        raise ValueError('Exact parent program axis required')
    value = author_payload(original)
    if value['decision_sha256'] != digest(chosen):
        raise ValueError('Author does not bind actual decision')
    after = program(value['source_text'].encode(), chosen['axis'])
    if type(value['test_text']) is not str or len(value['test_text'].encode()) > 32_768:
        raise ValueError('Bounded literal program cases required')
    cases = _literal_assignment(value['test_text'], 'CASES')
    if (type(cases) is not list or not 1 <= len(cases) <= 8
            or any(type(case) is not dict or set(case) != {'input', 'expected'} for case in cases)):
        raise ValueError('Actual run input/expected cases required')
    json.dumps(cases, allow_nan=False)
    return {'profile': after, 'cases': cases, 'author_sha256': digest(value),
            'source_sha256': hashlib.sha256(value['source_text'].encode()).hexdigest(),
            'test_source_sha256': hashlib.sha256(value['test_text'].encode()).hexdigest(),
            'tests_executed': False, 'claim': 'Executable program candidate; host parsed metadata only'}


def run_cases(runner, source, cases):
    results = []
    for case in cases:
        actual = runner.run(source, case['input'])
        results.append({'passed': digest(actual['value']) == digest(case['expected']), 'execution': actual})
    return results
