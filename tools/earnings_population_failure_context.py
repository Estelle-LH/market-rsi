"""Bounded raw public failure examples, never parsed financial facts or R input.

Reconstruct saved executions without running code. Original search responses
remain unchanged; nearby text and its hashes/offsets are explicitly supplied by
outer context preparation, not claimed as observations the R received.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from edgar_forecast_tools import FilingTools
from earnings_entry import checked, strict_json
from earnings_open_guest import MAX_RESULT_BYTES
import earnings_open_researcher as researcher
from market_rsi import digest

ROOT = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016')
NATIVE = Path('/private/tmp')
IDENT = r'edgar-population-20261016-[0-9]{2}'
MAX_BYTES = 24576


def _path(binding, pattern, limit):
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding['path']) is not str or type(binding['sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', binding['sha256'])
            or not re.fullmatch(pattern, binding['path'])):
        raise ValueError('Exact owned public failure binding required before read')
    path = Path(binding['path'])
    if (path.resolve() != path or not path.is_file() or path.is_symlink()
            or path.stat().st_nlink != 1 or path.stat().st_size > limit):
        raise ValueError('Canonical bounded original failure file required')
    return path


def _sample(row, request_index, hit, hit_index):
    return dict(request_index=request_index, hit_index=hit_index,
        request=deepcopy(row['request']), observed_hit=deepcopy(hit),
        observed_hit_sha256=digest(hit))


def _context(tools, sample, characters):
    hit, request = sample['observed_hit'], sample['request']
    path, number = hit['path'], hit['line']
    content = tools.files[path]
    lines = content.splitlines(keepends=True)
    line = content.splitlines()[number-1]
    # Match the original literal search crop, not a financial/header heuristic.
    position = line.casefold().find(request['arguments']['query'].casefold())
    anchor = sum(map(len, lines[:number-1])) + max(0, position-100)
    earliest = sum(map(len, lines[:max(0, number-21)]))
    offset = max(earliest, anchor-characters//2)
    arguments = dict(path=path, offset=offset, characters=characters)
    result = tools.dispatch('read_file', arguments)
    if not offset <= anchor < offset+len(result['text']):
        raise ValueError('Nearby public context must contain the original hit anchor')
    return dict(provided_by='harness_preparation_not_R_observation',
        source_sha256=hashlib.sha256(content.encode()).hexdigest(),
        read_arguments=arguments, read_result=result,
        text_sha256=hashlib.sha256(result['text'].encode()).hexdigest(),
        untrusted_evidence=True)


def project(probe_binding, *, source_binding, company):
    """Verify one owned cold probe and return at most three raw examples."""
    pattern = re.escape(str(NATIVE)) + r'/market-rsi-(' + IDENT + r')/review-([0-9]{2})-(forecast|controller|prior)-probe\.json'
    path = _path(probe_binding, pattern, 4500000)
    identifier, round_index, stage = re.fullmatch(pattern, str(path)).groups()
    # Authorship remains at its original version; a later owned probe can
    # execute those exact bytes without inventing a new candidate.py alias.
    source_pattern = re.escape(str(ROOT/'attempts')) + r'/(' + IDENT + r')/roles/author-([0-9]{2})/candidate\.py'
    source_path = _path(source_binding, source_pattern, 65536)
    source_identifier, source_round = re.fullmatch(source_pattern, str(source_path)).groups()
    source = checked(source_binding).decode('utf-8')
    probe = strict_json(checked(probe_binding))
    payload, execution = probe['input'], probe['execution']
    expected_stage = 'forecast' if stage == 'prior' else stage
    if (probe.get('company_id', company['cik']) != company['cik']
            or payload.get('stage') != expected_stage or payload.get('records') != []):
        raise ValueError('Cold failure company/stage/state differs')
    receipt_pattern = re.escape(str(ROOT/'attempts'/identifier/'code')) + r'/call-[0-9a-f]{32}/result\.json'
    for original in researcher.originals(execution):
        receipt = _path(original['receipt'], receipt_pattern, 100000)
        # Original guest print adds one newline; DockerRunner permits it too.
        for name, limit in [('input.json', 2200000), ('stdout.bin', MAX_RESULT_BYTES+1), ('stderr.bin', 65536)]:
            sibling = receipt.parent/name
            if (sibling.resolve() != sibling or not sibling.is_file()
                    or sibling.stat().st_nlink != 1 or sibling.stat().st_size > limit):
                raise ValueError('Saved execution originals escaped owned receipt')
    tools = FilingTools(company)
    if (payload.get('questions') != tools.files['questions.md']
            or payload.get('filing_index') != tools.files['filing_index.tsv']):
        raise ValueError('Failure public task differs from the exact allowed snapshot')
    researcher.verify(execution, source, payload, company)
    diagnostics = probe['diagnostics']
    if (diagnostics.get('source_sha256') != source_binding['sha256']
            or diagnostics.get('execution_sha256') != execution['receipt']['sha256']):
        raise ValueError('Failure diagnostics lost source/execution joins')
    rows = execution.get('research_observations', [])
    selected, seen, same_line, pair, total_hits = [], set(), {}, [], 0
    for ri, row in enumerate(rows):
        if row['request']['tool'] != 'search_files':
            continue
        chosen = False
        for hi, hit in enumerate(row['output']['hits']):
            total_hits += 1
            if not hit['path'].startswith('filings/'):
                continue
            if (set(hit) != {'path', 'line', 'text'} or hit['path'] not in tools.files
                    or type(hit['line']) is not int or not 1 <= hit['line'] <= len(tools.files[hit['path']].splitlines())):
                raise ValueError('Only exact original allowed filing search hits are public examples')
            sample = _sample(row, ri, hit, hi)
            key = (hit['path'], hit['line'], hit['text'])
            if not chosen and len(selected) < 3 and key not in seen:
                selected.append(sample)
                seen.add(key)
                chosen = True
            location = (hit['path'], hit['line'])
            previous = same_line.setdefault(location, sample)
            if (not pair and previous['request']['arguments']['query'] != row['request']['arguments']['query']
                    and previous['observed_hit']['text'] != hit['text']):
                pair = [deepcopy(previous), deepcopy(sample)]
    result = dict(schema='earnings_population_failure_context_v1',
        source_attempt_id=source_identifier, source_author_round=source_round,
        execution_attempt_id=identifier, execution_review_round=round_index,
        company_id=company['cik'], cutoff=company['cutoff'], stage=payload['stage'],
        allowed_manifest_sha256=digest(company['allowed_files']),
        probe=deepcopy(probe_binding), source=deepcopy(source_binding),
        first_execution=deepcopy(execution.get('request_execution', execution)['receipt']),
        final_execution=deepcopy(execution['receipt']),
        original_observations_sha256=digest(rows), original_request_count=len(rows),
        original_returned_hit_count=total_hits, examples=selected,
        distinct_query_crops_same_line=pair,
        selection=dict(policy='first distinct filing hit per original request, original order, maximum three',
            omitted_hit_observations=total_hits-len(selected), nearby_preceding_lines_max=20,
            context_characters_max=4000, serialized_bytes_max=MAX_BYTES),
        scope='Untrusted exact public excerpts, not financial facts or correctness. Nearby context/hashes/offsets are outer preparation only; original R search hits have path/line/text only. One original request phase, at most eight requests, remains unchanged. Different query crops are not contradictory source files. No new model/tool choice or predictive gain is claimed.')
    characters = 4000
    while True:
        for sample in selected:
            sample['outer_public_context'] = _context(tools, sample, characters)
        result['selection']['delivered_context_characters_max'] = characters
        result['selection']['contexts_shortened_for_packet_bound'] = characters != 4000
        if len(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()) <= MAX_BYTES:
            return result
        characters //= 2
        if characters < 500:
            raise ValueError('Exact raw failure evidence exceeds bounded context; do not silently drop provenance')
