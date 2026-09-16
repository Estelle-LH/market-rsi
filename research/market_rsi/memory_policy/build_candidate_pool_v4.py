"""Freeze the score-free v4 source pool from raw-file names and byte sizes."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import fresh_json, load_json


GROUPS = [
    {
        "name": "initial-train",
        "role": "initial_train",
        "required": 3,
        "candidates": [
            ("2026-09-11T06", 34_263_301),
            ("2026-09-11T07", 29_539_981),
            ("2026-09-11T08", 26_695_508),
        ],
    },
    {
        "name": "rolling-dev",
        "role": "dev",
        "required": 8,
        "candidates": [
            ("2026-09-11T09", 30_085_711),
            ("2026-09-11T10", 26_292_719),
            ("2026-09-11T11", 29_850_687),
            ("2026-09-11T13", 26_766_297),
            ("2026-09-11T14", 24_105_365),
            ("2026-09-11T15", 27_802_863),
            ("2026-09-11T16", 17_491_005),
            ("2026-09-11T17", 28_196_915),
        ],
    },
    {
        "name": "final-2026-09-11",
        "role": "final",
        "required": 5,
        "candidates": [
            ("2026-09-11T18", 44_822_853),
            ("2026-09-11T19", 47_950_716),
            ("2026-09-11T20", 39_921_300),
            ("2026-09-11T21", 37_490_067),
            ("2026-09-11T22", 52_270_551),
            ("2026-09-11T23", 246_518_987),
        ],
    },
    {
        "name": "final-2026-09-12",
        "role": "final",
        "required": 5,
        "candidates": [
            ("2026-09-12T04", 118_434_215),
            ("2026-09-12T05", 37_571_924),
            ("2026-09-12T06", 25_481_692),
            ("2026-09-12T07", 21_706_627),
            ("2026-09-12T08", 21_360_514),
            ("2026-09-12T09", 21_842_569),
            ("2026-09-12T10", 21_229_294),
        ],
    },
    {
        "name": "final-2026-09-13",
        "role": "final",
        "required": 5,
        "candidates": [
            ("2026-09-13T16", 57_852_752),
            ("2026-09-13T17", 126_587_733),
            ("2026-09-13T18", 307_540_886),
            ("2026-09-13T19", 307_130_584),
            ("2026-09-13T20", 257_519_027),
            ("2026-09-13T21", 138_908_484),
            ("2026-09-13T22", 128_107_903),
            ("2026-09-13T23", 118_575_960),
        ],
    },
    {
        "name": "final-2026-09-14",
        "role": "final",
        "required": 5,
        "candidates": [
            ("2026-09-14T10", 26_273_028),
            ("2026-09-14T11", 23_827_080),
            ("2026-09-14T12", 25_508_532),
            ("2026-09-14T13", 27_207_653),
            ("2026-09-14T14", 33_822_914),
            ("2026-09-14T15", 29_495_433),
            ("2026-09-14T16", 27_236_657),
        ],
    },
]


def build(prior_pool, v3_selection, output):
    prior = load_json(prior_pool)
    selection = load_json(v3_selection)
    exposed = set(prior["prior_exposure"])
    exposed.update(row["session"] for row in selection["initial_train"])
    exposed.update(row["session"] for row in selection["dev"][:2])
    groups = []
    seen = set()
    for group in GROUPS:
        candidates = [
            {"session": session, "compressed_bytes": compressed_bytes}
            for session, compressed_bytes in group["candidates"]
        ]
        names = [row["session"] for row in candidates]
        if names != sorted(names) or seen.intersection(names) or exposed.intersection(names):
            raise ValueError("v4 candidates must be chronological, unique, and unopened")
        seen.update(names)
        groups.append({**group, "candidates": candidates})
    value = {
        "schema": "memory_policy_candidate_pool_v1",
        "selection_rule": (
            "first passing candidates in each ordered group; no target statistics"
        ),
        "groups": groups,
        "prior_exposure": sorted(exposed),
    }
    fresh_json(output, value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-pool", required=True, type=Path)
    parser.add_argument("--v3-selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build(args.prior_pool, args.v3_selection, args.output)
    print({
        "candidates": sum(len(group["candidates"]) for group in result["groups"]),
        "required": sum(group["required"] for group in result["groups"]),
        "prior_exposure": len(result["prior_exposure"]),
    })
