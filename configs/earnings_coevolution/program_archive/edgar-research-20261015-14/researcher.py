PROGRAM = {'axis': 'R'}

import calendar
import csv
import datetime
import io
import json
import re
from decimal import Decimal, InvalidOperation
import html

GUIDANCE = 'Bind explicit historical periods, durations, units, segments and printed signs. Unknown is not zero. Derived quarters are calculations, not reported facts or forecasts. Preserve actual state bindings; never substitute a receipt hash for a source hash. Before forecasting, require an original-tool cold probe and independent matched-score review. The constructed literal cases are not original-table validation or evidence of benefit or adoption.'
SEGMENTS = ('Alico Citrus', 'Land Management and Other Operations')
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS['sept'] = 9
MONTH_RE = re.compile(r'\b(' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?\s+(\d{1,2})(?:,?\s+((?:19|20)\d{2}))?\b', re.I)
ISO_RE = re.compile(r'\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b')
YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')
DURATION_RE = re.compile(r'\b(three|six|nine|twelve|3|6|9|12)\s+months?\s+ended\b|\byears?\s+ended\b', re.I)
DURATIONS = {'three': 3, 'six': 6, 'nine': 9, 'twelve': 12, '3': 3, '6': 6, '9': 9, '12': 12}


def clean(text):
    text = re.sub(r'<sup\b[^>]*>.*?</sup>', '', str(text), flags=re.I | re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', text)).replace('*', '').replace('\xa0', ' ')).strip()


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def valid_sha(value):
    return value if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) else None


def number(value):
    if value is None or isinstance(value, bool):
        return None
    text = clean(value).replace('$', '').replace(',', '').replace(' ', '').replace('\u2212', '-')
    if not text or len(text) > 80:
        return None
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1]
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)', text):
        return None
    try:
        result = Decimal(text)
        if negative:
            result = -result
        if not result.is_finite():
            return None
        return int(result) if result == result.to_integral_value() else float(result)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def missing(value):
    return clean(value).replace('$', '').strip() in ('-', '\u2014', '\u2013', 'N/A', 'n/a')


def entries(payload):
    text = payload.get('filing_index', '')
    if not isinstance(text, str):
        return []
    question = payload.get('questions', '')
    match = re.search(r'\bfiled:\s*(\d{4})-?(\d{2})-?(\d{2})\b', question if isinstance(question, str) else '', re.I)
    cutoff = '-'.join(match.groups()) if match else '9999-12-31'
    result = []
    try:
        for row in csv.DictReader(io.StringIO(text), delimiter='\t'):
            path = row.get('path', '')
            date = row.get('date_filed', row.get('filed_date', ''))
            form = row.get('form_type', row.get('form', '')).upper().strip()
            if not isinstance(path, str) or not path.startswith('filings/') or '..' in path.split('/') or '\\' in path or '\x00' in path:
                continue
            if re.fullmatch(r'\d{8}', date):
                date = date[:4] + '-' + date[4:6] + '-' + date[6:]
            try:
                datetime.date.fromisoformat(date)
            except (TypeError, ValueError):
                continue
            if date < cutoff:
                result.append({'path': path, 'date': date, 'form': form})
    except (csv.Error, TypeError):
        return []
    return sorted(result, key=lambda item: (item['date'], item['path']), reverse=True)


def acquire(payload, index):
    annuals = [item for item in index if item['form'] == '10-K']
    quarters = [item for item in index if item['form'] == '10-Q']
    requests = []
    seen = set()

    def add(path, offset):
        key = (path, offset)
        if key not in seen and len(requests) < 8:
            requests.append({'tool': 'read_file', 'arguments': {'path': path, 'offset': offset, 'characters': 20000}})
            seen.add(key)

    if annuals:
        add(annuals[0]['path'], 0)
    for item in quarters[:2]:
        for offset in (0, 20000, 40000):
            add(item['path'], offset)
    question = payload.get('questions', '')
    match = re.search(r'\bfiled:\s*\d{4}-?(\d{2})-?\d{2}\b', question if isinstance(question, str) else '', re.I)
    target_month = int(match.group(1)) if match else None
    older = quarters[2:]
    seasonal = [item for item in older if target_month is not None and int(item['date'][5:7]) == target_month]
    if seasonal or older:
        add((seasonal or older)[0]['path'], 20000)
    for item in quarters[:2] + annuals[:1]:
        for offset in (60000, 80000, 100000):
            add(item['path'], offset)
    return requests


def state_bindings(payload):
    result = []
    used = 0
    omitted = 0
    raw = payload.get('records', [])
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('record'), dict):
            continue
        binding = {'sha256': item.get('sha256'), 'record': item['record']}
        size = len(json.dumps(binding, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        if used + size <= 24000:
            result.append(binding)
            used += size
        else:
            omitted += 1
    return result, omitted


def observations(payload, allowed, bindings):
    chunks = []
    problems = []
    raw = payload.get('research_observations', [])
    for observation in raw if isinstance(raw, list) else []:
        if not isinstance(observation, dict):
            continue
        request = observation.get('request', {})
        if not isinstance(request, dict) or request.get('tool') != 'read_file':
            continue
        arguments = request.get('arguments', {})
        if not isinstance(arguments, dict):
            continue
        path = arguments.get('path')
        offset = arguments.get('offset')
        characters = arguments.get('characters')
        if path not in allowed or not integer(offset) or offset < 0 or not integer(characters) or not 1 <= characters <= 20000:
            continue
        output = observation.get('output')
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except (ValueError, TypeError):
                output = None
        for unused in range(3):
            if isinstance(output, dict) and 'value' in output and isinstance(output['value'], dict):
                output = output['value']
            else:
                break
        if not isinstance(output, dict) or output.get('ok') is False or output.get('error'):
            problems.append({'source_path': path, 'offset': offset, 'reason': 'read_not_returned_successfully'})
            continue
        text = output.get('text')
        returned_offset = output.get('offset', offset)
        if output.get('path', path) != path or returned_offset != offset or not isinstance(text, str) or len(text) > characters:
            problems.append({'source_path': path, 'offset': offset, 'reason': 'unusable_read_envelope'})
            continue
        source_sha = valid_sha(output.get('source_sha256')) or valid_sha(output.get('file_sha256'))
        chunks.append({'path': path, 'offset': offset, 'text': text, 'sha': source_sha})
    for binding in bindings:
        record = binding['record']
        quote = record.get('quote')
        offset = record.get('offset')
        path = record.get('source_path')
        if record.get('kind') == 'fact' and path in allowed and integer(offset) and offset >= 0 and isinstance(quote, str) and len(quote) <= 20000 and quote.count('\n') >= 2 and '|' in quote:
            chunks.append({'path': path, 'offset': offset, 'text': quote, 'sha': valid_sha(record.get('source_sha256'))})
    merged = []
    for chunk in sorted(chunks, key=lambda item: (item['path'], item['offset'], -len(item['text']))):
        if merged and merged[-1]['path'] == chunk['path']:
            prior = merged[-1]
            end = prior['offset'] + len(prior['text'])
            overlap = end - chunk['offset']
            if overlap >= 0:
                shared = min(overlap, len(chunk['text']))
                start = chunk['offset'] - prior['offset']
                if prior['text'][start:start + shared] == chunk['text'][:shared]:
                    if overlap < len(chunk['text']):
                        prior['text'] += chunk['text'][overlap:]
                    if prior['sha'] and chunk['sha'] and prior['sha'] != chunk['sha']:
                        prior['sha'] = None
                    elif not prior['sha']:
                        prior['sha'] = chunk['sha']
                    continue
                problems.append({'source_path': chunk['path'], 'offset': chunk['offset'], 'reason': 'conflicting_overlapping_evidence'})
                continue
        merged.append(dict(chunk))
    return merged, problems


def columns(line):
    text = line.strip()
    if '|' not in text:
        return [text]
    if text.startswith('|'):
        text = text[1:]
    if text.endswith('|'):
        text = text[:-1]
    return text.split('|')


def measure(label):
    label = clean(label).lower().strip(' :')
    if re.match(r'^cash paid for interest\b', label):
        return 'cash_paid_interest_net_capitalized' if 'net' in label and 'capitalized' in label else 'cash_paid_interest'
    if re.match(r'^net cash\b', label) and 'operating activities' in label and re.search(r'provided|used', label):
        return 'operating_cash_flow'
    if re.match(r'^land and other leasing(?:\b|$)', label):
        return 'land_other_leasing_revenue'
    if re.fullmatch(r'(?:total )?operating expenses(?: \([^)]*\))?', label):
        return 'operating_expenses'
    if re.fullmatch(r'(?:total )?operating revenues?(?: \([^)]*\))?', label):
        return 'operating_revenue'
    return None


def scope(text):
    text = clean(text).lstrip('# ').strip()
    for segment in SEGMENTS:
        if text.lower() == segment.lower() or (len(text) <= 100 and text.lower().startswith(segment.lower() + ' (')):
            return segment
    if len(text) <= 150 and 'consolidated' in text.lower() and (text.lower() == 'consolidated' or re.search(r'statements?|cash flows|operations|income', text, re.I)):
        return 'consolidated'
    return None


def unit(text):
    text = clean(text).lower()
    if re.search(r'\bin\s+thousands\b', text):
        return 'USD in thousands'
    if re.search(r'\bin\s+millions\b', text):
        return 'USD in millions'
    if re.search(r'\b(?:amounts? in dollars|usd|u\.s\. dollars)\b', text):
        return 'USD'
    return None


def nearest(mapping, column):
    keys = [key for key in mapping if key <= column]
    if keys:
        return mapping[max(keys)]
    if len(mapping) == 1:
        return next(iter(mapping.values()))
    return None


def header_parts(parts):
    dates, years, durations, segments = {}, {}, {}, {}
    for index, raw in enumerate(parts):
        text = clean(raw)
        iso = list(ISO_RE.finditer(text))
        named = list(MONTH_RE.finditer(text))
        found = []
        for match in iso:
            found.append(tuple(int(value) for value in match.groups()))
        for match in named:
            found.append((int(match.group(3)) if match.group(3) else None, MONTHS[match.group(1).lower()], int(match.group(2))))
        if found:
            dates[index] = found[0] if len(set(found)) == 1 else None
        yy = YEAR_RE.findall(text)
        if yy:
            years[index] = int(yy[0]) if len(set(yy)) == 1 else None
        dd = list(DURATION_RE.finditer(text))
        if dd:
            counts = [DURATIONS[match.group(1).lower()] if match.group(1) else 12 for match in dd]
            ambiguous = re.search(r'\b(?:three|six|nine|twelve|3|6|9|12)\s+(?:and|&)\s+(?:three|six|nine|twelve|3|6|9|12)\s+months?', text, re.I)
            durations[index] = counts[0] if len(set(counts)) == 1 and not ambiguous else None
        ss = scope(text)
        if ss:
            segments[index] = ss
    return dates, years, durations, segments


def period_at(date_map, year_map, column):
    parts = nearest(date_map, column)
    if not parts:
        return None
    year = nearest(year_map, column)
    if year is None:
        year = parts[0]
    if year is None:
        return None
    try:
        return datetime.date(year, parts[1], parts[2]).isoformat()
    except (ValueError, TypeError):
        return None


def parse_block(block):
    cells, unknowns = [], []
    dates, years, durations, segment_columns = {}, {}, {}, {}
    header_quotes = []
    scope_value = None
    unit_value = None
    scope_quote = None
    unit_quote = None
    cursor = block['offset']
    after_data = False

    def clear_headers():
        dates.clear()
        years.clear()
        durations.clear()
        segment_columns.clear()
        header_quotes.clear()

    for complete_line in block['text'].splitlines(keepends=True):
        line = complete_line.rstrip('\r\n')
        position = cursor
        cursor += len(complete_line)
        if not line.strip():
            continue
        parts = columns(line)
        labels = [(i, clean(raw)) for i, raw in enumerate(parts) if clean(raw)]
        if not labels:
            continue
        label_index, label = labels[0]
        metric = measure(label)
        numeric_columns = [i for i in range(label_index + 1, len(parts)) if number(parts[i]) is not None or missing(parts[i])]
        is_data = metric is not None and bool(numeric_columns)
        pd, py, pm, ps = header_parts(parts)
        has_header = bool(pd or py or pm)
        line_scope = scope(label)
        line_unit = unit(line)
        quote = {'offset': position, 'quote': line}
        if not is_data:
            if '|' not in line and not has_header:
                clear_headers()
                after_data = False
                if line.lstrip().startswith('#') and not line_scope:
                    scope_value, scope_quote = None, None
                if line_scope == 'consolidated':
                    unit_value, unit_quote = None, None
            if line_scope:
                scope_value, scope_quote = line_scope, quote
            if line_unit:
                unit_value, unit_quote = line_unit, quote
            if has_header:
                if after_data:
                    clear_headers()
                    after_data = False
                if pd:
                    dates.clear()
                    dates.update(pd)
                if py:
                    years.clear()
                    years.update(py)
                if pm:
                    durations.clear()
                    durations.update(pm)
                if ps:
                    segment_columns.clear()
                    segment_columns.update(ps)
                header_quotes.append(quote)
            elif ps and '|' in line and not line_scope:
                segment_columns.clear()
                segment_columns.update(ps)
                header_quotes.append(quote)
            continue
        after_data = True
        for column in numeric_columns:
            literal = parts[column].strip()
            value = number(literal)
            end = period_at(dates, years, column)
            duration = nearest(durations, column)
            segment = nearest(segment_columns, column) or scope_value
            reason = None
            if not end or duration not in (3, 6, 9, 12):
                reason = 'missing_period_or_duration'
            elif not unit_value:
                reason = 'missing_scoped_unit'
            elif not segment:
                reason = 'missing_scoped_segment'
            elif metric == 'land_other_leasing_revenue' and segment != 'Land Management and Other Operations':
                reason = 'ambiguous_leasing_segment'
            elif value is None:
                reason = 'absent_or_non_numeric_cell'
            elif len(line) > 1600 or any(len(item['quote']) > 1600 for item in header_quotes):
                reason = 'evidence_quote_too_large'
            if reason:
                unknowns.append({'source_path': block['path'], 'offset': position, 'column': column, 'literal': literal, 'reason': reason})
                continue
            evidence = []
            for item in [scope_quote, unit_quote] + header_quotes:
                if item and item not in evidence:
                    evidence.append(item)
            evidence.sort(key=lambda item: item['offset'])
            cells.append({'kind': 'fact', 'measure': metric, 'segment': segment, 'period_end': end, 'duration_months': duration, 'unit': unit_value, 'value': value, 'literal': literal, 'source_path': block['path'], 'source_sha256': block['sha'], 'offset': position, 'quote': line, 'headers': evidence, 'state_sha256': []})
    return cells, unknowns


def link_state(cell, bindings):
    result = []
    for binding in bindings:
        record = binding['record']
        digest = valid_sha(binding['sha256'])
        if not digest or record.get('kind') != 'fact':
            continue
        if record.get('source_path') != cell['source_path'] or record.get('period_end') != cell['period_end'] or record.get('unit') != cell['unit'] or number(record.get('value')) != cell['value']:
            continue
        quote = record.get('quote')
        offset = record.get('offset')
        if isinstance(quote, str) and integer(offset) and offset == cell['offset'] and quote == cell['quote']:
            result.append(digest)
    return list(dict.fromkeys(result))


def shift_month_end(text, months):
    date = datetime.date.fromisoformat(text)
    if date.day != calendar.monthrange(date.year, date.month)[1]:
        return None
    number_month = date.year * 12 + date.month - 1 + months
    year, month = divmod(number_month, 12)
    month += 1
    if not 1 <= year <= 9999:
        return None
    return datetime.date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def derive(cells):
    groups = {}
    for index, cell in enumerate(cells):
        key = (cell['measure'], cell['segment'], cell['unit'], cell['period_end'], cell['duration_months'])
        groups.setdefault(key, []).append(index)
    result = []
    for key, current in groups.items():
        metric, segment, currency, end, duration = key
        if duration not in (6, 9, 12):
            continue
        previous_end = shift_month_end(end, -3)
        if not previous_end:
            continue
        previous = groups.get((metric, segment, currency, previous_end, duration - 3), [])
        if not previous:
            continue
        current_values = {cells[index]['value'] for index in current}
        previous_values = {cells[index]['value'] for index in previous}
        if len(current_values) != 1 or len(previous_values) != 1:
            continue
        a, b = current[0], previous[0]
        value = Decimal(str(cells[a]['value'])) - Decimal(str(cells[b]['value']))
        value = int(value) if value == value.to_integral_value() else float(value)
        result.append({'kind': 'calculation', 'measure': metric, 'segment': segment, 'period_end': end, 'duration_months': 3, 'unit': currency, 'value': value, 'inputs': [{'historical_cell': a}, {'historical_cell': b}], 'expression': 'c' + str(a) + ' - c' + str(b)})
    return result


def bounded(result):
    def size():
        return len(json.dumps({'ok': True, 'value': result}, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    while size() > 130000:
        result['truncated'] = True
        if result['derived_quarters']:
            result['derived_quarters'].pop()
        elif result['unknowns']:
            result['unknowns'].pop()
        elif result['record_bindings']:
            result['record_bindings'].pop()
            result['omitted_record_binding_count'] += 1
        elif result['historical_cells']:
            result['historical_cells'].pop()
        else:
            break
    return result


def run(payload):
    if not isinstance(payload, dict):
        payload = {}
    stage = 'controller' if payload.get('stage') == 'controller' else 'forecast'
    index = entries(payload)
    if 'research_observations' not in payload:
        requests = acquire(payload, index)
        if requests:
            return {'research_requests': requests}
    bindings, omitted = state_bindings(payload)
    blocks, unknowns = observations(payload, {item['path'] for item in index}, bindings)
    historical = []
    seen = set()
    for block in blocks:
        found, missing_cells = parse_block(block)
        unknowns.extend(missing_cells)
        for cell in found:
            key = (cell['source_path'], cell['offset'], cell['measure'], cell['segment'], cell['period_end'], cell['duration_months'], cell['literal'])
            if key in seen:
                continue
            seen.add(key)
            cell['state_sha256'] = link_state(cell, bindings)
            historical.append(cell)
    if not blocks:
        unknowns.append({'reason': 'no_returned_table_evidence'})
    result = {'stage': stage, 'historical_cells': historical, 'derived_quarters': derive(historical), 'forecasts': [], 'unknowns': unknowns, 'record_bindings': bindings, 'omitted_record_binding_count': omitted, 'guidance': GUIDANCE, 'truncated': False}
    return bounded(result)
