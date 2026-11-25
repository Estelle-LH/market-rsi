PROGRAM = {'axis': 'R'}

import calendar
import csv
import datetime
import html
import io
import json
import re
from decimal import Decimal, InvalidOperation

GUIDANCE = 'Historical only; missing is not zero. Equity ownership tables are excluded. Leasing is not segment total. Derived quarters are calculations, not forecasts. State hashes bind only matching supplied records; null file hashes require verification. Independent original-table and matched-score review remain required.'
MONTHS = {s.lower(): i for i, s in enumerate(calendar.month_name) if s}
MONTHS.update({s.lower(): i for i, s in enumerate(calendar.month_abbr) if s})
MONTHS['sept'] = 9
MONTH_RE = re.compile(r'\b(' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?\s+(\d{1,2})(?:,?\s+((?:19|20)\d{2}))?\b', re.I)
YEAR_RE = re.compile(r'(?:19|20)\d{2}')
ISO_RE = re.compile(r'\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b')
DURATION_RE = re.compile(r'\b(three|six|nine|twelve|3|6|9|12)\s+months?\s+ended\b|\byears?\s+ended\b', re.I)
AMBIGUOUS_DURATION = re.compile(r'\b(?:three|six|nine|twelve|3|6|9|12)\s+(?:and|&)\s+(?:three|six|nine|twelve|3|6|9|12)\s+months?', re.I)
DURATIONS = {'three': 3, 'six': 6, 'nine': 9, 'twelve': 12, '3': 3, '6': 6, '9': 9, '12': 12}
SEGMENTS = {'alico citrus': 'Alico Citrus', 'land management and other operations': 'Land Management and Other Operations'}


def clean(value):
    value = re.sub(r'<sup\b[^>]*>.*?</sup>', '', str(value), flags=re.I | re.S)
    value = html.unescape(re.sub(r'<[^>]*>', ' ', value))
    return re.sub(r'\s+', ' ', value.replace('*', '').replace('\xa0', ' ')).strip()


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def valid_sha(value):
    return value if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) else None


def number(value):
    text = clean(value).replace('$', '').replace(',', '').replace(' ', '').replace('\u2212', '-')
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1]
    if not text or len(text) > 80 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)', text):
        return None
    try:
        value = Decimal(text)
        if negative:
            value = -value
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def missing(value):
    return clean(value).replace('$', '').strip().lower() in ('-', '\u2014', '\u2013', 'n/a')


def unit(value):
    text = clean(value).lower()
    if 'in thousands' in text:
        return 'USD in thousands'
    if 'in millions' in text:
        return 'USD in millions'
    if text in ('usd', 'dollars', 'in dollars'):
        return 'USD'
    return None


def direct_measure(label):
    text = clean(label).lower().rstrip(':')
    # No company-name or section fallback for arbitrary financial rows.
    # In particular, attributable income, EPS and equity movements are not expenses.
    if any(s in text for s in ('attributable', 'stockholder', 'noncontrolling', 'non-controlling', 'per share')):
        return None
    if 'cash' in text and 'paid' in text and 'interest' in text:
        return 'cash_interest_paid'
    if 'cash' in text and 'operating activities' in text:
        return 'operating_cash_flow'
    if 'operating expenses' in text:
        return 'operating_expenses'
    if 'operating revenue' in text or text == 'total revenues':
        return 'operating_revenues'
    return None


def entries(payload):
    text = payload.get('filing_index', '')
    question = payload.get('questions', '')
    if not isinstance(text, str):
        return []
    match = re.search(r'\bfiled:\s*(\d{4})-?(\d{2})-?(\d{2})\b', question if isinstance(question, str) else '', re.I)
    cutoff = '-'.join(match.groups()) if match else None
    # Without a declared target cutoff, do not silently admit an unknown universe.
    if cutoff is None:
        return []
    result = []
    try:
        datetime.date.fromisoformat(cutoff)
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
    except (csv.Error, TypeError, AttributeError, ValueError):
        return []
    return sorted(result, key=lambda item: (item['date'], item['path']), reverse=True)


def acquire(payload, index):
    annuals = [item for item in index if item['form'] == '10-K']
    quarters = [item for item in index if item['form'] == '10-Q']
    requests, seen = [], set()
    def add(path, offset):
        if (path, offset) not in seen and len(requests) < 8:
            requests.append({'tool': 'read_file', 'arguments': {'path': path, 'offset': offset, 'characters': 20000}})
            seen.add((path, offset))
    if annuals:
        add(annuals[0]['path'], 0)
    for item in quarters[:2]:
        for offset in (0, 20000, 40000):
            add(item['path'], offset)
    question = payload.get('questions', '')
    match = re.search(r'\bfiled:\s*\d{4}-?(\d{2})-?\d{2}\b', question if isinstance(question, str) else '', re.I)
    month = int(match.group(1)) if match else None
    older = quarters[2:]
    seasonal = [item for item in older if month is not None and int(item['date'][5:7]) == month]
    if seasonal or older:
        add((seasonal or older)[0]['path'], 20000)
    for item in quarters[:2] + annuals[:1]:
        for offset in (60000, 80000, 100000):
            add(item['path'], offset)
    return requests


def state_bindings(payload):
    result, used, omitted = [], 0, 0
    records = payload.get('records', [])
    for item in records if isinstance(records, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('record'), dict):
            continue
        binding = {'sha256': item.get('sha256'), 'record': item['record']}
        try:
            size = len(json.dumps(binding, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
        except (TypeError, ValueError):
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
    observations = payload.get('research_observations', [])
    for observation in observations if isinstance(observations, list) else []:
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
        # A result receipt or snippet digest is not a full-file digest.
        sha = valid_sha(output.get('source_sha256')) or valid_sha(output.get('file_sha256'))
        blocks.append({'path': path, 'offset': start, 'text': text, 'source_sha256': sha})
    merged = []
    for block in sorted(blocks, key=lambda b: (b['path'], b['offset'])):
        if merged:
            prior = merged[-1]
            overlap = prior['offset'] + len(prior['text']) - block['offset']
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
    # A numeric data value such as Inventory 1911 never enters years.
    year = years.get(column) if years else parts[0]
    try:
        return datetime.date(year, parts[1], parts[2]).isoformat()
    except (TypeError, ValueError):
        return None


def parse_block(block, intern):
    facts, unknowns = [], []
    lines, cursor = [], block['offset']
    for complete in block['text'].splitlines(keepends=True):
        lines.append((cursor, complete.rstrip('\r\n')))
        cursor += len(complete)
    unit_hint, unit_quote, scope_hint, scope_quote = None, None, None, None
    excluded_area = False
    area_quote = None
    i = 0
    while i < len(lines):
        position, line = lines[i]
        text = clean(line)
        table_line = line.strip().startswith('|') and line.strip().endswith('|')
        if not table_line:
            if len(text) <= 180 and ('STATEMENTS OF' in text.upper() or 'STATEMENT OF' in text.upper()):
                excluded_area = 'EQUITY' in text.upper() and ('CHANGES' in text.upper() or 'STOCKHOLDER' in text.upper())
                area_quote = (position, line) if excluded_area else None
                scope_hint = 'consolidated' if 'CONSOLIDATED' in text.upper() else None
                scope_quote = (position, line) if scope_hint else None
                unit_hint, unit_quote = None, None
            if len(text) <= 180 and text.lower().startswith('note '):
                excluded_area, area_quote = False, None
            found_unit = unit(text)
            if found_unit and len(text) <= 180:
                unit_hint, unit_quote = found_unit, (position, line)
            i += 1
            continue
        table = []
        while i < len(lines):
            pos, raw_line = lines[i]
            if not (raw_line.strip().startswith('|') and raw_line.strip().endswith('|')):
                break
            if len(raw_line) <= 2000:
                parts = raw_line.strip()[1:-1].split('|')
                if not all(not clean(p) or re.fullmatch(r':?-+:?', clean(p)) for p in parts):
                    table.append((pos, raw_line, parts))
            i += 1
        ownership = None
        for pos, raw_line, parts in table:
            if clean(parts[0]).lower() in ('', '^^'):
                header_text = clean(' '.join(parts[1:])).lower()
                if 'retained earnings' in header_text or re.search(r'non[\s-]*controlling\s+interest', header_text):
                    ownership = (pos, raw_line)
                    break
        if excluded_area or ownership:
            pos, raw_line = ownership or area_quote
            unknowns.append({'source_path': block['path'], 'offset': pos, 'quote': raw_line, 'reason': 'equity_ownership_table_excluded'})
            unit_hint, unit_quote = None, None
            continue
        # Whole-table evidence establishes disaggregation, rather than carrying
        # an expense/revenue section accidentally from an earlier statement.
        proof = next(((pos, raw_line) for pos, raw_line, p in table if clean(p[0]).lower() == 'total revenues'), None)
        has_segments = any(clean(p[0]).lower() in SEGMENTS and all(not clean(v) for v in p[1:]) for _, _, p in table)
        has_expenses = any('operating expenses' in clean(p[0]).lower() for _, _, p in table)
        disaggregated = bool(proof and has_segments and not has_expenses)
        dates, years, durations, column_scopes, column_units = {}, {}, {}, {}, {}
        headers = [unit_quote] if unit_quote else []
        table_unit = unit_hint
        section, section_quote = None, None
        segment_section, segment_quote = None, None
        width = 0
        after_data = False
        reject_remaining = False
        for pos, raw_line, parts in table:
            label = clean(parts[0])
            low = label.lower().rstrip(':')
            nonempty = [clean(p) for p in parts[1:] if clean(p)]
            numeric = [c for c in range(1, len(parts)) if number(parts[c]) is not None or missing(parts[c])]
            year_header = low in ('', '^^', 'year', 'years') and bool(nonempty) and all(YEAR_RE.fullmatch(p) for p in nonempty)
            header_label = low in ('', '^^') or unit(label) is not None
            explicit_date = header_label and any(MONTH_RE.search(clean(p)) or ISO_RE.search(clean(p)) or DURATION_RE.search(clean(p)) for p in parts)
            scope_header = header_label and not numeric and any(clean(p).lower() in SEGMENTS for p in parts[1:])
            is_header = year_header or explicit_date or scope_header
            found_unit = unit(label)
            if found_unit:
                table_unit = found_unit
                if (pos, raw_line) not in headers:
                    headers.append((pos, raw_line))
            if is_header:
                if after_data:
                    unknowns.append({'source_path': block['path'], 'offset': pos, 'quote': raw_line, 'reason': 'multiple_header_blocks_require_separate_binding'})
                    reject_remaining = True
                if reject_remaining:
                    continue
                width = max(width, len(parts))
                if (pos, raw_line) not in headers:
                    headers.append((pos, raw_line))
                for column, raw in enumerate(parts):
                    value = clean(raw)
                    if not value:
                        continue
                    iso, month = list(ISO_RE.finditer(value)), list(MONTH_RE.finditer(value))
                    if iso:
                        dates[column] = tuple(map(int, iso[0].groups())) if len(iso) == 1 else None
                    elif month:
                        match = month[0]
                        dates[column] = (int(match.group(3)) if match.group(3) else None, MONTHS[match.group(1).lower()], int(match.group(2))) if len(month) == 1 else None
                    if year_header and column and YEAR_RE.fullmatch(value):
                        years[column] = int(value)
                    matches = list(DURATION_RE.finditer(value))
                    if matches:
                        values = [DURATIONS[m.group(1).lower()] if m.group(1) else 12 for m in matches]
                        durations[column] = values[0] if len(set(values)) == 1 and not AMBIGUOUS_DURATION.search(value) else None
                    if value.lower() in SEGMENTS:
                        column_scopes[column] = SEGMENTS[value.lower()]
                    elif scope_header and value.lower() in ('total', 'consolidated'):
                        column_scopes[column] = 'consolidated'
                    u = unit(value)
                    if u:
                        column_units[column] = u
                continue
            if reject_remaining:
                continue
            if not numeric:
                if low in ('operating revenues', 'operating revenue', 'operating expenses'):
                    section = 'operating_expenses' if low == 'operating expenses' else 'operating_revenues'
                    section_quote = (pos, raw_line)
                elif low in SEGMENTS and all(not clean(p) for p in parts[1:]):
                    segment_section, segment_quote = SEGMENTS[low], (pos, raw_line)
                continue
            after_data = True
            measure = direct_measure(label)
            selected_scope, selected_component = None, None
            extra_headers = []
            if measure:
                if section_quote and section == measure:
                    extra_headers.append(section_quote)
            elif low in SEGMENTS and section in ('operating_revenues', 'operating_expenses'):
                measure, selected_scope = section, SEGMENTS[low]
                extra_headers.append(section_quote)
            elif low == 'total' and disaggregated and segment_section:
                measure, selected_scope = 'operating_revenues', segment_section
                extra_headers.append(segment_quote)
            elif low == 'land and other leasing' and segment_section == 'Land Management and Other Operations' and (disaggregated or section in ('operating_revenues', 'operating_expenses')):
                measure = section or 'operating_revenues'
                selected_scope, selected_component = segment_section, 'Land and Other Leasing'
                extra_headers.append(segment_quote)
                if section_quote:
                    extra_headers.append(section_quote)
            else:
                # Exact component labels are the only inheritors. A row such
                # as attributable net income cannot inherit operating expenses.
                if not disaggregated:
                    section, section_quote = None, None
                continue
            if disaggregated:
                extra_headers.append(proof)
            columns = list(numeric)
            for column in range(1, len(parts)):
                if not clean(parts[column]) and (column in years or column in dates) and column not in columns:
                    columns.append(column)
            for column in sorted(columns):
                literal = parts[column].strip()
                value = number(literal)
                period = date_at(dates, years, column)
                duration = nearest(durations, column)
                selected_unit = nearest(column_units, column) or table_unit
                cell_scope = selected_scope or nearest(column_scopes, column) or scope_hint or 'consolidated'
                evidence = list(headers) + extra_headers
                if selected_scope is None and not nearest(column_scopes, column) and scope_hint and scope_quote:
                    evidence.append(scope_quote)
                absent = []
                for name, item in (('period_end', period), ('duration_months', duration), ('unit', selected_unit), ('value', value)):
                    if item is None:
                        absent.append(name)
                if not width or column >= width:
                    absent.append('column_alignment')
                if absent:
                    unknowns.append({'source_path': block['path'], 'offset': pos, 'quote': raw_line, 'literal': literal, 'reason': 'missing_or_ambiguous_binding', 'missing': absent})
                    continue
                refs = []
                for hpos, hline in sorted(set(h for h in evidence if h is not None)):
                    refs.append(intern(block['path'], hpos, hline))
                facts.append({'kind': 'fact', 'measure': measure, 'period_end': period, 'duration_months': duration, 'unit': selected_unit, 'value': value, 'segment': cell_scope, 'component': selected_component, 'source_path': block['path'], 'source_sha256': block['source_sha256'], 'offset': pos, 'quote': raw_line, 'literal': literal, 'column': column, 'header_refs': refs, 'state_sha256': []})
        # A note-table unit must not leak into an unrelated following table.
        unit_hint, unit_quote = None, None
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
            if any(key in record and record[key] != cell[key] for key in ('measure', 'segment', 'component', 'duration_months', 'column')):
                continue
            source_sha = valid_sha(record.get('source_sha256'))
            if source_sha and cell['source_sha256'] and source_sha != cell['source_sha256']:
                continue
            if source_sha and cell['source_sha256'] is None:
                cell['source_sha256'] = source_sha
            if binding['sha256'] not in cell['state_sha256']:
                cell['state_sha256'].append(binding['sha256'])


def derive_quarters(cells):
    groups, reported, result = {}, set(), []
    for index, cell in enumerate(cells):
        end = datetime.date.fromisoformat(cell['period_end'])
        if end.day != calendar.monthrange(end.year, end.month)[1]:
            continue
        signature = (cell['source_path'], cell['source_sha256'], cell['measure'], cell['segment'], cell['component'], cell['unit'])
        duration = cell['duration_months']
        if duration == 3:
            reported.add(signature + (cell['period_end'],))
        start = end.year * 12 + end.month - duration
        groups.setdefault(signature + (start, duration), []).append(index)
    for index, cell in enumerate(cells):
        duration = cell['duration_months']
        if duration not in (6, 9, 12):
            continue
        end = datetime.date.fromisoformat(cell['period_end'])
        if end.day != calendar.monthrange(end.year, end.month)[1]:
            continue
        signature = (cell['source_path'], cell['source_sha256'], cell['measure'], cell['segment'], cell['component'], cell['unit'])
        if signature + (cell['period_end'],) in reported:
            continue
        start = end.year * 12 + end.month - duration
        current = groups.get(signature + (start, duration), [])
        previous = groups.get(signature + (start, duration - 3), [])
        if len(current) != 1 or len(previous) != 1:
            continue
        earlier_index = previous[0]
        value = Decimal(str(cell['value'])) - Decimal(str(cells[earlier_index]['value']))
        value = int(value) if value == value.to_integral_value() else float(value)
        result.append({'kind': 'calculation', 'measure': cell['measure'], 'period_end': cell['period_end'], 'duration_months': 3, 'unit': cell['unit'], 'segment': cell['segment'], 'component': cell['component'], 'value': value, 'inputs': [{'historical_cell': index}, {'historical_cell': earlier_index}], 'expression': 'c' + str(index) + ' - c' + str(earlier_index)})
    return result


def compact_evidence(result):
    used = sorted({ref for cell in result['historical_cells'] for ref in cell['header_refs']})
    mapping = {old: new for new, old in enumerate(used)}
    result['evidence'] = [result['evidence'][old] for old in used]
    for cell in result['historical_cells']:
        cell['header_refs'] = [mapping[ref] for ref in cell['header_refs']]


def run(payload):
    if not isinstance(payload, dict):
        payload = {}
    stage = payload.get('stage', 'forecast')
    if stage not in ('forecast', 'controller'):
        stage = 'forecast'
    index = entries(payload)
    if 'research_observations' not in payload:
        requests = acquire(payload, index)
        if requests:
            return {'research_requests': requests}
    bindings, omitted = state_bindings(payload)
    blocks, unknowns = observation_blocks(payload, {item['path'] for item in index})
    evidence, evidence_map = [], {}
    def intern(path, offset, quote):
        key = (path, offset, quote)
        if key not in evidence_map:
            evidence_map[key] = len(evidence)
            evidence.append({'source_path': path, 'offset': offset, 'quote': quote})
        return evidence_map[key]
    cells, seen = [], set()
    for block in blocks:
        parsed, missing_cells = parse_block(block, intern)
        unknowns.extend(missing_cells)
        for cell in parsed:
            key = tuple(cell[key] for key in ('source_path', 'source_sha256', 'offset', 'column', 'measure', 'period_end', 'duration_months', 'unit', 'segment', 'component', 'value'))
            if key not in seen:
                seen.add(key)
                cells.append(cell)
    bind_state(cells, bindings)
    if not blocks and not unknowns:
        unknowns.append({'reason': 'no_usable_observations'})
    result = {'stage': stage, 'historical_cells': cells, 'evidence': evidence, 'derived_quarters': derive_quarters(cells), 'forecasts': [], 'unknowns': unknowns[:64], 'record_bindings': bindings, 'omitted_record_binding_count': omitted, 'truncated': len(unknowns) > 64 or omitted > 0, 'guidance': GUIDANCE}
    compact_evidence(result)
    # Leave room for {ok:true,value:...}; never increase the existing cap.
    while len(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')) > 125000:
        result['truncated'] = True
        if result['historical_cells']:
            result['historical_cells'].pop()
            result['derived_quarters'] = derive_quarters(result['historical_cells'])
            compact_evidence(result)
        elif result['unknowns']:
            result['unknowns'].pop()
        elif result['record_bindings']:
            result['record_bindings'].pop()
            result['omitted_record_binding_count'] += 1
        else:
            break
    return result
