# P0 Gate 1 Controller adapter — local review

Status: **offline adapter, transaction, live-entry ordering and Supervisor-parent wiring pass; source is uncommitted and unpublished; paid execution remains blocked**.

## Why this layer was needed

The existing Gate 1 components could build the aggregate input, validate a
decision, compile a plan-only task, and take one bounded public snapshot. They
did not own the actual Controller sample. A direct model call would therefore
have lacked one permanent claim tying together the first response, provider
receipt, parsed decision, compiled task and source version.

The new adapter fills only that gap. It does not fetch data, run a prediction,
open Dev/Final, or admit a dataset.

## Enforced behavior

1. Accept only the exact frozen aggregate packet. The existing packet at
   `artifacts/p0-data-admission-gate1-packet-20260919-01/controller-input.json`
   matches exactly and has SHA-256
   `097919661bb251dc93ea37a7c41ad0cec1e390fe2bb9ecbb29277a1e69a9dce1`.
2. Use the pinned GLM model, high-effort tokenizer contract, seed 23, no tools,
   one sample, a 60-second sample deadline and at most 2,048 output tokens.
3. Atomically consume one permanent cycle ID before writing the run output.
4. Preserve the first raw provider object and raw text before semantic review.
5. Never resample or repair a malformed, truncated or authority-bearing answer.
6. Reject model-supplied URLs, paths, commands, credentials, sealed roles or
   any fields outside the frozen decision schema.
7. Compile a successful answer into a plan-only task. Network fetch, purchase,
   sealed/scored data and formal admission all remain false.
8. Bind every artifact and executable source file by SHA-256.

## Exact current source hashes

| File | SHA-256 |
| --- | --- |
| `build_p0_gate1_controller_packet.py` | `22b5a09c4a23e3cf7af6f4a94e4213e9c6d17d4200e86904bbae868b0a95e8fd` |
| `p0_gate1_research_contract.py` | `81728be2ae372e5d8ad325a3191608eedb3bc25b2ba37be0c29015424d1bfbb3` |
| `p0_gate1_controller_adapter.py` | `93803db5e953df71b45743210af42009313f2f583155c9058bc52fb7b44b5904` |
| `p0_gate1_controller_outer.py` | `0f3290f556f8cb1a80ebd13e63d448dc46ac1e24824ff05620855e642967c9b1` |
| `p0_gate1_controller_live_entry.py` | `994cc6525fa3ff1a88715764012b3eb2526a3783238a5edaaced40db1d1073f2` |
| `p0_gate1_controller_supervisor_parent.py` | `20c355a56160a78d03ac9bc69b5fecab16b19c208489bea1631d5b80598e6139` |
| `run_p0_gate1_controller_adapter_canary.py` | `8f3ae21818289f016840a60f5b5ad1d7f101691eeae5f29db96761b06d68e2e4` |
| `run_p0_gate1_controller_outer_canary.py` | `b5fea29d939529937ef36657113b419cb7fa33374dc8e35820840d766666f0c9` |
| `p0_gate1_public_fetch.py` | `76620786849db45ebc3d747bd469fcff65019b9a7b27f5904069fd5e5eb712df` |
| `p0_gate1_watched_fetch.py` | `444e8c042b6790e07a6916a074594012fa44b18446afcfb863e8b9166e43f930` |
| `protocol_source_release.py` | `c74c6c6ed1a84100ce9dcd1a3889e619e8a1802b5643567a0558bdbf833e0f08` |

## Verification

- The broader Supervisor suite ran 373 checks. 371 passed in the restricted
  runner; the two local child/socket checks blocked by that runner both passed
  when rerun with their required local permissions.
- The real frozen tokenizer encoded the complete request as 700 input tokens.
  The hard cost upper bound at 2,048 output tokens is `$0.0282852`; no provider
  call was made during this check.
- Fresh zero-paid adapter canary
  `artifacts/p0-gate1-controller-adapter-canary-20260921-02` passed under the
  current adapter bytes. It used one
  fake response, compiled one plan-only task, made zero provider calls, cost
  `$0`, fetched nothing and admitted no data.
- Current adapter canary hashes:
  - adapter result: `5cad92b5805f2491495ec0d981ecaa6951cff8644402afdbf365fd8bcd040f5a`
  - permanent claim: `5d4aa5dbf8076c94a2228d3ea58da8e90781a43f03e2ec8825735e65c2661463`
  - decision: `68458246a9444d5a0e7155171cad03d03c2fefa271b5c8f1732d088ebb45b44d`
  - compiled task: `e33e1165c3fdcc06fe7dccc3c443d759e52352d8873b83fa9b8e36049cca94fb`
- Fresh zero-paid outer-transaction canary
  `artifacts/p0-gate1-controller-outer-canary-20260921-01` also passed. It
  exercised global claim/close, reserve/dispatch/metered settlement, the one
  adapter call and deterministic review. The publication and provider were
  explicitly synthetic: provider calls and actual provider cost were zero.
  Its synthetic ledger recorded `$0.00005103` only to test metered settlement.
  Independent readback matched result hash
  `5072df4adc37491f63453189ef47574ccb6b8b4536ff650491f82ec79ff14054`,
  review hash
  `fc35c60ccd52b809f72f07fa8f4a540304d168306fd262198070f8a85d81dde4`
  and task hash
  `179e3429c5fffcfb8b0cef11fcbd6ec29711350d97ffe84b5dddcb49a069ef54`.
  The job was terminal with no reservation remaining and global active cycle
  was null.
- Failure tests prove that a pre-send failure cancels the reservation, a
  malformed but metered answer settles actual returned usage, an unmetered
  timeout conservatively retains the `$0.05` upper, and an unreconciled
  dispatched crash keeps the global cycle active for repair.
- The live entry completes publication, packet, runtime, state, budget,
  duplicate-process and exact Supervisor ownership checks before reading the
  Tinker credential. The parent reuses the already accepted durable process
  monitor and exact cleanup control.

## Remaining gates

1. The Gate 1 production files and both canaries must be committed, tagged and
   published to the user's fork under a new immutable version.
2. Both zero-paid canaries and the parent-control acceptance must be repeated
   or reverified under the published bytes.
3. Only then may one fresh one-sample Controller source decision run. Its task
   remains plan-only until a separately admitted single public fetch.

Current unpublished protocol manifest: 315 files, aggregate SHA-256
`e530e3a3b8be5715af4c864da778aef84ed4216c700b8387e4077d60f7868992`.

No paid Controller call is authorized by this local review alone.
