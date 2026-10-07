"""One-shot five-slot episode lease for the synthetic PMB simple lane.

The lease is deliberately not a process runner.  It records a fail-closed
lifecycle and immutable commitments; it cannot launch Docker, call a provider,
open data, train, score, retry, or publish anything.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
import weakref
from typing import Any

from .artifact_store import ArtifactIntegrityError, ArtifactStore


_LEASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
_TERMINAL = {"closed_passed", "closed_failed", "unresolved"}
_REGISTRY = "episode-lease-registry"


@dataclass(frozen=True)
class _LeaseOwnership:
    """Externally held, identity-bound snapshot for one live lease handle."""

    store_ref: weakref.ReferenceType[ArtifactStore]
    store_root: str
    store_root_identity: tuple[int, int]
    lease_id: str
    journal_name: str
    registration_claim: tuple[str, int, str]
    state: str
    head: str
    next_slot: int
    early_stopped: bool


_LIVE_OWNERS: weakref.WeakKeyDictionary["EpisodeLease", _LeaseOwnership] = (
    weakref.WeakKeyDictionary()
)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} object required")
    return value


def _lease_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or value in {".", ".."}
        or _LEASE_ID_RE.fullmatch(value) is None
    ):
        raise ValueError("bounded safe episode lease ID required")
    return value


def _receipt_identity(receipt: object) -> tuple[str, int, str]:
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"bytes", "path", "sha256"}
        or not isinstance(receipt["path"], str)
        or type(receipt["bytes"]) is not int
        or receipt["bytes"] < 0
        or not isinstance(receipt["sha256"], str)
    ):
        raise ArtifactIntegrityError("exact lease claim receipt required")
    return receipt["path"], receipt["bytes"], receipt["sha256"]


def _store_root_identity(store: ArtifactStore) -> tuple[int, int]:
    identity = getattr(store, "_root_identity", None)
    if (
        not isinstance(identity, tuple)
        or len(identity) != 2
        or any(type(part) is not int for part in identity)
    ):
        raise ArtifactIntegrityError("artifact store root identity is unavailable")
    return identity


def _revoke_claim_owners(store: ArtifactStore, lease_id: str) -> None:
    """Revoke any in-process owner of a claim closed through recovery."""

    for handle, ownership in list(_LIVE_OWNERS.items()):
        if ownership.store_ref() is store and ownership.lease_id == lease_id:
            del _LIVE_OWNERS[handle]


class EpisodeLease:
    """A live lease handle; active leases cannot be reopened after restart."""

    def __init__(self, store: ArtifactStore, lease_id: str) -> None:
        self.store = store
        self.lease_id = _lease_id(lease_id)
        self.journal_name = f"episode-lease.{self.lease_id}"
        self._state = "registered"
        self._next_slot = 1
        self._early_stopped = False
        self._head: str | None = None

    @classmethod
    def create(
        cls,
        store: ArtifactStore,
        lease_id: str,
        *,
        registration: dict[str, Any],
    ) -> "EpisodeLease":
        """Claim a never-reused ID and the store's sole active lease."""

        lease_id = _lease_id(lease_id)
        registration = _object(registration, "registration")
        registry = cls._validate_registry(store)
        if registry["active_lease_id"] is not None:
            raise ValueError("another episode lease is active")

        claim = {
            "lease_id": lease_id,
            "registration": registration,
            "schema": "pmb_episode_lease_claim_v1",
        }
        claim_receipt = store.write_json_once(f"lease_ids/{lease_id}.json", claim)
        store.append_journal(
            _REGISTRY,
            {
                "artifacts": [claim_receipt],
                "event": "claimed",
                "lease_id": lease_id,
                "schema": "pmb_episode_lease_registry_event_v1",
            },
        )
        lease = cls(store, lease_id)
        registration_result = store.append_journal(
            lease.journal_name,
            {
                "artifacts": [claim_receipt],
                "detail": {"registration": registration},
                "event": "registered",
                "lease_id": lease_id,
                "schema": "pmb_episode_lease_event_v1",
                "state": "registered",
            },
        )
        registration_replay = store.verify_journal(
            lease.journal_name,
            expected_head=registration_result["head_sha256"],
        )
        registration_inspection = cls._inspect_replay(
            store, lease_id, registration_replay
        )
        if (
            registration_inspection["state"] != "registered"
            or registration_inspection["controller_next_slot"] != 1
            or registration_inspection["early_stopped"] is not False
        ):
            raise ArtifactIntegrityError("lease registration did not verify exactly")
        lease._head = registration_result["head_sha256"]
        _LIVE_OWNERS[lease] = _LeaseOwnership(
            store_ref=weakref.ref(store),
            store_root=str(store.root),
            store_root_identity=_store_root_identity(store),
            lease_id=lease_id,
            journal_name=lease.journal_name,
            registration_claim=_receipt_identity(claim_receipt),
            state="registered",
            head=registration_result["head_sha256"],
            next_slot=1,
            early_stopped=False,
        )
        return lease

    @property
    def state(self) -> str:
        return self._state

    @property
    def next_slot(self) -> int | None:
        if self._state in _TERMINAL or self._state in {
            "candidate_frozen",
            "terminal_review_pending",
        }:
            return None
        return 5 if self._early_stopped else self._next_slot

    @staticmethod
    def _validate_registry(store: ArtifactStore) -> dict[str, Any]:
        replay = store.verify_journal(_REGISTRY)
        active: str | None = None
        used: set[str] = set()
        for record in replay["entries"]:
            event = record["event"]
            if (
                not isinstance(event, dict)
                or event.get("schema") != "pmb_episode_lease_registry_event_v1"
                or event.get("event") not in {"claimed", "terminal"}
                or set(event) != (
                    {"artifacts", "event", "lease_id", "schema"}
                    if event.get("event") == "claimed"
                    else {"event", "lease_id", "schema", "terminal_state"}
                )
            ):
                raise ArtifactIntegrityError("episode lease registry schema changed")
            current_id = _lease_id(event["lease_id"])
            if event["event"] == "claimed":
                if active is not None or current_id in used:
                    raise ArtifactIntegrityError("overlapping or reused episode lease")
                if not isinstance(event["artifacts"], list) or len(event["artifacts"]) != 1:
                    raise ArtifactIntegrityError("lease claim receipt missing")
                store.verify_receipt(event["artifacts"][0])
                active = current_id
                used.add(current_id)
            else:
                if active != current_id or event["terminal_state"] not in _TERMINAL:
                    raise ArtifactIntegrityError("lease registry terminal mismatch")
                active = None
        return {
            "active_lease_id": active,
            "head_sha256": replay["head_sha256"],
            "used_lease_ids": sorted(used),
        }

    def _append(
        self,
        event: str,
        state: str,
        *,
        artifacts: list[dict[str, Any]],
        detail: dict[str, Any],
        next_slot: int | None = None,
        early_stopped: bool | None = None,
    ) -> None:
        ownership = self._verify_owner_fields()
        target_next_slot = self._next_slot if next_slot is None else next_slot
        target_early_stopped = (
            self._early_stopped if early_stopped is None else early_stopped
        )
        record = {
            "artifacts": artifacts,
            "detail": detail,
            "event": event,
            "lease_id": self.lease_id,
            "schema": "pmb_episode_lease_event_v1",
            "state": state,
        }
        result = self.store.append_journal(self.journal_name, record)
        replay = self.store.verify_journal(
            self.journal_name, expected_head=result["head_sha256"]
        )
        inspection = self._inspect_replay(self.store, self.lease_id, replay)
        if (
            inspection["state"] != state
            or inspection["journal_head_sha256"] != result["head_sha256"]
            or inspection["controller_next_slot"] != target_next_slot
            or inspection["early_stopped"] is not target_early_stopped
        ):
            raise ArtifactIntegrityError("lease transition did not verify exactly")
        self._head = result["head_sha256"]
        self._state = state
        self._next_slot = target_next_slot
        self._early_stopped = target_early_stopped
        _LIVE_OWNERS[self] = replace(
            ownership,
            state=state,
            head=result["head_sha256"],
            next_slot=target_next_slot,
            early_stopped=target_early_stopped,
        )

    def _verify_owner_fields(self) -> _LeaseOwnership:
        try:
            ownership = _LIVE_OWNERS.get(self)
        except (TypeError, AttributeError) as exc:
            raise ValueError(
                "reconstructed lease handle cannot advance; "
                "use mark_interrupted_unresolved"
            ) from exc
        if ownership is None:
            raise ValueError(
                "reconstructed lease handle cannot advance or terminal ownership "
                "was revoked; "
                "use mark_interrupted_unresolved"
            )
        if (
            ownership.store_ref() is not self.store
            or str(self.store.root) != ownership.store_root
            or _store_root_identity(self.store) != ownership.store_root_identity
            or self.lease_id != ownership.lease_id
            or self.journal_name != ownership.journal_name
            or self._state != ownership.state
            or self._head != ownership.head
            or self._next_slot != ownership.next_slot
            or self._early_stopped is not ownership.early_stopped
        ):
            raise ArtifactIntegrityError("live lease ownership snapshot changed")
        return ownership

    def _verify_live(self) -> None:
        ownership = self._verify_owner_fields()
        replay = self.store.verify_journal(
            self.journal_name, expected_head=ownership.head
        )
        inspection = self._inspect_replay(self.store, self.lease_id, replay)
        first_event = replay["entries"][0]["event"]
        claim_identity = _receipt_identity(first_event["artifacts"][0])
        if (
            inspection["state"] != ownership.state
            or inspection["journal_head_sha256"] != ownership.head
            or inspection["controller_next_slot"] != ownership.next_slot
            or inspection["early_stopped"] is not ownership.early_stopped
            or claim_identity != ownership.registration_claim
        ):
            raise ArtifactIntegrityError("live lease lifecycle snapshot changed externally")
        registry = self._validate_registry(self.store)
        if ownership.state not in _TERMINAL and (
            registry["active_lease_id"] != ownership.lease_id
        ):
            raise ArtifactIntegrityError("live lease lost its active registry claim")

    def capture_start_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._verify_live()
        if self._state != "registered":
            raise ValueError("start snapshot is allowed exactly once after registration")
        snapshot = _object(snapshot, "start snapshot")
        receipt = self.store.write_json_once(
            f"leases/{self.lease_id}/start_snapshot.json", snapshot
        )
        self._append(
            "start_snapshotted",
            "start_snapshotted",
            artifacts=[receipt],
            detail={},
        )

    def record_task(
        self,
        slot: int,
        *,
        intent: dict[str, Any],
        task: dict[str, Any],
        observation: dict[str, Any],
    ) -> None:
        """Consume one of slots 1--4; its observation may record a failure."""

        self._verify_live()
        if (
            type(slot) is not int
            or slot not in range(1, 5)
            or slot != self._next_slot
            or self._early_stopped
            or self._state
            not in (
                {"start_snapshotted"}
                | {f"running_round_{n}" for n in range(1, 5)}
            )
        ):
            raise ValueError("controller task slot is out of sequence or already consumed")
        payload = {
            "decision": "task",
            "intent": _object(intent, "slot intent"),
            "observation": _object(observation, "slot observation"),
            "slot": slot,
            "task": _object(task, "researcher task"),
        }
        receipt = self.store.write_json_once(
            f"leases/{self.lease_id}/slots/slot_{slot}.json", payload
        )
        self._append(
            "controller_slot",
            f"running_round_{slot}",
            artifacts=[receipt],
            detail={"decision": "task", "slot": slot},
            next_slot=self._next_slot + 1,
        )

    def stop_early(
        self,
        slot: int,
        *,
        intent: dict[str, Any],
        reason: str,
    ) -> None:
        """Consume the next slot as stop; only forced slot 5 may follow."""

        self._verify_live()
        if (
            type(slot) is not int
            or slot not in range(1, 5)
            or slot != self._next_slot
            or self._early_stopped
            or self._state
            not in (
                {"start_snapshotted"}
                | {f"running_round_{n}" for n in range(1, 5)}
            )
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ValueError("valid next controller stop slot and reason required")
        payload = {
            "decision": "stop",
            "intent": _object(intent, "slot intent"),
            "observation": None,
            "reason": reason,
            "slot": slot,
            "task": None,
        }
        receipt = self.store.write_json_once(
            f"leases/{self.lease_id}/slots/slot_{slot}.json", payload
        )
        self._append(
            "controller_slot",
            f"running_round_{slot}",
            artifacts=[receipt],
            detail={"decision": "stop", "slot": slot},
            next_slot=self._next_slot + 1,
            early_stopped=True,
        )

    def synthesize_and_freeze(
        self,
        *,
        synthesis: dict[str, Any],
        candidate: dict[str, Any],
    ) -> None:
        """Consume forced slot 5; it has no Researcher task and freezes output."""

        self._verify_live()
        ready = self._early_stopped or self._next_slot == 5
        if not ready or self._state not in {f"running_round_{n}" for n in range(1, 5)}:
            raise ValueError("slot 5 requires four consumed slots or an explicit early stop")
        payload = {
            "candidate": _object(candidate, "candidate commitment"),
            "decision": "synthesize",
            "observation": None,
            "slot": 5,
            "synthesis": _object(synthesis, "terminal synthesis"),
            "task": None,
        }
        receipt = self.store.write_json_once(
            f"leases/{self.lease_id}/slots/slot_5.json", payload
        )
        self._append(
            "slot_5_synthesis",
            "candidate_frozen",
            artifacts=[receipt],
            detail={"decision": "synthesize", "slot": 5},
        )

    def begin_terminal_review(self, request: dict[str, Any]) -> None:
        self._verify_live()
        if self._state != "candidate_frozen":
            raise ValueError("terminal review requires a frozen candidate")
        receipt = self.store.write_json_once(
            f"leases/{self.lease_id}/terminal_review_request.json",
            _object(request, "terminal review request"),
        )
        self._append(
            "terminal_review_pending",
            "terminal_review_pending",
            artifacts=[receipt],
            detail={},
        )

    def close(
        self,
        outcome: str,
        *,
        review: dict[str, Any],
        end_snapshot: dict[str, Any],
    ) -> None:
        self._verify_live()
        if self._state != "terminal_review_pending" or outcome not in {"passed", "failed"}:
            raise ValueError("passed/failed closure requires pending terminal review")
        end_receipt = self.store.write_json_once(
            f"leases/{self.lease_id}/end_snapshot.json",
            _object(end_snapshot, "end snapshot"),
        )
        review_receipt = self.store.write_json_once(
            f"leases/{self.lease_id}/terminal_review.json",
            {"outcome": outcome, "review": _object(review, "terminal review")},
        )
        terminal_state = f"closed_{outcome}"
        self._append(
            "terminal",
            terminal_state,
            artifacts=[end_receipt, review_receipt],
            detail={"outcome": outcome},
        )
        self._close_registry(terminal_state)

    def mark_unresolved(self, *, reason: str) -> None:
        """Terminally consume a live ambiguous lease; it cannot be retried."""

        self._verify_live()
        if self._state in _TERMINAL or not isinstance(reason, str) or not reason.strip():
            raise ValueError("nonterminal lease and unresolved reason required")
        self._append(
            "terminal",
            "unresolved",
            artifacts=[],
            detail={"reason": reason},
        )
        self._close_registry("unresolved")

    def _close_registry(self, terminal_state: str) -> None:
        self._verify_live()
        registry = self._validate_registry(self.store)
        if registry["active_lease_id"] != self.lease_id:
            raise ArtifactIntegrityError("cannot close a non-active lease")
        self.store.append_journal(
            _REGISTRY,
            {
                "event": "terminal",
                "lease_id": self.lease_id,
                "schema": "pmb_episode_lease_registry_event_v1",
                "terminal_state": terminal_state,
            },
        )
        closed = self._validate_registry(self.store)
        if closed["active_lease_id"] is not None:
            raise ArtifactIntegrityError("terminal lease registry close did not verify")
        try:
            del _LIVE_OWNERS[self]
        except KeyError as exc:
            raise ArtifactIntegrityError("terminal lease ownership was already revoked") from exc

    @classmethod
    def inspect(cls, store: ArtifactStore, lease_id: str) -> dict[str, Any]:
        """Read-only replay.  A nonterminal result must not be resumed."""

        lease_id = _lease_id(lease_id)
        replay = store.verify_journal(f"episode-lease.{lease_id}")
        if replay["length"] == 0:
            raise ValueError("unknown episode lease ID")
        result = cls._inspect_replay(store, lease_id, replay)
        result["restart_disposition"] = (
            "terminal_read_only" if result["state"] in _TERMINAL else "mark_unresolved_only"
        )
        return result

    @classmethod
    def mark_interrupted_unresolved(
        cls, store: ArtifactStore, lease_id: str, *, reason: str
    ) -> dict[str, Any]:
        """After process loss, close the exact active lease without reopening work."""

        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("interruption reason required")
        lease_id = _lease_id(lease_id)
        registry = cls._validate_registry(store)
        if registry["active_lease_id"] != lease_id:
            raise ValueError("only the exact active lease may be marked interrupted")
        journal_name = f"episode-lease.{lease_id}"
        replay = store.verify_journal(journal_name)
        if replay["length"] == 0:
            # A crash may occur after the global claim is durable but before the
            # per-lease registration append.  Reconstruct only that committed
            # registration, then terminally consume the ID below.
            registry_replay = store.verify_journal(_REGISTRY)
            claim_event = next(
                record["event"]
                for record in reversed(registry_replay["entries"])
                if record["event"].get("event") == "claimed"
                and record["event"].get("lease_id") == lease_id
            )
            claim_receipt = claim_event["artifacts"][0]
            claim = store.read_json_verified(claim_receipt)
            store.append_journal(
                journal_name,
                {
                    "artifacts": [claim_receipt],
                    "detail": {"registration": claim["registration"]},
                    "event": "registered",
                    "lease_id": lease_id,
                    "schema": "pmb_episode_lease_event_v1",
                    "state": "registered",
                },
            )
            replay = store.verify_journal(journal_name)
        before = cls._inspect_replay(store, lease_id, replay, allow_orphans=True)
        if before["state"] in _TERMINAL:
            # The terminal lease event won the race with a crash but the global
            # registry close did not.  Reconcile that exact state; do not change
            # it to unresolved or reopen any work.
            store.append_journal(
                _REGISTRY,
                {
                    "event": "terminal",
                    "lease_id": lease_id,
                    "schema": "pmb_episode_lease_registry_event_v1",
                    "terminal_state": before["state"],
                },
            )
            closed = cls._validate_registry(store)
            if closed["active_lease_id"] is not None:
                raise ArtifactIntegrityError(
                    "interrupted terminal registry reconciliation did not verify"
                )
            _revoke_claim_owners(store, lease_id)
            return cls.inspect(store, lease_id)
        orphan_receipts = [
            store.observe_uncommitted_receipt(path) for path in before["orphan_paths"]
        ]
        store.append_journal(
            journal_name,
            {
                "artifacts": orphan_receipts,
                "detail": {
                    "orphan_paths": before["orphan_paths"],
                    "reason": reason,
                    "restart_recovery": True,
                },
                "event": "terminal",
                "lease_id": lease_id,
                "schema": "pmb_episode_lease_event_v1",
                "state": "unresolved",
            },
        )
        store.append_journal(
            _REGISTRY,
            {
                "event": "terminal",
                "lease_id": lease_id,
                "schema": "pmb_episode_lease_registry_event_v1",
                "terminal_state": "unresolved",
            },
        )
        closed = cls._validate_registry(store)
        if closed["active_lease_id"] is not None:
            raise ArtifactIntegrityError("interrupted lease registry close did not verify")
        _revoke_claim_owners(store, lease_id)
        return cls.inspect(store, lease_id)

    @classmethod
    def _inspect_replay(
        cls,
        store: ArtifactStore,
        lease_id: str,
        replay: dict[str, Any],
        *,
        allow_orphans: bool = False,
    ) -> dict[str, Any]:
        expected_state: str | None = None
        next_slot = 1
        stopped = False
        expected_artifact_paths: set[str] = set()
        for index, record in enumerate(replay["entries"]):
            event = record["event"]
            if (
                not isinstance(event, dict)
                or set(event)
                != {"artifacts", "detail", "event", "lease_id", "schema", "state"}
                or event["schema"] != "pmb_episode_lease_event_v1"
                or event["lease_id"] != lease_id
                or not isinstance(event["artifacts"], list)
                or not isinstance(event["detail"], dict)
            ):
                raise ArtifactIntegrityError("episode lease event schema changed")
            for receipt in event["artifacts"]:
                store.verify_receipt(receipt)
                path = receipt.get("path")
                if path in expected_artifact_paths:
                    raise ArtifactIntegrityError("episode artifact was reused")
                expected_artifact_paths.add(path)

            kind, state, detail = event["event"], event["state"], event["detail"]
            artifact_paths = [receipt["path"] for receipt in event["artifacts"]]
            if index == 0:
                expected_claim_path = f"lease_ids/{lease_id}.json"
                if (
                    kind != "registered"
                    or state != "registered"
                    or artifact_paths != [expected_claim_path]
                    or set(detail) != {"registration"}
                ):
                    raise ArtifactIntegrityError("lease does not begin registered")
                claim = store.read_json_verified(event["artifacts"][0])
                if claim != {
                    "lease_id": lease_id,
                    "registration": detail["registration"],
                    "schema": "pmb_episode_lease_claim_v1",
                }:
                    raise ArtifactIntegrityError("lease registration claim changed")
                expected_state = state
                continue
            if expected_state in _TERMINAL:
                raise ArtifactIntegrityError("event appended after terminal lease state")
            if kind == "terminal" and state == "unresolved":
                if detail.get("restart_recovery") is True:
                    if (
                        set(detail) != {"orphan_paths", "reason", "restart_recovery"}
                        or detail["orphan_paths"] != artifact_paths
                        or any(
                            not path.startswith(f"leases/{lease_id}/")
                            for path in artifact_paths
                        )
                    ):
                        raise ArtifactIntegrityError("interrupted recovery evidence changed")
                elif set(detail) != {"reason"} or artifact_paths:
                    raise ArtifactIntegrityError("unresolved terminal event changed")
                if not isinstance(detail.get("reason"), str) or not detail["reason"].strip():
                    raise ArtifactIntegrityError("unresolved reason missing")
                expected_state = state
                continue
            if expected_state == "registered":
                if (
                    kind != "start_snapshotted"
                    or state != "start_snapshotted"
                    or detail
                    or artifact_paths != [f"leases/{lease_id}/start_snapshot.json"]
                    or not isinstance(store.read_json_verified(event["artifacts"][0]), dict)
                ):
                    raise ArtifactIntegrityError("lease start snapshot transition changed")
            elif kind == "controller_slot":
                slot = detail.get("slot")
                decision = detail.get("decision")
                if (
                    expected_state
                    not in (
                        {"start_snapshotted"}
                        | {f"running_round_{n}" for n in range(1, 5)}
                    )
                    or stopped
                    or slot != next_slot
                    or slot not in range(1, 5)
                    or decision not in {"task", "stop"}
                    or state != f"running_round_{slot}"
                    or set(detail) != {"decision", "slot"}
                    or artifact_paths != [f"leases/{lease_id}/slots/slot_{slot}.json"]
                ):
                    raise ArtifactIntegrityError("controller slot sequence changed")
                payload = store.read_json_verified(event["artifacts"][0])
                expected_payload_keys = (
                    {"decision", "intent", "observation", "slot", "task"}
                    if decision == "task"
                    else {"decision", "intent", "observation", "reason", "slot", "task"}
                )
                if (
                    not isinstance(payload, dict)
                    or set(payload) != expected_payload_keys
                    or payload["decision"] != decision
                    or payload["slot"] != slot
                    or not isinstance(payload["intent"], dict)
                    or (
                        decision == "task"
                        and (
                            not isinstance(payload["task"], dict)
                            or not isinstance(payload["observation"], dict)
                        )
                    )
                    or (
                        decision == "stop"
                        and (
                            payload["task"] is not None
                            or payload["observation"] is not None
                            or not isinstance(payload["reason"], str)
                            or not payload["reason"].strip()
                        )
                    )
                ):
                    raise ArtifactIntegrityError("controller slot payload changed")
                next_slot += 1
                stopped = decision == "stop"
            elif kind == "slot_5_synthesis":
                if (
                    expected_state not in {f"running_round_{n}" for n in range(1, 5)}
                    or not (stopped or next_slot == 5)
                    or detail != {"decision": "synthesize", "slot": 5}
                    or state != "candidate_frozen"
                    or artifact_paths != [f"leases/{lease_id}/slots/slot_5.json"]
                ):
                    raise ArtifactIntegrityError("forced slot-5 transition changed")
                payload = store.read_json_verified(event["artifacts"][0])
                if (
                    not isinstance(payload, dict)
                    or set(payload)
                    != {"candidate", "decision", "observation", "slot", "synthesis", "task"}
                    or payload["decision"] != "synthesize"
                    or payload["slot"] != 5
                    or payload["task"] is not None
                    or payload["observation"] is not None
                    or not isinstance(payload["candidate"], dict)
                    or not isinstance(payload["synthesis"], dict)
                ):
                    raise ArtifactIntegrityError("forced slot-5 payload changed")
            elif kind == "terminal_review_pending":
                if (
                    expected_state != "candidate_frozen"
                    or state != "terminal_review_pending"
                    or detail
                    or artifact_paths
                    != [f"leases/{lease_id}/terminal_review_request.json"]
                    or not isinstance(store.read_json_verified(event["artifacts"][0]), dict)
                ):
                    raise ArtifactIntegrityError("terminal-review transition changed")
            elif kind == "terminal":
                if (
                    expected_state != "terminal_review_pending"
                    or state not in {"closed_passed", "closed_failed"}
                    or detail != {"outcome": state.removeprefix("closed_")}
                    or artifact_paths
                    != [
                        f"leases/{lease_id}/end_snapshot.json",
                        f"leases/{lease_id}/terminal_review.json",
                    ]
                ):
                    raise ArtifactIntegrityError("terminal closure transition changed")
                end_snapshot = store.read_json_verified(event["artifacts"][0])
                review = store.read_json_verified(event["artifacts"][1])
                if (
                    not isinstance(end_snapshot, dict)
                    or not isinstance(review, dict)
                    or set(review) != {"outcome", "review"}
                    or review["outcome"] != detail["outcome"]
                    or not isinstance(review["review"], dict)
                ):
                    raise ArtifactIntegrityError("terminal closure payload changed")
            else:
                raise ArtifactIntegrityError("unknown episode lease transition")
            expected_state = state

        if expected_state is None:
            raise ArtifactIntegrityError("empty episode lease journal")
        artifact_root = f"leases/{lease_id}"
        actual = set(store.list_files(artifact_root))
        expected_under_lease = {
            path for path in expected_artifact_paths if path.startswith(artifact_root + "/")
        }
        missing = expected_under_lease - actual
        orphan_paths = sorted(actual - expected_under_lease)
        if missing:
            raise ArtifactIntegrityError("committed episode artifact is missing")
        if orphan_paths and not allow_orphans:
            raise ArtifactIntegrityError("orphaned, missing, or unexpected episode artifact")
        return {
            "controller_next_slot": next_slot,
            "early_stopped": stopped,
            "journal_head_sha256": replay["head_sha256"],
            "journal_length": replay["length"],
            "lease_id": lease_id,
            "next_slot": (
                None
                if expected_state in _TERMINAL
                or expected_state in {"candidate_frozen", "terminal_review_pending"}
                else (5 if stopped else next_slot)
            ),
            "orphan_paths": orphan_paths,
            "state": expected_state,
        }
