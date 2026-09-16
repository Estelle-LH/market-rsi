import unittest
from unittest.mock import patch
import capture_shadow_pilot as pilot


class PilotTests(unittest.TestCase):
    def test_fixed_scope_no_admission_and_memory_cap(self):
        with patch.object(pilot, 'EXPECTED_SOURCE', 'fixture', create=True), \
             patch.object(pilot, 'read_prefix', return_value=([], {'source_sha256': 'fixture'}), create=True), \
             patch.object(pilot, 'profile', return_value={}, create=True), \
             patch.object(pilot, 'legacy', return_value={}, create=True), \
             patch.object(pilot, 'shadow', return_value=([], {}), create=True), \
             patch.object(pilot, 'summarize', return_value={}, create=True), \
             patch.object(pilot.Path, 'read_bytes', return_value=b'fixture'), \
             patch.object(pilot.resource, 'setrlimit') as limits:
            result = pilot.run_pilot()
            self.assertEqual(pilot.MAX_RECORDS, 50000)
            self.assertEqual(limits.call_args.args[1], (512*1024*1024,)*2)
            self.assertFalse(result['source_admitted'])
            self.assertFalse(result['full_requested_capability_implemented'])

    def test_changed_source_stops_before_interpreting_prices(self):
        with patch.object(pilot, 'EXPECTED_SOURCE', 'fixture', create=True), \
             patch.object(pilot, 'read_prefix', return_value=([], {'source_sha256': 'changed'}), create=True), \
             patch.object(pilot, 'profile', create=True) as profile, \
             patch.object(pilot.resource, 'setrlimit'):
            with self.assertRaisesRegex(ValueError, 'source changed'): pilot.run_pilot()
            profile.assert_not_called()


if __name__ == '__main__': unittest.main()
