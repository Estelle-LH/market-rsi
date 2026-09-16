"""Freeze new aggregate evidence for one controller continuation, never sample."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import create
from paid_budget import PaidBudget
from controller_dependency_preflight import inspect
from prepare_tonight_design import verify_dependency_receipt

ROOT = Path(__file__).resolve().parents[1]
PARENT = 'tonight-data-scientist-design-20260911-06'
PARENT_MANIFEST = '1a928329a4d3457c0bd84716cfbdd95351c08115e85de3e982ee1760b34c2e0f'
EVIDENCE = {
    'completed-quote-audit': 'capture-batch-audit-20260911-01/report.json',
    'fixed-raw-prefix': 'capture-raw-prefix-20260911-01/report.json',
    'same-prefix-shadow-comparison': 'capture-shadow-prefix-20260911-01/report.json',
    'actual-link-reader-canary': 'public-links-live-canary-20260911-01/canary.json',
}


def evidence(path):
    r = load_json(path)
    if r.get('result_sha256') != digest({k: v for k, v in r.items() if k != 'result_sha256'}):
        raise ValueError('evidence digest changed')
    if r.get('source_admitted') is not False or r.get('fits') != 0:
        raise ValueError('no empirical source admission in this followup')
    return {'report': r, 'path': str(path), 'sha256': file_hash(path)}


def prepare(output, release, dependency):
    if output.exists(): raise ValueError('fresh controller workspace required')
    parent = ROOT/'artifacts'/PARENT
    if file_hash(parent/'workspace.json') != PARENT_MANIFEST: raise ValueError('parent manifest changed')
    config = load_json(parent/'workspace.json')
    for p, sha in config['files'].items():
        if file_hash(p) != sha: raise ValueError('frozen parent data/code changed')
    assessment = load_json(parent/'session/assessment.json')
    if assessment.get('valid') is not True or assessment.get('process_reaped') is not True:
        raise ValueError('exact previous controller not terminal')
    verify_dependency_receipt(load_json(dependency), inspect(release, ROOT/'artifacts/tokenizer-cache'))
    budget_path = ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
    budget = PaidBudget(budget_path).snapshot()
    if any(v['state'] == 'dispatched' and '-turn-' in k for k, v in budget['jobs'].items()):
        raise ValueError('another active/unresolved model turn')
    findings = [{'id': name, **evidence(ROOT/'artifacts'/relative)} for name, relative in EVIDENCE.items()]
    findings += [
        {'id': 'reviewed-interpretation-and-limits',
         'observations': [
             'The 8-date quote audit now completed; do not repeat the obsolete audit-still-missing claim.',
             '1.8149% crossed CSV rows is not a tradable arbitrage or a measured cause attribution.',
             'The chronological 5000-row raw prefix spans only1.605seconds, not a representative session.',
             'The current legacy parser emits0 quotes there; explicit WS snapshots yield2 two-sided states.',
             '9996 delta entries remain unanchored. Atomic and per-entry shadows show no difference in this prefix.',
             'No actual published CSV row comparison, historical ETL attestation, historical Gamma mapping or receive-clock proof yet.',
             'Missing local files do not prove an outage. Identical serialized clocks do not establish receive time.',
             'Official0..1 price is dollars/share, not cents. Valid-looking values alone do not prove our old field units.'],
         'primary_sources_opened_by_runner_not_by_you': [
             'https://docs.polymarket.com/market-data/realtime-data',
             'https://docs.polymarket.com/concepts/prices-orderbook'],
         'next_decision': 'Use these observations to research and specify the smallest verifiable next source work order. '
             'You can request a new capability but cannot execute arbitrary code or declare the source admitted. '
             'Choose your research response; the runner has not chosen a target, horizon, data mask or trainer.'},
        {'id': 'immutable-source-and-test-boundaries',
         'scope': 'Only previously opened diagnostic dates Aug21..25 and Sep07..09; Aug26..Sep06 remains protected.',
         'raw_inventory': {'files': 122, 'compressed_bytes': 11889232674, 'location': 'existing Linode archive'},
         'constraints': 'No source overwrite, purchase, new market download, hidden Test, raw-row upload, '
             'future-movement selection or relabeling opened dates as fresh Test. Min20untouched sessions for final claims remains.',
         'study_status': 'No admitted input cache; source research only, no fitting. Do not repeat blocked fit calls.'},
        {'id': 'version-and-funds', 'release': load_json(release)['publication'],
         'budget': {k: v for k, v in budget.items() if k != 'jobs'},
         'changes': 'v1.2.4 is human-directed engineering: actual successful public-body bytes settle; missing receipts retain upper; '
             'HTML returns real links. Same10MB total. Each text offset still fetches again, no body cache. '
             'Final50/repair20 remain protected. No new200budget. Archive is history, not current QA.'},
    ]
    archive = parent/'round-archive.json'
    sha = create(output, quality=config['quality'], findings=findings, allowed_dates=[],
        purpose='source_research', network=True, release_path=release,
        prior_archives=[{'path': str(archive), 'sha256': file_hash(archive)}])
    receipt = {'schema': 'source_repair_followup_preparation_v1', 'manifest_sha256': sha,
        'parent_manifest_sha256': PARENT_MANIFEST, 'parent_archive_sha256': file_hash(archive),
        'reader_sha256': file_hash(__file__), 'dependency_receipt_sha256': file_hash(dependency),
        'budget_authorization_sha256': file_hash(budget_path/'authorization.json'),
        'source_admitted': False, 'fits': 0, 'provider_calls': 0, 'raw_rows_uploaded': 0}
    fresh_json(output/'preparation.json', receipt)
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'release', 'dependency'): p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); print(prepare(a.output.resolve(), a.release.resolve(), a.dependency.resolve()))
