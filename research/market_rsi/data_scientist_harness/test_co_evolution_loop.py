import unittest

from data_scientist_harness.co_evolution_loop import (
    begin_experiment_batch,
    begin_next_experiment,
    bind_next_release,
    complete_experiment_batch,
    freeze_candidate_portfolio,
    open_harness_review,
    select_harness_candidate,
)


def sha(char):
    return char * 64


def release(version="h1", commit="a" * 40, tag="h1", token="1"):
    return {
        "harness_version": version,
        "release_sha256": sha(token),
        "commit": commit,
        "tag": tag,
        "published": True,
        "canary_sha256": sha("c"),
    }


def claim(release_value, identifier="e1"):
    return {
        "experiment_id": identifier,
        "harness_release_sha256": release_value["release_sha256"],
        "harness_commit": release_value["commit"],
        "pre_score_lock_sha256": sha("d"),
        "planned_inner_rounds": 7,
        "artifact_root": "artifacts/e1",
        "route_dev_policy": "sealed",
        "final_policy": "sealed_until_terminal_acceptance",
    }


def completion(release_value, identifier="e1"):
    return {
        "experiment_id": identifier,
        "harness_release_sha256": release_value["release_sha256"],
        "status": "complete",
        "inner_rounds_completed": 7,
        "manifest_sha256": sha("e"),
        "trajectory_sha256": sha("f"),
        "artifact_hashes": {"manifest.json": sha("e"), "trajectory.json": sha("f")},
        "cost_usd": 0.0,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "terminal_cleanup_passed": True,
    }


def observation():
    return {
        "observation_id": "data-small",
        "component": "data_acquisition",
        "severity": "blocking",
        "evidence_sha256": sha("f"),
        "problem": "Only one season is available.",
        "blocked_action": "Measure a multi-season learning curve.",
        "machine_observation": "Seven Train rounds ended at 4.59% MSE improvement.",
        "harness_interpretation": "Data breadth is the earliest unresolved bottleneck.",
    }


def candidate(identifier, novel=False):
    return {
        "candidate_id": identifier,
        "observation_ids": ["data-small"],
        "changed_component": "data_acquisition",
        "proposal_sha256": sha("a"),
        "previously_untried_in_project": novel,
        "literature_record_ids": ["0042"] if novel else [],
        "implementation_scope": "One isolated data acquisition capability.",
        "validation_plan": "Replay the old shortage and run positive/negative synthetic canaries.",
        "estimated_patch_lines": 100,
        "estimated_next_round_cost_usd": 0.0,
        "requests_kernel_change": False,
        "requests_sealed_data": False,
        "uses_predictive_dev_score": False,
    }


class CoEvolutionLoopTests(unittest.TestCase):
    def setUp(self):
        self.h1 = release()
        self.running = begin_experiment_batch(self.h1, claim(self.h1))
        self.completed = complete_experiment_batch(self.running, completion(self.h1))
        self.review = open_harness_review(self.completed, [observation()])
        self.portfolio = freeze_candidate_portfolio(
            self.review, [candidate("archive-search"), candidate("new-source-composer", novel=True)]
        )
        self.selection_value = {
            "selected_candidate_id": "new-source-composer",
            "selection_sha256": sha("7"),
            "eligible_candidate_ids": ["new-source-composer"],
            "validation_receipt_hashes": {"new-source-composer": sha("8")},
            "selection_rule": "earliest bottleneck, all canaries pass, lowest cost",
            "predictive_dev_score_used": False,
        }
        self.selected = select_harness_candidate(self.portfolio, self.selection_value)

    def test_unpublished_harness_cannot_start_experiment(self):
        value = dict(self.h1, published=False)
        with self.assertRaisesRegex(ValueError, "published"):
            begin_experiment_batch(value, claim(value))

    def test_harness_cannot_review_before_experiment_completes(self):
        with self.assertRaisesRegex(ValueError, "terminal experiment"):
            open_harness_review(self.running, [observation()])

    def test_observation_must_come_from_completed_experiment(self):
        value = observation(); value["evidence_sha256"] = sha("9")
        with self.assertRaisesRegex(ValueError, "completed experiment"):
            open_harness_review(self.completed, [value])

    def test_portfolio_must_include_untried_candidate(self):
        with self.assertRaisesRegex(ValueError, "previously untried"):
            freeze_candidate_portfolio(self.review, [candidate("archive-search"), candidate("second")])

    def test_large_candidate_portfolio_is_allowed_but_one_is_selected(self):
        values = [candidate(f"c{index:03d}", novel=index == 0) for index in range(100)]
        portfolio = freeze_candidate_portfolio(self.review, values)
        self.assertEqual(portfolio["candidate_count"], 100)

    def test_next_experiment_requires_new_published_release(self):
        h2 = {
            **release(version="h2", commit="b" * 40, tag="h2", token="2"),
            "parent_release_sha256": self.h1["release_sha256"],
            "selected_candidate_id": "new-source-composer",
            "selection_sha256": self.selection_value["selection_sha256"],
        }
        link = bind_next_release(self.selected, h2)
        next_claim = claim(h2, "e2")
        started = begin_next_experiment(link, next_claim)
        self.assertEqual(started["state"], "experiment_running")
        self.assertEqual(started["release"]["harness_version"], "h2")

    def test_same_commit_or_tag_cannot_be_reused(self):
        h2 = {
            **release(version="h2", commit=self.h1["commit"], tag="h2", token="2"),
            "parent_release_sha256": self.h1["release_sha256"],
            "selected_candidate_id": "new-source-composer",
            "selection_sha256": self.selection_value["selection_sha256"],
        }
        with self.assertRaisesRegex(ValueError, "fresh immutable"):
            bind_next_release(self.selected, h2)


if __name__ == "__main__":
    unittest.main()
