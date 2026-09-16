from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from market_rsi import fresh_json,file_hash,load_json
from memory_pilot.broker import Broker,acquire_broker_lock
from memory_pilot.study import heldout_gate,arm_cost


class PolicyTests(unittest.TestCase):
    def make(self,tmp,archive):
        root=Path(tmp);(root/'records').mkdir();(root/'trials').mkdir()
        fresh_json(root/'config.json',dict(source_hashes={},public_context={'visible':'aggregate Train only'},
            baseline={},archive=archive,train=[]))
        return Broker(root,file_hash(root/'config.json'))

    def test_no_hidden_or_shell_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=self.make(tmp,[])
            for tool in ('read_final','read_file','exec','get_other_arm'):
                self.assertEqual(b.call(tool,{}).get('status'),'error')
            self.assertEqual(len(b.records()),4)

    def test_independent_archive_empty_and_single_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=self.make(tmp,[])
            self.assertEqual(b.call('read_archive',{'offset':0})['text'],'[]')
            self.assertTrue(b.call('submit_candidate',{'trial_id':'baseline','reason':'Keep explicit baseline.'})['submitted'])
            with self.assertRaises(ValueError):b.call('inspect_experiment',{})

    def test_archive_pagination_no_silent_omission(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=self.make(tmp,[{'note':'x'*15000}]);first=b.call('read_archive',{'offset':0})
            self.assertEqual(first['next_offset'],12000)
            second=b.call('read_archive',{'offset':12000})
            self.assertEqual(len(first['text']+second['text']),first['total'])
            self.assertIsNone(second['next_offset'])

    def test_config_and_ledger_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=self.make(tmp,[]);b.call('read_archive',{'offset':0})
            p=Path(tmp)/'records/0000.json'
            p.write_text(p.read_text().replace('read_archive','read_archivX'))
            with self.assertRaises(ValueError):b.records()

    def test_dev_requires_two_distinct_frozen_submissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a.json';c=root/'b.json';fresh_json(a,{'plan':'a'});fresh_json(c,{'plan':'b'})
            commits=[dict(path=str(p),sha256=file_hash(p)) for p in (a,c)]
            with self.assertRaises(FileNotFoundError):heldout_gate(root,'2026-08-29','dev',commits)
            (root/'round-1').mkdir();fresh_json(root/'round-1/paired-freeze.json',dict(commitments=commits,models=dict(archive='a',independent='b',baseline='c')))
            heldout_gate(root,'2026-08-29','dev',commits)
            with self.assertRaises(ValueError):heldout_gate(root,'2026-08-29','dev',[commits[0]]*2)
            with self.assertRaises(FileNotFoundError):heldout_gate(root,'2026-09-10','final',commits)

    def test_reserved_not_called_spent(self):
        snapshot={'jobs':{'pilot-turn-001':dict(state='metered_terminal',metered_usd='.2',uncertain_upper_usd=None,upper_usd='1'),
            'pilot-turn-002':dict(state='reserved',metered_usd=None,uncertain_upper_usd=None,upper_usd='1')}}
        r=arm_cost(snapshot,'pilot');self.assertEqual(float(r['metered_usd']),.2);self.assertEqual(float(r['outstanding_usd']),1)

    def test_adjacent_tool_call_waits_for_transient_lock_contention(self):
        lock=object()
        with patch('memory_pilot.broker.fcntl.flock',side_effect=[BlockingIOError(),None]) as flock, \
             patch('memory_pilot.broker.time.sleep') as sleep:
            acquire_broker_lock(lock,timeout=1,poll=.02)
        self.assertEqual(flock.call_count,2);sleep.assert_called_once_with(.02)

    def test_persistent_lock_contention_fails_bounded(self):
        with patch('memory_pilot.broker.fcntl.flock',side_effect=BlockingIOError()), \
             patch('memory_pilot.broker.time.monotonic',side_effect=[0,2]), \
             patch('memory_pilot.broker.time.sleep'):
            with self.assertRaises(TimeoutError):
                acquire_broker_lock(object(),timeout=1,poll=.02)


if __name__=='__main__':unittest.main()
