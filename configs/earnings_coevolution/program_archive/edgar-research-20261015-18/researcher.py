PROGRAM = {'axis': 'R'}

import calendar
import csv
import datetime
import html
import io
import json
import re
from decimal import Decimal, InvalidOperation

GUIDANCE = 'Historical cells only; unknown is not zero. Derived quarters are calculations, not forecasts. Keep source hashes distinct from state bindings. Original-table cold-probe and independent matched-score review remain required; constructed literal cases do not establish benefit or adoption.'
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS['sept'] = 9
MONTH_RE = re.compile(r'\b(' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?\s+(\d{1,2})(?:,?\s+((?:19|20)\d{2}))?\b', re.I)
ISO_RE = re.compile(r'\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b')
YEAR_RE = re.compile(r'(?:19|20)\d{2}')
DURATION_RE = re.compile(r'\b(three|six|nine|twelve|3|6|9|12)\s+months?\s+ended\b|\byears?\s+ended\b', re.I)
AMBIGUOUS_DURATION = re.compile(r'\b(?:three|six|nine|twelve|3|6|9|12)\s+(?:and|&)\s+(?:three|six|nine|twelve|3|6|9|12)\s+months?', re.I)
DURATIONS = {'three': 3, 'six': 6, 'nine': 9, 'twelve': 12, '3': 3, '6': 6, '9': 9, '12': 12}


def clean(value):
    text = re.sub(r'<sup\b[^>]*>.*?</sup>', '', str(value), flags=re.I | re.S)
    text = html.unescape(re.sub(r'<[^>]*>', ' ', text))
    return re.sub(r'\s+', ' ', text.replace('*', '').replace('\xa0', ' ')).strip()


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def valid_sha(value):
    return value if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) else None


def number(value):
    if value is None or isinstance(value, bool):
        return None
    text = clean(value).replace('$', '').replace(',', '').replace(' ', '').replace('\u2212', '-')
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1]
    if not text or len(text) > 80 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)', text):
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


def scope(text):
    text = clean(text).lower()
    if 'alico citrus' in text:
        return 'Alico Citrus'
    if 'land management' in text:
        return 'Land Management and Other Operations'
    if 'consolidated' in text or re.search(r'\balico,?\s+inc\b', text):
        return 'consolidated'
    return None


def unit(text):
    text = clean(text).lower()
    if 'in thousands' in text:
        return 'USD in thousands'
    if 'in millions' in text:
        return 'USD in millions'
    if text in ('usd', 'dollars', 'in dollars'):
        return 'USD'
    return None


def measure(text):
    text = clean(text).lower()
    if 'interest' in text and 'paid' in text:
        return 'cash_interest_paid'
    if 'cash' in text and 'operating activities' in text:
        return 'operating_cash_flow'
    if 'operating expenses' in text:
        return 'operating_expenses'
    if 'operating revenues' in text or 'operating revenue' in text:
        return 'operating_revenues'
    if 'interest expense' in text:
        return 'interest_expense'
    if 'gross profit' in text or 'gross loss' in text:
        return 'gross_profit'
    if 'income before income taxes' in text or 'loss before income taxes' in text:
        return 'pretax_income'
    if ('net income' in text or 'net loss' in text) and not any(word in text for word in ('share', 'attributable', 'noncontrolling')):
        return 'net_income'
    return None


def entries(payload):
    text = payload.get('filing_index', '')
    question = payload.get('questions', '')
    if not isinstance(text, str):
        return []
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
    except (csv.Error, TypeError, AttributeError):
        return []
    return sorted(result, key=lambda item: (item['date'], item['path']), reverse=True)


def acquire(payload, index):
    annuals = [item for item in index if item['form'] == '10-K']
    quarters = [item for item in index if item['form'] == '10-Q']
    requests, seen = [], set()

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
    result, used, omitted = [], 0, 0
    raw = payload.get('records', [])
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('record'), dict):
            continue
        binding = {'sha256': item.get('sha256'), 'record': item['record']}
        try:
            size = len(json.dumps(binding, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
        except (ValueError, TypeError):
            omitted += 1
            continue
        if used + size <= 24000:
            result.append(binding)
            used += size
        else:
            omitted += 1
    return result, omitted


def observation_blocks(payload, allowed):
    blocks, problems = [], []
    raw = payload.get('research_observations', [])
    for observation in raw if isinstance(raw, list) else []:
        if not isinstance(observation, dict):
            continue
        request = observation.get('request', {})
        if not isinstance(request, dict) or request.get('tool') != 'read_file':
            continue
        args = request.get('arguments', {})
        if not isinstance(args, dict):
            continue
        path, start, count = args.get('path'), args.get('offset'), args.get('characters')
        if path not in allowed or not integer(start) or start < 0 or not integer(count) or not 1 <= count <= 20000:
            continue
        output = observation.get('output')
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except (ValueError, TypeError):
                output = None
        for unused in range(4):
            if isinstance(output, dict) and output.get('ok') is not False and not output.get('error') and isinstance(output.get('value'), dict):
                output = output['value']
            else:
                break
        if not isinstance(output, dict) or output.get('ok') is False or output.get('error'):
            problems.append({'source_path': path, 'offset': start, 'reason': 'read_not_returned_successfully'})
            continue
        text = output.get('text')
        if output.get('path', path) != path or output.get('offset', start) != start or not isinstance(text, str) or len(text) > count:
            problems.append({'source_path': path, 'offset': start, 'reason': 'unusable_read_envelope'})
            continue
        # A receipt hash, a snippet digest, and a file hash are different objects.
        source_sha = valid_sha(output.get('source_sha256')) or valid_sha(output.get('file_sha256'))
        blocks.append({'path': path, 'offset': start, 'text': text, 'source_sha256': source_sha})
    # Recover context across contiguous original reads, but never bridge a gap.
    merged = []
    for block in sorted(blocks, key=lambda b: (b['path'], b['offset'])):
        if merged:
            prior = merged[-1]
            end = prior['offset'] + len(prior['text'])
            overlap = end - block['offset']
            if prior['path'] == block['path'] and prior['source_sha256'] == block['source_sha256'] and 0 <= overlap <= len(block['text']):
                if not overlap or prior['text'][-overlap:] == block['text'][:overlap]:
                    prior['text'] += block['text'][overlap:]
                    continue
        merged.append(dict(block))
    return merged, problems


def nearest(mapping, column):
    candidates = [key for key in mapping if key <= column]
    return mapping[max(candidates)] if candidates else None


def date_at(dates, years, column):
    parts = nearest(dates, column)
    if parts is None:
        return None
    year = nearest(years, column)
    if year is None:
        year = parts[0]
    try:
        return datetime.date(year, parts[1], parts[2]).isoformat()
    except (ValueError, TypeError):
        return None


def parse_block(block):
    facts, unknowns = [], []
    dates, years, durations, segments, units = {}, {}, {}, {}, {}
    scope_value = unit_value = None
    scope_quote = unit_quote = section_quote = None
    section_measure = None
    map_quotes = []
    after_data = False
    width = 0
    cursor = block['offset']

    def quote_at(position, line):
        return {'offset': position, 'quote': line}

    def evidence():
        result, seen = [], set()
        for item in [scope_quote, unit_quote] + map_quotes + [section_quote]:
            if item is not None and (item['offset'], item['quote']) not in seen:
                result.append(dict(item))
                seen.add((item['offset'], item['quote']))
        return sorted(result, key=lambda item: item['offset'])

    for complete_line in block['text'].splitlines(keepends=True):
        line = complete_line.rstrip('\r\n')
        position = cursor
        cursor += len(complete_line)
        text = clean(line)
        if not text or len(line) > 2000:
            continue
        is_table = line.strip().startswith('|') and line.strip().endswith('|')
        if is_table:
            parts = line.strip()[1:-1].split('|')
            if all(not clean(part) or re.fullmatch(r':?-+:?', clean(part)) for part in parts):
                continue
            label = clean(parts[0])
        else:
            parts, label = ['', line], ''
        numeric_columns = [i for i in range(1, len(parts)) if number(parts[i]) is not None or missing(parts[i])]
        row_measure = measure(label) if is_table else None
        row_scope = scope(label) if is_table else None
        # A year row must be structurally a header: no financial row label,
        # and every nonempty value cell must be a four-digit year.
        nonempty = [clean(part) for part in parts[1:] if clean(part)]
        year_header = is_table and label.lower() in ('', 'year', 'years') and bool(nonempty) and all(YEAR_RE.fullmatch(part) for part in nonempty)
        explicit_header = any(DURATION_RE.search(clean(part)) or ISO_RE.search(clean(part)) or MONTH_RE.search(clean(part)) for part in parts)
        column_header = is_table and not label and not numeric_columns and any(scope(part) or unit(part) for part in parts[1:])
        header = year_header or column_header or (explicit_header and not (is_table and label and (row_measure or row_scope) and numeric_columns))

        if not is_table and not header:
            s, u, m = scope(text), unit(text), measure(text)
            if s is not None and len(text) <= 180:
                scope_value, scope_quote = s, quote_at(position, line)
                dates.clear(); years.clear(); durations.clear(); segments.clear(); units.clear()
                map_quotes, section_measure, section_quote, after_data, width = [], None, None, False, 0
                if 'statement' in text.lower() and not u:
                    unit_value, unit_quote = None, None
            if u is not None:
                unit_value, unit_quote = u, quote_at(position, line)
            if m is not None and len(text) <= 120:
                section_measure, section_quote = m, quote_at(position, line)
            continue

        if header:
            if after_data:
                dates.clear(); years.clear(); durations.clear(); segments.clear(); units.clear()
                map_quotes, section_measure, section_quote, width = [], None, None, 0
            after_data = False
            width = max(width, len(parts))
            map_quotes.append(quote_at(position, line))
            map_quotes = map_quotes[-6:]
            for column, raw in enumerate(parts):
                value = clean(raw)
                if not value:
                    continue
                iso = list(ISO_RE.finditer(value))
                month = list(MONTH_RE.finditer(value))
                if iso:
                    dates[column] = tuple(map(int, iso[0].groups())) if len(iso) == 1 else None
                elif month:
                    match = month[0]
                    dates[column] = (int(match.group(3)) if match.group(3) else None, MONTHS[match.group(1).lower()], int(match.group(2))) if len(month) == 1 else None
                if year_header and column > 0 and YEAR_RE.fullmatch(value):
                    years[column] = int(value)
                matches = list(DURATION_RE.finditer(value))
                if matches:
                    values = [DURATIONS[match.group(1).lower()] if match.group(1) else 12 for match in matches]
                    durations[column] = values[0] if len(set(values)) == 1 and not AMBIGUOUS_DURATION.search(value) else None
                s, u = scope(value), unit(value)
                if s is not None:
                    segments[column] = s
                if u is not None:
                    units[column] = u
            continue

        if not numeric_columns:
            if row_measure is not None:
                section_measure, section_quote = row_measure, quote_at(position, line)
            elif row_scope is not None and all(not clean(part) for part in parts[1:]):
                scope_value, scope_quote = row_scope, quote_at(position, line)
            u = unit(text)
            if u is not None:
                unit_value, unit_quote = u, quote_at(position, line)
            continue

        after_data = True
        # Numeric component rows describe themselves. They never mutate the
        # statement's scope or the scope of a following bold total.
        if row_measure is None and row_scope is None:
            continue
        selected_measure = row_measure or section_measure
        columns = list(numeric_columns)
        for column in range(1, len(parts)):
            if not clean(parts[column]) and (column in dates or column in years) and column not in columns:
                columns.append(column)
        for column in sorted(columns):
            raw = parts[column].strip()
            value = number(raw)
            period = date_at(dates, years, column)
            duration = nearest(durations, column)
            selected_scope = row_scope or nearest(segments, column) or scope_value
            selected_unit = nearest(units, column) or unit_value
            absent = []
            if selected_measure is None:
                absent.append('measure')
            if period is None:
                absent.append('period_end')
            if duration is None:
                absent.append('duration_months')
            if selected_unit is None:
                absent.append('unit')
            if selected_scope is None:
                absent.append('segment')
            if value is None:
                absent.append('value')
            if width and column >= width:
                absent.append('column_alignment')
            if absent:
                unknowns.append({'source_path': block['path'], 'offset': position, 'quote': line, 'literal': raw, 'reason': 'missing_or_ambiguous_binding', 'missing': absent})
                continue
            facts.append({'kind': 'fact', 'measure': selected_measure, 'period_end': period, 'duration_months': duration, 'unit': selected_unit, 'value': value, 'segment': selected_scope, 'source_path': block['path'], 'source_sha256': block['source_sha256'], 'offset': position, 'quote': line, 'literal': raw, 'headers': evidence(), 'state_sha256': []})
    return facts, unknowns


def bind_state(cells, bindings):
    for cell in cells:
        for binding in bindings:
            record = binding['record']
            if record.get('kind') != 'fact' or not valid_sha(binding.get('sha256')):
                continue
            keys = ('source_path', 'offset', 'quote', 'literal', 'period_end', 'unit', 'value')
            if any(record.get(key) != cell.get(key) for key in keys):
                continue
            source_sha = valid_sha(record.get('source_sha256'))
            if source_sha is not None and cell['source_sha256'] is not None and source_sha != cell['source_sha256']:
                continue
            if source_sha is not None and cell['source_sha256'] is None:
                cell['source_sha256'] = source_sha
            if binding['sha256'] not in cell['state_sha256']:
                cell['state_sha256'].append(binding['sha256'])


def derive_quarters(cells):
    groups, reported, result = {}, set(), []
    for index, cell in enumerate(cells):
        end = datetime.date.fromisoformat(cell['period_end'])
        duration = cell['duration_months']
        if end.day != calendar.monthrange(end.year, end.month)[1]:
            continue
        signature = (cell['measure'], cell['segment'], cell['unit'])
        if duration == 3:
            reported.add(signature + (cell['period_end'],))
        start_month = end.year * 12 + end.month - duration
        key = signature + (start_month, duration)
        groups.setdefault(key, []).append(index)
    for index, cell in enumerate(cells):
        duration = cell['duration_months']
        if duration not in (6, 9, 12):
            continue
        end = datetime.date.fromisoformat(cell['period_end'])
        if end.day != calendar.monthrange(end.year, end.month)[1]:
            continue
        signature = (cell['measure'], cell['segment'], cell['unit'])
        if signature + (cell['period_end'],) in reported:
            continue
        start_month = end.year * 12 + end.month - duration
        current = groups.get(signature + (start_month, duration), [])
        previous = groups.get(signature + (start_month, duration - 3), [])
        if len(current) != 1 or len(previous) != 1:
            continue
        previous_index = previous[0]
        earlier = cells[previous_index]
        # Do not combine conflicting file identities or mix source issuers.
        if earlier['source_path'] != cell['source_path']:
            continue
        value = Decimal(str(cell['value'])) - Decimal(str(earlier['value']))
        value = int(value) if value == value.to_integral_value() else float(value)
        result.append({'kind': 'calculation', 'measure': cell['measure'], 'period_end': cell['period_end'], 'duration_months': 3, 'unit': cell['unit'], 'segment': cell['segment'], 'value': value, 'inputs': [{'historical_cell': index}, {'historical_cell': previous_index}], 'expression': 'c' + str(index) + ' - c' + str(previous_index)})
    return result


def run(payload):
    if not isinstance(payload, dict):
        payload = {}
    stage = payload.get('stage', 'forecast')
    if stage not in ('forecast', 'controller'):
        stage = 'forecast'
    index = entries(payload)
    # Exactly one evidence phase. Its presence, even with failed observations,
    # prevents a retry or an implicit second acquisition.
    if 'research_observations' not in payload:
        requests = acquire(payload, index)
        if requests:
            return {'research_requests': requests}
    bindings, omitted = state_bindings(payload)
    blocks, unknowns = observation_blocks(payload, {item['path'] for item in index})
    cells, seen = [], set()
    for block in blocks:
        parsed, missing_cells = parse_block(block)
        unknowns.extend(missing_cells)
        for cell in parsed:
            key = (cell['source_path'], cell['source_sha256'], cell['offset'], cell['literal'], cell['measure'], cell['period_end'], cell['duration_months'], cell['unit'], cell['segment'], cell['value'])
            if key not in seen:
                seen.add(key)
                cells.append(cell)
    bind_state(cells, bindings)
    if not blocks and not unknowns:
        unknowns.append({'reason': 'no_usable_observations'})
    result = {'stage': stage, 'historical_cells': cells, 'derived_quarters': derive_quarters(cells), 'forecasts': [], 'unknowns': unknowns[:64], 'record_bindings': bindings, 'omitted_record_binding_count': omitted, 'truncated': len(unknowns) > 64 or omitted > 0, 'guidance': GUIDANCE}
    # Leave headroom for the mandatory outer {ok,value} serialization wrapper.
    while len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 125000:
        result['truncated'] = True
        if result['historical_cells']:
            result['historical_cells'].pop()
            result['derived_quarters'] = derive_quarters(result['historical_cells'])
        elif result['unknowns']:
            result['unknowns'].pop()
        elif result['record_bindings']:
            result['record_bindings'].pop()
            result['omitted_record_binding_count'] += 1
        else:
            break
    return result
