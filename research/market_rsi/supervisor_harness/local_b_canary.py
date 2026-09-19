"""Zero-paid local Docker transport canary; not a controller research round."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from market_rsi import canonical, digest, file_hash
from supervisor_harness.directional_handoff import DirectionalHandoff
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.local_b_container import LocalBFiles, docker_command, docker_ready


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "directional_guest_worker.py"


def _await_file(path: Path, process: subprocess.Popen, seconds: float = 8.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file() or path.is_symlink():
            return
        if process.poll() is not None:
            raise RuntimeError(f"B exited before {path.name}")
        time.sleep(0.01)
    raise TimeoutError(f"B did not publish {path.name}")


def _stop_exact(name: str) -> None:
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{index .Config.Labels \"market-rsi-canary\"}}", name],
        capture_output=True, text=True, timeout=5, check=False)
    if inspected.returncode == 0 and inspected.stdout.strip() == name:
        subprocess.run(["docker", "stop", "--time", "2", name],
                       capture_output=True, text=True, timeout=8, check=False)


def _container_absent(name: str) -> bool:
    inspected = subprocess.run(["docker", "inspect", name],
                               capture_output=True, text=True, timeout=5,
                               check=False)
    return inspected.returncode != 0


def run() -> dict:
    if not docker_ready():
        raise RuntimeError("Docker daemon unavailable; no B container started")
    cycle_id = "local-b-canary-" + uuid.uuid4().hex[:20]
    root = Path(tempfile.mkdtemp(prefix=cycle_id + "-", dir="/private/tmp"))
    work = root / "work"
    work.mkdir(mode=0o700)
    name = "market-rsi-b-" + cycle_id
    command = docker_command(container_name=name, source=SOURCE, work=work,
                             expected_orders=20)
    (root / "decision.md").write_text("zero-paid local synthetic canary; no formal admission\n")
    state = SupervisorGlobalState(root / "local-state", root / "decision.md")
    snapshot = state.initialize()
    input_sha = digest({"schema": "market_local_b_input_v1", "cycle_id": cycle_id})
    state.claim(cycle_id, expected_head_sha256=snapshot["head_sha256"],
                source_sha256=file_hash(SOURCE), prior_canary_sha256="0" * 64)
    (root / "manifest.json").write_text(canonical({
        "schema": "market_local_b_canary_manifest_v1", "cycle_id": cycle_id,
        "container_name": name, "guest_source_sha256": file_hash(SOURCE),
        "image": command[command.index("--workdir") + 2],
        "expected_orders": 20, "guest_command": command,
        "synthetic_only": True, "formal_admission": False}) + "\n")
    process = None
    b = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        b = SimpleNamespace(sandbox_id=name, files=LocalBFiles(work))
        handoff = DirectionalHandoff(researcher_sandbox=b, state=state,
                                     cycle_id=cycle_id, input_sha256=input_sha,
                                     receipt_root=root / "handoff")
        for sequence in range(20):
            task = {"schema": "market_directional_task_v1", "cycle_id": cycle_id,
                    "input_sha256": input_sha, "sequence": sequence,
                    "task_id": f"synthetic-{sequence:03d}",
                    "public_text": f"zero-paid public synthetic task {sequence:03d}"}
            handoff.send_task(sequence, task)
            _await_file(work / "acks" / f"{sequence:03d}.json", process)
            handoff.receive_ack(sequence)
            _await_file(work / "events" / f"{sequence:03d}.json", process)
            handoff.receive_event(sequence)
            handoff.read_event_for_a(sequence)
        stdout, stderr = process.communicate(timeout=8)
        (root / "guest-stdout.jsonl").write_text(stdout)
        (root / "guest-stderr.txt").write_text(stderr[:8192])
        if process.returncode != 0:
            raise RuntimeError(f"B exit={process.returncode}")
        milestones = [json.loads(line) for line in stdout.splitlines()]
        if len(milestones) != 40:
            raise ValueError("B milestone count is not 40")
        if not _container_absent(name):
            raise ValueError("exact B container remains after exit")
        summary = handoff.finish()
        if not summary["friction_criterion_passed"]:
            raise ValueError("local B handoff latency or integrity failed")
        state.close(cycle_id, outcome="passed", review_sha256=digest(summary))
        result = {"schema": "market_local_b_canary_result_v1", "cycle_id": cycle_id,
                  "artifact_root": str(root), "passed": True,
                  "friction": summary, "container_exited": True,
                  "exact_container_cleanup_verified": True,
                  "synthetic_only": True, "formal_admission": False}
        (root / "result.json").write_text(canonical(result) + "\n")
        return result
    except BaseException as exc:
        (root / "failure.txt").write_text(f"{type(exc).__name__}: {exc}\n")
        state.close(cycle_id, outcome="failed")
        raise
    finally:
        if b is not None:
            b.files.close()
        if process is not None and process.poll() is None:
            _stop_exact(name)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="start one new synthetic container")
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("Use --run for a fresh zero-paid synthetic container canary")
    result = run()
    print(json.dumps({"cycle_id": result["cycle_id"],
                      "artifact_root": result["artifact_root"],
                      "passed": result["passed"],
                      "handoff_p95_ns": result["friction"]["handoff_p95_ns"],
                      "event_visibility_p95_ns": result["friction"]["event_visibility_p95_ns"]}))


if __name__ == "__main__":
    main()
