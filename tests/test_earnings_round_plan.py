"""Pure finite-round-plan contract checks on owned synthetic bindings."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import earnings_round_plan as plan
from earnings_controller import CapacityController, CapacityAuthor
from test_earnings_ten_round_segment import TenRoundAssemblyFixture


class EarningsRoundPlanTests(unittest.TestCase):
    def fixture(self):
        return TenRoundAssemblyFixture(self)

    @staticmethod
    def context(fixture, role):
        return {
            "schema": f"earnings_capacity_{role}_transport_v2",
            "source_commit": fixture.runtime["source_commit"],
            "root": fixture.runtime["root"],
            "rates": deepcopy(fixture.runtime["rates"]),
            "limits": deepcopy(fixture.runtime["limits"][role]),
            "cutoff_utc": fixture.runtime["cutoff_utc"],
            "cutoff_monotonic": fixture.raw.window["cutoff_monotonic"],
            "slots": deepcopy(fixture.runtime["slots"][role]),
            "runtime": fixture.runtime_binding,
        }

    def test_round_count_preserves_v1_ceiling_and_admits_only_positive_offline_v2(self):
        fixture = self.fixture()
        self.assertEqual(plan.round_count(fixture.envelope), 10)

        for count in (1, 2, 3):
            legacy = deepcopy(fixture.envelope)
            legacy.update(schema="earnings_capacity_episode_v1", max_rounds=count,
                          slots=legacy["slots"][:count])
            with self.subTest(legacy=count):
                self.assertEqual(plan.round_count(legacy), count)
        legacy["max_rounds"] = 3
        with self.assertRaises((ValueError, TypeError)):
            plan.round_count(legacy, legacy_ceiling=2)

        invalid_counts = (True, False, 0, -1, 1.0, "10", None, float("inf"))
        for count in invalid_counts:
            changed = deepcopy(fixture.envelope)
            changed["max_rounds"] = count
            with self.subTest(count=repr(count)), self.assertRaises((ValueError, TypeError, OverflowError)):
                plan.round_count(changed)

        variants = (
            {"schema": "unknown"},
            {"mode": "live"},
            {"grant": {"live": True}},
            {"window": {"deadline": "later"}},
        )
        for update in variants:
            changed = deepcopy(fixture.envelope)
            changed.update(update)
            with self.subTest(update=update), self.assertRaises((ValueError, KeyError, TypeError)):
                plan.round_count(changed)

    def test_declared_slots_derives_exact_ordered_ten_ten_ten_thirty(self):
        fixture = self.fixture()
        before = fixture.retained_tree()
        expected = {
            "controller": [row["controller"] for row in fixture.slots],
            "author": [row["author"] for row in fixture.slots],
            "review": [row["review"] for row in fixture.slots],
            "forecast": [slot for row in fixture.plan_rows
                         for slot in (row["parent"], row["candidate"], row["downstream"])],
        }
        self.assertEqual(plan.declared_slots(fixture.envelope, fixture.plan), expected)
        self.assertEqual({role: len(slots) for role, slots in expected.items()},
                         {"controller": 10, "author": 10, "review": 10, "forecast": 30})
        self.assertEqual(fixture.retained_tree(), before)

    def test_declared_slots_rejects_count_order_shape_duplicate_and_path_drift(self):
        variants = []
        fixture = self.fixture()
        variants.append((fixture, dict(fixture.plan, rounds=fixture.plan["rounds"][:-1])))

        fixture = self.fixture()
        reversed_plan = deepcopy(fixture.plan)
        reversed_plan["rounds"] = list(reversed(reversed_plan["rounds"]))
        variants.append((fixture, reversed_plan))

        fixture = self.fixture()
        wrong_downstream = deepcopy(fixture.plan)
        wrong_downstream["rounds"][4]["downstream"] = wrong_downstream["rounds"][3]["downstream"]
        variants.append((fixture, wrong_downstream))

        fixture = self.fixture()
        missing = deepcopy(fixture.plan)
        missing["rounds"][0].pop("candidate")
        variants.append((fixture, missing))

        fixture = self.fixture()
        extra = deepcopy(fixture.plan)
        extra["rounds"][0]["extra"] = str(fixture.root / "roles" / "extra")
        variants.append((fixture, extra))

        fixture = self.fixture()
        duplicate_episode = deepcopy(fixture.envelope)
        duplicate_episode["slots"][1]["controller"] = duplicate_episode["slots"][0]["controller"]
        variants.append((fixture, fixture.plan, duplicate_episode))

        fixture = self.fixture()
        outside = deepcopy(fixture.plan)
        outside["rounds"][0]["parent"] = str(fixture.root / "outside" / "parent")
        variants.append((fixture, outside))

        for item in variants:
            fixture, matched = item[:2]
            envelope = item[2] if len(item) == 3 else fixture.envelope
            with self.subTest(matched=matched), self.assertRaises((ValueError, KeyError, TypeError)):
                plan.declared_slots(envelope, matched)

    def test_validate_runtime_plan_returns_exact_bound_episode_without_writes(self):
        fixture = self.fixture()
        before = fixture.retained_tree()
        self.assertEqual(plan.validate_runtime_plan(fixture.runtime), fixture.envelope)
        self.assertEqual(fixture.retained_tree(), before)
        self.assertEqual(fixture.factory_calls, 0)

    def test_validate_runtime_plan_rejects_schema_binding_identity_and_slot_drift(self):
        changes = (
            lambda value: value.update(schema="earnings_capacity_runtime_v2"),
            lambda value: value.update(episode=dict(value["episode"], sha256="a" * 64)),
            lambda value: value.update(matched_plan=dict(value["matched_plan"], sha256="b" * 64)),
            lambda value: value.update(id="different-id"),
            lambda value: value.update(root=str(Path(value["root"]) / "different")),
            lambda value: value.update(source_commit="f" * 40),
            lambda value: value.update(forecast_study={"path": "different", "sha256": "c" * 64}),
            lambda value: value["slots"]["controller"].pop(),
            lambda value: value["slots"]["forecast"].reverse(),
            lambda value: value.pop("matched_plan"),
        )
        for index, change in enumerate(changes):
            fixture = self.fixture()
            changed = deepcopy(fixture.runtime)
            change(changed)
            with self.subTest(index=index), self.assertRaises((ValueError, KeyError, TypeError, OSError)):
                plan.validate_runtime_plan(changed)

    def test_validate_runtime_plan_rejects_internally_bound_malformed_unknown_or_live_episode(self):
        for kind in ("unknown", "live", "grant", "extra", "missing"):
            fixture = self.fixture()
            episode = deepcopy(fixture.envelope)
            if kind == "unknown":
                episode["schema"] = "unknown"
            elif kind == "live":
                episode["mode"] = "live"
            elif kind == "grant":
                episode["grant"] = {"live": True}
            elif kind == "extra":
                episode["extra"] = True
            else:
                episode.pop("sources")
            episode_binding = fixture.save("changed-episode", episode)
            matched = deepcopy(fixture.plan)
            matched["episode"] = episode_binding
            matched_binding = fixture.save("changed-plan", matched)
            changed = deepcopy(fixture.runtime)
            changed.update(episode=episode_binding, matched_plan=matched_binding)
            with self.subTest(kind=kind), self.assertRaises((ValueError, KeyError, TypeError)):
                plan.validate_runtime_plan(changed)

    def test_validate_runtime_context_returns_bound_runtime_for_every_role(self):
        fixture = self.fixture()
        before = fixture.retained_tree()
        for role in ("controller", "author", "review", "forecast"):
            with self.subTest(role=role):
                self.assertEqual(plan.validate_context(self.context(fixture, role), role), fixture.runtime)
        self.assertEqual(fixture.retained_tree(), before)
        self.assertEqual(fixture.factory_calls, 0)

    def test_concrete_v2_controller_and_author_recheck_runtime_before_use(self):
        for role, constructor in (('controller', CapacityController), ('author', CapacityAuthor)):
            fixture = self.fixture()
            context = self.context(fixture, role)
            binding = fixture.save('bound-' + role, context)
            component = constructor(binding, budget=fixture.raw.budget, client_factory=fixture.client_factory)
            # Fault is confined to this fixture's generated runtime metadata.
            Path(fixture.runtime_binding['path']).write_bytes(b'{}\n')
            with self.subTest(role=role), self.assertRaises(ValueError):
                component._context()
            self.assertEqual(fixture.factory_calls, 0)
            self.assertFalse(Path(context['slots'][0]).exists())

    def test_validate_runtime_context_rejects_unknown_role_old_schema_and_field_drift(self):
        roles = ("controller", "author", "review", "forecast")
        for role in roles:
            changes = (
                lambda value: value.update(schema=f"earnings_capacity_{role}_transport_v1"),
                lambda value: value.update(runtime=dict(value["runtime"], sha256="d" * 64)),
                lambda value: value.update(source_commit="e" * 40),
                lambda value: value.update(root=str(Path(value["root"]) / "different")),
                lambda value: value["rates"].update(input="999"),
                lambda value: value["limits"].update(max_input_tokens=value["limits"]["max_input_tokens"] + 1),
                lambda value: value["slots"].pop(),
                lambda value: value.update(cutoff_utc="2098-01-01T00:00:00Z"),
                lambda value: value.pop("runtime"),
            )
            for index, change in enumerate(changes):
                fixture = self.fixture()
                changed = self.context(fixture, role)
                change(changed)
                with self.subTest(role=role, index=index), \
                     self.assertRaises((ValueError, KeyError, TypeError, OSError)):
                    plan.validate_context(changed, role)

        fixture = self.fixture()
        with self.assertRaises((ValueError, KeyError, TypeError)):
            plan.validate_context(self.context(fixture, "controller"), "unknown")


if __name__ == "__main__":
    unittest.main()
