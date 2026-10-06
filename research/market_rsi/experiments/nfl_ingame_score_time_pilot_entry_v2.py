"""Fresh one-trial authority entry; unchanged Controller prediction callbacks."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from experiments import nfl_ingame_score_time_joint_offset_v1 as candidate
from supervisor_harness import opened_train_discovery_worker as worker
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from data_scientist_harness.co_evolution_loop import micro_pair_hash

MODULE = "experiments.nfl_ingame_score_time_pilot_entry_v2"
BATCH = "market-rsi-coevo-score-time-20261006-03"
AUTH_SHA = "b22f1cfc873b772a934f332b97b70a891c8ca8a8b28348ab36ecf77699c3cc4b"


def require_admission(source_root, output):
    root = Path(output).resolve().parents[1]
    load = candidate.common.settlement._strict_json
    authority = root / "authorization.json"
    if worker.sha(authority) != AUTH_SHA:
        raise ValueError("fresh one-trial authority drift")
    grant = load(authority)
    start, end = [datetime.fromisoformat(grant[k].replace("Z", "+00:00"))
                  for k in ("start_utc", "deadline_utc")]
    if grant["batch_id"] != BATCH or not start <= datetime.now(timezone.utc) < end:
        raise ValueError("fresh trial identity/deadline changed")
    request = load(root / "worker" / (Path(output).name + ".request.json"))
    worker.validate(request, Path(__file__).parents[3])
    binding = load(root / "binding.json")
    native = ContinuousDiscoveryBatch(root).snapshot()
    branch = next(x for x in native["branches"] if x["attempt_id"] == request["attempt_id"])
    if (request["module"] != MODULE or request["candidate_id"] != candidate.TASK_ID
            or request["max_fits"] != 4 or request["attempt_id"] != Path(output).name
            or native["batch_id"] != BATCH or native["max_attempts"] != 1
            or native["deadline_utc"] != grant["deadline_utc"]
            or branch["stage"] != "execution_claimed" or branch["claim_id"] != request["attempt_id"] + "-claim"
            or request["runtime_pair_sha256"] != micro_pair_hash(native["micro_evolution"])
            or request["spec_sha256"] != binding["candidate_contract_sha256"]
            or Path(source_root).resolve() != worker.TRAIN.resolve()):
        raise ValueError("native claimed trial/source/pair/contract mismatch")
    candidate.harness.validate_binding(binding, dict(prepare_features=candidate.prepare_features,
        fit_predict=candidate.fit_predict, replay_predictor=candidate.replay_predictor))
    return binding


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    candidate.run(args.source_root, args.output, require_admission(args.source_root, args.output))
