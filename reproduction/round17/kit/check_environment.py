#!/usr/bin/env python3
"""Public-safe offline/strict-live environment doctor for Round 17."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROUND17 = HERE.parent
REPO = ROUND17.parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(source, *args):
    return subprocess.run(["git", *args], cwd=source, check=True,
                          capture_output=True, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path,
                        help="Exact private historical checkout; required for --strict-live")
    parser.add_argument("--python-bin", type=Path,
                        help="Pinned private Python binary; required for --strict-live")
    parser.add_argument("--strict-live", action="store_true")
    args = parser.parse_args()

    env = json.loads((HERE / "environment.json").read_text())
    evidence = json.loads((ROUND17 / "evidence.json").read_text())
    checks = {}
    for axis, expected in evidence["program_sha256"].items():
        path = ROUND17 / "frozen" / f"program_{axis}.py"
        checks[f"frozen_{axis}"] = sha256(path) == expected
        compile(path.read_bytes(), str(path), "exec")
    checks["python_major_minor"] = sys.version_info[:2] == (3, 12)
    checks["public_source_manifest"] = (REPO / "source-export.json").is_file()

    if args.strict_live:
        if args.source_root is None or args.python_bin is None:
            parser.error("--strict-live requires --source-root and --python-bin")
        source = args.source_root.resolve()
        python = args.python_bin.resolve()
        checks["historical_source_commit"] = git(source, "rev-parse", "HEAD") == env["historical_source_commit"]
        checks["historical_source_tracked_clean"] = (
            subprocess.run(["git", "diff", "--quiet"], cwd=source).returncode == 0
            and subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=source).returncode == 0
        )
        checks["pinned_python_hash"] = python.is_file() and sha256(python) == env["python"]["binary_sha256"]
        docker = subprocess.run(["docker", "version", "--format", "{{.Client.Version}}|{{.Server.Version}}"],
                                capture_output=True, text=True)
        checks["docker_available"] = docker.returncode == 0 and "|" in docker.stdout

    report = {
        "schema": "round17_environment_check_v1",
        "mode": "strict_live" if args.strict_live else "offline_public",
        "python": platform.python_version(),
        "machine": platform.machine(),
        "checks": checks,
        "pass": all(checks.values()),
    }
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
