#!/usr/bin/env python3
"""Adopt one unchanged pre-Dev objective for a formal learning study."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_rsi import fresh_json
from objective_contract import promote_diagnostic_objective_for_formal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-contract", required=True, type=Path)
    parser.add_argument("--output-receipt", required=True, type=Path)
    args = parser.parse_args()
    formal, receipt = promote_diagnostic_objective_for_formal(
        json.loads(args.input.read_bytes())
    )
    fresh_json(args.output_contract, formal)
    fresh_json(args.output_receipt, receipt)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
