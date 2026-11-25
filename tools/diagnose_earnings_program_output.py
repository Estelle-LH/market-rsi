"""Explicit one-shot output measurement, never a forecast or paid retry."""
import argparse
import hashlib
import json
from pathlib import Path

from earnings_open_code import DockerRunner
from supervisor_harness import capacity_feedback_engine as engine

SUFFIX = '''

# Trusted diagnostic wrapper only; preceding model algorithm is unchanged.
_market_rsi_measure_original_run = run
def run(payload):
    import json as _measure_json
    value = _market_rsi_measure_original_run(payload)
    encoded = _measure_json.dumps({'ok': True, 'value': value}, allow_nan=False)
    result = {'serialized_result_bytes': len(encoded.encode('utf-8')),
              'value_type': type(value).__name__}
    if isinstance(value, dict):
        result['field_json_bytes'] = {key: len(_measure_json.dumps(item, allow_nan=False).encode('utf-8')) for key, item in value.items()}
        result['targets'] = [{'target_id': item.get('target_id'), 'status': item.get('status'), 'comparables_count': len(item.get('comparables', []))} for item in value.get('targets', [])]
        result['evidence'] = [{'source_path': item.get('source_path'), 'quote_characters': len(item.get('quote', ''))} for item in value.get('evidence', [])]
    return result
'''


def measure(binding, root):
    request = engine.read(binding)
    if type(request) is not dict or set(request) != {'source', 'payload'}:
        raise ValueError('Exact preserved code/input required')
    if type(request['source']) is not str or '_market_rsi_measure_original_run' in request['source']:
        raise ValueError('Diagnostic binding collision')
    root = Path(root)
    if not root.is_absolute() or root.resolve() != root or root.exists():
        raise ValueError('Fresh canonical diagnostic root required; never retry')
    root.mkdir(mode=0o700)
    wrapped = request['source'] + SUFFIX
    intent = engine.save(root/'diagnostic-intent.json', {
        'original_input': binding,
        'original_source_sha256': hashlib.sha256(request['source'].encode()).hexdigest(),
        'wrapper_source_sha256': hashlib.sha256(wrapped.encode()).hexdigest(),
        'diagnostic_source': engine.pin(__file__),
        'max_calls': 1, 'timeout_seconds': 20, 'paid_calls': 0,
        'retry_allowed': False, 'scoring_or_adoption': False})
    runner = DockerRunner(root/'code', max_calls=1, timeout_seconds=20)
    measured = runner.run(wrapped, request['payload'])
    return engine.save(root/'measurement.json', {
        'intent': intent, 'measurement': measured,
        'scope': 'One explicitly authorized isolated output measurement. Original algorithm prefix/input unchanged; wrapper is Root-authored diagnostics, not model-authored improvement.',
        'paid_calls': 0, 'scoring_or_adoption': False, 'retry_allowed': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--execute-once', action='store_true')
    args = parser.parse_args()
    if not args.execute_once:
        parser.error('Explicit --execute-once required')
    print(json.dumps(measure({'path': args.input, 'sha256': args.sha256}, args.root)))
