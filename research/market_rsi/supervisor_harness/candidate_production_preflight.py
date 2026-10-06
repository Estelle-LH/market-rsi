"""Read-only fresh-admission checks, not execution authority or containment.

Parent metadata is meaningful only inside the independently reviewed committed
source set. This checker verifies that binding; it cannot prove source semantics.
Existing completed receipts must recover without running a new preflight.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import signal
import subprocess
import tempfile

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import continuous_discovery_batch as recorder
from supervisor_harness import opened_train_discovery_worker as w

EXPECTED_VERSIONS = {"python": "3.12.3", "numpy": "1.26.4",
                     "scipy": "1.14.0", "sklearn": "1.6.1"}
PROBE_SECONDS = 20
PROBE = ("import sys,json,numpy,scipy,sklearn; "
         "print(json.dumps({'versions':{'python':'.'.join(map(str,sys.version_info[:3])),"
         "'numpy':numpy.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__},"
         "'executable':sys.executable,'prefix':sys.prefix},sort_keys=True))")
PARENT_FIELDS = {"schema", "candidate_id", "module", "contract_sha256",
                 "research_parent_sha256", "comparison_incumbent_sha256", "mode",
                 "adapter_sources", "accepted_reference"}
MODES = {"legacy_c1_c7": "research/market_rsi/experiments/nfl_ingame_candidate_evidence_adapter.py",
         "accepted_prediction_reference": "research/market_rsi/experiments/nfl_ingame_prediction_reference.py"}
LEGACY_PARENTS = {"489d8268bd5243d94df9396f6dd5d616acfeab2d23f29d0e9e5903b7f156cce5",
                  "f5a80888069140a78ab637cf0e03a7bf3df3da2458151323a43e696bf88b8085"}


def _probe(alias, repo):
    """Only frozen dependency imports, bounded output/time and worker-equivalent env."""
    env = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", **w.THREADS}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        child = subprocess.Popen([alias, "-B", "-c", PROBE],
            cwd=Path(repo) / "research/market_rsi", env=env, stdout=stdout,
            stderr=stderr, start_new_session=True)
        try:
            code = child.wait(timeout=PROBE_SECONDS)
        except BaseException as error:
            if child.poll() is None:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait()
            if isinstance(error, subprocess.TimeoutExpired):
                raise ValueError("bounded dependency import probe timed out") from error
            raise
        stdout.seek(0); stderr.seek(0)
        output, errors = stdout.read(4097), stderr.read(4097)
    if code != 0 or len(output) > 4096 or errors:
        raise ValueError("dependency import probe failed or output exceeded bound")
    value = c._json(output)
    if (set(value) != {"versions", "executable", "prefix"}
            or value["versions"] != EXPECTED_VERSIONS
            or value["executable"] != alias
            or value["prefix"] != str(Path(alias).parent.parent)):
        raise ValueError("dependency versions or original virtualenv alias drift")
    return value


def _committed(relative, request, repo):
    if type(relative) is not str or relative not in request["files"]:
        raise ValueError("parent capability must belong to reviewed source files")
    path = Path(repo) / relative
    if (Path(relative).is_absolute() or ".." in Path(relative).parts
            or path.resolve() != path or not path.is_file()):
        raise ValueError("regular committed capability source required")
    blob = subprocess.check_output(["git", "show", request["source_commit"] + ":" + relative],
                                   cwd=repo, timeout=PROBE_SECONDS)
    if hashlib.sha256(blob).hexdigest() != request["files"][relative] or w.sha(path) != request["files"][relative]:
        raise ValueError("committed capability source hash drift")
    return path


def _parent(parent_check, request, contract, repo):
    path = _committed(parent_check, request, repo)
    metadata = c._json(path.read_bytes())
    expected = {"schema": "candidate_parent_support_v1", "candidate_id": request["candidate_id"],
        "module": request["module"], "contract_sha256": request["spec_sha256"],
        "research_parent_sha256": contract["actual_parent_sha256"],
        "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"]}
    if (set(metadata) != PARENT_FIELDS or any(metadata[key] != value for key, value in expected.items())
            or metadata["mode"] not in MODES or type(metadata["adapter_sources"]) is not dict
            or MODES[metadata["mode"]] not in metadata["adapter_sources"]):
        raise ValueError("independently reviewed parent capability binding drift")
    for relative, digest in metadata["adapter_sources"].items():
        _committed(relative, request, repo)
        if request["files"][relative] != digest:
            raise ValueError("parent adapter source hash drift")
    if metadata["mode"] == "legacy_c1_c7":
        if metadata["accepted_reference"] is not None or expected["research_parent_sha256"] not in LEGACY_PARENTS:
            raise ValueError("legacy replay supports only frozen C1/C7 parents")
    else:
        reference = metadata["accepted_reference"]
        if type(reference) is not dict or set(reference) != {"reference", "acceptance_binding"}:
            raise ValueError("independent accepted parent reference binding required")
        accepted = c._read(reference["acceptance_binding"])
        from experiments import nfl_ingame_prediction_reference as adapter
        if w.sha(Path(adapter.__file__).resolve()) != metadata["adapter_sources"][MODES[metadata["mode"]]]:
            raise ValueError("loaded parent header adapter differs from reviewed source")
        adapter.validate_header(reference["reference"], accepted)
        if reference["reference"]["runner"]["sha256"] != expected["research_parent_sha256"]:
            raise ValueError("parent reference lacks independently accepted identity")
        if len({item["path"] for item in accepted["reviews"].values()}) != 3:
            raise ValueError("distinct independent original reviews required")
        for original in [reference["reference"]["runner"], *accepted["reviews"].values()]:
            c._read(original, True)
        hashes, root = reference["reference"]["artifact_hashes"], Path(reference["reference"]["artifact_root"])
        if type(hashes) is not dict or not adapter.ARTIFACTS <= set(hashes):
            raise ValueError("complete comparison artifacts required before admission")
        for name, digest in hashes.items():
            if type(name) is not str or Path(name).name != name or name in {".", ".."}:
                raise ValueError("original comparison artifact basename required")
            c._read({"path": str(root / name), "sha256": digest}, True)
    return {"mode": metadata["mode"], "metadata_sha256": w.sha(path),
            "adapter_sources": metadata["adapter_sources"]}


def preflight(batch, request_binding, review_binding, contract_binding, repo, *, parent_check=None):
    """Validate fresh admission before select/reservation; never import a candidate.

    The caller must first verify original decision/authority admission as the
    existing handoff does. No supplied time, allowance/refund or request expansion.
    """
    if type(batch) is not recorder.ContinuousDiscoveryBatch:
        raise ValueError("original native recorder required")
    if batch._allow_test_clock:
        if (not callable(batch._clock) or not batch.root.is_relative_to(Path(tempfile.gettempdir()).resolve())):
            raise ValueError("test clock requires genuine temporary native fixture")
    elif batch._clock is not None:
        raise ValueError("production recorder must own its real clock")
    moment = batch._trusted_now(None, "preflight time")
    state = batch.snapshot(); batch._assert_live_batch(state, moment)
    request, review, contract = (c._read(binding) for binding in
                               (request_binding, review_binding, contract_binding))
    required_review = {"schema": "reviewed_candidate_request_v1", "passed": True,
        "batch_id": state["batch_id"], "request_sha256": request_binding["sha256"],
        "contract_sha256": contract_binding["sha256"], "source_commit": request["source_commit"],
        "files": request["files"], "semantic_source_matches_decision": True,
        "research_parent_sha256": contract["actual_parent_sha256"],
        "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"]}
    if (any(type(review.get(key)) is not type(value) or review.get(key) != value
            for key, value in required_review.items()) or request["spec_sha256"] != contract_binding["sha256"]
            or request["candidate_id"] != contract["candidate_id"]
            or request["max_fits"] > contract["resources"]["fits"]
            or request["max_wall_seconds"] > contract["resources"]["seconds"]):
        raise ValueError("reviewed request/contract/source drift")
    w.validate(request, repo)
    for relative in request["files"]:
        _committed(relative, request, repo)
    target = Path(request["python"]).resolve(strict=True)
    c._read({"path": str(target), "sha256": request["python_sha256"]}, True)
    c._read({"path": request["memory"], "sha256": request["memory_sha256"]}, True)
    if (any(key in batch.__dict__ for key in ("_trusted_now", "select_controller_pool"))
            or any(type(contract["resources"][key]) is not int for key in ("threads", "rss_bytes", "provider_calls"))
            or contract["resources"]["threads"] != 1
            or contract["resources"]["rss_bytes"] != 1073741824
            or contract["resources"]["provider_calls"] != 0
            or sum(item["stage"] == "execution_claimed" for item in state["branches"]) >= 2):
        raise ValueError("native clock methods or fixed resource boundary drift")
    attempt = request["attempt_id"]
    for relative in ("runs", "worker", "dispatch", "handoff"):
        directory = batch.root / relative
        if (directory.exists() or directory.is_symlink()) and (directory.resolve() != directory or not directory.is_dir()):
            raise ValueError("output isolation directory conflict")
    output = batch.root / "runs" / attempt
    if (output.exists() or output.is_symlink()
            or any(item["attempt_id"] == attempt for item in state["branches"])
            or any((batch.root / "worker").glob(attempt + ".*"))
            or any(path.exists() or path.is_symlink() for path in (
                batch.root / "dispatch" / (attempt + ".json"),
                batch.root / "handoff" / (attempt + ".json")))):
        raise ValueError("fresh output/attempt identity already occupied")
    reserved = 0
    for path in (batch.root / "worker").glob("*.request.json"):
        prior = c._read({"path": str(path), "sha256": w.sha(path)})
        if set(prior) != w.REQUEST_FIELDS or type(prior["max_fits"]) is not int or not 1 <= prior["max_fits"] <= 4:
            raise ValueError("invalid original worker reservation")
        reserved += prior["max_fits"]
    if reserved + request["max_fits"] > 12:
        raise ValueError("unchanged twelve-fit worker reservation ceiling")
    parent = _parent(parent_check, request, contract, repo)
    imports = _probe(request["python"], repo)
    completion = batch._trusted_now(None, "preflight completion")
    state = batch.snapshot(); batch._assert_live_batch(state, completion)
    return {"schema": "candidate_production_preflight_v1", "passed": True,
        "request_sha256": request_binding["sha256"], "review_sha256": review_binding["sha256"],
        "contract_sha256": contract_binding["sha256"], "state_sha256": state["state_sha256"],
        "python_alias": request["python"], "python_sha256": request["python_sha256"],
        "imports": imports, "parent": parent, "output": str(output),
        "preflight_completion_utc": completion.isoformat().replace("+00:00", "Z"),
        "candidate_execution_performed": False, "grants_authority": False}
