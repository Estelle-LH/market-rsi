"""Runner-owned immutable inputs, exclusive calls and append-only research log."""
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import stat
import time
import sys
import importlib.metadata

from data_science_tools.pipeline import BINDINGS, verify_review_files
from market_rsi import digest, file_hash, fresh_json, identifier, load_json
from data_scientist_harness.core_dependency import dependency_identity
from data_scientist_harness import VERSION
from data_scientist_harness.release import (source_files, source_hashes, validate_release,
                                          verify_git_publication, identity, CHANGE_ORIGIN)

ROOT = Path(__file__).resolve().parents[1]


def runtime_identity():
    packages = ("numpy", "scipy", "scikit-learn", "threadpoolctl", "joblib",
                "tinker", "transformers", "tokenizers", "huggingface-hub",
                "httpx", "python-dotenv")
    installed = sorted((str(dist.metadata.get("Name", "")).casefold().replace("_", "-"),
                        dist.version) for dist in importlib.metadata.distributions())
    return {"python":sys.version, "executable":str(Path(sys.executable).resolve()),
            "environment_prefix": str(Path(sys.prefix).resolve()),
            "packages":{k:importlib.metadata.version(k) for k in packages},
            "installed_distributions_sha256": digest(installed),
            "cpu_requirements_sha256": file_hash(ROOT/"data_scientist_harness/requirements-cpu.txt"),
            "shared_core": dependency_identity()}


def resident(path, maximum=300_000_000):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise ValueError("canonical non-symlink runner input required")
    s = path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size > maximum or getattr(s, "st_flags", 0) & 0x40000000:
        raise ValueError("bounded resident regular file required")
    return path


def input_files(path):
    # Read only the legacy input contract, not its mutable trials/archive state.
    names = ("input-result.json", "current-inputs.npz", "label-result.json", "primary-labels.npz",
             "panel-result.json", "objective-proposal.json", "data-use-proposal.json")
    return {name: resident(Path(path)/name) for name in names}


def create(root, *, data_root=None, quality, findings, allowed_dates, purpose,
           prior_archives=(), network=True, release_path=None, planning_context=None,
           aggregate_receipts=()):
    root = Path(root).resolve(); identifier(root.name)
    if root.exists() or purpose not in {
            "canary", "opened_train_research", "source_research", "aggregate_research"}:
        raise ValueError("fresh scoped workspace required")
    dependency_identity()
    runtime = runtime_identity()
    release = load_json(resident(Path(release_path).resolve(), 8_388_608)) if release_path else None
    publication = None
    if release is not None:
        sources = source_hashes(ROOT)
        validate_release(release, sources, runtime)
        publication = verify_git_publication(sources, root=ROOT, commit=release["publication"]["commit"])
    aggregate_only = purpose == "aggregate_research"
    if aggregate_only:
        if (quality is not None or data_root is not None or allowed_dates
                or planning_context is not None or not aggregate_receipts):
            raise ValueError("aggregate research requires receipts and forbids raw data, QA substitution, dates and planning context")
        readiness = {
            "schema": "data_scientist_aggregate_only_quality_v1",
            "status": "aggregate_only",
            "scope": "opened_train_aggregate_only",
            "stages": [],
            "blockers": ["raw input and training are not admitted in aggregate-only research"],
            "component_bindings": dict.fromkeys(BINDINGS),
            "raw_data_admitted": False,
            "training_allowed": False,
            "formal_evaluation_allowed": False,
        }
    else:
        if quality is None or aggregate_receipts:
            raise ValueError("standard workspace requires QA and forbids aggregate-only receipts")
        readiness = verify_review_files(**quality)
    from data_scientist_harness.source_study import validate_context
    validate_context(planning_context, readiness)
    if allowed_dates != sorted(set(allowed_dates)) or (data_root is not None and not allowed_dates):
        raise ValueError("predeclared opened-Train dates required")
    if quality is not None:
        for key in ("spec_path", "review_path"):
            resident(quality[key], 8_388_608)
    inputs = input_files(Path(data_root).resolve()) if data_root is not None else {}
    from data_scientist_harness.sanity import contract_inputs
    sanity_inputs = contract_inputs(Path(data_root).resolve()) if inputs else {}
    if inputs:
        declared = load_json(inputs["data-use-proposal.json"])["plan"]["open_train_utc_dates"]
        if declared != allowed_dates:
            raise ValueError("cannot widen prior Train scope")
    archives = []
    for ref in prior_archives:
        path = resident(ref["path"], 8_388_608)
        if file_hash(path) != ref["sha256"]:
            raise ValueError("prior archive changed")
        body = load_json(path)
        if body.get("schema") != "data_scientist_round_archive_v1":
            raise ValueError("explicit prior round archive required")
        archives.append({"origin": ref, "history_not_current_evidence": body})
    aggregate_sources = []
    for index, ref in enumerate(aggregate_receipts):
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise ValueError("exact aggregate receipt reference required")
        path = resident(Path(ref["path"]).resolve(), 32_000_000)
        if file_hash(path) != ref["sha256"]:
            raise ValueError("aggregate receipt changed")
        aggregate_sources.append((index, path, ref["sha256"]))
    root.mkdir(parents=True, mode=0o700)
    (root/"records").mkdir(); (root/"inputs").mkdir()
    frozen = {}
    for name, path in {**inputs, **sanity_inputs}.items():
        dest = root/"inputs"/name
        shutil.copyfile(path, dest)
        frozen[str(dest)] = file_hash(dest)
        if frozen[str(dest)] != file_hash(path):
            raise ValueError("input changed during copy")
    aggregate_inputs = []
    if aggregate_sources:
        aggregate_root = root / "aggregate-inputs"
        aggregate_root.mkdir(mode=0o700)
        for index, path, sha in aggregate_sources:
            dest = aggregate_root / f"{index:02d}-{path.name}"
            shutil.copyfile(path, dest)
            frozen[str(dest)] = file_hash(dest)
            if frozen[str(dest)] != sha:
                raise ValueError("aggregate receipt changed during copy")
            aggregate_inputs.append({
                "name": dest.name,
                "sha256": sha,
                "bytes": dest.stat().st_size,
            })
    # Freeze the actual implementation and its existing local dependencies.
    code = source_files(ROOT)
    for path in code:
        if path.name.startswith("test_"):
            continue
        resident(path)
        dest = root/"code"/path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        frozen[str(dest)] = file_hash(dest)
    fresh_json(root/"archive-input.json", {"prior_rounds": archives})
    fresh_json(root/"findings.json", findings)
    for name in ("archive-input.json", "findings.json"):
        frozen[str(root/name)] = file_hash(root/name)
    config = {"schema": "data_scientist_workspace_v1", "session_id": root.name, "purpose": purpose,
              "runtime": runtime, "harness_version": VERSION, "release": release,
              "harness_change_origin": CHANGE_ORIGIN, "release_preparation_check": publication,
              "files": frozen, "quality": quality, "allowed_train_dates": allowed_dates,
              "planning_context": planning_context,
              "aggregate_only": aggregate_only,
              "aggregate_inputs": aggregate_inputs,
              "aggregate_input_manifest_sha256": digest(aggregate_inputs),
              "inputs_present": bool(inputs), "input_manifest_sha256": digest({k:file_hash(v) for k,v in inputs.items()}),
              "public_network_enabled": bool(network), "public_fetch_body_cap": 10_000_000,
              "max_calls": 80, "max_trials": 8, "worker_timeout_seconds": 60,
              "formal_evaluation_allowed": False, "paid_execution_tools": False}
    fresh_json(root/"workspace.json", config)
    return file_hash(root/"workspace.json")


class Store:
    def __init__(self, root, manifest_sha256):
        self.root = Path(root).resolve()
        self.expected = manifest_sha256
        self.verify()

    def verify(self):
        resident(self.root/"workspace.json", 8_388_608)
        if file_hash(self.root/"workspace.json") != self.expected:
            raise ValueError("workspace manifest changed")
        self.config = load_json(self.root/"workspace.json")
        if self.config["schema"] != "data_scientist_workspace_v1":
            raise ValueError("wrong workspace schema")
        if (self.config.get("harness_version") != VERSION
                or self.config.get("harness_change_origin") != CHANGE_ORIGIN):
            raise ValueError("workspace harness version differs; never upgrade a running experiment")
        aggregate_only = self.config.get("aggregate_only") is True
        aggregate_inputs = self.config.get("aggregate_inputs")
        inputs_present = self.config.get("inputs_present") is True
        if (aggregate_only != (self.config.get("purpose") == "aggregate_research")
                or not isinstance(aggregate_inputs, list)
                or self.config.get("aggregate_input_manifest_sha256") != digest(
                    aggregate_inputs)
                or (aggregate_only and (inputs_present or not aggregate_inputs))
                or (not aggregate_only and aggregate_inputs)):
            raise ValueError("workspace aggregate/raw mode is inconsistent")
        if self.config["runtime"] != runtime_identity():
            raise ValueError("frozen CPU runtime changed")
        for name, sha in self.config["files"].items():
            resident(name)
            if file_hash(name) != sha:
                raise ValueError("frozen data/code/archive changed")
        if self.config.get("release") is not None:
            self.require_release()
        return self.config

    def require_release(self):
        code = self.root / "code"
        sources = {str(Path(p).relative_to(code)): sha for p, sha in self.config["files"].items()
                   if Path(p).is_relative_to(code)}
        return validate_release(self.config.get("release"), sources, self.config["runtime"])

    def quality(self):
        if self.config.get("aggregate_only"):
            return {
                "schema": "data_scientist_aggregate_only_quality_v1",
                "status": "aggregate_only",
                "scope": "opened_train_aggregate_only",
                "stages": [],
                "blockers": ["raw input and training are not admitted in aggregate-only research"],
                "component_bindings": dict.fromkeys(BINDINGS),
                "raw_data_admitted": False,
                "training_allowed": False,
                "formal_evaluation_allowed": False,
            }
        return verify_review_files(**self.config["quality"])

    def quality_before_training(self):
        if self.config.get("aggregate_only"):
            raise RuntimeError("aggregate-only workspace cannot train or select a trial")
        report = self.quality()
        if not all(s["status"] == "passed" for s in report["stages"][:4]):
            raise RuntimeError("data quality must pass before training; " + ", ".join(report["blockers"]))
        if self.config["purpose"] != "canary":
            self.require_release()
        if not self.config["inputs_present"]:
            raise RuntimeError("no admitted opened-Train input")
        bound = report["component_bindings"]
        if (bound["raw_manifest"] != self.config["input_manifest_sha256"]
                or bound["source_plan"] != file_hash(self.root/"inputs/data-use-proposal.json")):
            raise ValueError("quality review belongs to different input/source")
        from data_scientist_harness.sanity import read_contract
        read_contract(self.root/"inputs", self.config["input_manifest_sha256"], self.config["purpose"])
        return report

    def events(self):
        path = self.root/"activity.jsonl"
        if not path.exists():
            return []
        resident(path, 32_000_000)
        rows, previous = [], None
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                sha = row.pop("record_sha256")
                if row["previous"] != previous or row["sequence"] != len(rows)+1 or digest(row) != sha:
                    raise ValueError("append-only activity ledger corrupted")
                ref = row["record"]
                if file_hash(resident(ref["path"], 8_388_608)) != ref["sha256"]:
                    raise ValueError("research receipt changed")
                rows.append({**row, "record_sha256": sha})
                previous = sha
        return rows

    def records(self, tool=None):
        return [load_json(e["record"]["path"]) for e in self.events()
                if tool is None or e["tool"] == tool]

    def save(self, tool, arguments, result, status):
        events = self.events(); n = len(events)+1
        path = self.root/"records"/f"{n:04d}.json"
        fresh_json(path, {"tool": tool, "arguments": arguments, "result": result, "status": status,
                          "harness_release": identity(self.config)})
        event = {"sequence": n, "previous": events[-1]["record_sha256"] if events else None,
                 "recorded_unix_ns": time.time_ns(), "tool": tool,
                 "record": {"path": str(path), "sha256": file_hash(path)}}
        event["record_sha256"] = digest(event)
        with (self.root/"activity.jsonl").open("a") as stream:
            stream.write(json.dumps(event, sort_keys=True)+"\n"); stream.flush()
            import os
            os.fsync(stream.fileno())
        return {"record_id": f"{n:04d}", "record_sha256": event["record"]["sha256"], **result}

    def get(self, record_id, tool):
        if not isinstance(record_id, str) or len(record_id) != 4 or not record_id.isdigit():
            raise ValueError(f"known record ID required: use the exact four-digit record_id returned by {tool}, not prose or a title")
        self.events()
        path = self.root/"records"/(record_id+".json")
        if not any(e["record"]["path"] == str(path) for e in self.events()):
            raise ValueError("record is not in the append-only ledger")
        record = load_json(path)
        if record["tool"] != tool or record["status"] != "ok":
            matching=[Path(e['record']['path']).stem for e in self.events()
                if e['tool']==tool and load_json(Path(e['record']['path']))['status']=='ok']
            raise ValueError(f"completed matching research record required: {record_id} is {record['tool']} "
                f"with status {record['status']}; expected {tool}. Available successful IDs: {matching}")
        return record

    def get_one_of(self, record_id, tools):
        """Return one successful ledger record from an explicit tool allowlist."""
        if (not isinstance(tools, (tuple, list)) or not tools
                or any(not isinstance(tool, str) or not tool for tool in tools)):
            raise ValueError("nonempty expected tool allowlist required")
        if not isinstance(record_id, str) or len(record_id) != 4 or not record_id.isdigit():
            raise ValueError(
                "known record ID required: use an exact four-digit record_id, not prose or a title")
        self.events()
        path = self.root / "records" / (record_id + ".json")
        if not any(e["record"]["path"] == str(path) for e in self.events()):
            raise ValueError("record is not in the append-only ledger")
        record = load_json(path)
        if record["tool"] not in tools or record["status"] != "ok":
            allowed = ", ".join(tools)
            matching = [
                Path(e["record"]["path"]).stem
                for e in self.events()
                if e["tool"] in tools
                and load_json(Path(e["record"]["path"]))["status"] == "ok"
            ]
            raise ValueError(
                f"completed source-evidence record required: {record_id} is "
                f"{record['tool']} with status {record['status']}; expected one of "
                f"{allowed}. Available successful IDs: {matching}")
        return record

    def lock(self):
        handle = (self.root/"call.lock").open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            handle.close(); raise
        return handle
