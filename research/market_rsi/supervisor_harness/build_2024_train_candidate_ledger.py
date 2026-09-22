"""Build the complete offline 2024 Train-candidate denominator ledger.

The builder consumes only preserved source/manifests.  It does not fetch data,
open an evaluation split, infer the unresolved mapping, or admit Train data.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Mapping


SCHEMA = "market_rsi_2024_train_candidate_denominator_v1"
CANONICAL_REPO = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local"
)
SOURCE_ROOT = Path("artifacts/nfl-2024-refresh-20260921-01")
SOURCE_FILES = {
    "capture_manifest": SOURCE_ROOT / "manifest.json",
    "schedule_source": SOURCE_ROOT / "source/play_by_play_2024.csv.gz",
    "catalog_manifest": SOURCE_ROOT / "catalog/manifest.json",
    "catalog_payload": SOURCE_ROOT / "catalog/events.catalog.json",
    "mapping_manifest": SOURCE_ROOT / "mapping/manifest.json",
    "mapped_rows": SOURCE_ROOT / "mapping/candidate_mapping.csv",
    "mapping_failures": SOURCE_ROOT / "mapping/mapping_failures.json",
}
PINNED_SHA256 = {
    "capture_manifest": "699b6d86a48f55fa3719fdc6195babb6b3e7dedeac24d3439f4a4e492c399945",
    "schedule_source": "16eb7af043e705bf6d75c2ea4e59b0b28f49d2ab17ea3e7d68ed2877a308ee7f",
    "catalog_manifest": "51b9b950566f981c1de386fc42ec5019cd97f5ff10dbd509a0713f9aab0ad54b",
    "catalog_payload": "c89f097b6538ceee46bb7b2950c3fd9ab6971fc5a39ddf00da61e5f589a3c0eb",
    "mapping_manifest": "481a059fec037efdb88fe55f8a2ddc9e6cf9f12c57739adff987af0dce93e7af",
    "mapped_rows": "a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b",
    "mapping_failures": "afb9a7631a5a79852901c0a72ef78509a74d3ae5be50967aa9156eef922ba8fd",
}
MAPPED_FIELDS = (
    "polymarket_event_id", "event_slug", "event_start_utc",
    "nflverse_game_id", "nflverse_game_date", "away_team", "home_team",
    "slug_order", "date_resolution", "moneyline_market_id", "condition_id",
    "outcomes_json", "tokens_json",
)
EXPECTED_MISSING_EVENT = {
    "event_id": "17330",
    "reason": "moneyline_missing_or_ambiguous",
    "slug": "nfl-kc-phi-2025-02-09",
}
FORBIDDEN_KEYS = {"dev", "final", "score", "result", "outcome", "price", "trade"}


def file_hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"regular source file required: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()
    ).hexdigest()


def _canonical_source_paths(repo: Path) -> dict[str, Path]:
    canonical = CANONICAL_REPO.resolve(strict=True)
    if repo.is_symlink() or repo.resolve(strict=True) != canonical:
        raise ValueError("exact canonical repository required")
    paths = {}
    for name, relative in SOURCE_FILES.items():
        current = canonical
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"symlink source path rejected: {name}")
        if current.resolve(strict=True) != canonical / relative:
            raise ValueError(f"noncanonical source path rejected: {name}")
        paths[name] = current
    return paths


def _validate_hashes(paths: Mapping[str, Path], expected: Mapping[str, str]) -> dict:
    if set(paths) != set(SOURCE_FILES) or set(expected) != set(SOURCE_FILES):
        raise ValueError("exact source file set required")
    actual = {name: file_hash(paths[name]) for name in sorted(paths)}
    mismatch = {name for name in actual if actual[name] != expected[name]}
    if mismatch:
        raise ValueError("source hash mismatch: " + ",".join(sorted(mismatch)))
    return actual


def _assert_no_forbidden_keys(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = key.lower()
            if any(word in lowered for word in FORBIDDEN_KEYS):
                raise ValueError(f"forbidden ledger field: {key}")
            _assert_no_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_keys(item)


def _schedule_game_ids(path: Path) -> set[str]:
    games = set()
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "game_id" not in (reader.fieldnames or []):
            raise ValueError("schedule game_id field missing")
        for row in reader:
            game_id = row["game_id"]
            if game_id:
                games.add(game_id)
    if len(games) != 285:
        raise ValueError("expected exactly 285 schedule games")
    return games


def _assemble_verified(paths: Mapping[str, Path], expected_hashes: Mapping[str, str]) -> dict:
    hashes = _validate_hashes(paths, expected_hashes)
    capture = _load_json(paths["capture_manifest"])
    catalog = _load_json(paths["catalog_manifest"])
    catalog_events = _load_json(paths["catalog_payload"])
    mapping = _load_json(paths["mapping_manifest"])
    failures = _load_json(paths["mapping_failures"])

    if capture.get("schema") != "nfl_2024_fresh_source_version_v1":
        raise ValueError("unexpected capture manifest")
    if (capture.get("gamma_catalog_events") != 285
            or capture.get("mapped_games") != 284
            or capture.get("train_admitted") is not False
            or capture.get("dev_final_opened") is not False):
        raise ValueError("capture denominator or boundary drift")
    if (capture.get("pbp_gzip_sha256") != hashes["schedule_source"]
            or capture.get("gamma_catalog_manifest_sha256") != hashes["catalog_manifest"]
            or capture.get("mapping_manifest_sha256") != hashes["mapping_manifest"]
            or capture.get("mapping_sha256") != hashes["mapped_rows"]):
        raise ValueError("capture cross-reference mismatch")
    if (catalog.get("schema") != "polymarket_2024_nfl_train_catalog_manifest_v1"
            or catalog.get("events") != 285
            or catalog.get("two_outcome_moneyline_markets_on_candidates") != 284
            or catalog.get("catalog_sha256") != hashes["catalog_payload"]
            or catalog.get("train_admitted") is not False):
        raise ValueError("catalog denominator or boundary drift")
    if (mapping.get("schema")
            != "polymarket_2024_nfl_train_candidate_mapping_manifest_v1"
            or mapping.get("catalog_events") != 285
            or mapping.get("nflverse_2024_games") != 285
            or mapping.get("mapped_unique_games") != 284
            or mapping.get("unmapped_events") != 1
            or mapping.get("failure_reasons") != {"moneyline_missing_or_ambiguous": 1}
            or mapping.get("catalog_sha256") != hashes["catalog_payload"]
            or mapping.get("nflverse_sha256") != hashes["schedule_source"]
            or mapping.get("mapping_sha256") != hashes["mapped_rows"]
            or mapping.get("failures_sha256") != hashes["mapping_failures"]
            or mapping.get("train_admitted") is not False):
        raise ValueError("mapping denominator or boundary drift")

    if not isinstance(catalog_events, list) or len(catalog_events) != 285:
        raise ValueError("expected exactly 285 catalog events")
    catalog_by_id = {}
    for event in catalog_events:
        if not isinstance(event, dict):
            raise ValueError("invalid catalog event")
        event_id, slug = str(event.get("id", "")), event.get("slug")
        if not event_id or not isinstance(slug, str) or not slug:
            raise ValueError("catalog event identity missing")
        if event_id in catalog_by_id:
            raise ValueError("duplicate catalog event identity")
        catalog_by_id[event_id] = slug

    with paths["mapped_rows"].open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MAPPED_FIELDS:
            raise ValueError("unexpected mapping fields")
        mapped = list(reader)
    if len(mapped) != 284:
        raise ValueError("expected exactly 284 mapped rows")
    game_ids = [row["nflverse_game_id"] for row in mapped]
    event_ids = [row["polymarket_event_id"] for row in mapped]
    if any(not item for item in game_ids + event_ids):
        raise ValueError("blank mapped identity")
    if len(set(game_ids)) != 284 or len(set(event_ids)) != 284:
        raise ValueError("duplicate mapped identity")
    schedule_game_ids = _schedule_game_ids(paths["schedule_source"])
    unexpected = set(game_ids) - schedule_game_ids
    missing_schedule_games = schedule_game_ids - set(game_ids)
    if unexpected or len(missing_schedule_games) != 1:
        raise ValueError("schedule/mapping denominator mismatch")
    missing_schedule_game = next(iter(missing_schedule_games))
    if not isinstance(failures, list) or len(failures) != 1:
        raise ValueError("expected one explicit mapping failure")
    failure = failures[0]
    if set(failure) != {"event_id", "reason", "slug"}:
        raise ValueError("unexpected failure fields")
    if failure != EXPECTED_MISSING_EVENT:
        raise ValueError("unexpected missing event evidence")
    if failure["event_id"] in set(event_ids):
        raise ValueError("failed event also appears mapped")
    if set(catalog_by_id) != set(event_ids) | {failure["event_id"]}:
        raise ValueError("catalog/mapping membership mismatch")
    for row in mapped:
        if catalog_by_id.get(row["polymarket_event_id"]) != row["event_slug"]:
            raise ValueError("mapped event catalog identity mismatch")
    if catalog_by_id.get(failure["event_id"]) != failure["slug"]:
        raise ValueError("missing event catalog identity mismatch")

    rows = []
    for row in mapped:
        mapping_evidence = {
            field: row[field]
            for field in MAPPED_FIELDS
            if field not in {"outcomes_json", "tokens_json"}
        }
        ledger_row = {
            "candidate_id": f"game:{row['nflverse_game_id']}",
            "schedule_game_id": row["nflverse_game_id"],
            "game_date": row["nflverse_game_date"],
            "source_event_id": row["polymarket_event_id"],
            "source_event_slug": row["event_slug"],
            "source_event_start_utc": row["event_start_utc"],
            "mapping_status": "mapped",
            "missing_reason": None,
            "source_binding": {
                "schedule_identity_sha256": canonical_digest({
                    "schedule_game_id": row["nflverse_game_id"],
                    "schedule_source_sha256": hashes["schedule_source"],
                }),
                "catalog_identity_sha256": canonical_digest({
                    "source_event_id": row["polymarket_event_id"],
                    "source_event_slug": row["event_slug"],
                    "catalog_payload_sha256": hashes["catalog_payload"],
                }),
                "mapping_evidence_sha256": canonical_digest(mapping_evidence),
                "source_artifact_sha256": {
                    "schedule_source": hashes["schedule_source"],
                    "catalog_payload": hashes["catalog_payload"],
                    "mapped_rows": hashes["mapped_rows"],
                    "mapping_manifest": hashes["mapping_manifest"],
                },
            },
        }
        ledger_row["row_commitment_sha256"] = canonical_digest(ledger_row)
        rows.append(ledger_row)
    missing_row = {
        "candidate_id": f"game:{missing_schedule_game}",
        "schedule_game_id": missing_schedule_game,
        "game_date": None,
        "source_event_id": None,
        "source_event_slug": None,
        "source_event_start_utc": None,
        "mapping_status": "missing",
        "missing_reason": failure["reason"],
        "unmapped_catalog_event_evidence": {
            "source_event_id": failure["event_id"],
            "source_event_slug": failure["slug"],
            "claimed_as_mapping": False,
        },
        "source_binding": {
            "schedule_identity_sha256": canonical_digest({
                "schedule_game_id": missing_schedule_game,
                "schedule_source_sha256": hashes["schedule_source"],
            }),
            "catalog_identity_sha256": canonical_digest({
                "source_event_id": failure["event_id"],
                "source_event_slug": failure["slug"],
                "catalog_payload_sha256": hashes["catalog_payload"],
                "claimed_as_mapping": False,
            }),
            "mapping_failure_sha256": canonical_digest(failure),
            "source_artifact_sha256": {
                "schedule_source": hashes["schedule_source"],
                "catalog_payload": hashes["catalog_payload"],
                "mapping_failures": hashes["mapping_failures"],
                "mapping_manifest": hashes["mapping_manifest"],
            },
        },
    }
    missing_row["row_commitment_sha256"] = canonical_digest(missing_row)
    rows.append(missing_row)
    rows.sort(key=lambda row: row["candidate_id"])
    if len(rows) != 285 or sum(row["mapping_status"] == "mapped" for row in rows) != 284:
        raise ValueError("full denominator drift")

    ledger = {
        "schema": SCHEMA,
        "season": 2024,
        "role": "train_candidate_only",
        "admission_claim": False,
        "provider_cost_usd": "0",
        "denominator": {
            "candidate_rows": 285,
            "mapped_rows": 284,
            "missing_rows": 1,
        },
        "source_artifacts": {
            name: {"path": str(SOURCE_FILES[name]), "sha256": hashes[name]}
            for name in sorted(paths)
        },
        "rows": rows,
    }
    _assert_no_forbidden_keys(ledger)
    return ledger


def build(repo: Path) -> dict:
    """Build only from the exact pinned files in the canonical checkout."""
    return _assemble_verified(_canonical_source_paths(repo), PINNED_SHA256)


def run(repo: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("fresh output directory required")
    ledger = build(repo)
    output.mkdir(parents=True)
    ledger_path = output / "ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    ledger_reference = (str(ledger_path.relative_to(repo))
                        if ledger_path.is_relative_to(repo) else str(ledger_path))
    receipt = {
        "schema": "market_rsi_2024_train_candidate_denominator_receipt_v1",
        "ledger_path": ledger_reference,
        "ledger_sha256": file_hash(ledger_path),
        "candidate_rows": 285,
        "mapped_rows": 284,
        "missing_rows": 1,
        "admission_claim": False,
        "provider_cost_usd": "0",
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.repo.resolve(), args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
