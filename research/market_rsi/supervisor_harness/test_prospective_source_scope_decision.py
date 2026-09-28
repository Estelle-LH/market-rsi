import copy
import json
import unittest

from supervisor_harness.prospective_source_scope_decision import (
    DecisionValidationError,
    NON_AUTHORITY_KEYS,
    SCHEMA,
    build_decision,
    canonical_decision_bytes,
    non_authority_boundary,
    parse_canonical_decision,
    validate_decision,
)


def valid_decision():
    return build_decision(
        decision_id="dec_" + "a" * 26,
        scientific_source_response={
            "source_registry_entry_id": "src_" + "b" * 26,
            "response_class_id": "rsp_" + "c" * 26,
        },
        intended_uses={
            "requested_use_ids": ["model_training", "private_research"],
        },
        future_role_split={
            "requested_future_role": "train_candidate",
            "split_policy_id": "spl_" + "d" * 26,
            "split_policy_sha256": "1" * 64,
            "exposure_ledger_id": "not_yet_created",
            "unknown_exposure_policy": "treat_as_exposed",
            "cross_role_reuse_policy": "no_role_reassignment_after_observation",
        },
        horizon_cutoff={
            "claim_semantics": "prospective_point_in_time",
            "prediction_horizon_us": 60_000_000,
            "cutoff_semantics_id": "cut_" + "e" * 26,
            "cutoff_contract_sha256": "2" * 64,
            "label_window_start_relation": "strictly_after_cutoff",
            "label_window_end_relation": "at_or_before_cutoff_plus_horizon",
            "availability_formula_id": "max_authenticated_inclusive_upper_bound_us_v2",
            "availability_cutoff_relation": "availability_upper_bound_unix_us_lte_forecast_cutoff_unix_us",
            "provider_receiver_clocks_separate": True,
        },
        bounded_investigation={
            "mode": "first_party_document_review_only",
            "max_documents_proposed": 2,
            "max_provider_requests_proposed": 0,
            "max_raw_bytes_proposed": 0,
            "max_elapsed_seconds_proposed": 300,
            "max_spend_usd_micros_proposed": 0,
            "stop_on_first_rights_or_authority_unknown": True,
            "stop_before_unregistered_response_class": True,
            "preserve_failures_without_retry_expansion": True,
        },
    )


class ProspectiveSourceScopeDecisionTests(unittest.TestCase):
    def test_builder_returns_complete_scope_only_body_with_exact_false_boundary(self):
        value = valid_decision()
        self.assertEqual(value["schema"], SCHEMA)
        self.assertEqual(
            set(value),
            {
                "schema",
                "decision_id",
                "decision_status",
                "scientific_source_response",
                "intended_uses",
                "future_role_split",
                "horizon_cutoff",
                "bounded_investigation",
                "non_authority",
            },
        )
        self.assertEqual(set(value["non_authority"]), NON_AUTHORITY_KEYS)
        self.assertEqual(len(value["non_authority"]), 17)
        self.assertTrue(all(item is False for item in value["non_authority"].values()))

    def test_builder_copies_caller_objects_and_never_supplies_scientific_defaults(self):
        value = valid_decision()
        source = value["scientific_source_response"]
        source["source_registry_entry_id"] = "src_" + "f" * 26
        fresh = valid_decision()
        self.assertEqual(fresh["scientific_source_response"]["source_registry_entry_id"], "src_" + "b" * 26)
        with self.assertRaises(DecisionValidationError):
            build_decision(
                decision_id="dec_" + "a" * 26,
                scientific_source_response={},
                intended_uses=fresh["intended_uses"],
                future_role_split=fresh["future_role_split"],
                horizon_cutoff=fresh["horizon_cutoff"],
                bounded_investigation=fresh["bounded_investigation"],
            )

    def test_canonical_round_trip_is_sorted_compact_ascii_with_one_lf(self):
        value = valid_decision()
        encoded = canonical_decision_bytes(value)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertFalse(encoded.endswith(b"\n\n"))
        self.assertNotIn(b" ", encoded)
        self.assertEqual(parse_canonical_decision(encoded), value)
        self.assertEqual(json.loads(encoded), value)

    def test_noncanonical_and_duplicate_json_fail_closed(self):
        encoded = canonical_decision_bytes(valid_decision())
        for changed in (
            encoded[:-1],
            encoded + b"\n",
            b" " + encoded,
            encoded.replace(b'"schema":', b'"schema" :', 1),
        ):
            with self.subTest(changed=changed[:40]):
                with self.assertRaises(DecisionValidationError):
                    parse_canonical_decision(changed)
        duplicate = encoded.replace(
            b'{"bounded_investigation":',
            b'{"schema":"market_rsi_prospective_source_scope_decision_v1","bounded_investigation":',
            1,
        )
        with self.assertRaisesRegex(DecisionValidationError, "duplicate JSON member"):
            parse_canonical_decision(duplicate)

    def test_canonical_parser_rejects_noncanonical_integer_forms_and_nonfinite_values(self):
        encoded = canonical_decision_bytes(valid_decision())
        needle = b'"prediction_horizon_us":60000000'
        for token in (b"6e7", b"60000000.0", b"-0", b"060000000", b"NaN"):
            with self.subTest(token=token):
                changed = encoded.replace(needle, b'"prediction_horizon_us":' + token, 1)
                with self.assertRaises(DecisionValidationError):
                    parse_canonical_decision(changed)

    def test_unknown_members_reject_urls_credentials_commands_and_data_rows(self):
        additions = (
            ((), "url", "https://example.invalid/data"),
            (("scientific_source_response",), "credential", "secret"),
            (("bounded_investigation",), "command", "curl example.invalid"),
            (("horizon_cutoff",), "data_rows", [{"result": 1}]),
        )
        for path, key, item in additions:
            with self.subTest(path=path, key=key):
                value = valid_decision()
                target = value
                for member in path:
                    target = target[member]
                target[key] = item
                with self.assertRaisesRegex(DecisionValidationError, "exact member set"):
                    validate_decision(value)

    def test_locator_like_values_cannot_enter_opaque_ids(self):
        invalid = (
            "https://example.invalid",
            "src_/tmp/not-data",
            "src_" + "A" * 26,
            "src_" + "a" * 25,
            "src_" + "a" * 25 + "0",
        )
        for item in invalid:
            with self.subTest(item=item):
                value = valid_decision()
                value["scientific_source_response"]["source_registry_entry_id"] = item
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)

    def test_wrong_id_prefix_and_malformed_hashes_fail(self):
        mutations = (
            ("decision_id", "src_" + "a" * 26),
            ("future_role_split.split_policy_id", "cut_" + "d" * 26),
            ("future_role_split.split_policy_sha256", "A" * 64),
            ("horizon_cutoff.cutoff_contract_sha256", "2" * 63),
        )
        for dotted, changed in mutations:
            with self.subTest(field=dotted):
                value = valid_decision()
                target = value
                parts = dotted.split(".")
                for member in parts[:-1]:
                    target = target[member]
                target[parts[-1]] = changed
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)

    def test_requested_use_set_is_nonempty_sorted_unique_and_closed(self):
        bad = (
            [],
            ["private_research", "model_training"],
            ["model_training", "model_training"],
            ["model_training", "provider_access"],
            "model_training",
        )
        for uses in bad:
            with self.subTest(uses=uses):
                value = valid_decision()
                value["intended_uses"]["requested_use_ids"] = uses
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)

    def test_every_authority_field_is_required_boolean_false(self):
        for key in sorted(NON_AUTHORITY_KEYS):
            with self.subTest(key=key):
                value = valid_decision()
                value["non_authority"][key] = True
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)
        for changed in (0, None, "false"):
            value = valid_decision()
            value["non_authority"]["executable"] = changed
            with self.subTest(changed=changed):
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)
        value = valid_decision()
        del value["non_authority"]["publication_authorized"]
        with self.assertRaises(DecisionValidationError):
            validate_decision(value)
        value = valid_decision()
        value["non_authority"]["provider_fetch_authorized"] = False
        with self.assertRaises(DecisionValidationError):
            validate_decision(value)

    def test_json_booleans_and_floats_do_not_pass_integer_fields(self):
        fields = (
            ("horizon_cutoff", "prediction_horizon_us"),
            ("bounded_investigation", "max_documents_proposed"),
            ("bounded_investigation", "max_provider_requests_proposed"),
            ("bounded_investigation", "max_raw_bytes_proposed"),
            ("bounded_investigation", "max_elapsed_seconds_proposed"),
            ("bounded_investigation", "max_spend_usd_micros_proposed"),
        )
        for section, key in fields:
            for changed in (True, 1.5, "1"):
                with self.subTest(section=section, key=key, changed=changed):
                    value = valid_decision()
                    value[section][key] = changed
                    with self.assertRaises(DecisionValidationError):
                        validate_decision(value)

    def test_horizon_semantics_are_consistent(self):
        value = valid_decision()
        value["horizon_cutoff"].update(
            {
                "claim_semantics": "descriptive_no_forecast",
                "prediction_horizon_us": 0,
                "label_window_start_relation": "not_applicable",
                "label_window_end_relation": "not_applicable",
            }
        )
        validate_decision(value)

        bad_values = []
        item = copy.deepcopy(value)
        item["horizon_cutoff"]["prediction_horizon_us"] = 1
        bad_values.append(item)
        item = valid_decision()
        item["horizon_cutoff"]["prediction_horizon_us"] = 0
        bad_values.append(item)
        item = valid_decision()
        item["horizon_cutoff"]["label_window_end_relation"] = "not_applicable"
        bad_values.append(item)
        for item in bad_values:
            with self.assertRaises(DecisionValidationError):
                validate_decision(item)

    def test_investigation_modes_enforce_zero_spend_and_mode_caps(self):
        value = valid_decision()
        value["bounded_investigation"].update(
            {
                "mode": "synthetic_contract_fixture_only",
                "max_documents_proposed": 0,
            }
        )
        validate_decision(value)

        value = valid_decision()
        value["bounded_investigation"].update(
            {
                "mode": "bounded_response_canary_proposal",
                "max_documents_proposed": 0,
                "max_provider_requests_proposed": 1,
                "max_raw_bytes_proposed": 1000,
            }
        )
        validate_decision(value)

        changes = (
            {"max_spend_usd_micros_proposed": 1},
            {"max_provider_requests_proposed": 1},
            {"max_raw_bytes_proposed": 1},
            {"max_documents_proposed": 0},
            {"stop_on_first_rights_or_authority_unknown": False},
            {"stop_before_unregistered_response_class": False},
            {"preserve_failures_without_retry_expansion": False},
        )
        for changed in changes:
            with self.subTest(changed=changed):
                value = valid_decision()
                value["bounded_investigation"].update(changed)
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)

    def test_complete_mode_dependent_investigation_table(self):
        for mode in (
                "bounded_metadata_canary_proposal",
                "bounded_response_canary_proposal"):
            with self.subTest(mode=mode, documents=0):
                value = valid_decision()
                value["bounded_investigation"].update({
                    "mode": mode,
                    "max_documents_proposed": 0,
                })
                validate_decision(value)
            with self.subTest(mode=mode, documents=1):
                value["bounded_investigation"]["max_documents_proposed"] = 1
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)

        value = valid_decision()
        validate_decision(value)
        for changed in (
                {"max_documents_proposed": 0},
                {"max_provider_requests_proposed": 1},
                {"max_raw_bytes_proposed": 1}):
            with self.subTest(mode="first_party_document_review_only",
                              changed=changed):
                invalid = valid_decision()
                invalid["bounded_investigation"].update(changed)
                with self.assertRaises(DecisionValidationError):
                    validate_decision(invalid)

        value = valid_decision()
        value["bounded_investigation"].update({
            "mode": "synthetic_contract_fixture_only",
            "max_documents_proposed": 0,
        })
        validate_decision(value)
        for changed in (
                {"max_documents_proposed": 1},
                {"max_provider_requests_proposed": 1},
                {"max_raw_bytes_proposed": 1}):
            with self.subTest(mode="synthetic_contract_fixture_only",
                              changed=changed):
                invalid = copy.deepcopy(value)
                invalid["bounded_investigation"].update(changed)
                with self.assertRaises(DecisionValidationError):
                    validate_decision(invalid)

    def test_bound_exposure_ledger_id_must_be_opaque_and_role_fields_are_fixed(self):
        value = valid_decision()
        value["future_role_split"]["exposure_ledger_id"] = "led_" + "f" * 26
        validate_decision(value)
        for key, changed in (
            ("exposure_ledger_id", "unknown"),
            ("unknown_exposure_policy", "ignore_unknown"),
            ("cross_role_reuse_policy", "allow_reassignment"),
            ("requested_future_role", "train_and_final"),
        ):
            with self.subTest(key=key):
                value = valid_decision()
                value["future_role_split"][key] = changed
                with self.assertRaises(DecisionValidationError):
                    validate_decision(value)

    def test_validation_returns_isolated_copy(self):
        value = valid_decision()
        accepted = validate_decision(value)
        accepted["intended_uses"]["requested_use_ids"].append("raw_data_redistribution")
        self.assertEqual(value["intended_uses"]["requested_use_ids"], ["model_training", "private_research"])
        self.assertEqual(non_authority_boundary(), value["non_authority"])


if __name__ == "__main__":
    unittest.main()
