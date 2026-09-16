import copy
import unittest
from jsonschema import Draft202012Validator, ValidationError
import controller_source_review as original
import plan_schema_v2 as schema
from test_controller_source_review import fixture


class PlanSchemaTests(unittest.TestCase):
    def setUp(self):
        self.visible,self.plan,_=fixture();self.validator=Draft202012Validator(schema.PLAN_SCHEMA)

    def test_exact_fields_match_existing_semantic_validator(self):
        Draft202012Validator.check_schema(schema.PLAN_SCHEMA)
        self.assertEqual(set(schema.PLAN_SCHEMA['properties']),original.PLAN_FIELDS)
        self.validator.validate(self.plan)
        self.assertTrue(original.validate_plan(self.plan,self.visible,
            self.visible['evidence.json']['directory_receipts'])['proposal_valid'])

    def test_failed_run_shape_is_explained_and_rejected(self):
        for field,value in [('objects',[{'source':'fixture/source','advertised_bytes':123,'path':'x'}]),
                ('source_contract_changes','this must have been a list'),
                ('field_mapping',[{'status':'unverified'}])]:
            p=copy.deepcopy(self.plan);p[field]=value
            with self.subTest(field=field),self.assertRaises(ValidationError):self.validator.validate(p)

    def test_original_broker_tool_inventory_not_mutated(self):
        before=copy.deepcopy(original.TOOLS);new=schema.enriched_tools()
        self.assertEqual(original.TOOLS,before)
        changed=[(a,b) for a,b in zip(before,new) if a!=b]
        self.assertEqual(len(changed),1);self.assertEqual(changed[0][0]['name'],'propose_source_plan')

    def test_source_ids_are_not_conflated_with_revisions(self):
        a=schema.context_addendum(self.visible)
        self.assertIn('fixture/source',a['known_source_ids'])
        self.assertNotIn('synthetic-market-simulator',a['known_source_ids'])
        p=copy.deepcopy(self.plan);p['source_ids']=['fixture/source@'+'a'*40]
        with self.assertRaisesRegex(ValueError,'known real source'):
            original.validate_plan(p,self.visible,self.visible['evidence.json']['directory_receipts'])

    def test_unresolved_empty_objects_still_not_permission(self):
        p=copy.deepcopy(self.plan);p['objects']=[];self.validator.validate(p)
        result=original.validate_plan(p,self.visible,self.visible['evidence.json']['directory_receipts'])
        self.assertFalse(result['execution_admitted']);self.assertFalse(result['acquisition_admitted'])


if __name__=='__main__':unittest.main()
