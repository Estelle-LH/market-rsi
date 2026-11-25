"""Actual native external occupancy, no forecasts/fits/providers."""
from datetime import timedelta
import json
import unittest

import test_earnings_capacity_adapter as fixture
from market_rsi import digest
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch


class CapacityWorkTests(unittest.TestCase):
    def setUp(self):
        self.native = fixture.EarningsCapacityTests('test_earnings_reject_keeps_parent_and_history')
        self.native.setUp(); self.addCleanup(self.native.doCleanups)
        self.batch = self.native.batch
        self.pair = digest(self.batch.snapshot()['micro_evolution']['active_pair'])

    def record(self, action, work='test-work', **kwargs):
        args = dict(work_id=work, pair_sha256=self.pair, evidence_sha256='a'*64,
                    expected_state_sha256=self.batch.snapshot()['state_sha256'])
        args.update(kwargs)
        return self.batch.record_capacity_work(action, **args)

    def test_success_native_claim_cold_restore_and_zero_fake_fit(self):
        before = self.batch.snapshot()
        self.assertNotIn('capacity_work', before)
        claimed = self.record('claim')
        cold = ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True,
            test_clock=lambda: fixture.BASE, allow_test_clock=True)
        self.assertEqual(cold.snapshot(), claimed)
        self.assertEqual(claimed['active_attempt_ids'], ['test-work'])
        closed = self.record('complete')
        self.assertEqual(closed['active_attempt_ids'], [])
        self.assertEqual(closed['capacity_work'][0]['status'], 'completed')
        self.assertEqual(closed['capacity_work'][0],dict(claimed['capacity_work'][0],
            status='completed',output_evidence_sha256='a'*64,
            completed_at_utc=claimed['capacity_work'][0]['event_time_utc']))
        self.assertNotIn('failure_evidence_sha256',closed['capacity_work'][0])
        self.assertNotIn('failed_at_utc',closed['capacity_work'][0])
        self.assertEqual((closed['attempts_claimed'], closed['branches']),
                         (before['attempts_claimed'], before['branches']))

    def test_bad_or_duplicate_requests_do_not_append_and_do_not_refund(self):
        for kwargs in ({'pair_sha256': 'b'*64}, {'expected_state_sha256': 'c'*64}):
            before = self.batch.snapshot()
            with self.assertRaises(ValueError): self.record('claim', **kwargs)
            self.assertEqual(self.batch.snapshot(), before)
        self.record('claim'); self.record('complete')
        before = self.batch.snapshot()
        for action in ('claim', 'complete'):
            with self.assertRaises(ValueError): self.record(action)
            self.assertEqual(self.batch.snapshot(), before)

    def test_uncertain_claim_survives_restart_and_blocks_new_work(self):
        claimed = self.record('claim')
        self.assertEqual(self.native.restore().batch.snapshot(), claimed)
        with self.assertRaisesRegex(ValueError, 'busy'): self.record('claim', 'new-work')
        self.assertEqual(self.batch.snapshot(), claimed)

    def test_backward_time_deadline_and_finite_claim_ceiling(self):
        self.record('claim', now=fixture.BASE+timedelta(seconds=1))
        before = self.batch.snapshot()
        with self.assertRaisesRegex(ValueError, 'backward'): self.record('complete', now=fixture.BASE)
        self.assertEqual(self.batch.snapshot(), before)
        self.record('complete', now=fixture.BASE+timedelta(seconds=1))
        for n in (2, 3):
            self.record('claim', f'work-{n}', now=fixture.BASE+timedelta(seconds=n))
            self.record('complete', f'work-{n}', now=fixture.BASE+timedelta(seconds=n))
        before = self.batch.snapshot()
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            self.record('claim', 'work-4', now=fixture.BASE+timedelta(seconds=4))
        self.assertEqual(self.batch.snapshot(), before)

    def journal_bytes(self):
        return {path.name:path.read_bytes() for path in self.batch.journal_dir.glob('*.json')}

    def test_failed_terminal_releases_only_work_preserves_pending_parent_and_journal_prefix(self):
        self.native.propose('R')
        claimed=self.record('claim')
        prefix=self.journal_bytes()
        closed=self.record('fail',evidence_sha256='b'*64)
        self.assertEqual(closed['active_attempt_ids'],[])
        self.assertEqual(closed['capacity_work'][0],dict(claimed['capacity_work'][0],
            status='failed',failure_evidence_sha256='b'*64,
            failed_at_utc=claimed['capacity_work'][0]['event_time_utc']))
        self.assertNotIn('output_evidence_sha256',closed['capacity_work'][0])
        self.assertNotIn('completed_at_utc',closed['capacity_work'][0])
        changed={'active_attempt_ids','capacity_work','journal_length','journal_head_sha256','state_sha256'}
        self.assertEqual({k:v for k,v in claimed.items() if k not in changed},
            {k:v for k,v in closed.items() if k not in changed})
        self.assertIsNotNone(closed['micro_evolution']['pending'])
        self.assertEqual(closed['micro_evolution']['active_pair'],claimed['micro_evolution']['active_pair'])
        self.assertEqual(len(closed['capacity_work']),1)
        for name,raw in prefix.items():self.assertEqual(self.journal_bytes()[name],raw)
        terminal=json.loads(self.journal_bytes()[sorted(self.journal_bytes())[-1]])
        self.assertEqual(terminal['event'],'capacity_work_failed')
        self.assertEqual(terminal['payload'],{'work_id':'test-work','pair_sha256':self.pair,
            'evidence_sha256':'b'*64,'event_time_utc':closed['capacity_work'][0]['failed_at_utc']})

    def test_failed_cold_replay_from_missing_and_claimed_prefix_snapshot_is_exact(self):
        self.record('claim')
        prefix_snapshot=self.batch.snapshot_path.read_bytes()
        closed=self.record('fail',evidence_sha256='b'*64)
        final_snapshot=self.batch.snapshot_path.read_bytes()
        prefix=self.journal_bytes()
        for snapshot in (prefix_snapshot,None):
            if snapshot is None:self.batch.snapshot_path.unlink()
            else:self.batch.snapshot_path.write_bytes(snapshot)
            cold=ContinuousDiscoveryBatch(self.batch.root,allow_temporary=True,
                test_clock=lambda:fixture.BASE,allow_test_clock=True)
            self.assertEqual(cold.snapshot(),closed)
            self.assertEqual(cold.snapshot_path.read_bytes(),final_snapshot)
            self.assertEqual(self.journal_bytes(),prefix)

    def test_fail_before_claim_wrong_identity_pair_stale_and_repeat_do_not_append(self):
        before=self.batch.snapshot(); journal=self.journal_bytes()
        with self.assertRaisesRegex(ValueError,'exact active claim'):self.record('fail')
        self.assertEqual(self.batch.snapshot(),before);self.assertEqual(self.journal_bytes(),journal)
        claimed=self.record('claim'); journal=self.journal_bytes()
        for work,kwargs in (('other-work',{}),('test-work',{'pair_sha256':'c'*64}),
                ('test-work',{'expected_state_sha256':before['state_sha256']}),
                ('test-work',{'evidence_sha256':'not-a-digest'})):
            with self.subTest(work=work,kwargs=kwargs),self.assertRaises(ValueError):
                self.record('fail',work,**kwargs)
            self.assertEqual(self.batch.snapshot(),claimed);self.assertEqual(self.journal_bytes(),journal)
        closed=self.record('fail');journal=self.journal_bytes()
        for action in ('fail','complete','claim'):
            with self.subTest(action=action),self.assertRaises(ValueError):self.record(action)
            self.assertEqual(self.batch.snapshot(),closed);self.assertEqual(self.journal_bytes(),journal)

    def test_three_failed_claims_consume_finite_capacity_without_refund_or_adoption(self):
        before=self.batch.snapshot()
        for n in (1,2,3):
            moment=fixture.BASE+timedelta(seconds=n)
            self.record('claim',f'failed-{n}',now=moment)
            closed=self.record('fail',f'failed-{n}',now=moment)
        self.assertEqual([row['status'] for row in closed['capacity_work']],['failed']*3)
        self.assertEqual(len(closed['capacity_work']),closed['max_attempts'])
        self.assertEqual(closed['attempts_claimed'],before['attempts_claimed'])
        self.assertEqual(closed['failed_attempts'],before['failed_attempts'])
        self.assertEqual(closed['micro_evolution'],before['micro_evolution'])
        self.assertEqual(closed['incumbent_history'],before['incumbent_history'])
        with self.assertRaisesRegex(ValueError,'exhausted'):
            self.record('claim','fourth',now=fixture.BASE+timedelta(seconds=4))
        self.assertEqual(self.native.restore().batch.snapshot(),closed)

    def test_known_failure_may_close_after_deadline_but_cannot_backdate_or_reopen(self):
        self.record('claim',now=fixture.BASE+timedelta(seconds=1))
        claimed=self.batch.snapshot();prefix=self.journal_bytes()
        with self.assertRaisesRegex(ValueError,'backward'):self.record('fail',now=fixture.BASE)
        self.assertEqual(self.batch.snapshot(),claimed);self.assertEqual(self.journal_bytes(),prefix)
        later=fixture.BASE+timedelta(hours=2)
        closed=self.record('fail',now=later)
        self.assertEqual(closed['capacity_work'][0]['status'],'failed')
        self.assertEqual(closed['active_attempt_ids'],[])
        with self.assertRaisesRegex(ValueError,'deadline'):self.record('claim','new-work',now=later)
        self.assertEqual(self.batch.snapshot(),closed)

    def test_legacy_success_journal_replays_byte_exact_without_failed_fields(self):
        self.record('claim')
        closed=self.record('complete');snapshot=self.batch.snapshot_path.read_bytes()
        records=self.journal_bytes()
        self.assertFalse(any(b'capacity_work_failed' in raw for raw in records.values()))
        self.batch.snapshot_path.unlink()
        cold=ContinuousDiscoveryBatch(self.batch.root,allow_temporary=True,
            test_clock=lambda:fixture.BASE,allow_test_clock=True)
        self.assertEqual(cold.snapshot(),closed)
        self.assertEqual(cold.snapshot_path.read_bytes(),snapshot)
        self.assertEqual(self.journal_bytes(),records)


if __name__ == '__main__': unittest.main()
