#!/usr/bin/env python3
"""List active E2B sandbox identities without printing credentials."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import dotenv_values
from e2b import AsyncSandbox


async def main(env_file: Path):
    key = dotenv_values(env_file).get("E2B_API_KEY")
    if not key:
        raise ValueError("E2B credential unavailable")
    pager = AsyncSandbox.list(limit=100, api_key=key, request_timeout=15)
    items = []
    while pager.has_next:
        for item in await pager.next_items():
            items.append({"sandbox_id": item.sandbox_id, "state": str(item.state),
                          "template_id": item.template_id, "metadata": item.metadata})
    print(json.dumps({"active": len(items), "sandboxes": items}, sort_keys=True,
                     separators=(",", ":")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    asyncio.run(main(parser.parse_args().env_file))
