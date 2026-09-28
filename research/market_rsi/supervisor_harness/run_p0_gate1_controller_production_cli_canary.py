"""Zero-provider acceptance for the Gate 1 production CLI and Supervisor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness import bounded_live_outer_runner_v3 as shared_outer
from supervisor_harness import gate1_canary_receipt
from supervisor_harness import p0_gate1_controller_supervisor_parent as parent
from supervisor_harness import protocol_source_release
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import frozen_catalog_bytes
from supervisor_harness.p0_gate1_trade_query import SYNTHETIC_CATALOG_COMMITMENT_ID
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_controller_adapter import expected_packet


SCHEMA = "market_p0_gate1_controller_production_cli_canary_v1"
FAILURE_SCHEMA = "market_p0_gate1_controller_production_cli_canary_failure_v1"
CHILD = parent.CANARY_CHILD_ENTRY
LEGACY_RELEASE_COMMIT = "1" * 40
LEGACY_RELEASE_TAG_OBJECT = "2" * 40
_MAX_CHILD_LOG_TAIL_BYTES = 4096
_MAX_CHILD_LOG_FINAL_LINE_CHARS = 512
_SUPERVISOR_RESULT_FIELDS = (
    "schema", "cycle_id", "passed", "child_exit_code",
    "incident_created", "incident_id", "automatic_retry",
    "watchdog_head_sha256",
)


def _regular_file(path: Path) -> bool:
    path = Path(path)
    try:
        return not path.is_symlink() and path.is_file()
    except OSError:
        return False


def _small_json_object(path: Path) -> dict | None:
    path = Path(path)
    try:
        if not _regular_file(path) or path.stat().st_size > 64 * 1024:
            return None
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _is_nonzero_sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and value != "0" * 64
            and all(character in "0123456789abcdef" for character in value))


def _bounded_supervisor_result(value: object,
                               error_type: str | None) -> dict:
    """Keep only the parent's fixed, credential-free result vocabulary."""
    if not isinstance(value, dict):
        return {"returned": False, "error_type": error_type}
    fields = {}
    for name in _SUPERVISOR_RESULT_FIELDS:
        item = value.get(name)
        if item is None or type(item) in {bool, int}:
            fields[name] = item
        elif isinstance(item, str):
            fields[name] = item[:256]
        else:
            fields[name] = "invalid-value-type"
    return {"returned": True, "error_type": error_type, "fields": fields}


def _child_log_evidence(path: Path) -> tuple[str | None, str | None]:
    """Return an exact hash and a bounded, credential-free final log line."""
    path = Path(path)
    if not _regular_file(path):
        return None, None
    try:
        observed_hash = file_hash(path)
        with path.open("rb") as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - _MAX_CHILD_LOG_TAIL_BYTES))
            tail = handle.read(_MAX_CHILD_LOG_TAIL_BYTES)
    except OSError:
        return None, None
    lines = tail.decode("utf-8", errors="replace").splitlines()
    final_line = next((line for line in reversed(lines) if line.strip()), "")
    final_line = "".join(
        character if character.isprintable() else "?"
        for character in final_line)[-_MAX_CHILD_LOG_FINAL_LINE_CHARS:]
    lowered = final_line.lower()
    if any(marker in lowered for marker in (
            "api_key", "api-key", "authorization", "bearer",
            "password", "secret")):
        final_line = "[redacted credential-shaped child-log final line]"
    return observed_hash, final_line


def _write_failure(output: Path, *, cycle_id: str,
                   supervised: object, parent_error_type: str | None,
                   evidence_presence: dict, checks: dict,
                   reasons: list[str], child_log: Path) -> None:
    child_log_sha256, child_log_final_line = _child_log_evidence(child_log)
    fresh_json(Path(output) / "canary-failure.json", {
        "schema": FAILURE_SCHEMA,
        "cycle_id": cycle_id,
        "passed": False,
        "automatic_retry": False,
        "failure_reasons": reasons,
        "supervisor_result": _bounded_supervisor_result(
            supervised, parent_error_type),
        "evidence_presence": evidence_presence,
        "terminal_checks": checks,
        "child_log_sha256": child_log_sha256,
        "child_log_final_line": child_log_final_line,
    })


def execute(output: Path, *, no_catalog: bool = False,
            prior_canary_receipt: Path | None = None,
            prior_canary_sha256: str | None = None,
            release_tag: str | None = None,
            expected_source_sha256: str | None = None) -> dict:
    """Run the ordinary canary path, which always requires an exact prior."""
    if (release_tag is None) != (expected_source_sha256 is None):
        raise ValueError("exact release tag and source must be supplied together")
    verified_publication = None
    if release_tag is not None:
        verified_publication = parent.verified_first_canary_publication(
            release_tag=release_tag,
            expected_source_sha256=expected_source_sha256)
    return _execute(
        output, no_catalog=no_catalog,
        prior_canary_receipt=prior_canary_receipt,
        prior_canary_sha256=prior_canary_sha256,
        bootstrap_capability=None, verified_publication=None,
        ordinary_verified_publication=verified_publication)


def execute_first_canary_bootstrap(
        output: Path, *, release_tag: str,
        expected_source_sha256: str) -> dict:
    """Programmatic-only zero-provider creation of the first current receipt."""
    verified_publication = parent.verified_first_canary_publication(
        release_tag=release_tag,
        expected_source_sha256=expected_source_sha256)
    return _execute(
        output, no_catalog=True,
        prior_canary_receipt=None, prior_canary_sha256=None,
        bootstrap_capability=parent._FIRST_CANARY_BOOTSTRAP_CAPABILITY,
        verified_publication=verified_publication)


def _execute(output: Path, *, no_catalog: bool,
             prior_canary_receipt: Path | None,
             prior_canary_sha256: str | None,
             bootstrap_capability: object | None,
             verified_publication: object | None,
             ordinary_verified_publication: object | None = None) -> dict:
    output = Path(output)
    bootstrap = (bootstrap_capability is
                 parent._FIRST_CANARY_BOOTSTRAP_CAPABILITY)
    if (bootstrap_capability is not None and not bootstrap):
        raise ValueError("invalid first-canary bootstrap capability")
    if bootstrap and not output.is_absolute():
        raise ValueError("absolute first-canary output path required")
    if bootstrap and ordinary_verified_publication is not None:
        raise ValueError("ordinary verified publication cannot bootstrap")
    publication_token = (verified_publication if bootstrap
                         else ordinary_verified_publication)
    publication = (parent._publication_from_token(publication_token)
                   if publication_token is not None else None)
    if not bootstrap and verified_publication is not None:
        raise ValueError("verified publication is bootstrap-only")
    source_hashes = protocol_source_release.source_hashes()
    source_sha = digest(source_hashes)
    if publication is not None and (
            publication["source_sha256"] != source_sha
            or publication["source_hashes"] != source_hashes):
        raise ValueError("verified publication became stale before artifacts")
    if bootstrap and (prior_canary_receipt is not None
                      or prior_canary_sha256 is not None):
        raise ValueError("first-canary bootstrap cannot consume a prior receipt")
    if not bootstrap and (
            prior_canary_receipt is None or prior_canary_sha256 is None):
        raise ValueError("exact prior current-source canary receipt required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh production-CLI canary output required")
    output.mkdir(parents=True, mode=0o700)
    cycle_id = output.name + "-transaction"
    decision = output / "decision.md"
    decision.write_text("synthetic Gate 1 production-CLI canary only\n")
    state = SupervisorGlobalState(output / "global-state", decision)
    state_before = state.initialize()
    budget_root = output / "budget"
    budget = PaidBudget.create(budget_root, {
        "experiment_id": "gate1-production-cli-canary-budget",
        "cap_usd": "1",
        "target_usd": "0.05",
        "buckets_usd": {"setup": "0.5", "repair": "0.5"},
        "authority": "zero-provider production-CLI acceptance canary",
    })
    claims = output / "claims"
    claims.mkdir(mode=0o700)
    packet = output / "controller-input.json"
    packet.write_text(
        json.dumps(expected_packet(), sort_keys=True, indent=2) + "\n")
    runtime = output / "runtime.json"
    fresh_json(runtime, shared_outer.runtime_receipt())
    env_file = output / "offline.env"
    env_file.write_text("MARKET_RSI_OFFLINE_CANARY=1\n")
    tokenizer_cache = output / "tokenizer-cache"
    tokenizer_cache.mkdir(mode=0o700)
    catalog = None
    if not no_catalog:
        catalog = output / "synthetic-train-catalog.json"
        catalog.write_bytes(frozen_catalog_bytes())
    if bootstrap:
        prior_canary_receipt = (
            output / gate1_canary_receipt.FIRST_CANARY_BOOTSTRAP_FILE)
        fresh_json(
            prior_canary_receipt,
            gate1_canary_receipt.first_canary_bootstrap_document(
                publication=publication,
                runtime_sha256=digest(json.loads(runtime.read_text())),
                child_entry=CHILD,
            ))
        prior_canary_sha256 = file_hash(prior_canary_receipt)
    args = SimpleNamespace(
        root=output / cycle_id,
        claim_root=claims,
        global_state_root=output / "global-state",
        decision_doc=decision,
        budget_root=budget_root,
        packet=packet,
        runtime_receipt=runtime,
        env_file=env_file,
        tokenizer_cache=tokenizer_cache,
        catalog=catalog,
        expected_catalog_file_sha256=(file_hash(catalog)
                                      if catalog is not None else None),
        catalog_commitment_id=(SYNTHETIC_CATALOG_COMMITMENT_ID
                               if catalog is not None else None),
        experiment_id="gate1-production-cli-canary-budget",
        budget_cap_usd="1",
        cycle_id=cycle_id,
        expected_packet_file_sha256=file_hash(packet),
        expected_packet_canonical_sha256=digest(expected_packet()),
        expected_head_sha256=state_before["head_sha256"],
        expected_decision_sha256=file_hash(decision),
        prior_canary_receipt=prior_canary_receipt,
        prior_canary_sha256=prior_canary_sha256,
        release_tag=(publication["tag"] if publication is not None
                     else parent.CANARY_RELEASE_TAG),
        expected_release_commit=(publication["commit"]
                                 if publication is not None
                                 else LEGACY_RELEASE_COMMIT),
        expected_release_tag_object=(publication["tag_object"]
                                     if publication is not None
                                     else LEGACY_RELEASE_TAG_OBJECT),
        expected_source_sha256=source_sha,
        supervisor_root=output / "supervisor",
    )
    supervised = None
    parent_error_type = None
    try:
        supervised = parent.run(
            args, child_entry=CHILD,
            bootstrap_capability=bootstrap_capability,
            verified_publication=(verified_publication if bootstrap else None))
    except Exception as exc:  # Convert child/Supervisor failure to one receipt.
        parent_error_type = type(exc).__name__
    budget_after = None
    budget_error_type = None
    try:
        budget_after = budget.snapshot()
    except Exception as exc:
        budget_error_type = type(exc).__name__
    state_after = None
    state_error_type = None
    try:
        state_after = state.snapshot()
    except Exception as exc:
        state_error_type = type(exc).__name__
    jobs = (budget_after.get("jobs")
            if isinstance(budget_after, dict) else None)
    job = jobs.get(cycle_id) if isinstance(jobs, dict) else None
    child_result = args.root / "result.json"
    claim = args.supervisor_root / "supervisor-claim.json"
    supervisor_result = args.supervisor_root / "result.json"
    child_log = args.supervisor_root / "child.log"
    file_json = {
        "child_result": _small_json_object(child_result),
        "supervisor_claim": _small_json_object(claim),
        "supervisor_result": _small_json_object(supervisor_result),
    }
    evidence_presence = {
        "budget_snapshot": isinstance(budget_after, dict),
        "budget_job": isinstance(job, dict),
        "global_state_snapshot": isinstance(state_after, dict),
        "child_result": file_json["child_result"] is not None,
        "supervisor_claim": file_json["supervisor_claim"] is not None,
        "supervisor_result": file_json["supervisor_result"] is not None,
        "child_log": _regular_file(child_log),
    }
    checks = {
        "parent_returned": parent_error_type is None,
        "supervisor_passed": (
            isinstance(supervised, dict)
            and supervised.get("schema") == parent.supervisor.RESULT_SCHEMA
            and supervised.get("cycle_id") == cycle_id
            and supervised.get("passed") is True
            and supervised.get("incident_created") is False
            and supervised.get("child_exit_code") == 0
            and supervised.get("automatic_retry") is False
            and _is_nonzero_sha(
                supervised.get("watchdog_head_sha256"))),
        "supervisor_file_matches_return": (
            isinstance(supervised, dict)
            and file_json["supervisor_result"] == supervised),
        "budget_snapshot_readable": budget_error_type is None,
        "budget_job_metered_terminal": (
            isinstance(job, dict)
            and job.get("job_id") == cycle_id
            and job.get("state") == "metered_terminal"),
        "global_state_snapshot_readable": state_error_type is None,
        "global_state_terminal": (
            isinstance(state_after, dict)
            and state_after.get("active_cycle") is None
            and _is_nonzero_sha(state_after.get("last_review_sha256"))),
        "terminal_files_present": all(
            file_json[name] is not None for name in file_json),
        "child_log_present": evidence_presence["child_log"],
    }
    reasons = [name for name, passed in checks.items() if not passed]
    if reasons:
        _write_failure(
            output, cycle_id=cycle_id, supervised=supervised,
            parent_error_type=parent_error_type,
            evidence_presence=evidence_presence, checks=checks,
            reasons=reasons, child_log=child_log)
        raise RuntimeError(
            "Gate 1 production-CLI acceptance failed: " + ",".join(reasons))
    try:
        terminal_hashes = {
            "child_result_sha256": file_hash(child_result),
            "supervisor_claim_sha256": file_hash(claim),
            "supervisor_result_sha256": file_hash(supervisor_result),
        }
    except OSError:
        reasons = ["terminal_file_hash_failed"]
        checks["terminal_file_hashes"] = False
        _write_failure(
            output, cycle_id=cycle_id, supervised=supervised,
            parent_error_type=parent_error_type,
            evidence_presence=evidence_presence, checks=checks,
            reasons=reasons, child_log=child_log)
        raise RuntimeError(
            "Gate 1 production-CLI acceptance failed: terminal_file_hash_failed")
    result = {
        "schema": (gate1_canary_receipt.BOOTSTRAP_CANARY_SCHEMA
                   if bootstrap else SCHEMA),
        "cycle_id": cycle_id,
        "passed": True,
        "production_parent_used": True,
        "production_cli_arguments_used": True,
        "supervisor_claim_verified_by_child": True,
        "offline_provider_substituted": True,
        "provider_calls": 0,
        "actual_provider_cost_usd": "0",
        "synthetic_ledger_metered_usd": job["metered_usd"],
        "public_fetch_performed": False,
        "formal_data_admitted": False,
        "review_only_without_catalog": no_catalog,
        "automatic_retry": False,
        "packet_file_sha256": file_hash(packet),
        "packet_canonical_sha256": digest(expected_packet()),
        **terminal_hashes,
    }
    if bootstrap:
        result["first_canary_bootstrap_used"] = True
    fresh_json(output / "canary-result.json", result)
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--output", required=True, type=Path)
    value.add_argument("--no-catalog", action="store_true")
    value.add_argument("--prior-canary-receipt", type=Path)
    value.add_argument("--prior-canary-sha256")
    return value


if __name__ == "__main__":
    parsed = parser().parse_args()
    print(json.dumps(execute(
        parsed.output, no_catalog=parsed.no_catalog,
        prior_canary_receipt=parsed.prior_canary_receipt,
        prior_canary_sha256=parsed.prior_canary_sha256),
                     sort_keys=True))
