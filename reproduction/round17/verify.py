#!/usr/bin/env python3
"""Check the frozen programs and optionally recompute the historical score locally."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_programs(metadata):
    for axis, expected in metadata['program_sha256'].items():
        path = ROOT / 'frozen' / ('program_' + axis + '.py')
        if digest(path) != expected:
            raise ValueError(f'Frozen {axis} does not match the original descriptor')
        compile(path.read_bytes(), str(path), 'exec')


def verify_score(path, metadata):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata['original_comparison_sha256']:
        raise ValueError('Report bytes do not match the sealed round 17 comparison')
    payload = json.loads(raw)
    rows = payload['comparison']['rows']
    if payload.get('source_commit') != metadata['original_source'] or len(rows) != 25:
        raise ValueError('Expected the original source and all 25 company rows')
    if len({row['company_id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate company rows')
    total = Decimal(0)
    for row in rows:
        targets = row['targets']
        if {x['target_id'] for x in targets} != {f'T{i:03d}' for i in range(1, 6)} or len(targets) != 5:
            raise ValueError('Company must have all five target IDs exactly once')
        awards = [Decimal(str(x['candidate_award'])) for x in targets]
        if any(x not in (Decimal(0), Decimal('0.5'), Decimal(1)) for x in awards):
            raise ValueError('Unexpected awarded points')
        points = sum(awards, Decimal(0))
        if points != Decimal(str(row['points'])):
            raise ValueError('Company points do not match its target awards')
        total += points
    if total != Decimal('79.5') or total / len(rows) != Decimal('3.18'):
        raise ValueError('Recomputed aggregate does not match the recorded result')
    print(f'{len(rows)} companies, {5 * len(rows)} targets, {total} points, mean {total / len(rows)} / 5')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--score-report', type=Path, help='Exact comparison JSON kept outside this repository')
    args = parser.parse_args()
    metadata = json.loads((ROOT / 'evidence.json').read_text())
    verify_programs(metadata)
    print('Frozen R and H match their original SHA-256 and compile without executing candidate code.')
    if args.score_report is not None:
        verify_score(args.score_report, metadata)


if __name__ == '__main__':
    main()
