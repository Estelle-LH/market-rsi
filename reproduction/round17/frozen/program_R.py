PROGRAM = {'axis': 'R'}


import re
import csv
import io
import json
import math
import calendar
import html
from datetime import date, timedelta


_INSTRUCTIONS = 'Retain the seasonal anchor unless dated, target-linked evidence supports a bridge. Separate continuing activity, residual costs and one-offs; historical totals are comparators, not additive components. A wind-down does not imply zero. Unquantified target components remain unknown.'
_MONTH_NAMES = 'January February March April May June July August September October November December'.split()
_MONTH_PATTERN = '(' + '|'.join(_MONTH_NAMES) + ')'
_EVENT = re.compile(r'\b(?:wind[ -]down|wound down|ceas(?:e|ed|ing)|discontinu\w*|exited|exit|shut down|terminat\w*|restructur\w*|divest\w*|acquisition|acquired|disposed|sold|closed|closure)\b', re.I)
_STOP = set('a an and or the of for to from in on at by with was were is are be been as total net other amounts amount months month ended ending three six nine twelve year quarter'.split())
_FINANCIAL = set('total net operating revenue revenues expense expenses cash paid interest income earnings cost costs sales assets liabilities dividend dividends diluted basic adjusted profit loss'.split())
_REVIEW = ['verify_required_sources_and_period_units', 'require_dated_target_linked_departure', 'reconcile_components_without_zero_inference', 'matched_trial_only_freeze_pair_across_25']


def _clean(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', str(text))).replace('*', '').replace('_', '')).strip()


def _words(text):
    aliases = {'revenues': 'revenue', 'expenses': 'expense', 'costs': 'cost', 'activities': 'activity', 'operations': 'operation', 'shares': 'share', 'amounts': 'amount'}
    return [aliases.get(w, w) for w in re.findall(r'[a-z]+', _clean(text).lower()) if w not in _STOP]


def _dates(text):
    found = []
    for m in re.finditer(r'\b(\d{4})-(\d{2})-(\d{2})\b', str(text)):
        try:
            found.append((m.start(), date(*map(int, m.groups())).isoformat()))
        except ValueError:
            pass
    pattern = r'\b' + _MONTH_PATTERN + r'\s+(?:(\d{1,2}),?\s+)?(\d{4})\b'
    for m in re.finditer(pattern, str(text), re.I):
        try:
            month = [x.lower() for x in _MONTH_NAMES].index(m.group(1).lower()) + 1
            year = int(m.group(3))
            day = int(m.group(2)) if m.group(2) else calendar.monthrange(year, month)[1]
            found.append((m.start(), date(year, month, day).isoformat()))
        except ValueError:
            pass
    return [v for _, v in sorted(found)]


def _months(text):
    text = _clean(text).lower()
    names = {'three': 3, 'six': 6, 'nine': 9, 'twelve': 12}
    values = []
    for m in re.finditer(r'\b(three|six|nine|twelve|\d{1,2})\s+months?\s+ended\b', text):
        values.append(names[m.group(1)] if m.group(1) in names else int(m.group(1)))
    if re.search(r'\bquarter\s+ended\b', text):
        values.append(3)
    if re.search(r'\byear\s+ended\b', text):
        values.append(12)
    if re.search(r'\bas of\b', text) and not values:
        values.append(0)
    values = set(values)
    return next(iter(values)) if len(values) == 1 else None


def _unit(text):
    t = _clean(text).lower()
    if '%' in t or 'percent' in t:
        return ('percent', 1)
    if ('per share' in t or '/share' in t) and ('usd' in t or 'dollar' in t or '$' in t):
        return ('USD/share', 1)
    scale = 1000000000 if 'billion' in t else 1000000 if 'million' in t else 1000 if 'thousand' in t else 1
    if 'usd' in t or ('dollar' in t and not any(x in t for x in ['canadian', 'australian', 'hong kong'])):
        return ('USD', scale)
    if 'shares' in t:
        return ('shares', scale)
    return None


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        s = str(value).strip().replace(',', '').replace('$', '').replace('%', '').replace('−', '-')
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1]
        n = float(s)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _value(n):
    n = float(format(n, '.12g'))
    return int(n) if n.is_integer() else n


def _sha(value):
    return value.lower() if isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) else None


def _targets(text):
    result = []
    for m in re.finditer(r'^###\s+([^|\s]+)\s*\|\s*(.+)$', text, re.M):
        parts = m.group(2).split('|')
        label = parts[0].strip()
        um = re.search(r'\bunit=([^|\n]+)', m.group(2))
        short = re.split(r'\s+(?:for\s+)?(?:the\s+)?(?:(?:three|six|nine|twelve|\d+)\s+months?|quarter|year)\s+ended\b|\s+as of\b', label, maxsplit=1, flags=re.I)[0]
        ds = _dates(label)
        result.append({'target_id': m.group(1), 'description': short.strip(), 'period_end': ds[-1] if ds else None, 'months': _months(label), 'unit': um.group(1).strip() if um else None})
    return result


def _subject(description):
    if ' - ' in description:
        return description.split(' - ', 1)[0].strip()
    words = description.split()
    for i, word in enumerate(words):
        if re.sub(r'[^a-z]', '', word.lower()) in _FINANCIAL:
            return ' '.join(words[:i])
    return ''


def _matches(description, text):
    wanted, actual = set(_words(description)), set(_words(text))
    if not wanted:
        return False
    core = wanted & {'revenue', 'expense', 'interest', 'leasing', 'cash', 'income', 'cost', 'share', 'dividend', 'operating'}
    return core <= actual and len(wanted & actual) / len(wanted) >= 0.75


def _index(payload):
    questions = str(payload.get('questions', ''))
    limits = re.findall(r'through\s+(\d{4}-\d{2}-\d{2})', questions, re.I)
    filed = re.search(r'^\s*-\s*filed:\s*(\d{8})', questions, re.M | re.I)
    target_filed = None
    if filed:
        try:
            s = filed.group(1)
            target_filed = date(int(s[:4]), int(s[4:6]), int(s[6:]))
            limits.append((target_filed - timedelta(days=1)).isoformat())
        except ValueError:
            pass
    cutoff = min(limits) if limits else None
    hidden = re.search(r'^\s*-\s*accession:\s*(\S+)', questions, re.M | re.I)
    rows = []
    try:
        for row in csv.DictReader(io.StringIO(str(payload.get('filing_index', ''))), delimiter='\t'):
            path, filed_date = row.get('path', ''), row.get('date_filed', '')
            try:
                date.fromisoformat(filed_date)
            except (ValueError, TypeError):
                continue
            if not path.startswith('filings/') or '..' in path or '\\' in path or '\x00' in path:
                continue
            if cutoff and filed_date > cutoff:
                continue
            if hidden and row.get('accession') == hidden.group(1):
                continue
            rows.append({'path': path, 'date': filed_date, 'form': row.get('form_type', '').upper()})
    except (csv.Error, TypeError):
        pass
    rows.sort(key=lambda r: (r['date'], r['path']), reverse=True)
    unique = {}
    for r in rows:
        unique.setdefault(r['path'], r)
    rows = list(unique.values())
    if cutoff is None:
        cutoff = max([r['date'] for r in rows], default='0001-01-01')
    required = [r for r in rows if r['form'] == '10-K'][:1] + [r for r in rows if r['form'] == '10-Q'][:2]
    return rows, required, cutoff, target_filed


def _unwrap(output):
    for _ in range(6):
        if not isinstance(output, dict):
            return None
        if output.get('ok') is False or 'error' in output:
            return None
        if 'text' in output or 'hits' in output:
            return output
        if 'value' in output:
            output = output['value']
        elif 'result' in output:
            output = output['result']
        else:
            return None
    return None


def _spans(payload, allowed):
    spans, hashes, failures = [], {}, 0
    for binding in payload.get('records', []):
        if not isinstance(binding, dict):
            continue
        record = binding.get('record')
        if not isinstance(record, dict) or record.get('kind') != 'fact':
            continue
        path, quote = record.get('source_path'), record.get('quote')
        if path not in allowed or not isinstance(quote, str) or not quote:
            continue
        sh = _sha(record.get('source_sha256'))
        if sh:
            hashes[path] = sh
        offset = record.get('offset')
        spans.append({'path': path, 'text': quote[:16000], 'offset': offset if isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0 else None, 'sha': sh, 'origin': 'fact', 'meta': record})
    for observation in payload.get('research_observations', []):
        if not isinstance(observation, dict):
            failures += 1
            continue
        out = _unwrap(observation.get('output'))
        request = observation.get('request', {})
        if out is None:
            failures += 1
            continue
        args = request.get('arguments', {}) if isinstance(request, dict) else {}
        if 'text' in out:
            path = out.get('path', args.get('path'))
            text = out.get('text')
            offset = out.get('offset', args.get('offset'))
            if path in allowed and isinstance(text, str) and text:
                spans.append({'path': path, 'text': text[:20000], 'offset': offset if isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0 else None, 'sha': _sha(out.get('source_sha256')) or hashes.get(path), 'origin': 'read'})
        elif isinstance(out.get('hits'), list):
            for hit in out['hits'][:50]:
                if not isinstance(hit, dict) or hit.get('path') not in allowed or not isinstance(hit.get('text'), str):
                    continue
                offset = hit.get('offset')
                spans.append({'path': hit['path'], 'text': hit['text'][:4000], 'offset': offset if isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0 else None, 'sha': _sha(hit.get('source_sha256')) or hashes.get(hit['path']), 'line': hit.get('line'), 'origin': 'search'})
    # Adjacent exact read chunks are one continuous source region, not a new
    # observation or invented hash. This retains split table headers at20k.
    reads=sorted((s for s in spans if s['origin']=='read'),key=lambda s:(s['path'],s['offset'] if s['offset'] is not None else -1))
    merged=[]
    for span in reads:
        if (merged and merged[-1]['path']==span['path'] and merged[-1]['offset'] is not None
                and span['offset']==merged[-1]['offset']+len(merged[-1]['text'])
                and merged[-1]['sha']==span['sha']):
            merged[-1]=dict(merged[-1],text=merged[-1]['text']+span['text'])
        else:merged.append(dict(span))
    return [s for s in spans if s['origin']!='read']+merged, failures


def _cite(span, start=0, end=None):
    text = span['text'][start:end]
    result = {'source_path': span['path'], 'source_sha256': span.get('sha'), 'offset': span['offset'] + start if span.get('offset') is not None else None, 'quote': text[:420]}
    if span.get('line') is not None:
        result['line'] = span['line']
    return result


def _plan(targets, rows, required, spans, target_filed):
    # Same acquisition/bridge strategy and eight reads; resolve the intended
    # nearest prior seasonal filing rather than preferring a much older day.
    selected = [row for row in required if row['path'] not in {s['path'] for s in spans}]
    if target_filed:
        candidates = [r for r in rows if r['form'] == '10-Q' and r not in required]
        def distance(row):
            d = date.fromisoformat(row['date'])
            prior=date(target_filed.year-1,target_filed.month,min(target_filed.day,calendar.monthrange(target_filed.year-1,target_filed.month)[1]))
            return (abs((d-prior).days),-d.year)
        candidates.sort(key=distance)
        if candidates and distance(candidates[0])[0] <= 45:
            season = candidates[0]
            if season['path'] not in {s['path'] for s in spans}:
                selected.append(season)
    requests = []
    for row in selected[:4]:
        # Contiguous chunks can reach beyond front matter; missing/unsupported
        # tables still abstain under the original parser, never invent values.
        for offset in (0, 20000):
            requests.append({'tool': 'read_file', 'arguments': {
                'path': row['path'], 'offset': offset, 'characters': 20000}})
    return requests


def _bucket(text):
    t = _clean(text).lower()
    if re.search(r'one[ -]time|nonrecurring|non-recurring|severance|impairment|gain on sale|restructuring charge|accelerated depreciation', t):
        return 'one_offs'
    if re.search(r'residual|caretaking|maintenance|holding cost|property tax|run[ -]off|wind[ -]down cost|remaining cost', t):
        return 'residual_costs'
    if re.search(r'continuing activity|ongoing|retained|recurring|continuing services', t):
        return 'continuing_activity'
    return 'total'


def _table_columns(headers, column):
    fragments=[]
    for _,_,cells in headers:
        if column>=len(cells):continue
        fragment=cells[column]
        # Markdown || denotes a grouped date/duration heading. Do not forward
        # fill numeric year rows across empty currency columns.
        if not fragment:
            for previous in reversed(cells[1:column]):
                if previous:
                    if re.search(r'months?\s+ended|year\s+ended|quarter\s+ended|'+_MONTH_PATTERN,previous,re.I):fragment=previous
                    break
        if fragment:fragments.append(fragment)
    joined=' '.join(fragments);periods=set(_dates(joined));duration=_months(joined)
    if not periods:
        years=set(re.findall(r'\b(?:19|20)\d{2}\b',joined))
        monthday=re.findall(_MONTH_PATTERN+r'\s+(\d{1,2})\s*,?',joined,re.I)
        if len(years)==1 and len(set(monthday))==1:
            month,day=monthday[0];periods=set(_dates(month+' '+day+', '+next(iter(years))))
    return (next(iter(periods)) if len(periods)==1 else None),duration


def _table_unit(context, label):
    text=_clean(context);lower=text.lower();row=label.lower()
    # Do not turn an 'except per share' table heading into per-share units for
    # every monetary row; unqualified$ follows the original dollar convention.
    if re.search(r'canadian|australian|hong kong|\b(?:CAD|AUD|HKD|EUR|GBP)\b|[CA]\$',text,re.I):return None
    currency=bool(re.search(r'\bUSD\b|\bU\.?S\.? dollars?\b|\bdollars?\b|\$',text,re.I))
    if not currency:return None
    scales=re.findall(r'\b(?:in|amounts in|dollars in)\s+(thousands|millions|billions)\b',lower)
    scale={'thousands':1000,'millions':1000000,'billions':1000000000}.get(scales[-1],1) if scales else 1
    if re.search(r'per (?:common )?share|/share',row):return ('USD/share',1)
    if 'share' in row and re.search(r'weighted.average|outstanding',row):return ('shares',scale)
    return ('USD',scale)


def _table_notes(span, filed_date):
    notes,headers,section=[],[],'';text=span['text']
    for match in re.finditer(r'^.*$',text,re.M):
        line=match.group(0)
        if not line.strip().startswith('|'):
            if line.strip():headers=[];section=''
            continue
        # A nonclosed row may be a read-boundary cut through a number. Abstain
        # rather than silently dropping its last digit or inventing a value.
        if not line.strip().endswith('|'):continue
        cells=[_clean(c) for c in line.strip()[1:-1].split('|')]
        if not cells or all(not c or re.fullmatch(r'[-: ]+',c) for c in cells):continue
        # Identify date/header rows from numeric columns, not a data-row label
        # containing a year or footnote reference.
        values=cells[1:]
        header_label=(not cells[0] or bool(re.fullmatch(r'(?:years?|periods?|in thousands|in millions)',cells[0],re.I)))
        if header_label and any(re.search(r'\b(?:19|20)\d{2}\b|months?\s+ended|year\s+ended|quarter\s+ended|'+_MONTH_PATTERN,c,re.I) for c in values):
            headers.append((match.start(),line,cells));headers=headers[-8:];continue
        if not cells[0] or _number(cells[0]) is not None:continue
        if not any(_number(c) is not None for c in values):
            section=(cells[0] if re.search(r'operating (?:revenues?|expenses?)|per (?:common )?share|weighted.average.*shares?|shares?.*outstanding',cells[0],re.I) else '')
            continue
        if not headers:continue
        context=text[max(0,headers[0][0]-1000):match.end()]
        label=' '.join(x for x in (section,cells[0]) if x)
        unit=_table_unit(context,label)
        if unit is None:continue
        for col,cell in enumerate(values,1):
            value=_number(cell)
            if value is None:continue
            period,duration=_table_columns(headers,col)
            if duration is None:duration=_months(text[max(0,headers[0][0]-400):headers[0][0]])
            if period is None or duration is None or period>filed_date:continue
            source=_cite(span,match.start(),match.end())
            source['headers']=[_cite(span,p,p+len(h)) for p,h,_ in headers]
            notes.append({'text':label,'period_end':period,'months':duration,'native_unit':unit,'value':value,'source':source,'bucket':_bucket(label)})
    return notes


def _notes(spans, allowed):
    notes = []
    for span in spans:
        if span['origin'] == 'fact':
            record = span['meta']
            period, value = record.get('period_end'), _number(record.get('value'))
            duration, unit = _months(span['text']), _unit(record.get('unit', ''))
            try:
                date.fromisoformat(period)
            except (TypeError, ValueError):
                continue
            if value is None or duration is None or unit is None:
                continue
            if period > allowed[span['path']]['date'] and not re.search(r'expect|guidance|forecast|project', span['text'], re.I):
                continue
            notes.append({'text': span['text'], 'period_end': period, 'months': duration, 'native_unit': unit, 'value': value, 'source': _cite(span), 'bucket': _bucket(span['text'])})
        elif span['origin'] == 'read':
            notes.extend(_table_notes(span, allowed[span['path']]['date']))
    return notes


def _start(period, months):
    d = date.fromisoformat(period)
    if d.day != calendar.monthrange(d.year, d.month)[1] or months <= 0:
        return None
    index = d.year * 12 + d.month - months
    year, month0 = divmod(index, 12)
    return date(year, month0 + 1, 1).isoformat()


def _aligned(target, notes):
    wanted_unit = _unit(target.get('unit') or '')
    if wanted_unit is None:
        return []
    aligned, seen = [], set()
    for note in notes:
        if note['native_unit'][0] != wanted_unit[0] or not _matches(target['description'], note['text']):
            continue
        converted = dict(note)
        converted['value'] = _value(note['value'] * note['native_unit'][1] / wanted_unit[1])
        converted['unit'] = target['unit']
        key = (converted['period_end'], converted['months'], converted['value'], converted['bucket'])
        if key not in seen:
            seen.add(key)
            aligned.append(converted)
    # Derive a standalone quarter only from matching cumulative fiscal starts.
    derived = []
    for later in aligned:
        if later['months'] not in (6, 9, 12):
            continue
        for earlier in aligned:
            if earlier['months'] != later['months'] - 3 or earlier['bucket'] != later['bucket']:
                continue
            if not earlier['period_end'] < later['period_end']:
                continue
            start = _start(later['period_end'], later['months'])
            if start is None or start != _start(earlier['period_end'], earlier['months']):
                continue
            d = dict(later)
            d['months'] = 3
            d['value'] = _value(later['value'] - earlier['value'])
            d['source'] = {'kind': 'calculation', 'expression': 'later_ytd - earlier_ytd', 'inputs': [later['source'], earlier['source']]}
            derived.append(d)
    return sorted(aligned + derived, key=lambda n: n['period_end'], reverse=True)


def _pack(note):
    if note is None:
        return None
    return {'period_end': note['period_end'], 'months': note['months'], 'unit': note['unit'], 'value': note['value'], 'source': note['source']}


def _linked(target, text):
    subject = _subject(target['description'])
    words = set(_words(text))
    if subject:
        return set(_words(subject)) <= words
    wanted = set(_words(target['description']))
    if wanted & words & {'interest', 'revenue', 'expense', 'income', 'cash', 'cost', 'share', 'dividend'}:
        return True
    if 'interest' in wanted and words & {'debt', 'loan', 'refinancing'}:
        return True
    return 'cash' in wanted and 'operating' in wanted and bool(words & {'cost', 'expense', 'receipts', 'cash'})


def _event_for(target, spans, anchor):
    candidates, dedup = [], set()
    for span in spans:
        for match in re.finditer(r'[^\n.!?]+[.!?]?', span['text']):
            sentence = match.group(0)
            if not _EVENT.search(sentence) or not _linked(target, sentence):
                continue
            leading = len(sentence) - len(sentence.lstrip())
            sentence = sentence.strip()
            if not sentence or sentence in dedup:
                continue
            dedup.add(sentence)
            if re.search(r'\b(?:has not|have not|did not|no plans to|not ceased|not closed)\b', sentence, re.I):
                continue
            dates = _dates(sentence)
            when = max(dates) if dates else None
            if when and target['period_end']:
                end=date.fromisoformat(target['period_end'])
                start=date(end.year-1,end.month,min(end.day,calendar.monthrange(end.year-1,end.month)[1])).isoformat()
                # Old events are already in a valid seasonal anchor. Without
                # an anchor they cannot masquerade as a current-period break.
                if when<=start and (anchor is None or when>anchor['period_end']):continue
            if re.search(r'\b(?:may|could|would|if)\b', sentence, re.I):
                status = 'conditional'
            elif re.search(r'\b(?:ceased|terminated|completed|closed|wound down|discontinued|sold|exited|shut down|acquired)\b', sentence, re.I):
                status = 'realized'
            else:
                status = 'planned'
            if when is None:
                state = 'undated_signal'
            elif target['period_end'] and when > target['period_end']:
                state = 'future_change'
            elif status == 'conditional':
                state = 'conditional_signal'
            elif anchor and when <= anchor['period_end']:
                state = 'anchor_contains_change'
            elif status == 'realized':
                state = 'dated_change'
            else:
                state = 'planned_change'
            rank = {'dated_change': 0, 'planned_change': 1, 'anchor_contains_change': 2, 'undated_signal': 3, 'conditional_signal': 4, 'future_change': 5}[state]
            start = match.start() + leading
            candidates.append((rank, when or '', state, {'date': when, 'status': status, 'source': _cite(span, start, start + len(sentence))}))
    candidates.sort(key=lambda x: (x[0], -int(x[1].replace('-', '') or '0')))
    return (candidates[0][2], candidates[0][3]) if candidates else ('anchor', None)


def _unverified(value):
    if isinstance(value, dict):
        if 'source_path' in value and (value.get('source_sha256') is None or value.get('offset') is None):
            return True
        return any(_unverified(v) for v in value.values())
    if isinstance(value, list):
        return any(_unverified(v) for v in value)
    return False


def _compact(value):
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if key == 'quote' and isinstance(child, str):
                value[key] = child[:160]
            elif key == 'headers' and isinstance(child, list):
                value[key] = child[:1]
                _compact(value[key])
            else:
                _compact(child)
    elif isinstance(value, list):
        for child in value:
            _compact(child)


def _anchor_date_parent_run(payload):
    if not isinstance(payload, dict):
        return {'error': 'payload_must_be_an_object'}
    stage = payload.get('stage', 'forecast')
    if stage not in ('forecast', 'controller'):
        return {'error': 'unsupported_stage'}
    all_targets = _targets(str(payload.get('questions', '')))
    targets = all_targets[:32]
    rows, required, cutoff, target_filed = _index(payload)
    allowed = {r['path']: r for r in rows}
    spans, failures = _spans(payload, allowed)
    phase_used = 'research_observations' in payload
    if not phase_used:
        requests = _plan(targets, rows, required, spans, target_filed)
        if requests:
            return {'research_requests': requests}
    notes = _notes(spans, allowed)
    seen = {s['path'] for s in spans}
    warnings, bridges = [], []
    if not rows:
        warnings.append('index_empty')
    if not targets:
        warnings.append('no_targets')
    if len(all_targets) > len(targets):
        warnings.append('target_limit_reached')
    if any(r['path'] not in seen for r in required):
        warnings.append('incomplete_required_evidence')
    if failures:
        warnings.append('research_observations_failed')
    for target in targets:
        aligned = _aligned(target, notes)
        end, duration = target['period_end'], target['months']
        totals = [n for n in aligned if n['bucket'] == 'total' and n['months'] == duration and end and n['period_end'] < end]
        seasonal = [n for n in totals if n['period_end'][5:] == end[5:]] if end else []
        anchor = seasonal[0] if seasonal else None
        recent = next((n for n in totals if anchor is None or n['period_end'] > anchor['period_end']), None)
        gate, event = _event_for(target, spans, anchor)
        components = {'continuing_activity': [], 'residual_costs': [], 'one_offs': []}
        for bucket in components:
            candidates = [n for n in aligned if n['bucket'] == bucket and n['months'] == duration and end and n['period_end'] <= end]
            if event and event['date']:
                candidates = [n for n in candidates if n['period_end'] >= event['date']]
            components[bucket] = [_pack(n) for n in candidates[:2]]
        if anchor is None:
            warnings.append('anchor_missing:' + target['target_id'])
        elif end and int(end[:4]) - int(anchor['period_end'][:4]) > 1:
            warnings.append('stale_anchor:' + target['target_id'])
        if gate not in ('anchor', 'anchor_contains_change'):
            warnings.append('change_bridge_unquantified:' + target['target_id'])
        if end is None or duration is None or _unit(target.get('unit') or '') is None:
            warnings.append('target_period_or_unit_unresolved:' + target['target_id'])
        bridges.append({'target_id': target['target_id'], 'period_end': end, 'months': duration, 'unit': target['unit'], 'anchor': _pack(anchor), 'recent': _pack(recent), 'gate': gate, 'event': event, 'observed_components': components, 'target_components': {'continuing_activity': None, 'residual_costs': None, 'one_offs': None}, 'bridge_value': None})
    leads, lead_keys = [], set()
    for span in spans:
        if span['origin'] != 'search' or not any(_matches(t['description'], span['text']) for t in targets):
            continue
        key = (span['path'], span['text'])
        if key not in lead_keys and len(leads) < 4:
            lead_keys.add(key)
            leads.append(_cite(span))
    result = {'policy': 'dated_structural_bridge_v1', 'stage': stage, 'coverage': {'required': [r['path'] for r in required], 'seen': [r['path'] for r in required if r['path'] in seen], 'research_phase_used': phase_used, 'failed_observations': failures}, 'instructions': _INSTRUCTIONS, 'bridges': bridges, 'leads': leads, 'warnings': warnings, 'controller_checks': list(_REVIEW) if stage == 'controller' else []}
    if _unverified(result):
        warnings.append('source_location_or_hash_unverified')
    if len(json.dumps({'ok': True, 'value': result}, ensure_ascii=False).encode('utf-8')) > 120000:
        _compact(result)
        warnings.append('evidence_quotes_compacted')
    if len(json.dumps({'ok': True, 'value': result}, ensure_ascii=False).encode('utf-8')) > 120000:
        result['leads'] = []
        for bridge in bridges:
            bridge['recent'] = None
            bridge['observed_components'] = {'continuing_activity': [], 'residual_costs': [], 'one_offs': []}
        warnings.append('secondary_evidence_omitted_for_output_budget')
    return result


# Anchor-mismatch experiment. The retained policy remains responsible for
# anchors, components and event gates. This extension cannot write state,
# acquire a second evidence phase, or consume feedback as numerical labels.
_anchor_history_legacy_plan = _plan
_H_VERSION = 'anchor_history_rolling_origin_v1'
_H_PARAMETERS = {'minimum_history': 8, 'minimum_validation_origins': 4, 'required_relative_advantage': 0.2, 'recent_level': 'mean_of_last_two_quarters', 'validation_origin': 'historical_period_end_with_training_filings_available_by_that_date'}
_H_INSTRUCTION = ' Only a cited recent-level recommendation with past-only validation advantage may replace an anchor; all event gates and unquantified components retain parent treatment. Missing history is not zero.'


def _plan(targets, rows, required, spans, target_filed):
    if not targets:
        return _anchor_history_legacy_plan(targets, rows, required, spans, target_filed)
    selected = []
    def choose(row):
        if row and row['path'] not in {r['path'] for r in selected}:
            selected.append(row)
    for row in required:
        choose(row)
    # Acquisition only: retain the required K/two Qs, then seek distinct
    # older target-season history before spending the remaining slots on
    # recency. This is the live target-bearing plan, not the legacy alias.
    # Neither locator estimates nor this ranking enter numerical research.
    eligible = []
    for number, target in enumerate(targets):
        try:
            end = date.fromisoformat(target.get('period_end'))
        except (ValueError, TypeError):
            continue
        if target.get('months') in (0, 3, 6, 9, 12):
            eligible.append((number, target, end))
    by_path = {r['path']: r for r in rows}
    observed = {path: set() for path in by_path}
    for span in spans:
        path = span.get('path')
        if path not in by_path or span.get('offset') is None or not _sha(span.get('sha')):
            continue
        # Reuse original row/header interpretation. Do not treat a fact's
        # period metadata, a filing date, or an isolated year as a header.
        for note in _table_notes(span, by_path[path]['date']):
            period = date.fromisoformat(note['period_end'])
            for number, target, end in eligible:
                unit = _unit(target.get('unit') or '')
                same_day = period.day == end.day
                month_ends = (period.day == calendar.monthrange(period.year, period.month)[1]
                              and end.day == calendar.monthrange(end.year, end.month)[1])
                if (period < end and period.month == end.month and (same_day or month_ends)
                        and note['months'] == target['months']
                        and unit is not None and note['native_unit'][0] == unit[0]
                        and _h_signature(note['text']) == _h_signature(target['description'])):
                    observed[path].add((number, period.isoformat()))
    covered = set()
    for row in selected:
        covered.update(observed[row['path']])

    def locate(row):
        # Filing anniversaries locate unverified candidates only. Preserve
        # the parent's 45-day search tolerance, extending it to older years.
        # Missing or incompatible snippets do not prove data unavailable.
        candidates = {}
        if target_filed is None:
            return candidates
        filed = date.fromisoformat(row['date'])
        difference = target_filed.year - filed.year
        for number, target, end in eligible:
            forms = ('10-K',) if target['months'] == 12 else ('10-K', '10-Q') if target['months'] == 0 else ('10-Q',)
            if row['form'] not in forms:
                continue
            for lag in range(max(1, difference - 1), difference + 2):
                filing_year, period_year = target_filed.year - lag, end.year - lag
                if filing_year < 1 or period_year < 1:
                    continue
                prior = date(filing_year, target_filed.month, min(target_filed.day, calendar.monthrange(filing_year, target_filed.month)[1]))
                distance = abs((filed - prior).days)
                if distance <= 45:
                    period = date(period_year, end.month, min(end.day, calendar.monthrange(period_year, end.month)[1]))
                    key = (number, period.isoformat())
                    candidates[key] = min(candidates.get(key, (10000, 10000)), (lag, distance))
        return candidates

    locators = {r['path']: locate(r) for r in rows}
    located = set(covered)
    for row in selected:
        located.update(locators[row['path']])
    annual_or_stock = any(t['months'] in (0, 12) for _, t, _ in eligible)
    remaining = [r for r in rows if r['path'] not in {s['path'] for s in selected}
                 and (r['form'] == '10-Q' or
                      (r['form'] == '10-K' and (annual_or_stock or observed[r['path']])))]
    while remaining and len(selected) < 8:
        def priority(row):
            path = row['path']
            new = observed[path] - covered
            recent = -date.fromisoformat(row['date']).toordinal()
            if new:
                return (0, -len(new), -max(date.fromisoformat(p).toordinal() for _, p in new), recent, path)
            unlocated = [quality for key, quality in locators[path].items() if key not in located]
            if unlocated:
                lag, distance = min(unlocated)
                return (1, lag, distance, recent, path)
            return (2, 0, 0, recent, path)
        row = min(remaining, key=priority)
        remaining.remove(row)
        choose(row)
        covered.update(observed[row['path']])
        # This set prevents duplicate candidate-year allocations; it is not
        # a measurement ledger and never certifies a comparable period.
        located.update(observed[row['path']])
        located.update(locators[row['path']])
    selected = selected[:8]
    requests, used, primary = [], set(), {}
    def request(path, offset):
        key = (path, offset)
        if key in used or len(requests) >= 8:
            return
        used.add(key)
        if any(s['path'] == path and s['origin'] == 'read' and s.get('offset') == offset and len(s['text']) >= 16000 for s in spans):
            return
        requests.append({'tool': 'read_file', 'arguments': {'path': path, 'offset': offset, 'characters': 20000}})
    for row in selected:
        locations = [s['offset'] for s in spans if s['path'] == row['path'] and s.get('offset') is not None and (any(_matches(t['description'], s['text']) for t in targets) or _EVENT.search(s['text']))]
        # Known original row locations let a single read include the preceding
        # table headers. Without locations, use the original first-page bound;
        # do not invent a search hit or assume that front matter has a fixed size.
        offset = max(0, min(locations) - 6000) if locations else 0
        primary[row['path']] = offset
        request(row['path'], offset)
    for row in selected:
        offset = primary[row['path']]
        request(row['path'], 20000 if offset == 0 else max(0, offset - 16000))
    return requests


def _h_shift(period, months):
    d = date.fromisoformat(period)
    index = d.year * 12 + d.month - 1 + months
    year, month0 = divmod(index, 12)
    if year < 1 or year > 9999:
        return None
    month = month0 + 1
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def _h_month_end(period):
    try:
        d = date.fromisoformat(period)
        return d.day == calendar.monthrange(d.year, d.month)[1]
    except (ValueError, TypeError):
        return False


def _h_signature(text):
    # Exact measure/scope words after the parent's aliases and stop words.
    # A broader parent comparator must not silently become a model series.
    label = re.split(r'\s+(?:for\s+)?(?:the\s+)?(?:(?:three|six|nine|twelve|\d+)\s+months?|quarter|year)\s+ended\b|\s+as of\b', _clean(text), maxsplit=1, flags=re.I)[0]
    return tuple(sorted(set(_words(label))))


def _h_unit_header(span, source):
    if span.get('offset') is None or not source.get('headers'):
        return source
    first = source['headers'][0].get('offset')
    if first is None:
        return source
    end = first - span['offset']
    start = max(0, end - 2000)
    candidates = list(re.finditer(r'^.*\b(?:in|dollars in)\s+(?:thousands|millions|billions)\b.*$', span['text'][start:end], re.M | re.I))
    if candidates:
        match = candidates[-1]
        result = dict(source)
        result['unit_header'] = _cite(span, start + match.start(), start + match.end())
        return result
    return source


def _h_collect(target, spans, allowed):
    wanted_unit = _unit(target.get('unit') or '')
    end, duration = target.get('period_end'), target.get('months')
    if wanted_unit is None or duration not in (0, 3) or not _h_month_end(end):
        return [], 0
    wanted = _h_signature(target['description'])
    raw = []
    for span in spans:
        if span['origin'] == 'fact' and '\n|' not in span['text']:
            record = span['meta']
            literal = str(record.get('literal', ''))
            # Facts are numeric notes, not an extra normalized measurement
            # ledger. Reconstruct duration, scope and units from the quotation.
            if (not literal or literal not in span['text'] or len(span['text']) > 420
                    or _number(literal) is None or _number(literal) != _number(record.get('value'))
                    or record.get('period_end') not in _dates(span['text'])
                    or _unit(span['text']) != _unit(record.get('unit', ''))):
                continue
            candidates = _notes([span], allowed)
        else:
            candidates = _table_notes(span, allowed[span['path']]['date'])
            candidates = [dict(n, source=_h_unit_header(span, n['source'])) for n in candidates
                          if n['source'].get('quote', '').rstrip().endswith('|')
                          and all(h.get('quote', '').rstrip().endswith('|') for h in n['source'].get('headers', []))]
        for note in candidates:
            if (note['bucket'] != 'total' or note['native_unit'][0] != wanted_unit[0]
                    or _h_signature(note['text']) != wanted
                    or not note['period_end'] < end
                    or note['period_end'] > allowed[span['path']]['date']
                    or re.search(r'\b(?:expect|guidance|forecast|projected|estimated|may|could)\b', note['text'], re.I)):
                continue
            raw.append({'period_end': note['period_end'], 'months': note['months'],
                        'value': _value(note['value'] * note['native_unit'][1] / wanted_unit[1]),
                        'source': note['source'], 'available_on': allowed[span['path']]['date'],
                        'signature': wanted})
    # Standalone monetary quarters only: EPS, percentages, weighted-average
    # shares and stock balances are never differenced as additive cash totals.
    derived = []
    if duration == 3 and wanted_unit[0] == 'USD':
        starts = {}
        for note in raw:
            if note['months'] not in (3, 6, 9, 12):
                continue
            start = _start(note['period_end'], note['months'])
            if start is not None:
                starts.setdefault((note['signature'], note['months'], start), []).append(note)
        for later in raw:
            if later['months'] not in (6, 9, 12):
                continue
            start = _start(later['period_end'], later['months'])
            for earlier in starts.get((later['signature'], later['months'] - 3, start), []):
                if _h_shift(earlier['period_end'], 3) != later['period_end']:
                    continue
                derived.append({'period_end': later['period_end'], 'months': 3,
                                'value': _value(later['value'] - earlier['value']),
                                'available_on': max(later['available_on'], earlier['available_on']),
                                'signature': later['signature'],
                                'source': {'kind': 'calculation', 'expression': 'later_ytd - earlier_ytd',
                                           'inputs': [later['source'], earlier['source']]}})
    grouped = {}
    target_date = date.fromisoformat(end)
    for note in raw + derived:
        if note['months'] != duration or not _h_month_end(note['period_end']):
            continue
        d = date.fromisoformat(note['period_end'])
        distance = (target_date.year - d.year) * 12 + target_date.month - d.month
        if distance <= 0 or distance % 3:
            continue
        grouped.setdefault(note['period_end'], []).append(note)
    history, conflicts = [], 0
    for period, alternatives in sorted(grouped.items()):
        values = {n['value'] for n in alternatives}
        if len(values) != 1:
            # Neither a newer restatement nor a derived/direct disagreement
            # is resolved using the future validation outcome.
            conflicts += 1
            continue
        alternatives.sort(key=lambda n: (n['available_on'], n['source'].get('kind') == 'calculation', _unverified(n['source'])))
        history.append(alternatives[0])
    return history[-12:], conflicts


def _h_intern(source, bank, cache):
    if source.get('kind') == 'calculation':
        entry = {'kind': 'calculation', 'expression': source['expression'],
                 'inputs': [_h_intern(s, bank, cache) for s in source['inputs']]}
    else:
        entry = {k: source.get(k) for k in ('source_path', 'source_sha256', 'offset', 'quote')}
        if source.get('headers'):
            entry['headers'] = [_h_intern(s, bank, cache) for s in source['headers']]
        if source.get('unit_header'):
            entry['unit_header'] = _h_intern(source['unit_header'], bank, cache)
    key = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    if key not in cache:
        reference = 'H' + str(len(bank) + 1)
        cache[key] = reference
        bank[reference] = entry
    return cache[key]


def _h_research(targets, bridges, spans, allowed, cutoff):
    bank, cache, outputs = {}, {}, []
    coverage = {'targets': len(targets), 'histories_sufficient': 0, 'validated': 0, 'departures': 0}
    by_id = {b['target_id']: b for b in bridges}
    for target in targets:
        bridge = by_id[target['target_id']]
        history, conflicts = _h_collect(target, spans, allowed)
        observations = {n['period_end']: n for n in history}
        folds = []
        for note in history:
            origin = note['period_end']
            lag1 = observations.get(_h_shift(origin, -3))
            lag2 = observations.get(_h_shift(origin, -6))
            lag4 = observations.get(_h_shift(origin, -12))
            if not all((lag1, lag2, lag4)):
                continue
            if any(n['available_on'] > origin for n in (lag1, lag2, lag4)):
                continue
            folds.append({'period_end': origin,
                          'seasonal_absolute_error': _value(abs(note['value'] - lag4['value'])),
                          'recent_absolute_error': _value(abs(note['value'] - (lag1['value'] + lag2['value']) / 2))})
        seasonal_mae = _value(sum(f['seasonal_absolute_error'] for f in folds) / len(folds)) if folds else None
        recent_mae = _value(sum(f['recent_absolute_error'] for f in folds) / len(folds)) if folds else None
        enough = len(history) >= 8
        validated = enough and len(folds) >= 4
        coverage['histories_sufficient'] += int(enough)
        coverage['validated'] += int(validated)
        proposed, selection, reason, recommendation = 'retain_parent', 'retain_parent', 'insufficient_comparable_history', None
        if target['months'] not in (0, 3) or not _h_month_end(target['period_end']):
            reason = 'unsupported_target_period'
        elif enough and not validated:
            reason = 'insufficient_past_only_validation'
        elif validated:
            recent_wins = sum(f['recent_absolute_error'] < f['seasonal_absolute_error'] for f in folds)
            seasonal_wins = sum(f['seasonal_absolute_error'] < f['recent_absolute_error'] for f in folds)
            required_wins = math.ceil(0.6 * len(folds))
            if seasonal_mae > 0 and recent_mae <= 0.8 * seasonal_mae and recent_wins >= required_wins:
                proposed = 'recent_level'
            elif recent_mae > 0 and seasonal_mae <= 0.8 * recent_mae and seasonal_wins >= required_wins:
                proposed = 'seasonal_naive'
            reason = 'no_validation_advantage'
            if proposed != 'retain_parent':
                lag1 = observations.get(_h_shift(target['period_end'], -3))
                lag2 = observations.get(_h_shift(target['period_end'], -6))
                lag4 = observations.get(_h_shift(target['period_end'], -12))
                if not all((lag1, lag2, lag4)) or any(n['available_on'] > cutoff for n in (lag1, lag2, lag4)):
                    reason = 'forecast_origin_inputs_missing'
                elif any(_unverified(n['source']) for n in history):
                    reason = 'source_location_or_hash_unverified'
                elif bridge['gate'] != 'anchor' or bridge['event'] is not None:
                    reason = 'parent_event_precedence'
                elif bridge['anchor'] is None or bridge['anchor']['value'] != lag4['value']:
                    reason = 'parent_anchor_not_reconciled'
                else:
                    selection = proposed
                    if selection == 'seasonal_naive':
                        reason = 'validation_advantage_preserve_parent_anchor'
                    else:
                        reason = 'validation_advantage'
                        value = _value((lag1['value'] + lag2['value']) / 2)
                        if value != bridge['anchor']['value']:
                            recommendation = {'method': 'recent_level', 'value': value,
                                              'unit': target['unit'], 'period_end': target['period_end'],
                                              'inputs': [lag2, lag1]}
                            coverage['departures'] += 1
        rows = []
        for note in history:
            rows.append({'period_end': note['period_end'], 'value': note['value'],
                         'available_on': note['available_on'],
                         'evidence': _h_intern(note['source'], bank, cache)})
        if recommendation is not None:
            recommendation['inputs'] = [_h_intern(n['source'], bank, cache) for n in recommendation['inputs']]
        outputs.append({'target_id': target['target_id'], 'comparable_periods': len(history),
                        'conflicted_periods': conflicts,
                        'verified_periods': sum(not _unverified(n['source']) for n in history),
                        'history': rows,
                        'validation': {'folds': folds, 'seasonal_mae': seasonal_mae, 'recent_mae': recent_mae},
                        'proposed_selection': proposed, 'selection': selection,
                        'reason': reason, 'recommendation': recommendation})
    result = {'version': _H_VERSION, 'scope': 'Discovery_only_frozen_matched_trial25_original_awards',
              'parameters': dict(_H_PARAMETERS), 'coverage': coverage, 'targets': outputs, 'evidence': bank}
    if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > 48000:
        # Do not recommend a model after dropping the history needed to audit it.
        result['evidence'] = {}
        result['coverage']['departures'] = 0
        result['targets'] = [{'target_id': t['target_id'], 'comparable_periods': t['comparable_periods'],
                              'validation_origins': len(t['validation']['folds']),
                              'proposed_selection': t['proposed_selection'], 'selection': 'retain_parent',
                              'reason': 'history_evidence_output_budget', 'recommendation': None} for t in outputs]
    return result


def run(payload):
    result = _anchor_date_parent_run(payload)
    if not isinstance(result, dict) or 'error' in result or 'research_requests' in result:
        return result
    targets = _targets(str(payload.get('questions', '')))[:32]
    rows, required, cutoff, target_filed = _index(payload)
    allowed = {r['path']: r for r in rows}
    spans, failures = _spans(payload, allowed)
    result['anchor_history_research'] = _h_research(targets, result['bridges'], spans, allowed, cutoff)
    result['instructions'] += _H_INSTRUCTION
    if result['stage'] == 'controller':
        result['controller_checks'].append('audit_history_coverage_validation_and_nonactivation')
    def size():
        return len(json.dumps({'ok': True, 'value': result}, ensure_ascii=False).encode('utf-8'))
    if size() > 128000:
        result['leads'] = []
        for bridge in result['bridges']:
            bridge['recent'] = None
            bridge['observed_components'] = {'continuing_activity': [], 'residual_costs': [], 'one_offs': []}
        result['warnings'].append('secondary_evidence_omitted_for_history_output_budget')
    if size() > 128000:
        research = result['anchor_history_research']
        research['evidence'] = {}
        research['coverage']['departures'] = 0
        research['targets'] = [{'target_id': t['target_id'], 'selection': 'retain_parent',
                                'reason': 'combined_output_budget', 'recommendation': None} for t in research['targets']]
        result['warnings'].append('history_recommendations_withheld_for_output_budget')
    return result



# hypotheses ONLY. Admission uses returned evidence and actual publication dates.
_oc_base_run = run
_oc_base_plan = _plan
_oc_base_notes = _notes
_oc_base_aligned = _aligned


def _oc_shift(period, quarters):
    try:
        d = date.fromisoformat(period)
        if d.day != calendar.monthrange(d.year, d.month)[1]:
            return None
        y, m = divmod(d.year * 12 + d.month - 1 + 3 * quarters, 12)
        return date(y, m + 1, calendar.monthrange(y, m + 1)[1]).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _oc_when(source, allowed):
    if not isinstance(source, dict):
        return None
    if 'source_path' in source:
        row = allowed.get(source['source_path'])
        return row['date'] if row else None
    inputs = source.get('inputs')
    if isinstance(inputs, list) and inputs:
        dates = [_oc_when(s, allowed) for s in inputs]
        return max(dates) if all(dates) else None
    return None


def _notes(spans, allowed):
    result = _oc_base_notes(spans, allowed)
    for n in result:
        n['_origin_available_on'] = _oc_when(n['source'], allowed)
    return result


def _aligned(target, notes):
    # The parent removes identical period/value duplicates. Put the earliest
    # returned publication first, rather than letting a later comparative hide
    # an actually returned original vintage. Different values remain distinct;
    # no restatement is undone and all parent financial/validation gates remain.
    ordered = sorted(notes, key=lambda n: (
        n.get('_origin_available_on') or '9999-12-31',
        _unverified(n.get('source'))))
    return _oc_base_aligned(target, ordered)


def _oc_cite(source, depth=0):
    if 'source_path' in source:
        out = {k: source.get(k) for k in ('source_path', 'source_sha256', 'offset')}
        out['quote'] = str(source.get('quote', ''))[:140]
        if source.get('headers') and depth < 2:
            out['headers'] = [_oc_cite(s, depth + 1) for s in source['headers'][:2]]
        return out
    return {'kind': 'calculation', 'expression': source.get('expression'),
            'inputs': [_oc_cite(s, depth + 1) for s in source.get('inputs', [])[:2]]}


def _oc_public(note, allowed):
    return {'period_end': note['period_end'], 'value': note['value'],
            'unit': note['unit'], 'available_on': _oc_when(note['source'], allowed),
            'source': _oc_cite(note['source'])}


def _oc_rows(target, notes, allowed, asof):
    raw = [n for n in notes if _oc_when(n['source'], allowed) is not None
           and _oc_when(n['source'], allowed) <= asof]
    aligned = _aligned(target, raw)
    return [n for n in aligned if n['months'] == 3 and n['bucket'] == 'total'
            and n['period_end'] < target['period_end']
            and _oc_when(n['source'], allowed) is not None
            and _oc_when(n['source'], allowed) <= asof]


def _oc_pick(notes, period, allowed):
    choices = [n for n in notes if n['period_end'] == period]
    if not choices:
        return None, False
    latest = max(_oc_when(n['source'], allowed) for n in choices)
    choices = [n for n in choices if _oc_when(n['source'], allowed) == latest]
    if len({n['value'] for n in choices}) != 1:
        return None, True
    return min(choices, key=lambda n: _unverified(n['source'])), False


def _oc_audit(targets, notes, allowed, cutoff):
    diagnostics, bundles, rejections = [], [], []
    for t in targets[:32]:
        if t['months'] != 3 or _oc_shift(t['period_end'], 0) is None:
            diagnostics.append({'target_id': t['target_id'], 'history_periods': 0,
                'verified_periods': 0, 'candidate_origins': 0, 'complete_origins': 0,
                'verified_origins': 0, 'status': 'abstain',
                'blockers': ['unsupported_target_period']})
            continue
        full = _oc_rows(t, notes, allowed, cutoff)
        periods = sorted({n['period_end'] for n in full})
        history, conflict = [], False
        for p in periods:
            n, bad = _oc_pick(full, p, allowed)
            conflict = conflict or bad
            if n is not None:
                history.append(n)
        origins = [p for p in periods if _oc_shift(p, -4) is not None
                   and periods and _oc_shift(p, -4) >= periods[0]]
        complete = verified = 0
        reasons = set()
        for origin in origins:
            past = _oc_rows(t, notes, allowed, origin)
            inputs, failed = [], False
            for lag in (1, 2, 4):
                p = _oc_shift(origin, -lag)
                n, bad = _oc_pick(past, p, allowed)
                if n is not None:
                    inputs.append((lag, n))
                    continue
                failed = True
                alternatives = [v for v in full if v['period_end'] == p]
                reason = ('conflicting_returned_vintages' if bad else
                          'after_origin_vintage' if alternatives else 'missing_lag')
                reasons.add(reason)
                if len(rejections) < 2:
                    rejections.append({'target_id': t['target_id'], 'origin': origin,
                        'lag': lag, 'period_end': p, 'reason': reason,
                        'returned_available_on': sorted({_oc_when(v['source'], allowed)
                                                        for v in alternatives}),
                        'source_paths': sorted({v['source']['source_path']
                            for v in alternatives if 'source_path' in v['source']})})
            outcome, bad = _oc_pick(full, origin, allowed)
            conflict = conflict or bad
            if failed or outcome is None:
                continue
            complete += 1
            genuine = not any(_unverified(n['source']) for _, n in inputs)
            genuine = genuine and not _unverified(outcome['source'])
            verified += int(genuine)
            if len(bundles) < 2:
                bundles.append({'target_id': t['target_id'], 'origin': origin,
                    'provenance_verified': genuine,
                    'outcome': _oc_public(outcome, allowed),
                    'lag_inputs': [dict({'lag': lag}, **_oc_public(n, allowed))
                                   for lag, n in inputs]})
        verified_history = sum(not _unverified(n['source']) for n in history)
        blockers = []
        if len(history) < 8:
            blockers.append('insufficient_comparable_history')
        if complete < 4:
            blockers.append('insufficient_origin_complete_folds')
        if verified_history < len(history):
            blockers.append('source_location_or_hash_unverified')
        if complete < 4:
            blockers.extend(r for r in ('missing_lag', 'after_origin_vintage',
                'conflicting_returned_vintages') if r in reasons)
        if conflict and 'conflicting_returned_vintages' not in blockers:
            blockers.append('conflicting_returned_vintages')
        ready = (len(history) >= 8 and verified_history == len(history)
                 and verified >= 4 and not conflict)
        diagnostics.append({'target_id': t['target_id'], 'history_periods': len(history),
            'verified_periods': verified_history, 'candidate_origins': len(origins),
            'complete_origins': complete, 'verified_origins': verified,
            'status': 'ready_for_existing_validation' if ready else 'abstain',
            'blockers': blockers})
    return {'policy': 'origin_complete_v1', 'minimum_history': 8, 'minimum_folds': 4,
            'targets': diagnostics, 'bundles': bundles, 'rejections': rejections}


def _oc_plan(payload, targets, rows, required, spans, target_filed):
    from itertools import product
    seen = {s['path'] for s in spans}
    allowed = {r['path']: r for r in rows}
    selected = [r['path'] for r in required if r['path'] not in seen][:8]
    notes = _notes(spans, allowed)
    quarterly = [t for t in targets[:32] if t['months'] == 3
                 and _oc_shift(t['period_end'], 0) is not None]
    grids = {t['target_id']: [_oc_shift(t['period_end'], -i) for i in range(1, 21)]
             for t in quarterly}
    grid = set(p for g in grids.values() for p in g)
    explicit = {}
    try:
        for r in csv.DictReader(io.StringIO(str(payload.get('filing_index', ''))), delimiter='\t'):
            for key in ('period_of_report', 'report_period', 'period_end', 'report_date', 'period'):
                value = r.get(key, '')
                if re.fullmatch(r'\d{8}', value):
                    value = value[:4] + '-' + value[4:6] + '-' + value[6:]
                try:
                    date.fromisoformat(value)
                except (ValueError, TypeError):
                    continue
                if r.get('path') in allowed and value <= allowed[r['path']]['date']:
                    explicit[r['path']] = value
                    break
    except (csv.Error, TypeError):
        pass
    # Projected quarter coverage is never placed in _notes or supplied as facts.
    projected, annuals = {}, []
    def add(period, publication, paths):
        if period in grid:
            projected.setdefault(period, []).append((publication, frozenset(paths)))
    for r in rows:
        if r['path'] in seen or r['form'] not in ('10-Q', '10-K'):
            continue
        p = explicit.get(r['path'])
        if p is None:
            lag = 70 if r['form'] == '10-K' else 40
            ceiling = 140 if r['form'] == '10-K' else 100
            candidates = [p for p in grid if 0 < (date.fromisoformat(r['date']) - date.fromisoformat(p)).days <= ceiling]
            if not candidates:
                continue
            p = min(candidates, key=lambda p: (abs((date.fromisoformat(r['date']) - date.fromisoformat(p)).days - lag), p))
        if p not in grid:
            continue
        if r['form'] == '10-K':
            annuals.append((r, p))
        else:
            add(p, r['date'], [r['path']])
            add(_oc_shift(p, -4), r['date'], [r['path']])
    # A fiscal-Q4 projection costs BOTH an annual and a nine-month filing.
    # Actual subtraction still belongs exclusively to the original parser.
    plain = {p: list(v) for p, v in projected.items()}
    for r, p in annuals:
        for end in (p, _oc_shift(p, -4)):
            q3 = _oc_shift(end, -1)
            for publication, paths in plain.get(q3, []):
                add(end, max(publication, r['date']), set(paths) | {r['path']})
    bundles = set()
    for t in quarterly:
        coverage = {p: list(v) for p, v in projected.items()}
        for n in _aligned(t, notes):
            when = _oc_when(n['source'], allowed)
            if n['months'] == 3 and n['bucket'] == 'total' and when:
                coverage.setdefault(n['period_end'], []).append((when, frozenset()))
        for origin in sorted(grids[t['target_id']]):
            options = []
            for lag in (0, 1, 2, 4):
                p = _oc_shift(origin, -lag)
                choices = [(d, paths) for d, paths in coverage.get(p, [])
                           if lag == 0 or d <= origin]
                choices.sort(key=lambda v: (len(set(v[1]) - seen - set(selected)), v[0], sorted(v[1])))
                options.append([v[1] for v in choices[:2]])
            if all(options):
                for combination in product(*options):
                    paths = frozenset().union(*combination) - seen
                    if len(paths - set(selected)) <= 8 - len(selected):
                        bundles.add(paths)
    # Bounded bundle lookahead, not independent current-year file ranking.
    bundles = sorted(bundles, key=lambda b: (len(b - set(selected)), sorted(b)))[:256]
    chosen = set(selected) | seen
    while len(selected) < 8:
        before = sum(b <= chosen for b in bundles)
        best, best_score = None, None
        for b in bundles:
            extra = b - chosen
            if not extra or len(extra) > 8 - len(selected):
                continue
            gain = sum(other <= chosen | extra for other in bundles) - before
            score = (gain / len(extra), gain, -len(extra))
            if best_score is None or score > best_score:
                best, best_score = extra, score
        if best is None:
            break
        for r in rows:
            if r['path'] in best:
                selected.append(r['path'])
                chosen.add(r['path'])
    # With no feasible closure, retain useful ordinary acquisition rather than
    # pretending a bundle exists. There is still just one phase/eight reads.
    fallback = _oc_base_plan(targets, rows, required, spans, target_filed)
    for request in fallback:
        path = request.get('arguments', {}).get('path')
        if path in allowed and path not in chosen and len(selected) < 8:
            selected.append(path)
            chosen.add(path)
    return [{'tool': 'read_file', 'arguments': {'path': p, 'offset': 0,
             'characters': 20000}} for p in selected[:8]]


def run(payload):
    if not isinstance(payload, dict) or payload.get('stage', 'forecast') not in ('forecast', 'controller'):
        return _oc_base_run(payload)
    targets = _targets(str(payload.get('questions', '')))[:32]
    rows, required, cutoff, target_filed = _index(payload)
    allowed = {r['path']: r for r in rows}
    spans, failures = _spans(payload, allowed)
    prepared = payload
    if 'research_observations' not in payload:
        if not any(t['months'] == 3 and _oc_shift(t['period_end'], 0) for t in targets):
            return _oc_base_run(payload)
        requests = _oc_plan(payload, targets, rows, required, spans, target_filed)
        if requests:
            return {'research_requests': requests}
        prepared = dict(payload, research_observations=[])
    audit = _oc_audit(targets, _notes(spans, allowed), allowed, cutoff)
    # The Controller may receive a specific conservative research abstention.
    # Forecast numerical advice and all ready cases use the unchanged validator.
    if (payload.get('stage') == 'controller' and audit['targets']
            and not any(t['status'] == 'ready_for_existing_validation' for t in audit['targets'])):
        return {'origin_acquisition': audit, 'selection': 'retain_parent',
                'recommendation': None, 'reason': 'origin_or_provenance_gates_not_met',
                'validation_delegated': False}
    result = _oc_base_run(prepared)
    if isinstance(result, dict) and 'research_requests' not in result:
        result = dict(result, origin_acquisition=audit)
    return result
