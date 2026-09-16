"""Bounded anonymous HF *root directory metadata* inspection, never market data.

No resolve/download/data-viewer endpoint, recursion, credentials, redirects,
paid call, source selection, or acquisition authority exists in this tool.
Directory metadata proves advertised objects, not their contents or fitness.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_rsi import canonical, digest, file_hash, fresh_json

MAX_BYTES = 524288


def metadata_url(dataset, revision):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', dataset):
        raise ValueError('public owner/dataset identifier required')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('exact observed full revision required, not a branch alias')
    return f'https://huggingface.co/api/datasets/{dataset}/tree/{revision}?recursive=false&expand=false'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('metadata endpoint redirect rejected')


def bounded_get(url):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, headers={'Accept': 'application/json', 'Accept-Encoding': 'identity',
                                   'User-Agent': 'market-rsi-metadata-audit/1'})
    with opener.open(request, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('exact metadata endpoint must return HTTP 200')
        if response.headers.get_content_type() != 'application/json':
            raise ValueError('JSON metadata response required')
        if response.headers.get('Content-Encoding', 'identity') != 'identity':
            raise ValueError('compressed metadata response rejected')
        declared = response.headers.get('Content-Length')
        if declared is not None and (not declared.isdecimal() or int(declared) > MAX_BYTES):
            raise ValueError('metadata response length outside bound')
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('metadata response exceeded bound')
        if declared is not None and int(declared) != len(body):
            raise ValueError('metadata response length mismatch')
        return body, {'status': response.status, 'content_type': 'application/json',
            'etag': response.headers.get('ETag'), 'pagination_link': response.headers.get('Link'),
            'metadata_http_body_bytes': len(body)}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate metadata JSON key')
        result[key] = value
    return result


def no_constant(value):
    raise ValueError('nonfinite metadata JSON constant')


def parse_listing(body, headers):
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise ValueError('bounded metadata bytes required')
    records = json.loads(body, object_pairs_hook=unique_object, parse_constant=no_constant)
    if not isinstance(records, list) or len(records) > 1000:
        raise ValueError('bounded directory list required')
    seen = set(); objects = []
    for item in records:
        if not isinstance(item, dict) or item.get('type') not in ('file', 'directory'):
            raise ValueError('directory metadata item required')
        path = item.get('path')
        if (not isinstance(path, str) or not path or len(path) > 500
                or path in ('.', '..') or PurePosixPath(path).name != path
                or '/' in path or '\\' in path or any(ord(c) < 32 for c in path)):
            raise ValueError('root-only normalized object name required')
        if path in seen:
            raise ValueError('duplicate directory object')
        seen.add(path)
        size = item.get('size')
        if type(size) is not int or size < 0:
            raise ValueError('integer advertised bytes required')
        oid = item.get('oid')
        if not isinstance(oid, str) or not re.fullmatch(r'[0-9a-f]{40,64}', oid):
            raise ValueError('advertised object identifier required')
        lfs = item.get('lfs')
        sha = None
        if lfs is not None:
            if (not isinstance(lfs, dict) or type(lfs.get('size')) is not int
                    or lfs['size'] != size or not isinstance(lfs.get('oid'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', lfs['oid'])):
                raise ValueError('LFS advertised hash/size mismatch')
            sha = lfs['oid']
        objects.append({'path': path, 'type': item['type'], 'advertised_bytes': size,
                        'git_oid': oid, 'advertised_sha256': sha})
    return {'objects': sorted(objects, key=lambda x: x['path']),
        'root_listing_complete_by_http_pagination': not bool(headers.get('pagination_link')),
        'recursive_inventory_complete': False, 'raw_contents_verified': False,
        'event_time_coverage_verified': False, 'fresh_test_admitted': False,
        'acquisition_admitted': False, 'source_selected': False}


def run(dataset, revision, output, getter=bounded_get):
    url = metadata_url(dataset, revision)
    if output.exists():
        raise ValueError('fresh permanent metadata inspection ID required')
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / 'claim.json', {'dataset': dataset, 'revision': revision, 'url': url,
        'scope': 'anonymous root directory metadata only', 'max_http_body_bytes': MAX_BYTES,
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_selection': False, 'raw_download_authority_added': False})
    try:
        body, headers = getter(url)
        if not isinstance(body, bytes) or len(body) > MAX_BYTES:
            raise ValueError('bounded metadata bytes required')
        with (output / 'response.body.json').open('xb') as stream:
            stream.write(body)
        parsed = parse_listing(body, headers)
        result = {'schema': 'public_source_directory_metadata_review_v1', 'passed': True,
            'dataset': dataset, 'revision': revision, 'metadata_url': url, 'http': headers,
            'response_body_sha256': hashlib.sha256(body).hexdigest(),
            'claim_sha256': file_hash(output / 'claim.json'), 'inspector_sha256': file_hash(Path(__file__)),
            'new_market_data_download_bytes': 0, 'provider_calls': 0, **parsed}
        result['result_sha256'] = digest(result)
        fresh_json(output / 'result.json', result)
        return result
    except Exception as error:
        # Keep the claim/failed response; never retry the same inspection ID.
        fresh_json(output / 'failure.json', {'passed': False, 'error_type': type(error).__name__,
            'reason': str(error)[:2000], 'raw_download_authority_added': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.dataset, args.revision, args.output.resolve())
    print(canonical(result))
