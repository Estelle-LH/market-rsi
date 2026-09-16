import copy
import unittest
from prepare_source_study_revision_workspace import merge_findings


class RevisionFindingTests(unittest.TestCase):
    def test_repeated_revision_keeps_history_unique_and_unmodified(self):
        parent=[{"id":"source", "value":1}, {"id":"review", "value":"old"}]
        before=copy.deepcopy(parent)
        first=merge_findings(parent,[{"id":"review","value":"new"}],"manifest-a")
        second=merge_findings(first,[{"id":"review","value":"newer"}],"manifest-b")
        self.assertEqual(parent,before)
        self.assertEqual(len(second),4)
        self.assertEqual(len({f["id"] for f in second}),4)
        self.assertEqual([f["value"] for f in second],[1,"old","new","newer"])
        self.assertEqual(second[1]["historical_parent_manifest_sha256"],"manifest-a")
        self.assertEqual(second[2]["historical_finding_id"],"review")

    def test_corrupt_parent_and_collision_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"parent findings"):
            merge_findings([{"id":"x"},{"id":"x"}],[],"p")
        with self.assertRaisesRegex(ValueError,"new findings"):
            merge_findings([],[{"id":"x"},{"id":"x"}],"p")
        with self.assertRaisesRegex(ValueError,"collision"):
            merge_findings([{"id":"x"},{"id":"history:p:x"}],[{"id":"x"}],"p")


if __name__=="__main__":unittest.main()
