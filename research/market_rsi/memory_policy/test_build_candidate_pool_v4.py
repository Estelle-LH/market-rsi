from __future__ import annotations

import unittest

from memory_policy.build_candidate_pool_v4 import GROUPS


class BuildCandidatePoolV4Tests(unittest.TestCase):
    def test_fresh_chronological_roles_and_four_final_dates(self):
        sessions = [session for group in GROUPS for session, _ in group["candidates"]]
        self.assertEqual(len(sessions), len(set(sessions)))
        self.assertEqual(GROUPS[0]["role"], "initial_train")
        self.assertEqual(GROUPS[1]["role"], "dev")
        self.assertTrue(all(group["role"] == "final" for group in GROUPS[2:]))
        self.assertLess(
            max(session for session, _ in GROUPS[0]["candidates"]),
            min(session for session, _ in GROUPS[1]["candidates"]),
        )
        self.assertLess(
            max(session for session, _ in GROUPS[1]["candidates"]),
            min(session for group in GROUPS[2:] for session, _ in group["candidates"]),
        )
        self.assertEqual(sum(group["required"] for group in GROUPS[2:]), 20)
        self.assertEqual(
            {session[:10] for group in GROUPS[2:] for session, _ in group["candidates"]},
            {"2026-09-11", "2026-09-12", "2026-09-13", "2026-09-14"},
        )


if __name__ == "__main__":
    unittest.main()
