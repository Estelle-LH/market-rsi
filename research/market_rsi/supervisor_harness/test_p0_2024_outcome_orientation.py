from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import unittest

from supervisor_harness import p0_candidate_admission_integration as integration
from supervisor_harness import p0_2024_outcome_orientation as orientation


def encoded(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def fixture(*, slug_order: str = "home_away",
            outcomes: list[str] | None = None,
            tokens: list[str] | None = None) -> tuple[list[dict], list[dict[str, str]]]:
    outcomes = outcomes or ["Chiefs", "Ravens"]
    tokens = tokens or ["101", "202"]
    slug = ("nfl-kc-bal-2024-09-05" if slug_order == "home_away"
            else "nfl-bal-kc-2024-09-05")
    event = {
        "id": "13067",
        "slug": slug,
        "startTime": "2024-09-06T00:20:00Z",
        "markets": [{
            "id": "505839",
            "slug": slug,
            "sportsMarketType": "moneyline",
            "conditionId": "0x" + "6" * 64,
            "outcomes": encoded(outcomes),
            "clobTokenIds": encoded(tokens),
        }],
    }
    row = {
        "polymarket_event_id": "13067",
        "event_slug": slug,
        "event_start_utc": "2024-09-06T00:20:00Z",
        "nflverse_game_id": "2024_01_BAL_KC",
        "nflverse_game_date": "2024-09-05",
        "away_team": "BAL",
        "home_team": "KC",
        "slug_order": slug_order,
        "date_resolution": "exact",
        "moneyline_market_id": "505839",
        "condition_id": "0x" + "6" * 64,
        "outcomes_json": encoded(outcomes),
        "tokens_json": encoded(tokens),
    }
    return [event], [row]


def raw_catalog(events: list[dict]) -> bytes:
    return (json.dumps(events, sort_keys=True, separators=(",", ":")) + "\n").encode()


def raw_mapping(rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=orientation.MAPPING_FIELDS,
                            lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def verify(events: list[dict], rows: list[dict[str, str]], *,
           alias_table: object = orientation.TEAM_NAME_ALIASES) -> dict:
    catalog = raw_catalog(events)
    mapping = raw_mapping(rows)
    return orientation._verify_bound_orientation(
        catalog, mapping,
        expected_catalog_sha256=hashlib.sha256(catalog).hexdigest(),
        expected_mapping_sha256=hashlib.sha256(mapping).hexdigest(),
        expected_catalog_events=len(events),
        expected_mapped_events=len(rows),
        alias_table=alias_table,
    )


class PreservedOrientationTests(unittest.TestCase):
    def test_preserved_contract_remains_285_284_1_without_loading_raw_data(self) -> None:
        self.assertEqual(orientation.PRESERVED_CATALOG_EVENTS, 285)
        self.assertEqual(orientation.PRESERVED_MAPPED_EVENTS, 284)
        self.assertEqual(dict(orientation.PRESERVED_UNORIENTED_EVENT), {
            "event_id": "17330",
            "event_slug": "nfl-kc-phi-2025-02-09",
            "reason": "absent_from_candidate_mapping",
        })
        self.assertEqual(dict(integration.CANDIDATE_CONTRACT), {
            "candidate_rows": 285,
            "mapped_rows": 284,
            "mapping_resolved": False,
            "missing_rows": 1,
            "orientation_resolved": False,
            "season": 2024,
            "unresolved_event_id": "17330",
            "unresolved_event_slug": "nfl-kc-phi-2025-02-09",
            "unresolved_reason": "moneyline_missing_or_ambiguous",
            "unresolved_schedule_game_id": "2024_22_KC_PHI",
        })

    def test_home_away_and_away_home_slug_orders_are_explicit(self) -> None:
        for slug_order in ("home_away", "away_home"):
            with self.subTest(slug_order=slug_order):
                events, rows = fixture(slug_order=slug_order)
                receipt = verify(events, rows)["candidate_orientation_receipts"][0]
                self.assertEqual(receipt["away_team"], "BAL")
                self.assertEqual(receipt["away_outcome"], "Ravens")
                self.assertEqual(receipt["away_token_id"], "202")
                self.assertEqual(receipt["home_team"], "KC")
                self.assertEqual(receipt["home_outcome"], "Chiefs")
                self.assertEqual(receipt["home_token_id"], "101")

    def test_reversed_source_outcome_order_preserves_token_pairing(self) -> None:
        events, rows = fixture(
            outcomes=["Ravens", "Chiefs"], tokens=["202", "101"])
        receipt = verify(events, rows)["candidate_orientation_receipts"][0]
        self.assertEqual(receipt["away_outcome_index"], 0)
        self.assertEqual(receipt["away_token_id"], "202")
        self.assertEqual(receipt["home_outcome_index"], 1)
        self.assertEqual(receipt["home_token_id"], "101")

    def test_reversed_mapped_home_away_fails_against_game_id(self) -> None:
        events, rows = fixture()
        rows[0]["away_team"], rows[0]["home_team"] = "KC", "BAL"
        with self.assertRaisesRegex(ValueError, "nflverse game ID"):
            verify(events, rows)

    def test_alias_collision_fails_closed(self) -> None:
        events, rows = fixture()
        aliases = {team: list(names)
                   for team, names in orientation.TEAM_NAME_ALIASES.items()}
        aliases["BAL"].append("Chiefs")
        with self.assertRaisesRegex(ValueError, "ambiguous team-name alias"):
            verify(events, rows, alias_table=aliases)

    def test_noncanonical_but_noncolliding_alias_table_is_rejected(self) -> None:
        events, rows = fixture()
        aliases = {team: list(names)
                   for team, names in orientation.TEAM_NAME_ALIASES.items()}
        aliases["BAL"] = ["Baltimore Ravens"]
        with self.assertRaisesRegex(ValueError, "reviewed code-owned table"):
            verify(events, rows, alias_table=aliases)

    def test_unknown_outcome_label_fails_closed(self) -> None:
        events, rows = fixture(outcomes=["Chiefs", "Birds"])
        with self.assertRaisesRegex(ValueError, "absent from alias table"):
            verify(events, rows)

    def test_duplicate_outcome_names_fail_closed(self) -> None:
        events, rows = fixture(outcomes=["Chiefs", "Chiefs"])
        with self.assertRaisesRegex(ValueError, "duplicate outcome names"):
            verify(events, rows)

    def test_non_two_token_market_fails_closed(self) -> None:
        events, rows = fixture()
        events[0]["markets"][0]["clobTokenIds"] = encoded(["101"])
        rows[0]["tokens_json"] = encoded(["101"])
        with self.assertRaisesRegex(ValueError, "exactly two strings"):
            verify(events, rows)

    def test_mapping_token_mismatch_fails_closed(self) -> None:
        events, rows = fixture()
        rows[0]["tokens_json"] = encoded(["101", "303"])
        with self.assertRaisesRegex(ValueError, "differ from source market"):
            verify(events, rows)

    def test_duplicate_token_ids_fail_closed(self) -> None:
        events, rows = fixture(tokens=["101", "101"])
        with self.assertRaisesRegex(ValueError, "duplicate or noncanonical"):
            verify(events, rows)

    def test_preserved_catalog_substitution_fails_before_semantics(self) -> None:
        events, rows = fixture()
        catalog = raw_catalog(events)
        mapping = raw_mapping(rows)
        with self.assertRaisesRegex(ValueError, "trusted source hash"):
            orientation.verify_preserved_2024_orientation(
                catalog + b"\n", mapping)

    def test_preserved_mapping_substitution_fails_before_semantics(self) -> None:
        events, rows = fixture()
        catalog = raw_catalog(events)
        mapping = raw_mapping(rows)
        with self.assertRaisesRegex(ValueError, "trusted mapping hash"):
            orientation._verify_bound_orientation(
                catalog, mapping + b"\n",
                expected_catalog_sha256=hashlib.sha256(catalog).hexdigest(),
                expected_mapping_sha256=hashlib.sha256(mapping).hexdigest(),
                expected_catalog_events=1,
                expected_mapped_events=1,
                alias_table=orientation.TEAM_NAME_ALIASES)

    def test_duplicate_catalog_event_identity_fails_closed(self) -> None:
        events, rows = fixture()
        events.append(copy.deepcopy(events[0]))
        with self.assertRaisesRegex(ValueError, "invalid or duplicated"):
            verify(events, rows)

    def test_mapping_cannot_reference_absent_source_event(self) -> None:
        events, rows = fixture()
        rows[0]["polymarket_event_id"] = "99999"
        with self.assertRaisesRegex(ValueError, "absent source event"):
            verify(events, rows)

    def test_extra_moneyline_market_is_ambiguous(self) -> None:
        events, rows = fixture()
        extra = copy.deepcopy(events[0]["markets"][0])
        extra["id"] = "505840"
        events[0]["markets"].append(extra)
        with self.assertRaisesRegex(ValueError, "moneyline identity"):
            verify(events, rows)

    def test_receipt_is_deterministic(self) -> None:
        events, rows = fixture()
        self.assertEqual(verify(events, rows), verify(events, rows))


if __name__ == "__main__":
    unittest.main()
