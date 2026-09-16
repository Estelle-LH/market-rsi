"""Free real public-link discovery through the broker; no model or market rows."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_scientist_harness import fixtures
from data_scientist_harness.broker import Broker
from data_scientist_harness.public_budget import PublicBudget
from market_rsi import digest, fresh_json


def run(root):
    sha = fixtures.workspace(root, network=True)
    b = Broker(root, sha)
    b.call('inspect_harness', {})
    first = b.call('read_public_source', {'url': 'https://docs.polymarket.com/', 'offset': 0})
    links = [x['url'] for x in first['links'] if x['url'] == 'https://docs.polymarket.com/market-data/realtime-data']
    if not links: raise ValueError('required real link not delivered; no guessed URL fallback')
    second = b.call('read_public_source', {'url': links[0], 'offset': 0})
    budget = PublicBudget(root/'public-fetches', b.store.config['public_fetch_body_cap'], sha).snapshot()
    actual = first['receipt']['body_bytes'] + second['receipt']['body_bytes']
    if budget['charged_or_reserved_bytes'] != actual or budget['pending_attempts'] != 0:
        raise ValueError('real body byte settlement mismatch')
    report = {'schema': 'public_links_live_canary_v1', 'passed': True,
        'manifest_sha256': sha, 'actual_tinker_calls': 0, 'model_authorship_proven': False,
        'live_reads': 2, 'first_link_count': len(first['links']), 'followed_url': links[0],
        'first_body_bytes': first['receipt']['body_bytes'], 'second_body_bytes': second['receipt']['body_bytes'],
        'body_budget': budget, 'source_admitted': False, 'fits': 0,
        'read_scope': 'first text page plus actual link list; not entire linked document or GLM reading'}
    report['result_sha256'] = digest(report); fresh_json(root/'canary.json', report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    print(run(p.parse_args().output.resolve()))
