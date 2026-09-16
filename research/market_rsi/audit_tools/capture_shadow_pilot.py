"""One bounded scale pilot of the requested replay; NOT the full-day capability.

Fixed first50k records, not selected by score or price movement. Same source as
the first5k probe;64MiB decoded upper remains below a512MiB address-space cap.
No outage, complement-quote equality, clock or historical-identity certification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time


def run_pilot():
    global MAX_RECORDS
    MAX_RECORDS = 50000
    # Retain the original64MiB decoded cap; no whole-day decompression on disk.
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    started = time.monotonic()
    records, receipt = read_prefix()
    if receipt['source_sha256'] != EXPECTED_SOURCE: raise ValueError('source changed')
    profile(records)
    source = Path('/opt/d10/bin/etl.py').read_bytes()
    original = legacy(records, source)
    variants = {}
    for name, atomic in [('per_entry_with_ws_snapshots', False), ('atomic_with_ws_snapshots', True)]:
        states, counts = shadow(records, atomic, True)
        variants[name] = summarize(states, counts)
        del states
    return {'schema': 'capture_shadow_scale_pilot_v1', 'source': receipt,
        'legacy_current_code': original, 'shadow_variants': variants,
        'profile': profile(records), 'elapsed_seconds': time.monotonic()-started,
        'raw_rows_exported': 0, 'source_mutated': False, 'source_admitted': False, 'fits': 0,
        'full_requested_capability_implemented': False, 'actual_published_csv_compared': False,
        'full_day_error_frequency_proven': False, 'semantic_certification': False,
        'scope': 'first50000 records of same chronological first archived hour; engineering pilot only',
        'unknown': ['capture clock provenance', 'historical token mapping', 'quiet versus outage',
                    'independent sample size', 'full-day gaps and snapshot coverage'],
        'rejected_claims': ['missing files prove outage', 'mtime proves receive clock',
                            'arbitrary Yes+No quotes must sum exactly to one']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--remote', action='store_true')
    p.add_argument('--output', type=Path); a = p.parse_args()
    if a.remote:
        try: print(json.dumps(run_pilot()))
        except Exception as error:
            print(json.dumps({'failure_type': type(error).__name__, 'raw_rows_exported': 0})); sys.exit(1)
        sys.exit(0)
    if not a.output or a.output.exists(): raise ValueError('fresh output required')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from market_rsi import digest, file_hash, fresh_json, load_json
    root = Path(__file__).resolve().parents[1]
    controller = root/'artifacts/source-repair-followup-20260911-01'
    if (load_json(controller/'session/assessment.json').get('process_reaped') is not True
        or load_json(controller/'submitted-decision.json').get('action') != 'defer'
        or load_json(controller/'records/0007.json')['arguments']['name'] != 'd10_polymarket_raw_snapshot_replay_coverage_auditor'):
        raise ValueError('exact terminal controller work order required')
    sections = [Path(__file__).with_name(n).read_text().split("if __name__ == '__main__':")[0]
                for n in ('capture_raw_prefix.py', 'capture_shadow_replay.py')]
    source = ('\n'.join(sections) + '\n' + Path(__file__).read_text()).encode()
    a.output.mkdir(parents=True)
    fresh_json(a.output/'claim.json', {'reader_sha256': hashlib.sha256(source).hexdigest(),
        'controller_proposal_sha256': file_hash(controller/'records/0007.json'),
        'max_records': 50000, 'max_decoded_bytes': 64*1024*1024,
        'max_address_space_bytes': 512*1024*1024, 'remote_wall_seconds': 120,
        'scope': 'bounded prefix pilot, not activation of full capability or scientific thresholds'})
    try:
        response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            'root@173.255.231.4', 'nice -n 10 timeout 120s python3 - --remote'], input=source,
            capture_output=True, timeout=135)
    except subprocess.TimeoutExpired:
        fresh_json(a.output/'failure.json', {'failure': 'local_transport_timeout', 'remote_exit_unverified': True})
        raise
    if response.returncode or len(response.stdout) > 100000:
        fresh_json(a.output/'failure.json', {'exit_code': response.returncode, 'raw_rows_exported': 0})
        raise RuntimeError('pilot failed; claim and failure preserved')
    value = json.loads(response.stdout); value['claim_sha256'] = file_hash(a.output/'claim.json')
    value['result_sha256'] = digest(value); fresh_json(a.output/'report.json', value); print(json.dumps(value))
