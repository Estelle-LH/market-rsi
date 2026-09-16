"""Zero-provider controller/tool canary bound to the v2 study sources."""
from __future__ import annotations

import argparse
from pathlib import Path

import memory_policy.canary as engine
from memory_policy.study_v2 import hashes


def run(output, spec):
    engine.hashes = hashes
    return engine.run(Path(output).resolve(), Path(spec).resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    run(args.output, args.spec)
