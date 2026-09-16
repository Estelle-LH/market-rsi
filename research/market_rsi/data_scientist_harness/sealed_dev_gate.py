"""Persistent one-shot gate for an untouched Dev evaluation.

The Research Controller never receives this control directory.  The runner
hashes the Dev inputs without exposing their contents, freezes the reward and
evaluator, and consumes the single evaluation allowance *before* it opens the
Dev files.  A crash after the claim is still a consumed view; recovery needs a
new preregistered cycle rather than a score retry.
"""
from __future__ import annotations

from pathlib import Path
import string

from market_rsi import Journal, digest, file_hash, fresh_json, load_json


def _verify_sealed(record: dict) -> None:
    value = record.get("record_sha256", "")
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("sealed confirmation record required")
    body = {key: item for key, item in record.items() if key != "record_sha256"}
    if digest(body) != value:
        raise ValueError("sealed confirmation record was modified")


def data_commitment(files: dict[str, Path]) -> tuple[str, list[dict]]:
    """Return a content commitment without reading or returning data values."""
    if not files:
        raise ValueError("at least one Dev input is required")
    items = []
    for name in sorted(files):
        path = Path(files[name]).resolve()
        if not name or not path.is_file() or path.is_symlink():
            raise ValueError("Dev inputs must be named canonical files")
        items.append({"name": name, "sha256": file_hash(path), "bytes": path.stat().st_size})
    return digest(items), items


class SealedDevGate:
    """Runner-owned persistence for exactly one Dev exposure."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.private = self.root / "runner-private"
        self.public = self.root / "controller-visible"
        self.journal = Journal(self.private)

    @classmethod
    def reserve(cls, root: Path, confirmation: dict, eligibility_path: Path,
                evaluator_path: Path) -> "SealedDevGate":
        """Freeze cohort and reward before prospective Dev materialization."""
        gate = cls(root)
        if gate.root.exists():
            raise ValueError("fresh sealed-Dev gate directory required")
        _verify_sealed(confirmation)
        if confirmation.get("state") != "confirmation_frozen":
            raise ValueError("reward must be frozen before Dev is registered")
        contract = confirmation["contract"]
        eligibility_path = Path(eligibility_path).resolve()
        if not eligibility_path.is_file() or eligibility_path.is_symlink():
            raise ValueError("canonical Dev eligibility file required")
        eligibility_sha = file_hash(eligibility_path)
        if eligibility_sha != contract["eligible_data_sha256"]:
            raise ValueError("Dev cohort differs from the preregistered commitment")
        evaluator_path = Path(evaluator_path).resolve()
        if not evaluator_path.is_file() or evaluator_path.is_symlink():
            raise ValueError("canonical evaluator file required")
        if file_hash(evaluator_path) != contract["evaluator_spec_sha256"]:
            raise ValueError("evaluator differs from the preregistered reward")

        gate.private.mkdir(parents=True)
        gate.public.mkdir()
        fresh_json(gate.private / "confirmation.json", confirmation)
        fresh_json(gate.private / "reservation.json", {
            "schema": "prospective_dev_reservation_v1",
            "eligible_data_sha256": eligibility_sha,
            "eligibility_path": str(eligibility_path),
            "evaluator_path": str(evaluator_path),
            "evaluator_spec_sha256": file_hash(evaluator_path),
        })
        # The Controller sees commitments and policy, never Dev paths or values.
        fresh_json(gate.public / "confirmation-commitment.json", {
            "schema": "sealed_dev_public_commitment_v1",
            "confirmation_sha256": confirmation["record_sha256"],
            "eligible_data_sha256": eligibility_sha,
            "evaluator_spec_sha256": contract["evaluator_spec_sha256"],
            "primary_metric": contract["primary_metric"],
            "reward_direction": contract["reward_direction"],
            "baseline_id": contract["baseline_id"],
            "maximum_evaluation_uses": 1,
            "materialization_pending": True,
            "dev_paths_exposed": False,
            "dev_values_exposed": False,
        })
        with gate.journal.locked():
            gate.journal.append("dev_frozen", {
                "confirmation_sha256": confirmation["record_sha256"],
                "eligible_data_sha256": eligibility_sha,
                "materialization_pending": True,
            })
        return gate

    def register_materialization(self, dev_files: dict[str, Path], receipt: dict) -> dict:
        """Bind every preregistered cohort member without opening a score."""
        required = {"eligible_data_sha256", "selection_count", "materialized_count",
                    "excluded_count", "scored", "labels_summarized", "source_manifest_sha256"}
        if set(receipt) != required:
            raise ValueError("exact score-free materialization receipt required")
        reservation = load_json(self.private / "reservation.json")
        if receipt["eligible_data_sha256"] != reservation["eligible_data_sha256"]:
            raise ValueError("materialization belongs to another Dev cohort")
        if (type(receipt["selection_count"]) is not int or receipt["selection_count"] <= 0
                or receipt["materialized_count"] != receipt["selection_count"]
                or receipt["excluded_count"] != 0):
            raise ValueError("every preregistered Dev member must materialize")
        if receipt["scored"] is not False or receipt["labels_summarized"] is not False:
            raise ValueError("materialization must occur before any Dev score or label summary")
        source_sha = receipt["source_manifest_sha256"]
        if (not isinstance(source_sha, str) or len(source_sha) != 64
                or any(character not in string.hexdigits for character in source_sha)):
            raise ValueError("materialization source manifest hash required")
        if len(dev_files) != receipt["selection_count"]:
            raise ValueError("every preregistered Dev member must have exactly one committed file")
        commitment, items = data_commitment(dev_files)
        with self.journal.locked():
            records = self.journal.read()
            if any(row["event"] == "dev_materialized" for row in records):
                raise ValueError("Dev materialization already registered")
            manifest = {
                "schema": "sealed_dev_private_manifest_v2",
                "eligible_data_sha256": reservation["eligible_data_sha256"],
                "materialized_data_sha256": commitment,
                "files": [dict(item, path=str(Path(dev_files[item["name"]]).resolve()))
                          for item in items],
                "materialization_receipt": receipt,
            }
            fresh_json(self.private / "dev-manifest.json", manifest)
            self.journal.append("dev_materialized", {
                "eligible_data_sha256": reservation["eligible_data_sha256"],
                "materialized_data_sha256": commitment,
                "file_count": len(items),
                "scored": False,
            })
            return manifest

    def _load_and_verify(self) -> tuple[dict, dict]:
        confirmation = load_json(self.private / "confirmation.json")
        reservation = load_json(self.private / "reservation.json")
        manifest = load_json(self.private / "dev-manifest.json")
        _verify_sealed(confirmation)
        contract = confirmation["contract"]
        if (manifest["eligible_data_sha256"] != contract["eligible_data_sha256"]
                or file_hash(reservation["eligibility_path"]) != contract["eligible_data_sha256"]):
            raise ValueError("Dev manifest no longer matches frozen reward")
        if file_hash(reservation["evaluator_path"]) != contract["evaluator_spec_sha256"]:
            raise ValueError("evaluator changed after reward freeze")
        files = {item["name"]: Path(item["path"]) for item in manifest["files"]}
        commitment, items = data_commitment(files)
        if commitment != manifest["materialized_data_sha256"] or items != [
            {key: item[key] for key in ("name", "sha256", "bytes")} for item in manifest["files"]
        ]:
            raise ValueError("Dev data changed after freeze")
        return confirmation, manifest

    def claim_once(self, evaluation_id: str) -> dict:
        """Consume the one-shot allowance before returning private inputs."""
        if not evaluation_id or "/" in evaluation_id or ".." in evaluation_id:
            raise ValueError("safe evaluation id required")
        with self.journal.locked():
            records = self.journal.read()
            if any(row["event"] == "dev_evaluation_claimed" for row in records):
                raise ValueError("sealed Dev evaluation allowance already consumed")
            confirmation, manifest = self._load_and_verify()
            self.journal.append("dev_evaluation_claimed", {
                "evaluation_id": evaluation_id,
                "confirmation_sha256": confirmation["record_sha256"],
                "eligible_data_sha256": manifest["eligible_data_sha256"],
                "allowance_remaining": 0,
            })
        return {
            "evaluation_id": evaluation_id,
            "confirmation": confirmation,
            "dev_files": {item["name"]: item["path"] for item in manifest["files"]},
            "evaluator_path": load_json(self.private / "reservation.json")["evaluator_path"],
        }

    def record_result(self, evaluation_id: str, result: dict) -> dict:
        """Bind a terminal score record to the consumed one-shot claim."""
        with self.journal.locked():
            records = self.journal.read()
            claims = [row for row in records if row["event"] == "dev_evaluation_claimed"]
            terminals = [row for row in records if row["event"] == "dev_evaluation_terminal"]
            if len(claims) != 1 or claims[0]["payload"]["evaluation_id"] != evaluation_id:
                raise ValueError("matching consumed Dev claim required")
            if terminals:
                raise ValueError("Dev evaluation already has a terminal result")
            if not isinstance(result, dict) or not result:
                raise ValueError("nonempty result required")
            receipt = {
                "schema": "sealed_dev_result_receipt_v1",
                "evaluation_id": evaluation_id,
                "confirmation_sha256": claims[0]["payload"]["confirmation_sha256"],
                "result_sha256": digest(result),
                "evaluation_uses": 1,
                "allowance_remaining": 0,
            }
            self.journal.append("dev_evaluation_terminal", receipt)
            fresh_json(self.public / "evaluation-receipt.json", receipt)
            return receipt
