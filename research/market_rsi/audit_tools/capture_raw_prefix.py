"""Bounded read of the first archived diagnostic prefix; return aggregates only.

No source edits, model calls, labels, raw rows or market identifiers are exported.
The prefix is selected by chronological filename, never by future price movement.
This is not a full-file integrity, historical clock, or source-admission proof.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SOURCE = Path('/opt/d10/raw/data/polymarket/polymarket-20260821T00.jsonl.zst')
EXPECTED_BYTES = 331091663
MAX_RECORDS = 5000
MAX_DECODED = 64 * 1024 * 1024
MAX_LINE = 1024 * 1024
EVENTS = {'book', 'price_change', 'last_trade_price', 'tick_size_change',
          'best_bid_ask', 'new_market', 'market_resolved'}


def profile(records):
    counts = Counter(); envelope = Counter(); fields = Counter(); times = []
    for record in records:
        if not isinstance(record, dict):
            counts['non_object_envelope'] += 1
            continue
        for key in ('t', 'src', 'm'):
            if key in record: envelope[key] += 1
        t = record.get('t')
        if type(t) not in (int, float) or datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat() != '2026-08-21':
            raise ValueError('clock outside exact diagnostic date; no price analysis')
        times.append(t)
        source = record.get('src')
        counts['source_' + (source if source in {'rest', 'ws'} else 'unknown')] += 1
        message = record.get('m')
        messages = message if isinstance(message, list) else [message]
        for m in messages:
            if not isinstance(m, dict):
                counts['non_object_message'] += 1
                continue
            et = m.get('event_type')
            counts['event_' + (et if et in EVENTS else 'other_or_absent')] += 1
            for key in ('asset_id', 'market', 'timestamp', 'hash', 'bids', 'asks', 'price_changes'):
                if key in m: fields[key] += 1
            if 'timestamp' in m:
                try:
                    diff = t - int(m['timestamp'])
                    counts['wrapper_before_message_timestamp' if diff < 0 else 'wrapper_not_before_message_timestamp'] += 1
                except (ValueError, TypeError): counts['unparsed_message_timestamp'] += 1
            if et == 'price_change':
                changes = m.get('price_changes', [])
                counts['price_change_entries'] += len(changes)
                if len(changes) > 1: counts['multi_entry_price_change_messages'] += 1
                for c in changes:
                    for key in ('asset_id', 'price', 'size', 'side', 'best_bid', 'best_ask'):
                        if key in c: fields['change_' + key] += 1
    return {'envelope_fields': dict(envelope), 'message_fields': dict(fields), 'counts': dict(counts),
            'first_wrapper_timestamp_ms': times[0] if times else None,
            'last_wrapper_timestamp_ms': times[-1] if times else None,
            'wrapper_clock_semantics_verified': False}


def read_prefix():
    if SOURCE.is_symlink() or not SOURCE.is_file(): raise ValueError('exact source missing')
    before = SOURCE.stat()
    if before.st_size != EXPECTED_BYTES: raise ValueError('source size changed')
    sha = hashlib.sha256()
    with SOURCE.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): sha.update(block)
    proc = subprocess.Popen(['zstd', '-dc', '--', str(SOURCE)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    records = []; consumed = 0; prefix_sha = hashlib.sha256(); stop = 'eof'
    try:
        while len(records) < MAX_RECORDS:
            line = proc.stdout.readline(min(MAX_LINE + 1, MAX_DECODED - consumed + 1))
            if not line: break
            consumed += len(line)
            if consumed > MAX_DECODED or len(line) > MAX_LINE: raise ValueError('prefix byte bound')
            prefix_sha.update(line)
            records.append(json.loads(line))  # Parse errors fail; never skip them.
        else: stop = 'fixed_record_limit'
    finally:
        proc.stdout.close()
        if proc.poll() is None: proc.terminate()
        try: code = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill(); code = proc.wait(timeout=5)
    if stop == 'eof' and code != 0: raise ValueError('decoder failed before prefix complete')
    after = SOURCE.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('source changed during prefix read')
    return records, {'source_path': str(SOURCE), 'source_bytes': before.st_size,
        'source_sha256': sha.hexdigest(), 'prefix_decoded_bytes': consumed,
        'prefix_sha256': prefix_sha.hexdigest(), 'prefix_records': len(records), 'stop_reason': stop,
        'decoder_exit_code': code, 'decoder_reaped': True, 'full_content_verified': False}


def remote():
    records, receipt = read_prefix()
    return {'schema': 'capture_raw_prefix_v1', **receipt, 'profile': profile(records),
        'raw_rows_exported': 0, 'identifiers_exported': 0, 'labels_built': 0, 'fits': 0,
        'source_admitted': False, 'source_mutated': False,
        'selection': 'first 5000 records of first file on earliest authorized diagnostic day'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--remote', action='store_true'); p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.remote:
        try: print(json.dumps(remote()))
        except Exception as error:
            print(json.dumps({'failure_type': type(error).__name__, 'raw_rows_exported': 0})); sys.exit(1)
        sys.exit(0)
    if not a.output or a.output.exists(): raise ValueError('fresh output required')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from market_rsi import file_hash, fresh_json, digest
    a.output.mkdir(parents=True)
    fresh_json(a.output/'claim.json', {'pid': os.getpid(), 'reader_sha256': file_hash(__file__),
        'source_path': str(SOURCE), 'expected_source_bytes': EXPECTED_BYTES,
        'max_records': MAX_RECORDS, 'max_decoded': MAX_DECODED, 'created_ns': time.time_ns()})
    response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        'root@173.255.231.4', 'nice -n 10 timeout 90s python3 - --remote'],
        input=Path(__file__).read_bytes(), capture_output=True, timeout=105)
    if response.returncode or len(response.stdout) > 100000:
        fresh_json(a.output/'failure.json', {'exit_code': response.returncode, 'raw_rows_exported': 0})
        raise RuntimeError('raw prefix probe failed; preserve claim and failure')
    value = json.loads(response.stdout)
    value['claim_sha256'] = file_hash(a.output/'claim.json'); value['result_sha256'] = digest(value)
    fresh_json(a.output/'report.json', value); print(json.dumps(value))
