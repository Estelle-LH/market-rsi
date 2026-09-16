import copy
import unittest
from market_rsi import digest
from finding_aliases import alias_findings


class AliasTests(unittest.TestCase):
    def test_all_original_content_retained_without_mutation(self):
        values=[{"id":"history:"+"a"*64+":review","failed":True,"evidence":{"raw":"unchanged"}},
                {"id":"current-budget","budget":"not a charge"}]
        before=copy.deepcopy(values);result=alias_findings(values)
        self.assertEqual(values,before)
        self.assertEqual([r["id"] for r in result],["f001","f002"])
        self.assertEqual([r["source_finding"] for r in result],before)
        self.assertEqual([r["source_finding_sha256"] for r in result],[digest(v) for v in before])

    def test_content_hash_changes_even_when_display_ids_dont(self):
        one=alias_findings([{"id":"original","value":1}]);two=alias_findings([{"id":"original","value":2}])
        self.assertEqual(one[0]["id"],two[0]["id"])
        self.assertNotEqual(digest(one),digest(two))

    def test_empty_duplicates_and_realias_rejected(self):
        for value in ([],[{"id":"x"},{"id":"x"}],alias_findings([{"id":"x"}])):
            with self.assertRaises(ValueError):alias_findings(value)

    def test_all_18_short_ids_work_with_existing_exact_set_rule(self):
        values=alias_findings([{"id":"history:"+str(i).zfill(64)} for i in range(18)])
        responses=[{"id":v["id"]} for v in values]
        exact=lambda r:len(r)==len(values) and {x["id"] for x in r}=={x["id"] for x in values}
        self.assertTrue(exact(responses));self.assertFalse(exact(responses[:-1]))
        responses[0]["id"]="f000";self.assertFalse(exact(responses))


if __name__=="__main__":unittest.main()
