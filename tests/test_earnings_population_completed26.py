"""Opt-in original26 continuation proof; no transport/candidate/scorer execution.

Only original file/SQLite/Git reads are permitted. The actual historical loader
and every admission/receipt/source/Native validator it invokes remain unmocked.
This is not a new live Controller or a prospective runtime approval.
"""
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
from earnings_population_delta_author import implementation_base
from earnings_population_roles import scientific
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_COMPLETED26') == '1',
                     'Root-only guarded original26 completed ancestry; no API/QA decode/writes')
class Actual26CompletedOrigin(unittest.TestCase):
    def test_exact_scored_feedback_and_pool_leave_reuse_routing_behind(self):
        tempfile.gettempdir()  # Resolve once before prohibiting filesystem writes.
        allowed = {'CIK0000003545', 'CIK0000004457', 'CIK0000017313'}
        original_resident = completed.tasks.resident
        qa_hashes = {original_resident(cik)['kernel']['qa']['sha256'] for cik in allowed}
        original_decode, original_connect = json.loads, sqlite3.connect
        original_run = subprocess.run
        counters = dict(file_opens=0, readonly_connections=0, git_reads=0, resident_calls=0)

        def resident(cik):
            if cik not in allowed:
                raise AssertionError('No nondevelopment company may be opened')
            counters['resident_calls'] += 1
            return original_resident(cik)

        def public_decode(raw, *args, **kwargs):
            value = raw.encode() if isinstance(raw, str) else raw
            if isinstance(value, (bytes, bytearray)) and hashlib.sha256(value).hexdigest() in qa_hashes:
                raise AssertionError('No protected QA decode')
            return original_decode(raw, *args, **kwargs)

        def readonly_open(function):
            def guarded(path, *args, **kwargs):
                mode = kwargs.get('mode', args[0] if args else 'r')
                if type(mode) is str and any(flag in mode for flag in 'wax+'):
                    raise AssertionError('No file writes')
                if type(mode) is int and mode & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                    raise AssertionError('No writable file descriptors')
                if not isinstance(path, int):
                    if set(re.findall(r'CIK[0-9]{10}', os.fsdecode(path))) - allowed:
                        raise AssertionError('No nondevelopment file opens')
                    counters['file_opens'] += 1
                return function(path, *args, **kwargs)
            return guarded

        def readonly_db(path, *args, **kwargs):
            if '?mode=ro' not in str(path) or kwargs.get('uri') is not True:
                raise AssertionError('Read-only SQLite URI required')
            counters['readonly_connections'] += 1
            return original_connect(path, *args, **kwargs)

        def git_read(command, *args, **kwargs):
            if not isinstance(command, list) or command[:2] != ['git', 'show']:
                raise AssertionError('Only original historical Git reads are allowed')
            counters['git_reads'] += 1
            return original_run(command, *args, **kwargs)

        binding = dict(
            path=str(completed.bootstrap.OWNED / 'attempts/edgar-population-20261016-26/population-run-result.json'),
            sha256='5875b9cb6a05682de0323fc1e15801ffd2c8aa15db92152fbc00cba436693533')
        started = time.monotonic()
        with ExitStack() as stack:
            stack.enter_context(patch.object(completed.tasks, 'resident', side_effect=resident))
            stack.enter_context(patch.object(json, 'loads', side_effect=public_decode))
            stack.enter_context(patch.object(sqlite3, 'connect', side_effect=readonly_db))
            stack.enter_context(patch.object(subprocess, 'run', side_effect=git_read))
            stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')))
            for module in (builtins, io, os):
                stack.enter_context(patch.object(module, 'open', readonly_open(module.open)))
            with completed.history.validation_epoch():
                origin = completed.load(binding, root=completed.bootstrap.OWNED,
                    ledger=completed.bootstrap.LEDGER, repo=completed.bootstrap.REPO)
            # This historical decision is only an eligibility input, not a new
            # Controller/Author dispatch. Scored26 cannot activate an old
            # rejected implementation base, even when its reference survives.
            prior_decision = scientific(engine.read(origin['research_feedback']['decision']))
            self.assertIsNone(implementation_base(prior_decision, None, origin['feedback'],
                                                  origin['reference_candidate']))

        self.assertEqual(origin['previous_result'], binding)
        self.assertEqual(origin['feedback']['sha256'],
                         'd208fa46f581feba16677f6d65caa3b8bb6c6f2e80750ca69961be76e106d2c2')
        self.assertEqual(origin['last_scored_feedback'], origin['feedback'])
        self.assertEqual(origin['research_feedback']['kind'], 'scored_dev')
        self.assertEqual([row['points'] for row in origin['research_feedback']['results']], [3, 3, 3])
        self.assertEqual(origin['population']['stable_id'],
                         '45dba7755f9137ced8db9fd57f611025f4d1237ee882fd651d931465b3074ec8')
        self.assertEqual(origin['population']['explorers'], [
            '11cebd96927bc57b5a8800769d5e6dfbaeb0ace8f6b8715456c6daabb7e1a127',
            '80d9428741890b72ab6bb91171e9a9e9118ead0e4a663ec933dd06b4495dfd40'])
        self.assertIn('29ac9cbd7166c6e83cb1866028485264d6649fcfe152da9414ec5c3b163742b3',
                      origin['population']['versions'])
        self.assertEqual(set(origin['population']['exposed_companies']), allowed)
        self.assertEqual(origin['research_feedback']['candidate']['id'],
                         '80d9428741890b72ab6bb91171e9a9e9118ead0e4a663ec933dd06b4495dfd40')
        historical_reference = origin['reference_candidate']
        self.assertEqual(historical_reference['id'],
                         '90c2d2e1fec67f0fd709adffc396c228dc5772811cdd5d22cb509c56f9c91643')
        self.assertIs(historical_reference['reference_only'], True)
        self.assertEqual(historical_reference['source_delivery'], 'paged_reference')
        self.assertNotIn(historical_reference['id'], origin['population']['versions'])
        for routing in ('author_stage_reuse', 'review_stage_reuse', 'controller_stage_import'):
            self.assertNotIn(routing, origin)
        self.assertTrue(origin.get('delivery_lessons'))
        self.assertTrue(counters['git_reads'])
        self.assertTrue(counters['readonly_connections'])
        print('ACTUAL26_GUARDED', json.dumps(dict(
            elapsed_seconds=time.monotonic()-started,
            pool_sha256=digest(origin['population']),
            latest_feedback=origin['feedback'], last_scored_feedback=origin['last_scored_feedback'],
            explorers=origin['population']['explorers'],
            scores=[row['points'] for row in origin['research_feedback']['results']],
            delivery_lesson_count=len(origin['delivery_lessons']),
            historical_rejected_reference_id=historical_reference['id'],
            latest_scored_candidate_id=origin['research_feedback']['candidate']['id'],
            scored_feedback_opens_rejected_implementation_base=False,
            active_reuse_routing=False, actual_new_Controller_called=False,
            **counters), sort_keys=True))


if __name__ == '__main__':
    unittest.main()
