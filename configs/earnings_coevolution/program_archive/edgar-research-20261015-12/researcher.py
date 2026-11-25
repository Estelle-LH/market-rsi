PROGRAM = {'axis': 'R'}

import calendar
import csv
import datetime
import html
import io
import json
import re
from decimal import Decimal, InvalidOperation

FORECAST_GUIDANCE = 'Use explicitly bound historical cells; blanks and dashes are unknown. Cumulative differences are calculations, not reported quarters. Forecast separately. Missing source hashes remain unknown; existing state bindings are not new records.'
CONTROLLER_GUIDANCE = FORECAST_GUIDANCE + ' Judge matched original-score benefit and nonregression, not record count. This advice makes no adoption or score-gain claim.'
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS['sept'] = 9
MD = re.compile(r'\b(' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?\s+(\d{1,2})(?:,?\s+((?:19|20)\d{2}))?\b', re.I)
DURATION = re.compile(r'\b(three|six|nine|twelve|3|6|9|12)\s+months?\s+ended\b|\byear\s+ended\b', re.I)
COUNTS = {'three': 3, 'six': 6, 'nine': 9, 'twelve': 12, '3': 3, '6': 6, '9': 9, '12': 12}
YEAR = re.compile(r'\b(?:19|20)\d{2}\b')


def clean(value):
    text = html.unescape(re.sub(r'<[^>]*>', ' ', str(value)))
    return re.sub(r'\s+', ' ', text.replace('*', '').replace('\xa0', ' ')).strip()


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    text = clean(value).replace('\u2212', '-')
    if text.startswith('$'):
        text = text[1:].strip()
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1].strip()
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', text):
        return None
    try:
        result = Decimal(text.replace(',', ''))
        return -result if negative else result
    except InvalidOperation:
        return None


def plain(value):
    return int(value) if value == value.to_integral_value() else float(value)


def allowed_paths(index):
    result = []
    if not isinstance(index, str):
        return result
    for row in csv.reader(io.StringIO(index), delimiter='\t'):
        for field in row:
            path = field.strip()
            if path.startswith('filings/') and path.endswith('.md') and '..' not in path.split('/') and path not in result:
                result.append(path)
    return result


def wrappers(payload):
    raw = payload.get('records', [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and isinstance(item.get('record'), dict) and isinstance(item.get('sha256'), str)]


def plan(paths, records):
    requests = []
    windows = []
    for binding in records:
        record = binding['record']
        path, offset = record.get('source_path'), record.get('offset')
        if record.get('kind') != 'fact' or path not in paths or not integer(offset) or offset < 0:
            continue
        if any(p == path and start <= offset < start + 20000 for p, start in windows):
            continue
        start = max(0, offset - 8000)
        windows.append((path, start))
        requests.append({'tool': 'read_file', 'arguments': {'path': path, 'offset': start, 'characters': 20000}})
        if len(requests) == 8:
            break
    if requests:
        return requests
    queries = ['Cash paid for interest', 'Land and Other Leasing', 'Total operating expenses', 'Net cash']
    for path in sorted(paths, reverse=True)[:2]:
        for query in queries:
            requests.append({'tool': 'search_files', 'arguments': {'query': query, 'path_prefix': path, 'max_hits': 5}})
    return requests


def unwrap(output):
    for unused in range(5):
        if not isinstance(output, dict):
            return None
        if output.get('ok') is False or output.get('error') or output.get('truncated') is True:
            return None
        if isinstance(output.get('value'), dict) and 'text' not in output and 'hits' not in output:
            output = output['value']
        else:
            return output
    return None


def source_hash(output):
    value = output.get('source_sha256', output.get('file_sha256'))
    return value if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) else None


def acquire(observations, paths, unknowns, leads):
    chunks = []
    if not isinstance(observations, list):
        unknowns.append({'reason': 'invalid_research_observations'})
        return chunks
    if len(observations) > 8:
        unknowns.append({'reason': 'excess_observations_ignored'})
    for index, observation in enumerate(observations[:8]):
        if not isinstance(observation, dict):
            unknowns.append({'request_index': index, 'reason': 'invalid_observation'})
            continue
        request = observation.get('request', {})
        if not isinstance(request, dict):
            request = {}
        args = request.get('arguments', {})
        if not isinstance(args, dict):
            args = {}
        output = unwrap(observation.get('output'))
        tool = request.get('tool')
        if output is None:
            unknowns.append({'request_index': index, 'reason': 'failed_or_incomplete_observation'})
            continue
        if tool == 'search_files':
            prefix, query, maximum = args.get('path_prefix'), args.get('query'), args.get('max_hits')
            valid = prefix in ['', 'filings/'] + paths and isinstance(query, str) and 1 <= len(query) <= 200 and integer(maximum) and 1 <= maximum <= 50
            if not valid:
                unknowns.append({'request_index': index, 'reason': 'invalid_search_binding'})
                continue
            hits = output.get('hits', [])
            if isinstance(hits, list):
                for hit in hits[:maximum]:
                    if not isinstance(hit, dict):
                        continue
                    path = hit.get('path', hit.get('file'))
                    text = hit.get('text', hit.get('nearby', ''))
                    if path in paths and (prefix in ('', 'filings/') or path == prefix) and isinstance(text, str):
                        leads.append({'source_path': path, 'line': hit.get('line'), 'text': text[:800]})
            continue
        if tool != 'read_file':
            unknowns.append({'request_index': index, 'reason': 'unsupported_evidence_tool'})
            continue
        path, offset, count = args.get('path'), args.get('offset'), args.get('characters')
        text = output.get('text')
        valid = path in paths and integer(offset) and offset >= 0 and integer(count) and 1 <= count <= 20000
        valid = valid and isinstance(text, str) and len(text) <= count and output.get('path', path) == path and output.get('offset', offset) == offset
        if not valid:
            unknowns.append({'request_index': index, 'reason': 'read_binding_mismatch'})
            continue
        chunks.append({'path': path, 'offset': offset, 'text': text, 'sha': source_hash(output)})
    merged = []
    for chunk in sorted(chunks, key=lambda c: (c['path'], c['sha'] or '', c['offset'])):
        if merged:
            previous = merged[-1]
            end = previous['offset'] + len(previous['text'])
            if previous['path'] == chunk['path'] and previous['sha'] == chunk['sha'] and chunk['offset'] <= end:
                overlap = min(end - chunk['offset'], len(chunk['text']))
                start = chunk['offset'] - previous['offset']
                if previous['text'][start:start + overlap] != chunk['text'][:overlap]:
                    merged.pop()
                    unknowns.append({'source_path': chunk['path'], 'offset': chunk['offset'], 'reason': 'conflicting_read_overlap'})
                else:
                    previous['text'] += chunk['text'][overlap:]
                continue
        merged.append(dict(chunk))
    return merged


def citation(offset, quote):
    return {'offset': offset, 'quote': quote}


def cells_of(line):
    pipes = [m.start() for m in re.finditer(r'\|', line)]
    if len(pipes) < 2:
        return []
    return [line[pipes[i] + 1:pipes[i + 1]].strip() for i in range(len(pipes) - 1)]


def segment_name(label):
    label = clean(label).lower().rstrip(':')
    if label == 'alico citrus':
        return 'Alico Citrus'
    if label in ('land management and other operations', 'land management & other operations'):
        return 'Land Management and Other Operations'
    return None


def unit_name(value):
    text = clean(value).lower().replace('_', ' ')
    if text in ('usd thousands', 'usd thousand', 'thousands of dollars', 'dollars in thousands'):
        return 'USD_thousands'
    if text in ('usd millions', 'millions of dollars', 'dollars in millions'):
        return 'USD_millions'
    if text in ('usd', 'dollars', 'us dollars'):
        return 'USD'
    return None


def prefix_context(prefix):
    unit = None
    scope = None
    unit_ref = None
    scope_ref = None
    for offset, line in prefix[-64:]:
        text = clean(line).lower()
        before_except = text.split('except')[0]
        if not re.search(r'\b(boxes|acres|shares)\b', before_except):
            match = re.search(r'\bin (thousands|millions|dollars)\b', text)
            if match:
                unit = {'thousands': 'USD_thousands', 'millions': 'USD_millions', 'dollars': 'USD'}[match.group(1)]
                unit_ref = citation(offset, line)
        heading = line.lstrip().startswith(('#', '**')) or (line.strip() and line.strip().isupper())
        if heading:
            named = segment_name(line)
            if named:
                scope, scope_ref = named, citation(offset, line)
            elif 'consolidated' in text:
                scope, scope_ref = 'Consolidated', citation(offset, line)
    return unit, scope, unit_ref, scope_ref


def header_update(raw, columns, headers, offset, line):
    if clean(raw[0]):
        return False
    tokens = [clean(value) for value in raw[1:]]
    recognized = any(DURATION.search(t) or MD.search(t) or YEAR.fullmatch(t) or 'change' in t.lower() or '%' in t for t in tokens)
    if not recognized:
        return False
    if any(DURATION.search(t) for t in tokens):
        for column in columns:
            column.clear()
        headers.clear()
    for index, token in enumerate(tokens):
        if index >= len(columns):
            break
        duration, date = DURATION.search(token), MD.search(token)
        if duration or date:
            stop = index + 1
            while stop < len(tokens) and not tokens[stop]:
                stop += 1
            values = {}
            if duration:
                values['duration'] = COUNTS.get((duration.group(1) or '').lower(), 12)
            if date:
                values['month'] = MONTHS[date.group(1).lower()]
                values['day'] = int(date.group(2))
                if date.group(3):
                    values['year'] = int(date.group(3))
            for position in range(index, min(stop, len(columns))):
                columns[position].update(values)
        if YEAR.fullmatch(token):
            columns[index]['year'] = int(token)
        if 'change' in token.lower() or '%' in token:
            columns[index]['invalid'] = True
    headers.append(citation(offset, line))
    del headers[:-4]
    return True


def period(column):
    if column.get('invalid') or column.get('duration') not in (3, 6, 9, 12):
        return None
    try:
        end = datetime.date(column['year'], column['month'], column['day'])
        return end.isoformat(), column['duration']
    except (KeyError, ValueError, TypeError):
        return None


def measure_name(label, section, scope):
    label = clean(label).lower().rstrip(':')
    if 'cash paid for interest' in label:
        return 'cash_interest', 'cash'
    if 'net cash' in label and 'operating activities' in label:
        return 'operating_cash', 'cash'
    if label in ('net (loss) income', 'net income (loss)', 'net income', 'net loss'):
        return 'net_income', 'accrual'
    if label == 'interest expense':
        return 'interest_expense', 'accrual'
    if label == 'land and other leasing':
        return ('leasing_revenue' if section == 'revenue' else 'leasing_expenses' if section == 'expense' else None), 'accrual'
    if label in ('alico citrus', 'total alico citrus'):
        return ('citrus_revenue' if section == 'revenue' else 'citrus_expenses' if section == 'expense' else None), 'accrual'
    if label in ('total operating expenses', 'total operating costs and expenses'):
        return ('citrus_expenses' if scope == 'Alico Citrus' else 'operating_expenses'), 'accrual'
    if label in ('total operating revenues', 'total operating revenue'):
        return ('citrus_revenue' if scope == 'Alico Citrus' else 'operating_revenue'), 'accrual'
    if label == 'total' and scope and section:
        if scope == 'Alico Citrus':
            return ('citrus_revenue' if section == 'revenue' else 'citrus_expenses'), 'accrual'
        return ('operating_revenue' if section == 'revenue' else 'operating_expenses'), 'accrual'
    return None


def parse_table(chunk, rows, prefix, historical, unknowns):
    width = min(16, max(len(cells_of(line)) - 1 for offset, line in rows))
    if width < 1:
        return
    columns = [{} for unused in range(width)]
    headers = []
    unit, scope, unit_ref, scope_ref = prefix_context(prefix)
    section = None
    section_ref = None
    for offset, line in rows:
        raw = cells_of(line)
        if not raw or all(not clean(value) or re.fullmatch(r'[-:]+', clean(value)) for value in raw):
            continue
        if header_update(raw, columns, headers, offset, line):
            continue
        label = clean(raw[0])
        if not label:
            continue
        data = raw[1:width + 1]
        empty = all(not value.strip() for value in data)
        lower = label.lower().rstrip(':')
        if lower in ('operating revenues', 'operating revenue', 'operating expenses', 'operating costs and expenses') and empty:
            section = 'revenue' if 'revenue' in lower else 'expense'
            section_ref = citation(offset, line)
            continue
        named = segment_name(label)
        if named and empty:
            scope, scope_ref = named, citation(offset, line)
            continue
        if empty and 'net cash' in lower and 'operating activities' in lower and raw[0].startswith('**'):
            continue
        row_scope = named or scope
        definition = measure_name(label, section, row_scope)
        if definition is None:
            continue
        measure, basis = definition
        refs = [ref for ref in [scope_ref, unit_ref, section_ref] + headers if ref is not None]
        unique = {(ref['offset'], ref['quote']): ref for ref in refs}
        context = [unique[key] for key in sorted(unique)]
        for index in range(width):
            literal = data[index] if index < len(data) else ''
            value = numeric(literal)
            binding = period(columns[index])
            reason = None
            if value is None:
                reason = 'missing_or_ambiguous_value'
            elif binding is None:
                reason = 'ambiguous_period'
            elif unit is None:
                reason = 'ambiguous_unit'
            elif row_scope is None:
                reason = 'ambiguous_segment'
            elif measure is None:
                reason = 'ambiguous_measure_scope'
            elif len(line) > 1200 or any(len(ref['quote']) > 1000 for ref in context):
                reason = 'oversize_evidence_quote'
            if reason:
                unknowns.append({'source_path': chunk['path'], 'offset': offset, 'column': index + 1, 'literal': literal if len(literal) <= 200 else None, 'reason': reason})
                continue
            historical.append({'kind': 'fact', 'measure': measure, 'segment': row_scope, 'basis': basis, 'period_end': binding[0], 'duration_months': binding[1], 'unit': unit, 'value': plain(value), 'literal': literal, 'column': index + 1, 'source_path': chunk['path'], 'source_sha256': chunk['sha'], 'offset': offset, 'quote': line, 'context': context, 'state_refs': []})


def parse_chunk(chunk, historical, unknowns):
    prefix, rows = [], []
    offset = chunk['offset']
    for full_line in chunk['text'].splitlines(keepends=True):
        line = full_line.rstrip('\r\n')
        is_table = line.lstrip().startswith('|') and line.rstrip().endswith('|')
        if is_table:
            rows.append((offset, line))
        else:
            if rows:
                parse_table(chunk, rows, prefix, historical, unknowns)
                rows, prefix = [], []
            prefix.append((offset, line))
            prefix = prefix[-64:]
        offset += len(full_line)
    if rows:
        parse_table(chunk, rows, prefix, historical, unknowns)


def identity(cell):
    return tuple(cell[key] for key in ('measure', 'segment', 'basis', 'unit', 'period_end', 'duration_months'))


def fiscal_start(cell):
    end = datetime.date.fromisoformat(cell['period_end'])
    if end.day != calendar.monthrange(end.year, end.month)[1]:
        return None
    month_index = end.year * 12 + end.month - cell['duration_months']
    return month_index


def derive_quarters(cells, unknowns):
    groups = {}
    for index, cell in enumerate(cells):
        groups.setdefault(identity(cell), []).append(index)
    usable = []
    for key, indices in groups.items():
        if len({str(cells[index]['value']) for index in indices}) != 1:
            unknowns.append({'measure': key[0], 'period_end': key[4], 'reason': 'conflicting_historical_values'})
        else:
            usable.append(indices[0])
    result = []
    for current_index in usable:
        current = cells[current_index]
        start = fiscal_start(current)
        if start is None or current['duration_months'] not in (6, 9, 12):
            continue
        for prior_index in usable:
            prior = cells[prior_index]
            if tuple(current[k] for k in ('measure', 'segment', 'basis', 'unit')) != tuple(prior[k] for k in ('measure', 'segment', 'basis', 'unit')):
                continue
            if current['duration_months'] - prior['duration_months'] != 3 or fiscal_start(prior) != start:
                continue
            value = Decimal(str(current['value'])) - Decimal(str(prior['value']))
            result.append({'kind': 'calculation', 'measure': current['measure'], 'segment': current['segment'], 'basis': current['basis'], 'period_end': current['period_end'], 'duration_months': 3, 'unit': current['unit'], 'value': plain(value), 'inputs': [current_index, prior_index], 'expression': 'inputs[0] - inputs[1]'})
    return result


def link_state(cells, records):
    for cell in cells:
        for index, binding in enumerate(records):
            record = binding['record']
            if record.get('kind') != 'fact' or record.get('source_path') != cell['source_path'] or record.get('period_end') != cell['period_end']:
                continue
            if record.get('offset') != cell['offset'] or record.get('quote') != cell['quote']:
                continue
            if unit_name(record.get('unit', '')) != cell['unit'] or numeric(record.get('value')) != numeric(cell['value']):
                continue
            if cell['source_sha256'] is not None and record.get('source_sha256') != cell['source_sha256']:
                continue
            if record.get('literal') != cell['literal']:
                continue
            cell['state_refs'].append(index)


def compact_unique(items, maximum):
    result, seen = [], set()
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
            if len(result) == maximum:
                break
    return result


def bounded(result):
    trimmed = False
    def size():
        return len(json.dumps({'ok': True, 'value': result}, ensure_ascii=True).encode('utf-8'))
    while size() > 120000:
        trimmed = True
        if result['derived_quarters']:
            result['derived_quarters'].pop()
        elif result['historical_cells']:
            result['historical_cells'].pop()
        elif result['leads']:
            result['leads'].pop()
        elif result['state_bindings']:
            result['state_bindings'].pop()
        elif result['unknowns']:
            result['unknowns'].pop()
        else:
            break
    if trimmed:
        result['unknowns'].append({'reason': 'output_limit_omissions', 'detail': 'Omitted advice is not absent evidence; original state is unchanged.'})
    return result


def run(payload):
    if not isinstance(payload, dict) or payload.get('stage') not in ('forecast', 'controller'):
        return {'error': 'unsupported_stage'}
    stage = payload['stage']
    paths = allowed_paths(payload.get('filing_index', ''))
    records = wrappers(payload)
    if 'research_observations' not in payload:
        requests = plan(paths, records)
        if requests:
            return {'research_requests': requests}
    unknowns, leads, historical = [], [], []
    if not paths:
        unknowns.append({'reason': 'no_allowed_filing_paths'})
    chunks = acquire(payload.get('research_observations', []), paths, unknowns, leads)
    for chunk in chunks:
        parse_chunk(chunk, historical, unknowns)
    historical = compact_unique(historical, 96)
    link_state(historical, records)
    derived = derive_quarters(historical, unknowns)
    leads = compact_unique(leads, 16)
    if leads and not historical:
        unknowns.append({'reason': 'table_context_not_returned', 'detail': 'Search hits are leads only; original header, units and segment evidence are still needed through the ordinary evidence workflow.'})
    result = {'stage': stage, 'historical_cells': historical, 'derived_quarters': derived, 'unknowns': compact_unique(unknowns, 64), 'state_bindings': records, 'leads': leads, 'guidance': CONTROLLER_GUIDANCE if stage == 'controller' else FORECAST_GUIDANCE}
    return bounded(result)
