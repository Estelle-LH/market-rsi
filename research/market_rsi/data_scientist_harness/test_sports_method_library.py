import unittest

from data_scientist_harness import sports_method_library
from data_scientist_harness.broker import TOOLS, validate_shape


class SportsMethodLibraryTests(unittest.TestCase):
    def test_current_and_proposed_methods_are_distinguished(self):
        value = sports_method_library.inspect("market_response")
        status = {method["id"]: method["status"] for method in value["methods"]}
        self.assertEqual(status["ridge_response"], "executable_now")
        self.assertEqual(status["game_clustered_local_projection"], "implemented_unreleased")
        self.assertFalse(value["library_selects_winner"])

    def test_tool_schema_requires_known_stage(self):
        schema = next(tool["inputSchema"] for tool in TOOLS
                      if tool["name"] == "inspect_sports_method_library")
        validate_shape({"stage": "state_prediction"}, schema)
        with self.assertRaisesRegex(ValueError, "choose one of"):
            validate_shape({"stage": "unknown"}, schema)


if __name__ == "__main__":
    unittest.main()
