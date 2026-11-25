"""Path-policy equivalence and fresh-read refusals; inert temporary files only."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_continuation as history


class HistoricalPathContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.root, self.repo = self.home/'owned', self.home/'repo'
        self.artifacts = self.home/'artifacts'
        self.ident = 'edgar-population-20261016-10'
        self.reader = history._Reader(self.root, self.home/'ledger.sqlite3', self.repo, self.ident)
        artifact_policy = patch.object(history.tasks, 'ARTIFACTS', self.artifacts)
        artifact_policy.start()
        self.addCleanup(artifact_policy.stop)

    def write(self, path, value=None, *, raw=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps({'synthetic': True} if value is None else value).encode()
                         if raw is None else raw)
        return self.bound(path)

    def bound(self, path):
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def owned(self, name='value.json', *, ident=None, kind='attempts', root=None):
        return (self.root if root is None else root)/kind/(ident or self.ident)/name

    def legacy_roots(self):
        reader = self.reader
        allowed = [reader.root/kind/ident for ident in reader.ids for kind in ('inputs', 'attempts')]
        allowed += [Path('/private/tmp')/('market-rsi-'+ident) for ident in reader.ids]
        allowed += [history.tasks.ARTIFACTS/'edgar-research-objective-20261014',
            Path('/__LOCAL_RESEARCH_HOME__/Library/Application Support/MarketRSI/co-evo-earnings/episodes/edgar-research-20261015-09')]
        return allowed

    def test_tuple_containment_matches_original_posix_path_boundaries(self):
        paths = ['/', '/a', '/a/b', '/a/b/c', '/a/bad', '/a/b-c', '/a/b/../c',
                 '/a/同一/表.json', '/a/同一性/表.json', '/private/tmp', '/private/tmpx']
        roots = ['/', '/a', '/a/b', '/a/b/c', '/a/同一', '/private/tmp', '.', 'relative']
        for path in map(Path, paths):
            for root in map(Path, roots):
                with self.subTest(path=path, root=root):
                    self.assertEqual(history._contains(path.parts, root.parts), path.is_relative_to(root))

    def test_allowed_root_parts_exactly_match_legacy_policy(self):
        self.reader.ids.update({'edgar-population-20261016-01', 'edgar-population-20261016-07'})
        self.assertEqual(set(self.reader._allowed_parts()), {path.parts for path in self.legacy_roots()})
        for root in self.legacy_roots():
            for path in (root, root/'file.json', root.parent/(root.name+'-foreign')/'file.json'):
                with self.subTest(path=path):
                    actual = any(history._contains(path.parts, prefix) for prefix in self.reader._allowed_parts())
                    self.assertEqual(actual, any(path.is_relative_to(p) for p in self.legacy_roots()))

    def test_only_constructed_lexical_roots_are_reused(self):
        first = self.reader._allowed_parts()
        self.assertIs(first, self.reader._allowed_parts())
        self.reader.extra.add(self.home/'one-exact-file.json')
        self.assertIs(first, self.reader._allowed_parts())
        self.reader.ids.add('edgar-population-20261016-07')
        self.assertIsNot(first, self.reader._allowed_parts())
        before = self.reader._allowed_parts()
        self.reader.ids = set(self.reader.ids)
        self.assertIs(before, self.reader._allowed_parts())

    def test_ids_add_remove_and_replacement_take_effect_immediately(self):
        other = 'edgar-population-20261016-07'
        bound = self.write(self.owned(ident=other))
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.reader.read(bound)
        self.reader.ids.add(other)
        self.assertEqual(self.reader.read(bound), {'synthetic': True})
        self.reader.ids.remove(other)
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.reader.read(bound)
        self.reader.ids = {other}
        self.assertEqual(self.reader.read(bound), {'synthetic': True})
        self.reader.ids = {self.ident}
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.reader.read(bound)

    def test_root_mutation_invalidates_constructed_roots(self):
        old = self.write(self.owned())
        new_root = self.home/'second-owned'
        new = self.write(self.owned(root=new_root))
        self.reader.read(old)
        self.reader.root = new_root
        self.assertEqual(self.reader.read(new), {'synthetic': True})
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.reader.read(old)

    def test_artifacts_mutation_invalidates_only_corresponding_root(self):
        old = self.write(self.artifacts/'edgar-research-objective-20261014/old.json')
        self.reader.read(old)
        new_artifacts = self.home/'other-artifacts'
        new = self.write(new_artifacts/'edgar-research-objective-20261014/new.json')
        history.tasks.ARTIFACTS = new_artifacts
        self.assertEqual(self.reader.read(new), {'synthetic': True})
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.reader.read(old)

    def test_extra_is_an_exact_fresh_membership_not_a_cached_root(self):
        path = self.home/'external.json'
        bound = self.write(path)
        sibling = self.write(self.home/'external.json-child/other.json')
        self.reader._allowed_parts()
        self.reader.extra.add(path)
        self.assertEqual(self.reader.read(bound), {'synthetic': True})
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.reader.read(sibling)
        self.reader.extra.remove(path)
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            self.reader.read(bound)
        self.reader.extra = {path}
        self.assertEqual(self.reader.read(bound), {'synthetic': True})

    def test_source_authority_is_checked_even_when_bytes_already_cached(self):
        path = self.repo/'historical.py'
        bound = self.write(path, raw=b'{"old_source": true}')
        self.reader.commit = 'a'*40
        self.reader.sources = {(str(path), bound['sha256'])}
        with patch.object(history, '_git', return_value=path.read_bytes()) as git:
            self.assertEqual(self.reader.read(bound), {'old_source': True})
            self.reader.sources.clear()
            self.reader.extra.add(path)
            with self.assertRaisesRegex(ValueError, 'Unregistered historical production source'):
                self.reader.read(bound)
            self.assertEqual(git.call_count, 1)

    def test_repo_mutation_reclassifies_path_instead_of_reusing_old_policy(self):
        path = self.repo/'file.json'
        bound = self.write(path)
        self.reader.extra.add(path)
        with self.assertRaisesRegex(ValueError, 'Unregistered historical production source'):
            self.reader.read(bound)
        self.reader.repo = self.home/'different-repo'
        self.assertEqual(self.reader.read(bound), {'synthetic': True})

    def test_fresh_resolve_regular_file_bytes_hash_and_json_every_read(self):
        path = self.owned()
        bound = self.write(path, {'generation': 1})
        observed = {'resolve': 0, 'is_file': 0, 'read_bytes': 0, 'json': 0}
        originals = {name: getattr(Path, name) for name in ('resolve', 'is_file', 'read_bytes')}
        original_json = history.e.strict_json
        def wrapped(name):
            def call(instance, *args, **kwargs):
                if instance == path:
                    observed[name] += 1
                return originals[name](instance, *args, **kwargs)
            return call
        def decode(*args, **kwargs):
            observed['json'] += 1
            return original_json(*args, **kwargs)
        with ExitStack() as stack:
            for name in originals:
                stack.enter_context(patch.object(Path, name, wrapped(name)))
            stack.enter_context(patch.object(history.e, 'strict_json', side_effect=decode))
            self.assertEqual(self.reader.read(bound), {'generation': 1})
            self.assertEqual(self.reader.read(bound), {'generation': 1})
        self.assertEqual(observed, {'resolve': 2, 'is_file': 2, 'read_bytes': 2, 'json': 2})
        path.write_text('{"generation": 2}')
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            self.reader.read(bound)
        self.assertEqual(self.reader.read(self.bound(path)), {'generation': 2})
        path.write_bytes(b'not-json')
        with self.assertRaises(ValueError):
            self.reader.read(self.bound(path))

    def test_repeated_read_detects_symlink_replacement_and_missing_file(self):
        path = self.owned()
        bound = self.write(path)
        self.reader.read(bound)
        target = self.home/'target.json'
        target.write_bytes(path.read_bytes())
        path.unlink(); path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Canonical non-symlink'):
            self.reader.read(bound)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing original'):
            self.reader.read(bound)

    def test_boundary_alias_directory_and_noncanonical_bindings_stay_refused(self):
        good = self.owned()
        bound = self.write(good)
        variants = [dict(bound, path=str(good.parent.parent/(self.ident+'-foreign')/'value.json')),
                    dict(bound, path=str(good.parent/'..'/self.ident/'value.json')),
                    dict(bound, path='relative/value.json')]
        for value in variants:
            with self.subTest(path=value['path']), self.assertRaises(ValueError):
                self.reader.read(value)
        directory = good.parent/'directory'
        directory.mkdir()
        with self.assertRaisesRegex(ValueError, 'Missing original'):
            self.reader.read({'path': str(directory), 'sha256': '0'*64})
        with self.assertRaisesRegex(ValueError, 'Exact original binding'):
            self.reader.read(dict(bound, extra='not accepted'))

    def test_foreign_file_is_not_read_when_containment_refuses_it(self):
        path = self.home/'not-owned/original.json'
        bound = self.write(path)
        self.reader._allowed_parts()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Foreign bytes must not open')):
            with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
                self.reader.read(bound)


if __name__ == '__main__':
    unittest.main()
