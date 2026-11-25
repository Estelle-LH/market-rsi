"""Population-only edit delivery; assemble text, never execute candidate code.

The original model response authors edits and tests, not the unchanged parent.
Services separately preserve that response and the mechanically assembled source.
"""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
import re

from edgar_forecast_tools import function
from earnings_capacity_adapter import decision
from earnings_entry import checked, strict_json
from earnings_open_program import arguments, candidate, program
from earnings_open_roles import AUTHOR, OpenAuthor, _format
from earnings_population_roles import message
from market_rsi import digest

FORMAT_NAME = 'earnings_population_delta_author_v1'
FIELDS = {'decision_sha256', 'parent_source_sha256', 'edits', 'test_text'}
BASE_FORMAT = 'earnings_population_delta_author_v2'
BASE_FIELDS = {'decision_sha256', 'comparison_parent_source_sha256',
               'implementation_base_source_sha256', 'edits', 'test_text'}
DELIVERY = (
    'Return only decision_sha256, parent_source_sha256, edits and test_text, copying both supplied hashes. '
    'edits is a list of1..16 objects, each exactly kind, old_text and new_text. kind is replace or append. '
    'A replace old_text must be nonempty and occur exactly once in the ORIGINAL parent, including '
    'overlapping matches; replacement ranges must not overlap. Anchors never refer to previously edited '
    'text. new_text may be empty for deletion. An append has old_text="", nonempty new_text, occurs at '
    'most once and is last. Do not include unchanged parent source merely to re-deliver it. Edits may '
    'replace complete uniquely anchored functions or implementation regions; this delivery format does '
    'not restrict scientific algorithms to parameters or force an append-only or percentage change. '
    'The assembled program must satisfy all original PROGRAM/run and65536-byte limits; test_text keeps '
    'the original literal CASES contract and32768-byte ceiling. Preserve parent bytes outside edits. '
    'A no-op is invalid. Only edits/tests are newly model-authored; assembly reuses unchanged parent bytes. ')
BASE_DELIVERY = DELIVERY.replace(
    'decision_sha256, parent_source_sha256, edits and test_text, copying both supplied hashes.',
    'decision_sha256, comparison_parent_source_sha256, implementation_base_source_sha256, edits and test_text, copying all supplied hashes.').replace(
    'ORIGINAL parent', 'ORIGINAL implementation base').replace(
    'unchanged parent', 'unchanged implementation base').replace(
    'parent bytes', 'implementation-base bytes') + (
    'The implementation base is unadopted source, not the active comparison parent. Current-program tools '
    'still read the active comparison parent; edit the exact inline implementation_base_source_text. '
    'The resulting program must differ from both sources. A trial versus the active comparison parent '
    'measures accumulated repairs, not the isolated effect of these latest edits. ')


def _original(binding):
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding['path']) is not str or not Path(binding['path']).is_absolute()
            or str(Path(binding['path'])) != binding['path']
            or type(binding['sha256']) is not str
            or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])):
        raise ValueError('Exact canonical parent source binding required')
    path = Path(binding['path'])
    try:
        if (path.resolve() != path or path.is_symlink() or not path.is_file()
                or path.stat().st_nlink != 1):
            raise ValueError('Canonical regular single-link parent required before source read')
    except (OSError, RuntimeError) as error:
        raise ValueError('Canonical regular single-link parent metadata unavailable') from error
    return checked(binding)


def _parent(binding, chosen):
    data = _original(binding)
    before = program(data, chosen['axis'])
    return data.decode('utf-8'), before


def _decision(chosen):
    if type(chosen) is not dict:
        raise ValueError('Typed scientific decision required')
    frozen = decision(chosen, parent_pair_sha256=chosen.get('parent_pair_sha256'),
                      feedback_sha256=chosen.get('feedback_sha256'))
    if frozen['axis'] not in {'R', 'H'}:
        raise ValueError('Continue cannot author a delta program')
    return frozen


def implementation_base(chosen, comparison, feedback_binding, reference, *, _depth=0):
    """Rejoin current verified rejected-source receipts, never replay a runtime.

    Eligibility is R-only. Source/receipt checks are not a new execution, quality
    approval or independent reconstruction of the original allowed public data.
    The admitted campaign origin already owns that historical verification.
    """
    frozen = _decision(chosen)
    if frozen['axis'] != 'R':
        return None
    feedback = strict_json(_original(feedback_binding))
    if (feedback.get('schema') != 'earnings_population_campaign_feedback_v1'
            or feedback.get('kind') != 'review_rejected'):
        return None
    child = feedback.get('candidate')
    if type(child) is not dict or child.get('axis') != 'R':
        return None
    if (type(reference) is not dict or reference.get('id') != child.get('id')
            or reference.get('parent') != child.get('parent') or reference.get('axis') != 'R'
            or reference.get('source') != child.get('R') or reference.get('reference_only') is not True
            or reference.get('source_delivery') != 'paged_reference'):
        raise ValueError('Implementation base differs from exact current rejected reference')
    if child['parent'] != frozen['parent_pair_sha256']:
        return None  # A different valid active-parent choice remains ordinary v1.
    if child.get('author') != 'model:DeltaAuthor':
        return None  # Legacy full-source authorship is not silently upgraded.
    if (_depth >= 24 or comparison.get('id') != frozen['parent_pair_sha256']
            or comparison['id'] != digest({a: comparison[a]['sha256'] for a in ('R', 'H')})
            or frozen['feedback_sha256'] != digest(feedback_binding)
            or feedback.get('score_state') != 'unscored' or feedback.get('results') != []
            or child.get('H') != comparison['H']
            or child['id'] != digest({a: child[a]['sha256'] for a in ('R', 'H')})):
        raise ValueError('Exact unscored R base/active comparison/other axis required')
    for axis in ('R', 'H'):
        _original(comparison[axis]); _original(child[axis])
    source, _ = _parent(child['R'], frozen)
    def one(rows, name, label):
        values = [b for b in rows if name(Path(b['path']))]
        if len(values) != 1:
            raise ValueError('One exact implementation-base '+label+' required')
        return values[0]
    assembly_binding = one(child['evidence'], lambda p: p.name == 'delta-assembly.json', 'assembly')
    assembly = strict_json(_original(assembly_binding))
    old_projection = strict_json(_original(assembly['scientific_decision']))
    old = old_projection['scientific_decision']
    if (old.get('parent_pair_sha256') != comparison['id'] or old.get('axis') != 'R'
            or assembly.get('schema') not in {'earnings_population_delta_assembly_v1','earnings_population_delta_assembly_v2'}
            or assembly.get('axis') != 'R'
            or old_projection.get('scientific_decision_sha256') != digest(old)
            or assembly.get('scientific_decision_sha256') != digest(old)
            or assembly.get('source') != child['R']
            or assembly.get('parent_source') != comparison['R']
            or assembly.get('parent_version_id') != comparison['id']
            or assembly['scientific_decision'] not in child['evidence']
            or assembly['raw_patch_response'] not in child['evidence']):
        raise ValueError('Original rejected Delta/active-parent/source provenance required')
    if assembly['schema'] == 'earnings_population_delta_assembly_v2' and (
            assembly.get('comparison_parent_source') != comparison['R']
            or assembly.get('comparison_parent_version_id') != comparison['id']
            or type(assembly.get('implementation_base')) is not dict):
        raise ValueError('Original v2 comparison-parent provenance differs')
    prior_base = assembly.get('implementation_base') if assembly.get('schema') == 'earnings_population_delta_assembly_v2' else None
    raw = strict_json(_original(assembly['raw_patch_response']))
    business = assemble(comparison['R'], old, raw, implementation_base=prior_base, _depth=_depth+1)
    if (business['source_text'] != source or digest(business) != assembly['assembled_business_sha256']
            or business['test_text'].encode() != _original(assembly['tests'])):
        raise ValueError('Original rejected Delta does not reconstruct exact source/tests')
    reviewed = feedback['exploration_review']; evidence = reviewed['evidence']
    if reviewed.get('accepted_for_exploration') is not False:
        raise ValueError('An adopted or unreviewed source is not a rejected repair base')
    cases_binding = one(evidence, lambda p: p.name.endswith('-cases.json'), 'authored cases')
    cases = strict_json(_original(cases_binding))
    parsed = candidate(business, program(_original(comparison['R']), 'R'), old)
    rows = cases.get('results')
    if (cases.get('candidate_id') != child['id'] or type(rows) is not list
            or len(rows) != len(parsed['cases']) or any(type(r.get('passed')) is not bool for r in rows)):
        raise ValueError('Exact rejected-source authored-case receipts required')
    if not all(row['passed'] for row in rows):
        return None  # Failing-test bases require a separately supported path.
    import earnings_open_researcher as researcher
    for row, case in zip(rows, parsed['cases']):
        if digest(researcher.execution_value(row['execution'], source, case['input'])) != digest(case['expected']):
            raise ValueError('Rejected-source case flags differ from original execution')
    outcome_binding = one(evidence, lambda p: p.name.endswith('-outcome.json'), 'quality outcome')
    outcome = strict_json(_original(outcome_binding))
    review_binding = one(evidence, lambda p: p.name == 'response.json' and re.fullmatch(r'review-[0-9]+', p.parent.name), 'original model review')
    if (outcome.get('schema') != 'earnings_population_exploration_review_v1'
            or outcome.get('candidate_id') != child['id'] or outcome.get('accepted_for_exploration') is not False
            or message(strict_json(_original(review_binding))) != {k: outcome[k] for k in ('candidate_id', 'accepted_for_exploration', 'rationale')}):
        raise ValueError('Rejected-source outcome differs from original model review')
    probes = []
    for stage in ('forecast', 'controller'):
        bound = one(evidence, lambda p: re.fullmatch(r'review-[0-9]+-'+stage+r'-probe.json', p.name), stage+' cold probe')
        probe = strict_json(_original(bound)); payload = probe['input']; run = probe['execution']
        if (probe.get('company_id') != feedback['company_id'] or payload.get('stage') != stage
                or payload.get('records') != [] or probe['diagnostics'].get('source_sha256') != child['R']['sha256']
                or probe['diagnostics'].get('execution_sha256') != run['receipt']['sha256']):
            raise ValueError('Rejected-source cold probe company/source/input differs')
        following = payload
        if 'request_execution' in run:
            requested = researcher.requests(researcher.execution_value(run['request_execution'], source, payload))
            if requested is None or [row['request'] for row in run.get('research_observations', [])] != requested:
                raise ValueError('Rejected-source cold evidence phase differs from original requests')
            following = dict(payload, research_observations=run['research_observations'])
        value = researcher.execution_value(run, source, following)
        if researcher.requests(value) is not None:
            raise ValueError('Rejected-source cold probe is unfinished')
        probes.append(deepcopy(bound))
    return dict(schema='earnings_population_implementation_base_v1', axis='R', version_id=child['id'],
        source=deepcopy(child['R']), comparison_parent=dict(id=comparison['id'],
            R=deepcopy(comparison['R']), H=deepcopy(comparison['H'])), reference=deepcopy(reference),
        feedback_binding=deepcopy(feedback_binding), original_assembly=deepcopy(assembly_binding),
        quality_review=deepcopy(review_binding), authored_cases=deepcopy(cases_binding), cold_probes=probes,
        adopted=False, scope='Inert tested-quality-rejected implementation base; active comparison parent remains distinct. Fresh source/cases/Review required; no forecast or adoption permission.')


def checked_base(base, chosen, parent_binding, *, _depth=0):
    if type(base) is not dict or base.get('schema') != 'earnings_population_implementation_base_v1':
        raise ValueError('Typed verified implementation base required')
    comparison = base['comparison_parent']
    if comparison.get(chosen['axis']) != parent_binding:
        raise ValueError('Implementation base changed the active comparison source')
    actual = implementation_base(chosen, comparison, base['feedback_binding'], base['reference'], _depth=_depth)
    if actual is None or digest(actual) != digest(base):
        raise ValueError('Implementation base differs from current exact rejected-source proof')
    return base['source']


def _edit_source(parent, edits):
    """The single literal assembler shared by preview and final delivery."""
    if type(edits) is not list or not 1 <= len(edits) <= 16:
        raise ValueError('One to sixteen literal edits required')
    spans, suffix = [], ''
    for index, edit in enumerate(edits):
        if (type(edit) is not dict or set(edit) != {'kind', 'old_text', 'new_text'}
                or type(edit['kind']) is not str or edit['kind'] not in {'replace', 'append'}
                or type(edit['old_text']) is not str or type(edit['new_text']) is not str
                or edit['old_text'] == edit['new_text']):
            raise ValueError('Exact non-noop literal edit required')
        old, new = edit['old_text'], edit['new_text']
        if len(old.encode('utf-8')) > 65536 or len(new.encode('utf-8')) > 65536:
            raise ValueError('Edit exceeds assembled source ceiling')
        if edit['kind'] == 'append':
            if old or not new or suffix or index != len(edits) - 1:
                raise ValueError('Only one nonempty final append is allowed')
            suffix = new
            continue
        start = parent.find(old) if old else -1
        if start < 0 or parent.find(old, start + 1) >= 0:
            raise ValueError('Replacement anchor must occur exactly once in original parent')
        spans.append((start, start + len(old), new))
    spans.sort(key=lambda row: row[0])
    cursor, pieces = 0, []
    for start, end, new in spans:
        if start < cursor:
            raise ValueError('Original replacement ranges overlap')
        pieces.extend((parent[cursor:start], new))
        cursor = end
    source = ''.join(pieces) + parent[cursor:] + suffix
    if source == parent:
        raise ValueError('No source change is not a candidate')
    return source


def assemble(parent_binding, chosen, original_raw_completed_response, *, implementation_base=None, _depth=0):
    """Assemble literal edits; original candidate AST/cases checks stay final."""
    frozen = _decision(chosen)
    bound = parent_binding if implementation_base is None else checked_base(implementation_base, frozen, parent_binding, _depth=_depth)
    parent, before = _parent(bound, frozen)
    patch = message(original_raw_completed_response)
    fields = FIELDS if implementation_base is None else BASE_FIELDS
    if (type(patch) is not dict or set(patch) != fields
            or patch['decision_sha256'] != digest(frozen)
            or (implementation_base is None and patch['parent_source_sha256'] != parent_binding['sha256'])
            or (implementation_base is not None and (patch['comparison_parent_source_sha256'] != parent_binding['sha256']
                or patch['implementation_base_source_sha256'] != bound['sha256']))
            or type(patch['edits']) is not list or not 1 <= len(patch['edits']) <= 16
            or type(patch['test_text']) is not str):
        raise ValueError('Exact decision/parent-bound delta fields required')
    source = _edit_source(parent, patch['edits'])
    if implementation_base is not None and hashlib.sha256(source.encode()).hexdigest() in {bound['sha256'], parent_binding['sha256']}:
        raise ValueError('New source must differ from implementation base and active comparison parent')
    business = {'decision_sha256': digest(frozen), 'source_text': source,
                'test_text': patch['test_text']}
    candidate(business, before, frozen)
    return business


def preview(parent_binding, chosen, edits_json, *, implementation_base=None):
    """Structural source feedback only; no tests, execution, files or approval."""
    try:
        frozen = _decision(chosen)
        bound = parent_binding if implementation_base is None else checked_base(implementation_base, frozen, parent_binding)
        parent, _ = _parent(bound, frozen)
    except (ValueError, TypeError, KeyError, OSError, SyntaxError) as error:
        raise RuntimeError('Preview authority could not be verified') from error
    if type(edits_json) is not str:
        raise RuntimeError('Preview accepts only an edits_json string')
    result = dict(schema='earnings_population_delta_preview_v1',
        decision_sha256=digest(frozen), parent_source_sha256=parent_binding['sha256'],
        source_utf8_bytes=None, source_limit_bytes=65536, excess_source_utf8_bytes=None,
        source_valid=False, errors=[], tests_validated=False, code_executed=False,
        candidate_saved=False, final_approval=False)
    if implementation_base is not None:
        result.pop('parent_source_sha256')
        result.update(schema='earnings_population_delta_preview_v2',
            comparison_parent_source_sha256=parent_binding['sha256'],
            implementation_base_source_sha256=bound['sha256'])
    try:
        edits = strict_json(edits_json)
    except ValueError:
        result['errors'] = [{'code': 'invalid_edits_json'}]
        return result
    try:
        source = _edit_source(parent, edits)
        encoded = source.encode('utf-8')
    except (ValueError, UnicodeError) as error:
        # No exception text/source excerpt is copied into the model observation.
        result['errors'] = [{'code': 'invalid_literal_edits', 'error_type': type(error).__name__}]
        return result
    result.update(source_utf8_bytes=len(encoded), source_sha256=hashlib.sha256(encoded).hexdigest(),
                  excess_source_utf8_bytes=max(0, len(encoded) - 65536))
    if implementation_base is not None and result['source_sha256'] in {bound['sha256'], parent_binding['sha256']}:
        result['errors'] = [{'code': 'source_equals_base_or_comparison_parent'}]
        return result
    if len(encoded) > 65536:
        result['errors'] = [{'code': 'source_size_exceeded'}]
        return result
    try:
        program(encoded, frozen['axis'])
    except SyntaxError as error:
        result['errors'] = [{'code': 'invalid_python_syntax', 'line': error.lineno, 'column': error.offset}]
    except (ValueError, UnicodeError):
        result['errors'] = [{'code': 'invalid_program_metadata'}]
    else:
        result['source_valid'] = True
    return result


class _PreviewBroker:
    """One role-local pure tool; underlying authority and budgets stay live."""
    name = 'preview_delta_source'

    def __init__(self, base):
        self.base, self.active = base, None
        self.implementation_base, self.base_proof_sha256 = None, None
        self.original = deepcopy(base.definitions)
        if type(self.original) is not list or any(t.get('name') == self.name for t in self.original):
            raise ValueError('Distinct source preview definition required')
        self.tool = function(self.name,
            'Optional structural preview of literal edits against this Author invocation\'s exact active parent/decision. '
            'Supply edits_json only, a JSON list with the final delta edit rules. Returns source bytes/excess/AST errors, '
            'not source text, test validation, code execution, financial quality or final approval.',
            {'edits_json': {'type': 'string'}})
        self.preview_calls, self.preview_returned = 0, 0
        self.forwarded_calls, self.forwarded_returned = 0, 0

    def _check(self):
        try:
            generated = getattr(type(self.base), '_definitions', None)
            if (self.base.definitions != self.original
                    or callable(generated) and self.base._definitions() != self.original):
                raise RuntimeError('Underlying broker definitions drifted')
        except (ValueError, TypeError, KeyError, OSError) as error:
            raise RuntimeError('Underlying broker definitions could not be verified') from error

    @property
    def definitions(self):
        self._check()
        return deepcopy(self.original + [self.tool])

    def current_programs(self):
        self._check()
        return self.base.current_programs()

    def research_context(self, *, include_source=False):
        self._check()
        reader = getattr(type(self.base), 'research_context', None)
        return reader(self.base, include_source=include_source) if callable(reader) else None

    def available_traces(self):
        self._check()
        return self.base.available_traces()

    def activate(self, parent_binding, chosen, *, implementation_base=None):
        if self.active is not None:
            raise RuntimeError('An Author preview invocation is already active')
        self.active = deepcopy((parent_binding, chosen))
        self.implementation_base = deepcopy(implementation_base)
        try:
            if implementation_base is not None:
                checked_base(implementation_base, chosen, parent_binding)
                self.base_proof_sha256 = digest(implementation_base)
            self._active_parent()
        except BaseException:
            self.active = None
            self.implementation_base, self.base_proof_sha256 = None, None
            raise

    def _active_parent(self):
        self._check()
        if self.active is None:
            raise RuntimeError('No active Author invocation for source preview')
        bound, chosen = self.active
        try:
            _parent(bound, _decision(chosen))
            current = self.base.current_programs()
            if current[chosen['axis']]['source_sha256'] != bound['sha256']:
                raise ValueError('Current parent differs')
            if self.implementation_base is not None:
                if (digest(self.implementation_base) != self.base_proof_sha256
                        or self.implementation_base['comparison_parent'][chosen['axis']] != bound):
                    raise ValueError('Implementation-base proof drifted')
                _original(self.implementation_base['feedback_binding'])
                _parent(self.implementation_base['source'], chosen)
        except (ValueError, TypeError, KeyError, OSError, SyntaxError) as error:
            raise RuntimeError('Active preview parent/decision drift') from error
        return bound, chosen

    def _budget(self, *, before=False):
        calls = getattr(self.base, 'calls', None)
        returned = getattr(self.base, 'returned', None)
        calls = calls if type(calls) is int else self.forwarded_calls
        returned = returned if type(returned) is int else self.forwarded_returned
        if (calls + self.preview_calls > 64 - int(before)
                or returned + self.preview_returned > 2_000_000):
            raise RuntimeError('Original shared research action budget exhausted')

    def dispatch(self, name, args):
        self._check()
        self._budget(before=True)
        if name != self.name:
            self.forwarded_calls += 1
            result = self.base.dispatch(name, args)
            self.forwarded_returned += len(json.dumps(result, allow_nan=False).encode())
            self._check()
            self._budget()
            return result
        bound, chosen = self._active_parent()
        try:
            arguments(args, self.tool['parameters'])
            if len(json.dumps(args, ensure_ascii=False, allow_nan=False).encode()) > 65536:
                raise ValueError('Argument bytes exceed original bound')
        except (ValueError, TypeError, KeyError) as error:
            raise RuntimeError('Exact bounded preview protocol required') from error
        self.preview_calls += 1
        result = {'value': preview(bound, chosen, args['edits_json'], implementation_base=self.implementation_base)}
        self.preview_returned += len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode())
        self._active_parent()
        self._budget()
        return result


def review_index(parent_binding, chosen, original_binding, source_binding, *,
                 version_id, assembly_binding):
    """Pure verified navigation, not code execution or a quality assessment.

    Pager coordinates count decoded code points, preserving original newlines.
    AST ranges locate declarations only; they do not prove runtime behavior.
    The caller/broker retains authority for the registered population version.
    """
    if type(version_id) is not str or not re.fullmatch('[0-9a-f]{64}', version_id):
        raise ValueError('Exact registered version identifier required')
    frozen = _decision(chosen)
    raw = strict_json(_original(original_binding))
    assembly = strict_json(_original(assembly_binding))
    base = assembly.get('implementation_base') if assembly.get('schema') == 'earnings_population_delta_assembly_v2' else None
    assembled = assemble(parent_binding, frozen, raw, implementation_base=base)
    source = _original(source_binding).decode('utf-8')
    if (source != assembled['source_text'] or type(assembly) is not dict
            or assembly.get('schema') != ('earnings_population_delta_assembly_v1' if base is None else 'earnings_population_delta_assembly_v2')
            or assembly.get('axis') != frozen['axis']
            or assembly.get('parent_version_id') != frozen['parent_pair_sha256']
            or assembly.get('parent_source') != parent_binding
            or assembly.get('raw_patch_response') != original_binding
            or assembly.get('source') != source_binding
            or assembly.get('scientific_decision_sha256') != digest(frozen)
            or assembly.get('assembled_business_sha256') != digest(assembled)
            or _original(assembly.get('tests')).decode('utf-8') != assembled['test_text']):
        raise ValueError('Index must join exact original delta/parent/assembly/source/tests')
    if base is not None and (assembly.get('comparison_parent_source') != parent_binding
            or assembly.get('comparison_parent_version_id') != frozen['parent_pair_sha256']):
        raise ValueError('Index comparison parent differs from implementation base')
    effective_binding = parent_binding if base is None else base['source']
    parent, _ = _parent(effective_binding, frozen)
    edits = message(raw)['edits']
    replacements = sorted((parent.index(e['old_text']), len(e['old_text']), e['new_text'])
                          for e in edits if e['kind'] == 'replace')
    ranges, shift = [], 0
    for start, old_size, new in replacements:
        ranges.append(dict(kind='replace', parent=[start, start + old_size],
                           candidate=[start + shift, start + shift + len(new)]))
        shift += len(new) - old_size
    if edits[-1]['kind'] == 'append':
        ranges.append(dict(kind='append', parent=[len(parent), len(parent)],
                           candidate=[len(parent) + shift, len(source)]))

    def read_at(offset, end):
        offset = min(offset, len(source) - 1)
        return dict(tool='read_population_program', arguments=dict(version_id=version_id,
            axis=frozen['axis'], offset=offset, characters=max(1, min(4000, end - offset))))

    offsets = [0]
    # AST lines use physical universal newlines, not Unicode separators that
    # str.splitlines also recognizes inside otherwise valid string literals.
    offsets.extend(match.end() for match in re.finditer(r'\r\n|\r|\n', source))
    if offsets[-1] != len(source):
        offsets.append(len(source))
    definitions, runs = [], []
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        first = min([node.lineno] + [d.lineno for d in node.decorator_list])
        lo, hi = offsets[first - 1], offsets[node.end_lineno]
        row = dict(name=node.name[:80], kind='class' if isinstance(node, ast.ClassDef) else 'function',
                   start_char=lo, end_char=hi)
        if len(node.name) > 80:
            row['name_truncated'] = True
        if isinstance(node, ast.FunctionDef) and node.name == 'run':
            runs.append(row)
        if any(lo < r['candidate'][1] and hi > r['candidate'][0]
               or r['candidate'][0] == r['candidate'][1] and lo < r['candidate'][0] < hi
               for r in ranges):
            definitions.append(row)
    # program(...) already requires a top-level run declaration. Last declaration
    # is a navigation target, not a claim about arbitrary dynamic rebinding.
    entrypoint = runs[-1]
    entrypoint = dict(entrypoint, read=read_at(entrypoint['start_char'], entrypoint['end_char']))
    result = dict(schema='earnings_population_review_index_v1', axis=frozen['axis'],
        version_id=version_id, decision_sha256=digest(frozen), source=deepcopy(source_binding),
        parent=deepcopy(parent_binding), raw_patch_response=deepcopy(original_binding),
        assembly=deepcopy(assembly_binding), source_characters=len(source),
        changed_ranges=ranges, changed_functions=definitions, total_changed_functions=len(definitions),
        omitted_functions=0, entrypoint=entrypoint, first_read=deepcopy(entrypoint['read']),
        notice='Verified navigation only. Use supplied character offsets, not sequential prefix pages. '
               'Declarations/deltas do not prove preserved behavior or financial correctness.')
    if base is not None:
        result.update(schema='earnings_population_review_index_v2', parent=deepcopy(effective_binding),
            comparison_parent=deepcopy(parent_binding), comparison_parent_version_id=frozen['parent_pair_sha256'],
            implementation_base_version_id=base['version_id'], range_basis='implementation_base',
            notice='Verified navigation relative to the unadopted implementation base, not active comparison parent. Fresh trials versus the active parent measure accumulated repairs, not isolated marginal edits; no quality/adoption claim.')
    size = lambda: len(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
    while size() > 6000 and result['changed_functions']:
        result['changed_functions'].pop()
        result['omitted_functions'] += 1
    if size() > 6000:
        # Long canonical paths are not needed by the existing version/axis pager.
        # Preserve every identity, range and run locator without gating algorithms.
        for key in ('source', 'parent', 'raw_patch_response', 'assembly', *(['comparison_parent'] if base is not None else [])):
            result[key] = dict(sha256=result[key]['sha256'])
        result['binding_paths_omitted'] = True
    return result


class DeltaAuthor(OpenAuthor):
    """Original counted Author with an opt-in population edit response only."""

    def __init__(self, *args, broker, **kwargs):
        super().__init__(*args, broker=_PreviewBroker(broker), **kwargs)

    def _final_instruction(self):
        return (getattr(self, '_delivery', DELIVERY) + 'Finish the complete declared JSON and test cases now. No further tools; '
                'do not return source_text, a diff fence, line-number patch or commentary.')

    def author(self, chosen, before_profile, slot, *, parent_binding, implementation_base=None):
        frozen = _decision(chosen)
        parent_binding = deepcopy(parent_binding)
        parent, before = _parent(parent_binding, frozen)
        current = self.broker.current_programs()
        if (type(before_profile) is not dict or before_profile != before
                or type(current) is not dict or type(current.get(frozen['axis'])) is not dict
                or current[frozen['axis']].get('source_sha256') != parent_binding['sha256']):
            raise ValueError('Delta parent differs from exact current broker program/metadata')
        prompt = {'decision': frozen, 'before_profile': deepcopy(before),
                  'decision_sha256': digest(frozen), 'parent_source': deepcopy(parent_binding),
                  'parent_source_sha256': hashlib.sha256(parent.encode('utf-8')).hexdigest()}
        context_reader = getattr(type(self.broker), 'research_context', None)
        if callable(context_reader):
            context = context_reader(self.broker, include_source=True)
            if context is not None:
                prompt['research_context'] = context
        if implementation_base is not None:
            base_binding = checked_base(implementation_base, frozen, parent_binding)
            if (prompt.get('research_context', {}).get('implementation_base') != implementation_base
                    or prompt['research_context'].get('implementation_base_decision') != frozen):
                raise ValueError('Author base differs from actual broker feedback context')
            prompt.pop('parent_source'); prompt.pop('parent_source_sha256')
            prompt.update(comparison_parent=dict(version_id=frozen['parent_pair_sha256'], source=deepcopy(parent_binding)),
                comparison_parent_source_sha256=parent_binding['sha256'],
                implementation_base=deepcopy(implementation_base),
                implementation_base_source_sha256=base_binding['sha256'],
                implementation_base_source_text=_original(base_binding).decode())
        elif prompt.get('research_context', {}).get('implementation_base') is not None:
            raise ValueError('Eligible bound implementation base cannot silently disappear')
        fields = {'decision_sha256': {'type': 'string', 'enum': [digest(frozen)]},
                  'parent_source_sha256': {'type': 'string', 'enum': [parent_binding['sha256']]},
                  'edits': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'items': {
                      'type': 'object', 'properties': {
                          'kind': {'type': 'string', 'enum': ['replace', 'append']},
                          'old_text': {'type': 'string'}, 'new_text': {'type': 'string'}},
                      'required': ['kind', 'old_text', 'new_text'], 'additionalProperties': False}},
                  'test_text': {'type': 'string'}}
        delivery, format_name = DELIVERY, FORMAT_NAME
        if implementation_base is not None:
            fields.pop('parent_source_sha256')
            fields.update(comparison_parent_source_sha256={'type':'string','enum':[parent_binding['sha256']]},
                implementation_base_source_sha256={'type':'string','enum':[base_binding['sha256']]})
            delivery, format_name = BASE_DELIVERY, BASE_FORMAT
        instructions = AUTHOR.replace('source_text contains exactly one',
                                      'The assembled program contains exactly one').replace(
            'Return only decision_sha256, source_text and test_text, copying the supplied decision digest. ',
            delivery)
        instructions += (' You may optionally call preview_delta_source(edits_json) before final delivery. '
            'It checks literal assembly, source UTF-8 bytes and PROGRAM/run syntax/metadata only against '
            'this exact active parent and decision. It does not execute code, validate CASES, judge '
            'financial correctness, save a candidate or grant approval; final assembly and test checks remain required. ')
        if implementation_base is not None:
            instructions = instructions.replace('this exact active parent and decision',
                'the verified inline implementation base and exact decision, not the active comparison source returned by current-program reads')

        def decode(response):
            assemble(parent_binding, frozen, response, implementation_base=implementation_base)
            return message(response)  # Saved delta is the actual model patch, never a forged full-source reply.

        # Normal construction always installs the role-local broker. The type
        # guard leaves inert decode-only object.__new__ fixtures unchanged.
        preview_broker = self.broker if isinstance(self.broker, _PreviewBroker) else None
        previous_tool = None
        if preview_broker is not None:
            preview_broker.activate(parent_binding, frozen, implementation_base=implementation_base)
            if implementation_base is not None:
                previous_tool = deepcopy(preview_broker.tool)
                preview_broker.tool['description'] = previous_tool['description'].replace(
                    'exact active parent/decision', 'verified implementation base/decision (not active comparison parent)')
                self.definitions = preview_broker.definitions
        self._delivery = delivery
        try:
            return self._run_open(prompt, slot, instructions, _format(format_name, fields),
                                  decode, 'delta', 'COMPLETED_CANDIDATE')
        finally:
            if preview_broker is not None:
                preview_broker.active = None
                preview_broker.implementation_base, preview_broker.base_proof_sha256 = None, None
                if previous_tool is not None:
                    preview_broker.tool = previous_tool
                    self.definitions = preview_broker.definitions
            self.__dict__.pop('_delivery', None)
