# Historical NFL price-change task

The [source index](profile.json) points to the existing implementation; it does
not configure, authorize or launch a run. Existing hash-bound operation and
batch manifests remain authoritative. Source files stay in their original
locations for historical bindings and replay.

The target is a same-token trade-VWAP change over five minutes, using trailing
30-second VWAP windows. The existing scorer uses paired game-equal MSE and
reports date/week uncertainty and coverage on common rows. Baselines are no
price change and the frozen ordinary HGB recipe in the indexed runner.

This is repeatedly inspected historical Train research. Trade VWAP is not an
executable bid/ask quote; the task does not establish profitable trading,
untouched evaluation or self-improvement. Earnings is a planned adapter and
has no implemented profile here.
