"""Synthetic immutable Git bytes; no Git command, history, model or real ledger.

The original LRU and Reader validators are used. Only subprocess output is
invented. The final test reuses the existing temporary runtime/SQLite fixture;
its source/admission/resident seams do not prove real admission or wall benefit.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import earnings_population_continuation as history
import earnings_population_runtime as runtime
import test_earnings_population_runtime as runtime_tests


class GitCacheCapacity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.repo = self.home / 'repo'
        self.root = self.home / 'owned'
        self.commit = 'a' * 40
        self.overrides, self.missing = {}, set()
        history._git.cache_clear()
        self.addCleanup(history._git.cache_clear)
        mocked = patch.object(history.subprocess, 'run', side_effect=self.git_bytes)
        self.run = mocked.start()
        self.addCleanup(mocked.stop)

    def git_bytes(self, command, *, cwd, check, capture_output):
        self.assertEqual(command[:2], ['git', 'show'])
        self.assertEqual(len(command), 3)
        self.assertIs(check, True)
        self.assertIs(capture_output, True)
        commit, name = command[2].split(':', 1)
        key = (cwd, commit, name)
        if key in self.missing:
            raise subprocess.CalledProcessError(128, command, stderr=b'synthetic missing object')
        raw = self.overrides.get(key, json.dumps(dict(repo=str(cwd), commit=commit, name=name)).encode())
        return SimpleNamespace(stdout=raw)

    def reader(self, commit, bound):
        reader = history._Reader(self.root, self.home / 'inert.sqlite3', self.repo,
                                 'edgar-population-20261016-10')
        reader.register_sources(dict(source_commit=commit, sources={'synthetic': bound}))
        return reader

    def source(self, name='tools/synthetic.py', *, commit=None, raw=b'{"original":true}'):
        commit = self.commit if commit is None else commit
        self.overrides[(self.repo, commit, name)] = raw
        return dict(path=str(self.repo / name), sha256=hashlib.sha256(raw).hexdigest())

    def test_2163_immutable_keys_repeat_identical_without_repeat_subprocesses(self):
        self.assertEqual(history._git.cache_parameters(), dict(maxsize=4096, typed=False))
        names = [f'tools/synthetic_{number:04d}.py' for number in range(2163)]
        first = [history._git(self.repo, self.commit, name) for name in names]
        self.assertEqual(self.run.call_count, 2163)
        self.assertEqual([history._git(self.repo, self.commit, name) for name in names], first)
        self.assertEqual(self.run.call_count, 2163)
        self.assertEqual(history._git.cache_info()._asdict(),
                         dict(hits=2163, misses=2163, maxsize=4096, currsize=2163))

    def test_repo_commit_and_path_remain_distinct_keys(self):
        keys = [(self.repo, self.commit, 'a.py'),
                (self.home / 'other-repo', self.commit, 'a.py'),
                (self.repo, 'b' * 40, 'a.py'),
                (self.repo, self.commit, 'b.py')]
        values = [history._git(*key) for key in keys]
        self.assertEqual(len(set(values)), 4)
        self.assertEqual([history._git(*key) for key in keys], values)
        self.assertEqual(self.run.call_count, 4)

    def test_capacity_remains_bounded_with_original_lru_eviction(self):
        for number in range(4096):
            history._git(self.repo, self.commit, str(number))
        history._git(self.repo, self.commit, '0')
        history._git(self.repo, self.commit, '4096')
        history._git(self.repo, self.commit, '0')
        self.assertEqual(self.run.call_count, 4097)
        history._git(self.repo, self.commit, '1')  # Oldest untouched entry was evicted.
        self.assertEqual(self.run.call_count, 4098)
        self.assertEqual(history._git.cache_info().currsize, 4096)

    def test_missing_subprocess_object_error_is_not_cached(self):
        key = (self.repo, self.commit, 'missing.py')
        self.missing.add(key)
        for _ in range(2):  # Two invented calls, not an operational retry.
            with self.assertRaises(subprocess.CalledProcessError):
                history._git(*key)
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(history._git.cache_info().currsize, 0)

    def test_warm_git_still_checks_bound_hash_and_source_registration(self):
        bound = self.source()
        reader = self.reader(self.commit, bound)
        self.assertEqual(reader.read(bound), {'original': True})
        forged = dict(bound, sha256='0' * 64)
        other = self.reader(self.commit, forged)
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            other.read(forged)  # Warm real LRU bytes, not a mocked Reader result.
        reader.sources.clear()
        with self.assertRaisesRegex(ValueError, 'Unregistered'):
            reader.read(bound)
        self.assertEqual(self.run.call_count, 1)

    def test_warm_reader_still_checks_current_namespace(self):
        bound = self.source()
        reader = self.reader(self.commit, bound)
        reader.read(bound)
        reader.repo = self.home / 'different-repo'
        with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
            reader.read(bound)
        self.assertEqual(self.run.call_count, 1)

    def test_changed_commit_clears_reader_bytes_and_rechecks_hash(self):
        bound = self.source()
        reader = self.reader(self.commit, bound)
        reader.read(bound)
        new_commit = 'b' * 40
        newer = self.source(commit=new_commit, raw=b'{"original":false}')
        reader.register_sources(dict(source_commit=new_commit, sources={'synthetic': bound}))
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            reader.read(bound)
        reader.register_sources(dict(source_commit=new_commit, sources={'synthetic': newer}))
        self.assertEqual(reader.read(newer), {'original': False})
        self.assertEqual(self.run.call_count, 2)


class WarmHistoricalCacheCurrentSource(runtime_tests.Fixture):
    def test_current_source_same_size_restored_mtime_tamper_remains_refused(self):
        history._git.cache_clear()
        self.addCleanup(history._git.cache_clear)
        bound = self.bound()
        runtime.preflight(bound)  # Original inert admission, temporary ledger only.
        source_bound = self.source_bindings[runtime.PLAN]
        source = Path(source_bound['path'])
        raw, stat = source.read_bytes(), source.stat()
        reader = history._Reader(self.owned, self.ledger, self.repo, self.id)
        reader.register_sources(dict(source_commit=self.commit, sources=self.source_bindings))
        with patch.object(history.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)) as git:
            self.assertEqual(reader.read(source_bound, binary=True), raw)
            changed = raw.replace(b'plan_v1', b'plan_v2', 1)
            self.assertNotEqual(changed, raw)
            self.assertEqual(len(changed), len(raw))
            source.write_bytes(changed)
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            # Historical Git bytes deliberately stay original; they are not
            # authority for fresh current Source admission.
            self.assertEqual(reader.read(source_bound, binary=True), raw)
            with self.assertRaises(ValueError):
                runtime.preflight(bound)
            self.assertEqual(git.call_count, 1)


if __name__ == '__main__':
    unittest.main()
