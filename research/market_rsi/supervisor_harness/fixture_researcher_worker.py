"""Tiny real subprocess for the zero-paid cycle canary; NOT a sandbox."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import file_hash, fresh_json, load_json


def main(root: Path) -> None:
    source = root / "facts.json"
    content = load_json(source)
    if content != {"scope": "synthetic_fixture", "message": "public canary"}:
        raise ValueError("unexpected fixture input")
    observed = file_hash(source)
    fresh_json(root / "trace.json", {"schema": "research_fixture_trace_v1",
                                     "calls": [{"action": "read_public_fixture",
                                                "input_sha256": observed}]})
    fresh_json(root / "output.json", {"schema": "research_fixture_output_v1",
                                      "observed_sha256": observed})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    main(parser.parse_args().root)
