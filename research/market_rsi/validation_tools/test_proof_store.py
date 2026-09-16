import copy
from pathlib import Path
import tempfile
import unittest

import proof_store as store
from market_rsi import canonical, digest, file_hash
from test_independent_validation import fixture


class ProofStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.p, self.c, self.r, self.b = fixture()
        self.manifest = {'schema': 'historical_runner_proof_manifest_v1',
            'context_sha256': self.c['context_sha256'], 'proposal_sha256': digest(self.p), 'proofs': {}}
        self.proofs = {}
        for kind in sorted(store.PROOF_KINDS):
            payload = {k:self.r[k] for k in store.TOP_FIELDS[kind]}
            if kind in store.SESSION_FIELDS:
                payload['sessions'] = [{k:s[k] for k in store.SESSION_FIELDS[kind] | {'utc_date'}}
                                       for s in self.r['sessions']]
            self.proofs[kind] = {'schema': 'historical_runner_metadata_proof_v1', 'kind': kind,
                'context_sha256': self.c['context_sha256'], 'proposal_sha256': digest(self.p), 'payload': payload}
            self.save_proof(kind)
        self.save_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def save_proof(self, kind):
        path = self.root / (kind + '.json'); path.write_text(canonical(self.proofs[kind]))
        self.manifest['proofs'][kind] = {'path': path.name, 'sha256': file_hash(path)}

    def save_manifest(self):
        path = self.root / 'manifest.json'; path.write_text(canonical(self.manifest))
        self.anchor = file_hash(path)

    def check(self):
        return store.inspect_bundle(self.root, 'manifest.json', self.anchor, self.p, self.c, self.b)

    def test_full_fixture_reassembles_but_never_executes(self):
        result = self.check()
        self.assertTrue(result['metadata_gate_passed']); self.assertTrue(result['proof_file_integrity_verified'])
        self.assertFalse(result['proof_truth_proven_by_hashes']); self.assertFalse(result['execution_admitted'])
        self.assertFalse(result['dispatch_token_created'])

    def test_changed_proof_rejected(self):
        (self.root / 'coverage.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'proof bytes'):
            self.check()

    def test_self_rehash_cannot_replace_external_manifest_anchor(self):
        self.manifest['context_sha256'] = 'a' * 64
        (self.root / 'manifest.json').write_text(canonical(self.manifest))
        with self.assertRaisesRegex(ValueError, 'proof bytes'):
            self.check()

    def test_missing_kind_fails(self):
        self.manifest['proofs'].pop('exposure_history'); self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'proof set'):
            self.check()

    def test_other_proposal_fails(self):
        self.proofs['coverage']['proposal_sha256'] = 'b' * 64
        self.save_proof('coverage'); self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'another kind/context/proposal'):
            self.check()

    def test_inconsistent_day_sets_fail(self):
        self.proofs['coverage']['payload']['sessions'].pop()
        self.save_proof('coverage'); self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'exactly match'):
            self.check()

    def test_extra_self_asserted_field_fails(self):
        self.proofs['coverage']['payload']['execution_admitted'] = True
        self.save_proof('coverage'); self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'per-kind proof payload'):
            self.check()

    def test_low_coverage_truthfully_blocks_even_with_valid_hash(self):
        self.proofs['coverage']['payload']['sessions'][0]['coverage_fraction'] = .1
        self.save_proof('coverage'); self.save_manifest()
        r = self.check(); self.assertFalse(r['metadata_gate_passed'])
        self.assertTrue(any('insufficient_coverage' in b for b in r['blockers']))

    def test_absolute_path_rejected(self):
        self.manifest['proofs']['coverage']['path'] = str(self.root / 'coverage.json'); self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'runner-relative'):
            self.check()

    def test_parent_traversal_rejected(self):
        self.manifest['proofs']['coverage']['path'] = '../coverage.json'; self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'runner-relative'):
            self.check()

    def test_symlink_proof_rejected(self):
        original = self.root / 'coverage.json'; moved = self.root / 'moved.json'
        original.rename(moved); original.symlink_to(moved)
        with self.assertRaises(OSError):
            self.check()

    def test_symlink_directory_rejected(self):
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink ancestor'):
            store.read_pinned_json(self.root / 'link', 'manifest.json', self.anchor)

    def test_duplicate_json_key_rejected(self):
        path = self.root / 'ambiguous.json'; path.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            store.read_pinned_json(self.root, path.name, file_hash(path))

    def test_nonfinite_number_rejected(self):
        path = self.root / 'nan.json'; path.write_text('{"a":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'):
            store.read_pinned_json(self.root, path.name, file_hash(path))

    def test_oversized_file_rejected(self):
        path = self.root / 'big.json'; path.write_bytes(b' ' * (store.MAX_PROOF_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'bounded regular'):
            store.read_pinned_json(self.root, path.name, file_hash(path))
