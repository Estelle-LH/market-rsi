"""Trusted Harbor-owner child. Its key never enters the candidate sandbox."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harbor_process import read_context, run_child


def main():
    raw = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("bounded input exceeded")
    data = json.loads(raw)
    if data != read_context(data["root"]):
        raise ValueError("stdin differs from parent-owned process input")
    asyncio.run(run_child(data["root"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
