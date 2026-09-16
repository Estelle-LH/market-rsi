"""Read a bounded root document for an already controller-selected source.

Execution-side acquisition/storage preflight, NOT a new controller decision or
permission to obtain data. Old exact-request document tools are not relaxed.
"""
import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from pinned_source_document import bounded_doc_get, verify_document, MAX_DOC_BYTES
from public_source_metadata import metadata_url


def validate_selected(plan, listing, name):
    if name not in {"README.md", "VALIDATION.md"}:
        raise ValueError("root documentation only, never samples or data")
    if plan.get("proposal_valid") is not True or plan.get("acquisition_admitted") is not False:
        raise ValueError("valid non-acquiring controller proposal required")
    metadata_url(listing["dataset"], listing["revision"])
    selected = {(o["source_id"], o["revision"]) for o in plan["body"]["objects"]}
    if (listing["dataset"], listing["revision"]) not in selected:
        raise ValueError("document source/revision not in controller-selected objects")
    obj = next((o for o in listing["objects"] if o["path"] == name and o["type"] == "file"), None)
    if obj is None or not 0 < obj["advertised_bytes"] <= MAX_DOC_BYTES:
        raise ValueError("bounded advertised root document required")
    return f'https://huggingface.co/datasets/{listing["dataset"]}/raw/{listing["revision"]}/{name}', obj


def run(session, result_audit, directory_receipt, name, output, getter=bounded_doc_get):
    audit = load_json(result_audit)
    decision_path = session / "workspace/submitted-source-review-decision.json"
    decision = load_json(decision_path)
    if audit.get("passed") is not True or audit.get("result_sha256") != digest(
            {k: v for k, v in audit.items() if k != "result_sha256"}) \
            or file_hash(decision_path) != audit["decision_sha256"] or decision["action"] != "propose":
        raise ValueError("unchanged audited controller decision required")
    plan_path = session / "workspace/plans" / decision["artifact_id"] / "result.json"
    if file_hash(plan_path) != audit["inputs"][str(plan_path)]:
        raise ValueError("selected proposal changed")
    plan = load_json(plan_path)
    listing = load_json(directory_receipt)
    if listing.get("passed") is not True or listing.get("result_sha256") != digest(
            {k: v for k, v in listing.items() if k != "result_sha256"}) \
            or file_hash(directory_receipt.parent / "response.body.json") != listing["response_body_sha256"]:
        raise ValueError("unchanged independent directory receipt required")
    url, obj = validate_selected(plan, listing, name)
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / "claim.json", {
        "purpose": "selected_source_storage_preflight_document_only", "url": url,
        "result_audit_sha256": file_hash(result_audit), "decision_sha256": file_hash(decision_path),
        "proposal_sha256": file_hash(plan_path), "directory_receipt_sha256": file_hash(directory_receipt),
        "max_document_bytes": MAX_DOC_BYTES, "market_data_acquisition": False,
        "model_requested_exact_document": False, "automatic_retry": False,
    })
    try:
        body, http = getter(url)
        verify_document(body, obj)
        with (output / "document.txt").open("xb") as stream:
            stream.write(body)
        report = {
            "schema": "selected_source_preflight_document_v1", "passed": True,
            "dataset": listing["dataset"], "revision": listing["revision"], "name": name,
            "url": url, "http": http, "document_sha256": hashlib.sha256(body).hexdigest(),
            "claim_sha256": file_hash(output / "claim.json"), "new_market_data_bytes": 0,
            "new_model_calls": 0, "source_choice_changed": False, "acquisition_admitted": False,
            "inspector_sha256": file_hash(Path(__file__)),
        }
        report["result_sha256"] = digest(report)
        fresh_json(output / "result.json", report)
        return report
    except Exception as exc:
        fresh_json(output / "failure.json", {"passed": False, "error_type": type(exc).__name__,
            "message_sha256": digest(str(exc)), "automatic_retry": False, "market_data_acquisition": False})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("session", "result-audit", "directory-receipt", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--name", required=True)
    args = vars(parser.parse_args())
    report = run(**{k: v.resolve() if isinstance(v, Path) else v for k, v in args.items()})
    print(canonical(report))
