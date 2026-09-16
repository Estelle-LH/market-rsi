"""Read a pinned, terminated source-only session across harness versions.

Does not instantiate a live Store, import frozen code, replace VERSION/runtime,
resume a session, or grant data admission. Integrity mechanics reuse the existing
Store/event/release and session-audit contracts. See TEMPORAL_HANDOFF_2026-09-13.md.
"""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from market_rsi import digest, file_hash, load_json
from data_scientist_harness.store import resident
from data_scientist_harness.source_study import current

PINS = {
    "manifest": "2cb7e29e5aacc9d77c94f57aa75e8713a69aa0f673a19094bd78bd24ff275e02",
    "proposal": "7ff30153bfdf984706e7efbb0a4c9e5088e63949ec41abe43f15aa66108d7587",
    "release": "f1554ae10541ef5abe4aa0a68c6dce89413baf9d74f116b29c1f4488f3a5739f",
    "audit": "e7d90637654a192edf3ba5a1110be4aa93a6791747bb733bf490e3990af211cc",
    "archive": "3ab6778b1ac50b6fcc79c3865d3485c1488f03ca6f3d4fa8c35d3674d1d4b844",
}


def hashed(path, expected):
    path = resident(Path(path), 32_000_000)
    if file_hash(path) != expected:
        raise ValueError("archived evidence hash differs: " + path.name)
    return path


def enclosed(root, name):
    path = Path(name)
    if (not path.is_absolute() or ".." in path.parts or not path.is_relative_to(root)
            or path.resolve() != path):
        raise ValueError("archived reference outside exact parent")
    return path


class ArchivedSourceSession:
    """Read-only historical view. Intentionally has no save/lock/dispatch method."""

    def __init__(self, root, audit_path, budget, pins=None):
        self.root = Path(root).resolve()
        pins = PINS if pins is None else pins  # Fixtures only; production CLI uses PINS.
        self.expected = pins["manifest"]
        self.config = load_json(hashed(self.root/"workspace.json", self.expected))
        c = self.config
        if (c["schema"] != "data_scientist_workspace_v1" or c["purpose"] != "source_research"
                or c["inputs_present"] is not False or c["allowed_train_dates"] != []
                or c["formal_evaluation_allowed"] is not False or c["paid_execution_tools"] is not False
                or c["session_id"] != self.root.name):
            raise ValueError("only terminated source-only history can migrate")
        release = c["release"]
        if (release["release_sha256"] != pins["release"]
                or release["release_sha256"] != digest({k:v for k,v in release.items() if k != "release_sha256"})
                or release["harness_version"] != c["harness_version"]
                or release["runtime"] != c["runtime"]
                or release["harness_change_origin"] != c["harness_change_origin"]
                or c["harness_change_origin"] != "human_directed_engineering"
                or release["publication"]["origin"] != "https://github.com/Estelle-LH/RSIBench-Data.git"):
            raise ValueError("historical release binding differs")
        sources = {}
        for name, sha in c["files"].items():
            path = enclosed(self.root, name)
            if path.is_relative_to(self.root/"code"):
                sources[str(path.relative_to(self.root/"code"))] = sha
            elif path not in {self.root/"findings.json", self.root/"archive-input.json"}:
                raise ValueError("unexpected source-only frozen input")
            hashed(path, sha)
        if sources != release["source_hashes"]:
            raise ValueError("historical frozen source set differs from its release")
        audit = load_json(resident(Path(audit_path).resolve(), 8_388_608))
        if (audit["result_sha256"] != pins["audit"]
                or audit["result_sha256"] != digest({k:v for k,v in audit.items() if k != "result_sha256"})
                or audit["manifest_sha256"] != self.expected or audit["workspace"] != str(self.root)
                or audit["controller_valid"] is not True or audit["process_reaped"] is not True
                or audit["fits_completed"] != 0 or audit["integrity_and_cost_check_passed"] is not True):
            raise ValueError("pinned successful historical audit required")
        assessment = load_json(hashed(self.root/"session/assessment.json", audit["assessment_sha256"]))
        if (assessment["manifest_sha256"] != self.expected or assessment["exit_code"] != 0
                or assessment["valid"] is not True or assessment["process_reaped"] is not True
                or assessment["evidence_mode"] != "paid_controller" or assessment["source_hashes"] != sources
                or assessment["harness_release"] != audit["harness_release"]
                or assessment["harness_release"]["release_sha256"] != pins["release"]
                or assessment["unresolved_accounting"]):
            raise ValueError("historical terminal/source proof differs")
        self._events, self._records = [], []
        previous = None
        for index, line in enumerate(resident(self.root/"activity.jsonl", 32_000_000).read_text().splitlines(), 1):
            row = json.loads(line)
            unsigned = {k:v for k,v in row.items() if k != "record_sha256"}
            path = self.root/"records"/f"{index:04d}.json"
            if (row["sequence"] != index or row["previous"] != previous
                    or row["record_sha256"] != digest(unsigned) or row["record"]["path"] != str(path)):
                raise ValueError("historical event chain differs")
            record = load_json(hashed(path, row["record"]["sha256"]))
            if record["tool"] != row["tool"] or record["harness_release"] != audit["harness_release"]:
                raise ValueError("historical tool identity differs")
            self._events.append(row); self._records.append(record); previous = row["record_sha256"]
        counts = Counter((r["tool"], r["status"]) for r in self._records)
        if (assessment["tool_calls"] != len(self._records)
                or audit["tools"] != [{"tool":t,"status":s,"count":n} for (t,s),n in sorted(counts.items())]
                or any(r["tool"] == "train_candidate" for r in self._records)
                or counts["submit_research_decision", "ok"] != 1
                or self._records[-1]["tool"] != "submit_research_decision"):
            raise ValueError("historical tool terminal set differs")
        self.proposal_ref = current(self)
        if not self.proposal_ref or self.proposal_ref["sha256"] != pins["proposal"]:
            raise ValueError("historical first proposal differs")
        decision = load_json(hashed(self.root/"submitted-decision.json", audit["decision_sha256"]))
        if (decision != audit["decision"] or decision["action"] != "defer"
                or decision["source_study_proposal"] != self.proposal_ref
                or decision != {k:v for k,v in self._records[-1]["result"].items() if k != "bytes"}):
            raise ValueError("historical decision differs")
        archive = load_json(hashed(self.root/"round-archive.json", pins["archive"]))
        if (archive["schema"] != "data_scientist_round_archive_v1" or archive["manifest_sha256"] != self.expected
                or archive["decision"] != decision or archive["pre_submission_activity"] != self._events[:-1]
                or archive["current_findings"] != load_json(self.root/"findings.json")
                or archive["trial_summaries"] or archive["research_trace"] != decision["research_trace"]):
            raise ValueError("historical archive differs from source records")
        for suffix, key in (("json", "json_sha256"), ("md", "markdown_sha256")):
            hashed(self.root/("research-trace."+suffix), decision["research_trace"][key])
        jobs = {k:v for k,v in budget["jobs"].items() if k.startswith(self.root.name+"-turn-")}
        if set(jobs) != {t["job_id"] for t in audit["turns"]} or len(jobs) != assessment["turns"]:
            raise ValueError("historical provider turn set differs")
        total = Decimal(0)
        for t in audit["turns"]:
            job = jobs[t["job_id"]]
            path = self.root/"session"/("turn-"+t["job_id"].rsplit("-turn-",1)[1])/"response.json"
            response = load_json(hashed(path, t["response_sha256"]))
            amount = Decimal(response["receipt"]["metered_cost_usd"])
            if (job["state"] != "metered_terminal" or t["state"] != job["state"]
                    or amount != Decimal(job["metered_usd"]) or amount != Decimal(t["metered_usd"])):
                raise ValueError("historical provider cost differs")
            total += amount
        if total != Decimal(audit["session_metered_usd"]) or Decimal(audit["session_uncertain_upper_usd"]) != 0:
            raise ValueError("historical total differs")
        self.receipt = {"schema":"archived_source_session_verified_v1", "pins":pins,
            "parent":str(self.root), "old_version":c["harness_version"], "old_runtime":c["runtime"],
            "frozen_files_verified":len(c["files"]), "tool_records_verified":len(self._records),
            "provider_turns_verified":len(jobs), "session_metered_usd":str(total),
            "archive":{"path":str(self.root/"round-archive.json"),"sha256":pins["archive"]},
            "historical_release_revalidated_by_pinned_receipt":True,
            "old_runtime_executed":False,"old_workspace_modified":False,"same_harness":False,
            "raw_market_data_loaded":False,"source_admitted":False,"new_dev_test_admitted":False}

    def records(self, tool=None):
        return [r for r in self._records if tool is None or r["tool"] == tool]
