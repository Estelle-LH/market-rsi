"""Compatibility command; the developer check implementation is in market_rsi."""
from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from market_rsi.checks import main

    raise SystemExit(main())
