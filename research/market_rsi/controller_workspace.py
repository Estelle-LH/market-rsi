"""Frozen visible workspace and runner queue for the Codex-harnessed controller.

The model sees Train labels, label-free Dev features, its own history and a
public-literature snapshot.  Dev labels and Future Test stay outside this
workspace.  Candidate execution is requested through an append-only directory
queue and returns only a reusable Train-CV diagnostic.  The current Dev is run
once by the outer runner after the controller has frozen its decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from controller_harness_contract import MAX_CANDIDATE_EXECUTIONS
from controller_harness_contract import ALLOWED_TOOLS
from harness_evolution import baseline_profile, validate_profile
from market_rsi import canonical, digest, fresh_json, identifier
from objective_contract import (pilot_reference_objective_contract,
                                validate_objective_contract)
from prediction_stream import PUBLIC_FIELDS, TRAIN_FIELDS, finite
from training_population_policy import audit_open_train


SCHEMA = "market_controller_workspace_v2"
DATA_SCHEMA = "market_controller_train_dev_v1"
LITERATURE_SCHEMA = "market_public_literature_snapshot_v1"
ALGORITHM_SCHEMA = "market_controller_algorithm_catalog_v1"
GUIDE_SCHEMA = "market_controller_research_guide_v1"
MAX_PAGE_ROWS = 100
MAX_HISTORY_BYTES = 1_048_576
MAX_LITERATURE_RESULTS = 8


def default_research_guide() -> dict:
    return {
        "schema": GUIDE_SCHEMA,
        "purpose": "Fixed harness guidance for traceable research; it is not a controller-written learned guide and does not prescribe the answer.",
        "steps_are_required": False,
        "steps": [
            "Read the frozen objective contract before studying models or features.",
            "State the prediction target, available features, split boundary and fixed metric.",
            "Measure or reconstruct the simplest valid baseline before adding complexity.",
            "Measure target difficulty: unchanged fraction, RMSE in probability basis points, and error by day and whole game.",
            "Treat rows as autocorrelated observations, not independent samples; inspect days, whole games, markets, and move-size bands.",
            "If flat rows dominate, you may use causal activity sampling, opened-Train-only stratification with capped weights, or a separate activity head, but preserve the original population and report its unweighted score.",
            "For numerical conditioning you may fit a centered or scaled Train-only delta target, but convert predictions back to midpoint units before the unchanged runner score.",
            "Search relevant literature and link any cited paper IDs to the candidate rationale.",
            "State one falsifiable hypothesis and the expected failure condition.",
            "Prefer one main algorithmic change per immutable candidate version.",
            "Run only through the runner; compare reusable Train-CV diagnostics on the same rows.",
            "Classify a failure as candidate, data, protocol or infrastructure before reacting.",
            "Select one executed candidate and record evidence, limitations and rejected alternatives.",
        ],
        "logging": {
            "literature": "Every query and returned paper is recorded automatically.",
            "algorithms": "Every catalog view, candidate rationale, source hash, execution and selection is recorded automatically.",
            "failed_actions": "Failed searches, writes, executions and submissions remain in the append-only logs.",
        },
        "freedom": "The controller may combine, modify or create methods outside the catalog.",
        "controller_chooses": ["model hypothesis", "action order", "whether to search",
                               "algorithm", "features", "training transformation",
                               "diagnostics", "candidate count"],
        "memory_mode": "archive_only",
        "controller_may_rewrite_this_guide": False,
        "forbidden": ["Future-Test access", "Dev-label access", "changing the frozen objective",
                      "changing the scorer",
                      "reusing a consumed Dev block for evaluation", "changing the data lifecycle",
                      "filtering or weighting Dev/Test membership using future target movement",
                      "dropping failed rows", "unlogged paid execution"],
        "data_lifecycle": {
            "learning_access": "All Train and previously scored Dev data and labels are available.",
            "current_dev": "Features only; it is scored once after the controller freezes one candidate and exits.",
            "train_cv": "Candidate iterations may see only reusable diagnostics computed from already-open Train data.",
            "score_visibility": "The sealed Dev score first appears in the next round's Archive.",
            "promotion": "The scored Dev block becomes Train for the next round.",
            "next_evaluation": "Every later round must use a fresh sealed Dev block.",
            "transfer": "Sealed until every final submission is frozen.",
            "enforcement": "Runner-owned harness state; this guide cannot change it.",
        },
    }


def default_algorithm_catalog() -> dict:
    common = {"dependencies": ["python-standard-library"], "controller_may_modify": True}
    algorithms = [
        {**common, "algorithm_id": "persistence-baseline", "family": "baseline",
         "summary": "Predict from the latest allowed quoted probability or a simple constant.",
         "use_when": "Establishing the minimum valid benchmark and detecting target leakage.",
         "assumptions": ["The latest allowed quote is available at decision time."],
         "cost_class": "very-low", "risks": ["Can hide an overly easy or leaked target."],
         "paper_ids": []},
        {**common, "algorithm_id": "regularized-linear-model", "family": "linear",
         "summary": "Fit a regularized linear relationship between engineered features and target.",
         "use_when": "Effects are approximately additive and a transparent baseline is useful.",
         "assumptions": ["A stable relation transfers from Train to Dev."],
         "cost_class": "low", "risks": ["Scale sensitivity", "distribution shift"],
         "paper_ids": ["cont-kukanov-stoikov-2010"]},
        {**common, "algorithm_id": "queue-imbalance-model", "family": "market-microstructure",
         "summary": "Use bid/ask queue imbalance and spread to model short-horizon price movement.",
         "use_when": "Top-of-book depth is reliable and the horizon is short.",
         "assumptions": ["Displayed size has predictive content", "Book states are synchronized"],
         "cost_class": "low", "risks": ["Stale size", "venue-specific behavior"],
         "paper_ids": ["gould-bonart-2015", "cont-kukanov-stoikov-2010"]},
        {**common, "algorithm_id": "online-logistic-update", "family": "online-learning",
         "summary": "Update bounded coefficients sequentially as labeled observations arrive.",
         "use_when": "Relationships drift and labels arrive in chronological order.",
         "assumptions": ["Only past labels are used", "Update order is chronological"],
         "cost_class": "low", "risks": ["Learning-rate instability", "non-binary targets"],
         "paper_ids": []},
        {**common, "algorithm_id": "probability-recalibration", "family": "calibration",
         "summary": "Map raw probabilities to better calibrated probabilities using held-out Train data.",
         "use_when": "Ranking is useful but probabilities are systematically biased.",
         "assumptions": ["A calibration subset can be isolated without leakage."],
         "cost_class": "low", "risks": ["Small-sample overfit", "reduced sharpness"],
         "paper_ids": ["guo-et-al-2017", "arrieta-ibarra-et-al-2022"]},
        {**common, "algorithm_id": "weighted-ensemble", "family": "ensemble",
         "summary": "Combine independently motivated predictors with weights fit on Train only.",
         "use_when": "Component errors differ and every component is already auditable.",
         "assumptions": ["Weights are selected without Dev-label tuning."],
         "cost_class": "medium", "risks": ["Hidden multiple testing", "correlated errors"],
         "paper_ids": []},
    ]
    return {"schema": ALGORITHM_SCHEMA, "algorithms": algorithms,
            "catalog_is_exhaustive": False,
            "note": "This is a capability map, not a list of required choices."}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _regular(path: Path, maximum: int = 16 * 1024 * 1024) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized controller input")
    return path.read_bytes()


def _json(path: Path, maximum: int = 16 * 1024 * 1024):
    return json.loads(_regular(path, maximum))


def _write(path: Path, value) -> None:
    fresh_json(path, value)
    os.chmod(path, 0o600)


def _artifact(path: Path, split: str) -> dict:
    value = _json(path)
    if (not isinstance(value, dict) or value.get("schema") != "market_permitted_rows_v1"
            or value.get("split") != split or not isinstance(value.get("rows"), list)
            or not value["rows"] or not isinstance(value.get("feature_names"), list)):
        raise ValueError("invalid permitted Train/Dev artifact")
    fields = TRAIN_FIELDS
    if any(not isinstance(row, dict) or set(row) != fields for row in value["rows"]):
        raise ValueError("unexpected Train/Dev row schema")
    return value


def _public_dev(row: dict) -> dict:
    return {key: row[key] for key in PUBLIC_FIELDS}


def prepare_workspace(
    output: Path,
    *,
    session_id: str,
    experiment_id: str,
    task_id: str,
    arm: str,
    train_path: Path,
    dev_path: Path,
    own_history: dict,
    literature_snapshot: dict,
    opaque_test_commitment: str,
    objective_contract: dict | None = None,
    research_guide: dict | None = None,
    algorithm_catalog: dict | None = None,
    harness_profile: dict | None = None,
) -> dict:
    """Create one new controller-visible workspace without Dev labels."""
    for value in (session_id, experiment_id, task_id, arm):
        identifier(value)
    if (len(opaque_test_commitment) != 64
            or any(ch not in "0123456789abcdef" for ch in opaque_test_commitment)):
        raise ValueError("opaque Test commitment required")
    if (not isinstance(own_history, dict)
            or len(canonical(own_history).encode()) > MAX_HISTORY_BYTES):
        raise ValueError("bounded own-history object required")
    if (not isinstance(literature_snapshot, dict)
            or literature_snapshot.get("schema") != LITERATURE_SCHEMA
            or not isinstance(literature_snapshot.get("papers"), list)):
        raise ValueError("frozen public-literature snapshot required")
    if objective_contract is None:
        objective_contract = pilot_reference_objective_contract(experiment_id)
    objective_contract = validate_objective_contract(
        objective_contract, experiment_id=experiment_id
    )
    if (arm == "archive-self-improvement"
            and objective_contract["selection"]["evidence_class"] != "formal_learning"):
        raise ValueError("formal controller workspace requires a formal frozen objective")
    research_guide = default_research_guide() if research_guide is None else research_guide
    algorithm_catalog = default_algorithm_catalog() if algorithm_catalog is None else algorithm_catalog
    harness_profile = baseline_profile(ALLOWED_TOOLS) if harness_profile is None else harness_profile
    from archive_snapshot import validate_history
    history_check = validate_history(own_history)
    profile_sha256 = hashlib.sha256((canonical(harness_profile) + "\n").encode()).hexdigest()
    if (not history_check["legacy_empty"]
            and own_history["harness_profile_sha256"] != profile_sha256):
        raise ValueError("Archive history belongs to a different H0 harness")
    if (not isinstance(research_guide, dict) or research_guide.get("schema") != GUIDE_SCHEMA
            or not isinstance(research_guide.get("steps"), list)):
        raise ValueError("frozen controller research guide required")
    if (not isinstance(algorithm_catalog, dict)
            or algorithm_catalog.get("schema") != ALGORITHM_SCHEMA
            or not isinstance(algorithm_catalog.get("algorithms"), list)
            or len({item.get("algorithm_id") for item in algorithm_catalog["algorithms"]})
            != len(algorithm_catalog["algorithms"])):
        raise ValueError("frozen controller algorithm catalog required")
    validate_profile(harness_profile, allowed_tools=ALLOWED_TOOLS)

    train = _artifact(Path(train_path), "train")
    dev = _artifact(Path(dev_path), "dev")
    if (train["experiment_id"] != dev["experiment_id"]
            or train["task_id"] != task_id or dev["task_id"] != task_id
            or train["feature_names"] != dev["feature_names"]):
        raise ValueError("Train/Dev task binding changed")
    train_games = {row["game_id"] for row in train["rows"]}
    dev_games = {row["game_id"] for row in dev["rows"]}
    if train_games & dev_games:
        raise ValueError("Train and Dev games overlap")

    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "execution-requests").mkdir(mode=0o700)
    (output / "execution-results").mkdir(mode=0o700)
    data = {
        "schema": DATA_SCHEMA,
        "experiment_id": experiment_id,
        "task_id": task_id,
        "feature_names": train["feature_names"],
        "train": train["rows"],
        "dev": [_public_dev(row) for row in dev["rows"]],
        "dev_labels_visible": False,
    }
    _write(output / "train-dev-public.json", data)
    _write(output / "own-history.json", own_history)
    _write(output / "literature-snapshot.json", literature_snapshot)
    _write(output / "research-guide.json", research_guide)
    _write(output / "algorithm-catalog.json", algorithm_catalog)
    _write(output / "harness-profile.json", harness_profile)
    _write(output / "objective-contract.json", objective_contract)
    files = {}
    for name in ("train-dev-public.json", "own-history.json", "literature-snapshot.json",
                 "research-guide.json", "algorithm-catalog.json", "harness-profile.json",
                 "objective-contract.json"):
        path = output / name
        files[name] = {"sha256": _sha(path), "bytes": path.stat().st_size}
    manifest = {
        "schema": SCHEMA,
        "session_id": session_id,
        "experiment_id": experiment_id,
        "source_experiment_id": train["experiment_id"],
        "task_id": task_id,
        "arm": arm,
        "opaque_test_commitment": opaque_test_commitment,
        "objective_contract_sha256": objective_contract["objective_contract_sha256"],
        "files": files,
        "limits": {
            "max_page_rows": MAX_PAGE_ROWS,
            "max_candidate_executions": MAX_CANDIDATE_EXECUTIONS,
            "max_literature_results": MAX_LITERATURE_RESULTS,
        },
        "dev_labels_in_workspace": False,
        "future_test_in_workspace": False,
    }
    _write(output / "controller-workspace.json", manifest)
    validate_workspace(output)
    return manifest


def validate_workspace(workspace: Path) -> dict:
    workspace = Path(workspace).resolve()
    manifest = _json(workspace / "controller-workspace.json")
    if (not isinstance(manifest, dict) or set(manifest) != {
        "schema", "session_id", "experiment_id", "source_experiment_id", "task_id", "arm",
        "opaque_test_commitment", "objective_contract_sha256", "files", "limits", "dev_labels_in_workspace",
        "future_test_in_workspace",
    } or manifest["schema"] != SCHEMA or manifest["dev_labels_in_workspace"] is not False
            or manifest["future_test_in_workspace"] is not False
            or manifest["limits"] != {
                "max_page_rows": MAX_PAGE_ROWS,
                "max_candidate_executions": MAX_CANDIDATE_EXECUTIONS,
                "max_literature_results": MAX_LITERATURE_RESULTS,
            }):
        raise ValueError("controller workspace manifest changed")
    for value in (manifest["session_id"], manifest["experiment_id"],
                  manifest["source_experiment_id"], manifest["task_id"], manifest["arm"]):
        identifier(value)
    if set(manifest["files"]) != {
            "train-dev-public.json", "own-history.json", "literature-snapshot.json",
            "research-guide.json", "algorithm-catalog.json", "harness-profile.json",
            "objective-contract.json"}:
        raise ValueError("controller visible-file set changed")
    for name, receipt in manifest["files"].items():
        path = workspace / name
        raw = _regular(path)
        if receipt != {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}:
            raise ValueError("controller visible input changed")
    data = _json(workspace / "train-dev-public.json")
    if (set(data) != {"schema", "experiment_id", "task_id", "feature_names", "train", "dev",
                     "dev_labels_visible"} or data["schema"] != DATA_SCHEMA
            or data["experiment_id"] != manifest["experiment_id"]
            or data["task_id"] != manifest["task_id"] or data["dev_labels_visible"] is not False
            or any(set(row) != TRAIN_FIELDS for row in data["train"])
            or any(set(row) != PUBLIC_FIELDS for row in data["dev"])):
        raise ValueError("controller public data boundary changed")
    literature = _json(workspace / "literature-snapshot.json")
    if literature.get("schema") != LITERATURE_SCHEMA or not isinstance(literature.get("papers"), list):
        raise ValueError("literature snapshot changed")
    guide = _json(workspace / "research-guide.json")
    if guide.get("schema") != GUIDE_SCHEMA or not isinstance(guide.get("steps"), list):
        raise ValueError("controller research guide changed")
    catalog = _json(workspace / "algorithm-catalog.json")
    algorithms = catalog.get("algorithms")
    if (catalog.get("schema") != ALGORITHM_SCHEMA or not isinstance(algorithms, list)
            or len({item.get("algorithm_id") for item in algorithms}) != len(algorithms)):
        raise ValueError("controller algorithm catalog changed")
    validate_profile(_json(workspace / "harness-profile.json"), allowed_tools=ALLOWED_TOOLS)
    objective = validate_objective_contract(
        _json(workspace / "objective-contract.json"),
        experiment_id=manifest["experiment_id"],
    )
    if objective["objective_contract_sha256"] != manifest["objective_contract_sha256"]:
        raise ValueError("controller workspace objective commitment changed")
    from archive_snapshot import validate_history
    history = _json(workspace / "own-history.json")
    history_check = validate_history(history)
    if (not history_check["legacy_empty"]
            and history["harness_profile_sha256"]
            != _sha(workspace / "harness-profile.json")):
        raise ValueError("controller workspace changed its Archive H0 harness")
    return manifest


def read_research_guide(workspace: Path) -> dict:
    validate_workspace(workspace)
    return _json(Path(workspace) / "research-guide.json")


def read_harness_profile(workspace: Path) -> dict:
    """Return the active inner harness profile; outer authority stays in code."""
    validate_workspace(workspace)
    return _json(Path(workspace) / "harness-profile.json")


def read_objective_contract(workspace: Path) -> dict:
    """Return the read-only objective frozen before the Dev schedule."""
    manifest = validate_workspace(workspace)
    value = _json(Path(workspace) / "objective-contract.json")
    if value["objective_contract_sha256"] != manifest["objective_contract_sha256"]:
        raise ValueError("frozen objective does not match workspace")
    return value


def list_algorithms(workspace: Path, family: str | None = None) -> dict:
    validate_workspace(workspace)
    catalog = _json(Path(workspace) / "algorithm-catalog.json")
    if family is not None and (not isinstance(family, str) or not family.strip()):
        raise ValueError("nonempty algorithm family required")
    items = catalog["algorithms"]
    if family is not None:
        items = [item for item in items if item.get("family") == family]
    return {"schema": catalog["schema"], "catalog_is_exhaustive": False,
            "algorithms": [{key: item[key] for key in
                            ("algorithm_id", "family", "summary", "cost_class")}
                           for item in items],
            "catalog_sha256": _sha(Path(workspace) / "algorithm-catalog.json")}


def inspect_algorithm(workspace: Path, algorithm_id: str) -> dict:
    validate_workspace(workspace)
    if not isinstance(algorithm_id, str) or not algorithm_id.strip():
        raise ValueError("nonempty algorithm ID required")
    catalog = _json(Path(workspace) / "algorithm-catalog.json")
    matches = [item for item in catalog["algorithms"] if item.get("algorithm_id") == algorithm_id]
    if len(matches) != 1:
        raise ValueError("unknown algorithm ID")
    return {"algorithm": matches[0],
            "catalog_sha256": _sha(Path(workspace) / "algorithm-catalog.json")}


def inspect(workspace: Path, arguments: dict) -> dict:
    manifest = validate_workspace(workspace)
    data = _json(Path(workspace) / "train-dev-public.json")
    view = arguments.get("view", "summary")
    if view == "summary" and set(arguments) <= {"view", "split"}:
        selected = arguments.get("split")
        if selected not in {None, "train", "dev"}:
            raise ValueError("summary split must be train or dev")
        train, dev = data["train"], data["dev"]
        target = [finite(row["target"]) for row in train]
        result = {
            "schema": "market_controller_data_summary_v1",
            "task_id": manifest["task_id"],
            "objective_id": _json(
                Path(workspace) / "objective-contract.json"
            )["objective_id"],
            "objective_contract_sha256": manifest["objective_contract_sha256"],
            "feature_names": data["feature_names"],
            "candidate_contract": {
                "language": "python3",
                "dependencies": "Python standard library only",
                "required_functions": ["fit(train_rows, feature_names)",
                                       "predict(model, public_row)"],
                "prediction_range": [0.0, 1.0],
                "network": "disabled",
                "evaluation_delivery": "one public Train-CV row at a time",
                "dev_labels_visible": False,
                "visible_execution_metric": "reusable_train_cv_only",
                "sealed_dev_score_returned_this_session": False,
            },
            "train": {"rows": len(train), "games": len({r["game_id"] for r in train}),
                      "first_decision_ms": train[0]["decision_ms"],
                      "last_decision_ms": train[-1]["decision_ms"],
                      "target_mean": sum(target) / len(target)},
            "dev": {"rows": len(dev), "games": len({r["game_id"] for r in dev}),
                    "first_decision_ms": dev[0]["decision_ms"],
                    "last_decision_ms": dev[-1]["decision_ms"],
                    "labels_visible": False},
            "data_sha256": manifest["files"]["train-dev-public.json"]["sha256"],
            "open_train_population_audit": audit_open_train(train),
        }
        if selected is not None:
            result["selected_split"] = selected
        return result
    if view == "rows" and set(arguments) <= {"view", "split", "offset", "limit"}:
        split = arguments.get("split")
        offset, limit = arguments.get("offset", 0), arguments.get("limit", 25)
        if (split not in {"train", "dev"} or type(offset) is not int or offset < 0
                or type(limit) is not int or not 1 <= limit <= MAX_PAGE_ROWS):
            raise ValueError("invalid bounded Train/Dev page")
        rows = data[split]
        return {"split": split, "offset": offset, "limit": limit, "total": len(rows),
                "rows": rows[offset:offset + limit], "labels_visible": split == "train",
                "data_sha256": manifest["files"]["train-dev-public.json"]["sha256"]}
    raise ValueError("invalid inspect_train_dev arguments")


def search_literature(workspace: Path, query: str, max_results: int = 5) -> dict:
    validate_workspace(workspace)
    if (not isinstance(query, str) or not query.strip() or len(query) > 1000
            or type(max_results) is not int or not 1 <= max_results <= MAX_LITERATURE_RESULTS):
        raise ValueError("invalid literature query")
    snapshot = _json(Path(workspace) / "literature-snapshot.json")
    terms = {term.lower() for term in query.split() if term.strip()}
    ranked = []
    for paper in snapshot["papers"]:
        if not isinstance(paper, dict) or set(paper) != {
                "paper_id", "title", "url", "year", "abstract", "content_sha256"}:
            raise ValueError("literature paper schema changed")
        haystack = f"{paper['title']} {paper['abstract']}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            ranked.append((score, paper["paper_id"], paper))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return {"query": query, "snapshot_sha256": _sha(Path(workspace) / "literature-snapshot.json"),
            "results": [paper for _, _, paper in ranked[:max_results]]}


class ExecutionQueue:
    def __init__(self, workspace: Path, *, timeout_seconds: int = 300):
        self.workspace = Path(workspace).resolve()
        self.manifest = validate_workspace(self.workspace)
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
            raise ValueError("bounded execution wait required")
        self.timeout_seconds = timeout_seconds

    def request(self, candidate_name: str) -> dict:
        if (not isinstance(candidate_name, str) or not candidate_name.endswith(".py")
                or "/" in candidate_name or "\\" in candidate_name):
            raise ValueError("flat Python candidate required")
        candidate = self.workspace / candidate_name
        source = _regular(candidate, 131_072)
        requests = self.workspace / "execution-requests"
        claimed = sorted(requests.glob("*.json"))
        if len(claimed) >= MAX_CANDIDATE_EXECUTIONS:
            raise ValueError("controller candidate-execution allowance exhausted")
        index = len(claimed) + 1
        execution_id = f"{self.manifest['session_id']}-execution-{index:02d}"
        request = {
            "schema": "market_controller_execution_request_v1",
            "execution_id": execution_id,
            "session_id": self.manifest["session_id"],
            "experiment_id": self.manifest["experiment_id"],
            "task_id": self.manifest["task_id"],
            "candidate_name": candidate_name,
            "candidate_sha256": hashlib.sha256(source).hexdigest(),
            "workspace_manifest_sha256": digest(self.manifest),
            "evaluation_role": "train_cv",
            "automatic_retry": False,
        }
        _write(requests / f"{execution_id}.json", request)
        result_path = self.workspace / "execution-results" / f"{execution_id}.json"
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if result_path.exists():
                result = _json(result_path, 2 * 1024 * 1024)
                if (not isinstance(result, dict)
                        or result.get("schema") != "market_controller_execution_result_v1"
                        or result.get("execution_id") != execution_id
                        or result.get("request_sha256") != digest(request)
                        or result.get("candidate_sha256") != request["candidate_sha256"]
                        or result.get("evaluation_role") != "train_cv"
                        or result.get("execution_verified") is not True
                        or result.get("future_test_used") is not False
                        or result.get("automatic_retry") is not False):
                    raise ValueError("controller execution result is not independently bound")
                if result.get("status") not in {"completed", "candidate_failed"}:
                    raise ValueError("runner-owned candidate execution failed at the infrastructure layer")
                return result
            time.sleep(0.05)
        raise TimeoutError("runner-owned candidate execution did not return before deadline")
