# Earnings research harness

This review package contains selected source, an offline check and aggregate experiment evidence. The original experiments ran with local sealed inputs and a fixed execution window. The GitHub copy is for reading and offline debugging.

## Last complete experiment

Candidate 222 passed proposal review. Evaluation windows 223–225 scored the same frozen candidate on all **25 training companies and 125 targets**. It scored **3.04 / 5**, against the incumbent's **3.18 / 5**. The incumbent was retained. This was a reused training panel.

The exact historical proposal source is `5c716ddb2cdae975e8f3280f845d23e2facde1d9`. The exact final evaluation source is `9022aeb400efa332ddeb8e2ec883f7ff9ab72651`. For each exported source excerpt, `source-manifest.json` names its original file and functions. The full original evaluation checkpoint is retained locally.

## Harness sequence

The Controller proposes a change. Author implements the proposal. Review checks the candidate before it can be frozen. A separate evaluation scores the frozen candidate. The loop records stage completion and failures so interrupted work can be distinguished from a completed result.

Run the offline check from this directory with `python3 smoke.py`. It uses the standard library.
