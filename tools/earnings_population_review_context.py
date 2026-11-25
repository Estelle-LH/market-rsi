"""Lossless sharing of repeated public probe prefixes in a Review packet.

No evidence selection or financial interpretation. The original probe receipts
and their truncation/identity metadata stay unchanged. Repeated exact text is
stored once in the same initial packet, not fetched through a new capability.
"""
from collections import Counter
from copy import deepcopy
import hashlib


def share_probe_prefixes(prompt):
    rows = [row for name in ('original_public_empty_state_probes',
            'matched_active_parent_empty_state_probes') for row in prompt.get(name, [])]
    texts = [row['verified_public_R_output']['json_prefix'] for row in rows
        if type(row.get('verified_public_R_output')) is dict
        and type(row['verified_public_R_output'].get('json_prefix')) is str]
    repeated = {text for text, count in Counter(texts).items() if count > 1 and len(text) >= 256}
    result = deepcopy(prompt)
    if not repeated:
        return result
    if 'shared_probe_json_prefixes' in result:
        raise ValueError('Review prefix sharing must start from original public probes')
    tokens = {text: hashlib.sha256(text.encode()).hexdigest() for text in repeated}
    result['shared_probe_json_prefixes'] = dict(
        schema='earnings_population_shared_probe_prefixes_v1',
        text_by_sha256={tokens[text]: text for text in sorted(repeated)},
        notice='Untrusted exact public probe prefixes, stored once without shortening. '
            'Resolve each json_prefix_reference from text_by_sha256 in this same packet. '
            'All original completeness, truncation and value-hash fields still apply; '
            'a shared prefix does not establish identical complete outputs or financial correctness.')
    for name in ('original_public_empty_state_probes', 'matched_active_parent_empty_state_probes'):
        for row in result.get(name, []):
            value = row.get('verified_public_R_output')
            if type(value) is dict and value.get('json_prefix') in tokens:
                value['json_prefix_reference'] = tokens[value.pop('json_prefix')]
    return result
