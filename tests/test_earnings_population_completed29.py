"""Root-only original29 history proof, not a new inference or scored trial."""
from contextlib import ExitStack
import builtins
import hashlib
import io
import json
import os
import re
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import earnings_population_completed as completed
from earnings_population_broker import public_feedback
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_COMPLETED29') == '1',
                    'Root-only guarded completed29 replay; no API/QA decoding/writes')
class Actual29CompletedOrigin(unittest.TestCase):
    def test_original_completed_pool_feedback_scores_and_legacy_public_shape(self):
        tempfile.gettempdir()
        allowed = {'CIK0000003545', 'CIK0000004457', 'CIK0000017313'}
        original_resident = completed.tasks.resident
        qa_hashes = {original_resident(cik)['kernel']['qa']['sha256'] for cik in allowed}
        original_decode, original_connect = json.loads, sqlite3.connect
        original_run = subprocess.run
        counts = dict(file_opens=0, readonly_connections=0, git_reads=0, resident_calls=0)

        def resident(cik):
            if cik not in allowed:
                raise AssertionError('No nondevelopment resident')
            counts['resident_calls'] += 1
            return original_resident(cik)

        def public_decode(raw, *args, **kwargs):
            data = raw.encode() if isinstance(raw, str) else raw
            if isinstance(data, (bytes, bytearray)) and hashlib.sha256(data).hexdigest() in qa_hashes:
                raise AssertionError('No protected QA decode')
            return original_decode(raw, *args, **kwargs)

        def readonly_open(function):
            def guarded(path, *args, **kwargs):
                mode = kwargs.get('mode', args[0] if args else 'r')
                if type(mode) is str and any(flag in mode for flag in 'wax+'):
                    raise AssertionError('No historical writes')
                if type(mode) is int and mode & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                    raise AssertionError('No writable file descriptors')
                if not isinstance(path, int):
                    if set(re.findall(r'CIK[0-9]{10}', os.fsdecode(path))) - allowed:
                        raise AssertionError('No nondevelopment file opens')
                    counts['file_opens'] += 1
                return function(path, *args, **kwargs)
            return guarded

        def ro_db(path, *args, **kwargs):
            if '?mode=ro' not in str(path) or kwargs.get('uri') is not True:
                raise AssertionError('Read-only SQLite required')
            counts['readonly_connections'] += 1
            return original_connect(path, *args, **kwargs)

        def git_read(command, *args, **kwargs):
            if type(command) is not list or command[:2] != ['git', 'show']:
                raise AssertionError('Only original historical Git reads')
            counts['git_reads'] += 1
            return original_run(command, *args, **kwargs)

        root = completed.bootstrap.OWNED
        bound = dict(path=str(root/'attempts/edgar-population-20261016-29/population-run-result.json'),
            sha256='e17f64044ad9ed7c784656c81df7a3ea102555f5b023a23b2a6e2f71eff6635c')
        started = time.monotonic()
        with ExitStack() as stack:
            stack.enter_context(patch.object(completed.tasks, 'resident', side_effect=resident))
            stack.enter_context(patch.object(json, 'loads', side_effect=public_decode))
            stack.enter_context(patch.object(sqlite3, 'connect', side_effect=ro_db))
            stack.enter_context(patch.object(subprocess, 'run', side_effect=git_read))
            stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')))
            for module in (builtins, io, os):
                stack.enter_context(patch.object(module, 'open', readonly_open(module.open)))
            with completed.history.validation_epoch():
                origin = completed.load(bound, root=root, ledger=completed.bootstrap.LEDGER,
                    repo=completed.bootstrap.REPO)
            actual = engine.read(origin['feedback'])
            legacy = public_feedback(origin['feedback'], origin['population']['versions'])
        self.assertEqual(origin['previous_result'], bound)
        self.assertEqual(origin['feedback']['sha256'],
            'ed2df489037129d6816c675b5bc90a0f88d65838d99224ef8c4dc400cd1b7d58')
        self.assertEqual(origin['feedback'], origin['last_scored_feedback'])
        self.assertEqual(origin['research_feedback'], actual)
        self.assertEqual([r['points'] for r in actual['results']], [3, 3, 3.5])
        self.assertEqual([[t['points_awarded'] for t in r['target_scores']]
            for r in legacy['results']], [[1, 0, 1, 1, 0], [1, 0, 1, 1, 0], [1, 0, 1, 1, .5]])
        self.assertEqual(origin['population']['stable_id'],
            '45dba7755f9137ced8db9fd57f611025f4d1237ee882fd651d931465b3074ec8')
        self.assertEqual(origin['population']['explorers'], [
            '80d9428741890b72ab6bb91171e9a9e9118ead0e4a663ec933dd06b4495dfd40',
            '7633e4620d5a478333580d607706bb5944762beaada126230cf8bdaa213f8b2f'])
        self.assertEqual(digest(origin['population']),
            'c65becd90ec595a5ee8036117c818ba1194e72712d66d10cafeca79b5ce28549')
        for row in legacy['results']:
            self.assertNotIn('public_predictions', row)
        self.assertEqual(set(origin['population']['exposed_companies']), allowed)
        for key in ('author_stage_reuse', 'review_stage_reuse', 'controller_stage_import'):
            self.assertNotIn(key, origin)
        print('ACTUAL29_GUARDED', json.dumps(dict(seconds=time.monotonic()-started,
            pool_sha256=digest(origin['population']), feedback=origin['feedback'],
            scores=[r['points'] for r in actual['results']], legacy_projection_sha256=digest(legacy),
            new_API_calls=0, protected_QA_decoded=False, **counts), sort_keys=True))


if __name__ == '__main__':
    unittest.main()
