import unittest

from memory_policy.materialize_worker_v2 import validate_policy


POLICY = {
    "parent_address_space_bytes": 4 * 1024**3,
    "decoder_address_space_bytes": 256 * 1024**2,
    "max_decoded_bytes": 4 * 1024**3,
    "max_entities": 10000,
    "max_total_observations": 12000000,
    "max_entity_observations": 200000,
    "remote_wall_seconds": 2100,
    "remote_process_seconds": 2180,
    "local_transport_seconds": 2220,
}


class MaterializeWorkerV2Tests(unittest.TestCase):
    def test_exact_reviewed_policy(self):
        self.assertEqual(validate_policy(POLICY), POLICY)
        changed = dict(POLICY, max_total_observations=12000001)
        with self.assertRaises(ValueError):
            validate_policy(changed)


if __name__ == "__main__":
    unittest.main()
