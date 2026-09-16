"""Verify forensic receipt integrity and summarize evidence, without source admission."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import load_json, file_hash, fresh_json
from capture_cross_forensic import digest, CSV_HASH, RAW_HASH, ETL_HASH, DAY


def evidence(report):
    t = report['locator']['case']['timestamp_ms']
    result = {'csv_case_reproduced_price_and_size': report['analysis']['legacy_exact_csv_price_size_matches'] > 0}
    for name, variant in report['analysis']['variants'].items():
        same = [s for s in variant['case_context'] if s['timestamp_ms'] == t]
        entries = [s for s in same if s['kind'] == 'delta_entry']
        complete = [s for s in same if s['kind'] == 'message_complete']
        source = [s for s in entries if 'source_bbo_status' in s]
        # Empty/missing/ambiguous cases never become a positive assertion by vacuous truth.
        result[name] = {'same_time_states': len(same), 'delta_entries': len(entries),
            'complete_messages': len(complete), 'source_bbo_entries': len(source),
            'source_bbo_crossed_entries': sum(s['source_bbo_status'] == 'crossed' for s in source),
            'source_bbo_matches_csv_entries': sum(s['source_matches_csv_price_pair'] for s in source),
            'replay_crossed_entries': sum(s['status'] == 'crossed' for s in entries),
            'replay_crossed_complete_messages': sum(s['status'] == 'crossed' for s in complete),
            'all_complete_messages_uncrossed': bool(complete) and all(s['status'] == 'uncrossed' for s in complete),
            'all_source_bbos_uncrossed': bool(source) and len(source) == len(entries)
                and all(s['source_bbo_status'] == 'uncrossed' for s in source)}
    result['causal_scope'] = 'One selected diagnostic case; not population frequency or historical version attestation.'
    return result


def audit(root):
    r = load_json(root/'report.json'); claim = load_json(root/'claim.json')
    if r['result_sha256'] != digest({k: v for k, v in r.items() if k != 'result_sha256'}):
        raise ValueError('report hash mismatch')
    if r['claim_sha256'] != file_hash(root/'claim.json'): raise ValueError('claim hash mismatch')
    if claim['day'] != DAY or claim['csv_sha256'] != CSV_HASH or claim['raw_sha256'] != RAW_HASH or claim['etl_sha256'] != ETL_HASH:
        raise ValueError('source scope changed')
    if r['reader_sha256'] != claim['reader_sha256']: raise ValueError('reader commitment mismatch')
    if r['locator']['csv_sha256'] != CSV_HASH or r['raw_receipt']['raw_sha256'] != RAW_HASH:
        raise ValueError('source commitment mismatch')
    if r['exit_code'] != 0 or r['ssh_reaped'] is not True or r['raw_receipt']['decoder_reaped'] is not True:
        raise ValueError('incomplete process cleanup')
    if r['raw_receipt']['decoder_exit_code'] != 0 or r['raw_receipt']['full_fixed_hour_decoded'] is not True:
        raise ValueError('incomplete fixed-hour read')
    if r['raw_frames_exported'] != 0 or r['identifiers_exported'] != 0 or r['fits'] != 0:
        raise ValueError('scope expanded')
    if any(r[k] is not False for k in ('source_mutated', 'source_admitted', 'new_test_opened')):
        raise ValueError('source/test scope expanded')
    packets = [load_json(p) for p in sorted(root.glob('progress-*.json'))]
    if packets[0].get('locator') != r['locator']: raise ValueError('locator receipt mismatch')
    terminal = [p['report'] for p in packets if p.get('stage') == 'complete']
    bound = {k: v for k, v in r.items() if k not in
             {'reader_sha256', 'claim_sha256', 'exit_code', 'ssh_reaped', 'result_sha256'}}
    if terminal != [bound]: raise ValueError('terminal receipt mismatch')
    result = {'receipt_integrity_passed': True, 'report_file_sha256': file_hash(root/'report.json'),
              'evidence': evidence(r), 'source_admitted': False, 'fits': 0, 'new_test_opened': False}
    result['result_sha256'] = digest(result)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(); value = audit(a.run)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fresh_json(a.output, value); print(value)
