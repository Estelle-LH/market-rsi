"""Common prior only; not an agent worker, access-control layer or paid launcher."""

import argparse
import hashlib
import json
from pathlib import Path


COMMON_SOURCE = Path(__file__).with_name("COMMON_RESEARCH_START.md")
ARMS = frozenset({"reset", "archive", "learn"})
KEYS = {"schema", "origin", "source_name", "common_sha256", "system_prompt"}


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def freeze_common(destination):
    """Freeze once. Caller supplies a fresh run-owned artifact path."""
    raw = COMMON_SOURCE.read_bytes()
    prompt = raw.decode("utf-8")
    if not prompt.strip():
        raise ValueError("empty common starting instructions")
    payload = {
        "schema": "market_rsi_common_start_v1",
        "origin": "human_authored_prior",
        "source_name": COMMON_SOURCE.name,
        "common_sha256": hashlib.sha256(raw).hexdigest(),
        "system_prompt": prompt,
    }
    # Exclusive creation: never overwrite an earlier arm's starting conditions.
    with Path(destination).open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    return payload["common_sha256"]


def common_system_prompt(manifest_path, arm):
    """Identical for all arms. Only this returned string is model input.

    A trusted runner must separately bind the manifest hash to each request and
    isolate arm/task evidence. Never use this to serialize historical source docs
    or the live chat. Current source drift fails closed rather than refreezing.
    """
    if arm not in ARMS:
        raise ValueError("unknown research arm")
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != KEYS:
        raise ValueError("invalid common manifest fields")
    if (payload["schema"] != "market_rsi_common_start_v1"
            or payload["origin"] != "human_authored_prior"
            or payload["source_name"] != COMMON_SOURCE.name):
        raise ValueError("invalid common manifest provenance")
    prompt = payload["system_prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("invalid common text")
    if (sha256(prompt) != payload["common_sha256"]
            or hashlib.sha256(COMMON_SOURCE.read_bytes()).hexdigest()
            != payload["common_sha256"]):
        raise ValueError("common starting instructions changed")
    return prompt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps({"common_sha256": freeze_common(args.destination)}))


if __name__ == "__main__":
    main()
