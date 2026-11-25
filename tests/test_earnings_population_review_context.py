"""Lossless Review packet sharing, not a token-fit or prediction assertion."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from earnings_population_review_context import share_probe_prefixes


def expand(packet):
    result = deepcopy(packet)
    table = result.pop('shared_probe_json_prefixes')['text_by_sha256']
    for name in ('original_public_empty_state_probes', 'matched_active_parent_empty_state_probes'):
        for row in result.get(name, []):
            value = row.get('verified_public_R_output', {})
            if 'json_prefix_reference' in value:
                token = value.pop('json_prefix_reference')
                text = table[token]
                if hashlib.sha256(text.encode()).hexdigest() != token:
                    raise ValueError('Changed public prefix')
                value['json_prefix'] = text
    return result


class ReviewPrefixTests(unittest.TestCase):
    def test_repeated_prefix_not_whole_output_shared_losslessly_with_all_metadata(self):
        text = 'Exact public financial evidence 界 ' * 200
        a = dict(json_prefix=text, complete=False, value_sha256='a'*64, total_characters=20000)
        b = dict(a, value_sha256='b'*64, total_characters=21000)
        original = dict(candidate_id='child', original_public_empty_state_probes=[
            dict(stage='forecast', verified_public_R_output=a, receipt={'sha256':'1'*64}),
            dict(stage='controller', verified_public_R_output=b, receipt={'sha256':'2'*64})])
        before = deepcopy(original)
        packet = share_probe_prefixes(original)
        self.assertEqual(original, before)
        self.assertEqual(expand(packet), original)
        self.assertEqual(len(packet['shared_probe_json_prefixes']['text_by_sha256']), 1)
        self.assertEqual(packet['original_public_empty_state_probes'][1]['verified_public_R_output']['value_sha256'], 'b'*64)
        self.assertFalse(packet['original_public_empty_state_probes'][1]['verified_public_R_output']['complete'])
        self.assertLess(len(json.dumps(packet)), len(json.dumps(original)))

    def test_unique_complete_and_small_outputs_are_unchanged(self):
        for output in ({'value':{'method':'original'}, 'complete':True},
                {'json_prefix':'x'*1000, 'complete':False}, {'json_prefix':'short', 'complete':False}):
            original = {'original_public_empty_state_probes':[{'verified_public_R_output':output}]}
            self.assertEqual(share_probe_prefixes(original), original)

    def test_changed_shared_text_and_second_application_are_detectable(self):
        original = {'original_public_empty_state_probes':[
            {'verified_public_R_output':{'json_prefix':'x'*1000}} for _ in range(2)]}
        packed = share_probe_prefixes(original)
        key = next(iter(packed['shared_probe_json_prefixes']['text_by_sha256']))
        packed['shared_probe_json_prefixes']['text_by_sha256'][key] += 'changed'
        with self.assertRaises(ValueError): expand(packed)
        conflict = dict(original, shared_probe_json_prefixes={})
        with self.assertRaises(ValueError): share_probe_prefixes(conflict)

    def test_original23_review_packet_reconstructs_exactly_with_smaller_public_bytes(self):
        path = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016/attempts/edgar-population-20261016-23/roles/review-01/effective-input.json')
        raw = path.read_bytes(); token = hashlib.sha256(raw).hexdigest()
        original = json.loads(raw)
        packet = share_probe_prefixes(original)
        self.assertEqual(expand(packet), original)
        self.assertEqual(len(packet['shared_probe_json_prefixes']['text_by_sha256']), 2)
        encode = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        self.assertGreater(len(encode(original))-len(encode(packet)), 12000)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), token)
        # No inference/count/provider access, candidate execution or hidden labels.


if __name__ == '__main__': unittest.main()
