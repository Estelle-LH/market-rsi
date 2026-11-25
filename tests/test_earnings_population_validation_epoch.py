"""Inert validation snapshots: original checks, fewer duplicate filesystem reads.

Temporary JSON/Git/ledger fixtures only; no historical replay, HTTP or model code.
"""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_continuation as history
import earnings_population_runtime as runtime
import test_earnings_population_runtime as original_runtime_tests


class EpochReaderContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.root, self.repo = self.home/'owned', self.home/'repo'
        self.ledger = self.home/'api-budget.sqlite3'
        self.ident = 'edgar-population-20261016-10'
        self.reader = self.new_reader()
        self.path = self.root/'attempts'/self.ident/'historical.json'
        self.bound = self.save(self.path, {'values': [1], 'original': True})

    def new_reader(self):
        return history._Reader(self.root, self.ledger, self.repo, self.ident)

    def save(self, path, value=None, *, raw=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(value).encode() if raw is None else raw)
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def counts(self, path):
        counts = dict(resolve=0, is_file=0, read_bytes=0, json=0)
        original = {key: getattr(Path, key) for key in ('resolve', 'is_file', 'read_bytes')}
        decode = history.e.strict_json
        stack = ExitStack(); self.addCleanup(stack.close)
        def wrapped(name):
            def call(instance, *args, **kwargs):
                if instance == path: counts[name] += 1
                return original[name](instance, *args, **kwargs)
            return call
        def parsed(raw):
            counts['json'] += 1
            return decode(raw)
        for key in original: stack.enter_context(patch.object(Path, key, wrapped(key)))
        stack.enter_context(patch.object(history.e, 'strict_json', side_effect=parsed))
        return counts

    def test_nested_readers_keep_semantic_calls_but100reads_become_first_and_final(self):
        counts = self.counts(self.path)
        other = self.new_reader()
        with history.validation_epoch():
            active = history._VALIDATION_EPOCH.get()
            for _ in range(50):
                value = self.reader.read(self.bound); value['values'].append('not cached')
                with history.validation_epoch():
                    self.assertIs(history._VALIDATION_EPOCH.get(), active)
                    self.assertEqual(other.read(self.bound)['values'], [1])
            self.assertEqual(counts, dict(resolve=1, is_file=1, read_bytes=1, json=1))
        self.assertEqual(counts, dict(resolve=2, is_file=2, read_bytes=2, json=1))
        self.assertIsNone(history._VALIDATION_EPOCH.get())

    def test_default_no_epoch_keeps_original_fresh_read_and_json_contract(self):
        counts = self.counts(self.path)
        for _ in range(3): self.reader.read(self.bound)
        self.assertEqual(counts, dict(resolve=3, is_file=3, read_bytes=3, json=3))

    def test_next_epoch_revalidates_instead_of_reusing_old_snapshot(self):
        counts = self.counts(self.path)
        for _ in range(2):
            with history.validation_epoch(): self.reader.read(self.bound)
        self.assertEqual(counts, dict(resolve=4, is_file=4, read_bytes=4, json=2))
        self.path.write_text('{"values": [2], "original": true}')
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            with history.validation_epoch(): self.reader.read(self.bound)

    def test_namespace_ids_extra_and_repo_are_fresh_before_hit(self):
        with history.validation_epoch():
            self.reader.read(self.bound)
            self.reader.ids.clear()
            with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
                self.reader.read(self.bound)
            self.reader.extra.add(self.path)
            self.assertEqual(self.reader.read(self.bound)['values'], [1])
            self.reader.extra.clear()
            with self.assertRaises(ValueError): self.reader.read(self.bound)
            self.reader.ids.add(self.ident)
            self.reader.repo = self.root
            with self.assertRaisesRegex(ValueError, 'Unregistered historical production source'):
                self.reader.read(self.bound)

    def test_cached_path_is_not_authority_for_a_different_reader(self):
        with history.validation_epoch():
            self.reader.read(self.bound)
            other = self.new_reader(); other.ids.clear()
            with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
                other.read(self.bound)

    def test_persistent_same_size_restored_mtime_tamper_refused_at_exit(self):
        original = self.path.read_bytes(); stat = self.path.stat()
        changed = original.replace(b'[1]', b'[2]'); self.assertEqual(len(changed), len(original))
        with self.assertRaisesRegex(ValueError, 'epoch exit'):
            with history.validation_epoch():
                self.reader.read(self.bound)
                self.path.write_bytes(changed)
                os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                self.assertEqual(self.reader.read(self.bound)['values'], [1])
        self.assertIsNone(history._VALIDATION_EPOCH.get())

    def test_deleted_symlink_and_nonregular_file_refused_before_successful_exit(self):
        for mutation in ('deleted', 'symlink', 'directory'):
            bound = self.save(self.path, {'values': [1]})
            target = self.home/'same-content.json'; target.write_bytes(self.path.read_bytes())
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with history.validation_epoch():
                    self.reader.read(bound); self.path.unlink()
                    if mutation == 'symlink': self.path.symlink_to(target)
                    elif mutation == 'directory': self.path.mkdir()
            if self.path.is_symlink(): self.path.unlink()
            elif self.path.is_dir(): self.path.rmdir()

    def test_baseexceptions_reset_even_nested_epoch_and_failed_epoch_is_not_reused(self):
        for error in (KeyboardInterrupt, SystemExit):
            with self.subTest(error=error.__name__), self.assertRaises(error):
                with history.validation_epoch():
                    with history.validation_epoch():
                        self.reader.read(self.bound); raise error('synthetic')
            self.assertIsNone(history._VALIDATION_EPOCH.get())
        self.path.write_text('changed')
        with self.assertRaises(ValueError):
            with history.validation_epoch(): self.reader.read(self.bound)

    def test_binary_then_json_deepcopy_and_bad_json_exception_not_cached(self):
        with history.validation_epoch():
            raw = self.reader.read(self.bound, binary=True)
            first = self.reader.read(self.bound); first['values'].append(2)
            self.assertEqual(self.reader.read(self.bound)['values'], [1])
            self.assertEqual(raw, self.reader.read(self.bound, binary=True))
        malformed = self.save(self.path, raw=b'not-json'); counts = self.counts(self.path)
        with history.validation_epoch():
            self.reader.read(malformed, binary=True)
            for _ in range(2):
                with self.assertRaises(ValueError): self.reader.read(malformed)
        self.assertEqual(counts['json'], 2)

    def test_binding_shape_hash_and_canonical_alias_not_bypassed_by_hit(self):
        with history.validation_epoch():
            self.reader.read(self.bound)
            for bound in (dict(self.bound, sha256='0'*64), dict(self.bound, extra=True),
                          dict(self.bound, path=str(self.path.parent/'..'/self.ident/self.path.name))):
                with self.subTest(bound=bound), self.assertRaises(ValueError): self.reader.read(bound)

    def test_conflicting_hashes_for_one_path_cannot_both_pass_epoch_exit(self):
        with self.assertRaisesRegex(ValueError, 'epoch exit'):
            with history.validation_epoch():
                self.reader.read(self.bound)
                second = self.save(self.path, {'new': True})
                self.assertEqual(self.reader.read(second), {'new': True})

    def test_sources_keep_original_git_path_and_fresh_registration(self):
        source = self.repo/'historical.json'; bound = self.save(source, {'source': True})
        self.reader.commit = 'a'*40; self.reader.sources = {(str(source), bound['sha256'])}
        with patch.object(history, '_git', return_value=source.read_bytes()) as git:
            with history.validation_epoch():
                self.reader.read(bound); self.reader.read(bound)
                self.assertEqual(history._VALIDATION_EPOCH.get().entries, {})
                self.reader.sources.clear()
                with self.assertRaisesRegex(ValueError, 'Unregistered'): self.reader.read(bound)
            self.assertEqual(git.call_count, 1)  # Existing Reader source cache only.

    def test_clock_budget_ledger_claim_and_owner_reads_are_never_cached(self):
        names = ['clock.json', 'clock.binding.json', 'budget-summary.json', 'ledger.json',
                 'owner.json', 'round-0001-input.claim.json', 'claim.json']
        paths = [self.path.parent/name for name in names]
        paths += [self.home/'.capacity-runtime-claims'/'opaque-id.result.json', self.ledger]
        for path in paths:
            bound = self.save(path, {'dynamic': 1}); self.reader.extra.add(path)
            with self.subTest(path=path), history.validation_epoch():
                self.reader.read(bound); self.assertEqual(history._VALIDATION_EPOCH.get().entries, {})
                path.write_text('{"dynamic": 2}')
                with self.assertRaisesRegex(ValueError, 'hash differs'): self.reader.read(bound)

    def test_saturation_falls_back_to_original_reads_without_new_admission_failure(self):
        counts = self.counts(self.path)
        with patch.object(history, '_EPOCH_MAX_BYTES', 0), history.validation_epoch():
            for _ in range(3): self.assertEqual(self.reader.read(self.bound)['values'], [1])
            self.assertEqual(history._VALIDATION_EPOCH.get().entries, {})
        self.assertEqual(counts, dict(resolve=3, is_file=3, read_bytes=3, json=3))

    def test_scan_still_traverses_and_reads_all_bindings(self):
        with patch.object(self.reader, 'read', wraps=self.reader.read) as read:
            with history.validation_epoch():
                for _ in range(10): self.reader.scan({'a': [self.bound, {'b': self.bound}]})
            self.assertEqual(read.call_count, 20)


class EpochPreflightContracts(original_runtime_tests.Fixture):
    def test_original_preflight_reuses_historical_reads_but_checks_ledger_each_call(self):
        path = self.root/'inert-history.json'; bound = original_runtime_tests.save(path, {'history': 1})
        reader = history._Reader(self.owned, self.ledger, self.repo, self.id)
        original_study = runtime._study
        def study(value):
            for _ in range(20): self.assertEqual(reader.read(bound), {'history': 1})
            return original_study(value)
        with patch.object(runtime, '_study', side_effect=study), patch.object(runtime, '_ledger', wraps=runtime._ledger) as ledger:
            self.assertEqual(runtime.preflight(self.bound())['id'], self.id)
            self.assertEqual(runtime.preflight(self.bound())['id'], self.id)
            self.assertEqual(ledger.call_count, 2)
            self.db.execute('UPDATE config SET blocked=1'); self.db.commit()
            with self.assertRaises(runtime.BudgetStop): runtime.preflight(self.bound())
            self.assertEqual(ledger.call_count, 3)
        self.assertIsNone(history._VALIDATION_EPOCH.get())

    def test_changed_current_source_remains_fresh_between_epochs(self):
        bound = self.bound(); runtime.preflight(bound)
        source = Path(self.source_bindings[runtime.PLAN]['path']); source.write_text('changed source')
        with self.assertRaises(ValueError): runtime.preflight(bound)
        self.assertIsNone(history._VALIDATION_EPOCH.get())

    def test_current_cutoff_remains_fresh_between_epochs(self):
        bound = self.bound(); runtime.preflight(bound)
        runtime.time.time.return_value = self.now + 5401
        with self.assertRaises(runtime.BudgetStop): runtime.preflight(bound)
        self.assertIsNone(history._VALIDATION_EPOCH.get())

    def test_preflight_cannot_return_success_before_final_rehash(self):
        path = self.root/'inert-history.json'; bound = original_runtime_tests.save(path, {'history': 1})
        reader = history._Reader(self.owned, self.ledger, self.repo, self.id)
        def body(*args, **kwargs):
            reader.read(bound); path.write_text('{"history": 2}')
            return {'would_have_succeeded': True}
        delivered = False
        with patch.object(runtime, '_preflight', side_effect=body):
            with self.assertRaisesRegex(ValueError, 'epoch exit'):
                runtime.preflight({'inert_wrapper_test': True}); delivered = True
        self.assertFalse(delivered); self.assertIsNone(history._VALIDATION_EPOCH.get())


if __name__ == '__main__': unittest.main()
