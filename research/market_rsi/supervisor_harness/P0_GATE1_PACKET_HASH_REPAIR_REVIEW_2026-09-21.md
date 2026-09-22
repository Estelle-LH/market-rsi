# P0 Gate 1 packet-hash repair — local review

Status: **causal repair implemented and locally validated through the complete
production CLI/Supervisor boundary; source is uncommitted and unpublished; no
paid retry is authorized**.

## Preserved failure

The immutable attempt `market-rsi-gate1-controller-20260921-01` exited before
provider credential access with `Gate 1 packet differs from frozen hash`.
It made zero model calls, fetched no data, incurred `$0` provider cost, created
one Supervisor incident, performed exact cleanup and was not retried.

## Root cause

The frozen packet receipt committed SHA-256 of the pretty-printed
`controller-input.json` file:

`097919661bb251dc93ea37a7c41ad0cec1e390fe2bb9ecbb29277a1e69a9dce1`

The live runner loaded the same JSON object and compared its canonical digest:

`239f7bc35aee19ec229ada3a2da0c56b31c607a27dd453c94dfc82399597512e`

The object was unchanged; the serialized bytes differed. Unit and synthetic
transaction canaries used canonical JSON directly and therefore did not cover
the real pretty-printed artifact path.

## Repair

1. New packet receipts name both `packet_file_sha256` and
   `packet_canonical_sha256`; the historical `packet_sha256` remains the file
   commitment for compatibility.
2. The Supervisor parent checks both commitments before creating its output
   directory or starting a child.
3. The live child repeats both checks and passes only the canonical commitment
   into the object-level transaction.
4. Tests prove that either mismatch stops before `subprocess.Popen` and before
   a Supervisor output root exists.
5. A dedicated zero-provider canary checks the exact historical packet and its
   original receipt through the same parent preflight helper.
6. The canary is part of the immutable protocol source manifest.

## Production-source hashes

| File | SHA-256 |
| --- | --- |
| `build_p0_gate1_controller_packet.py` | `2e9d2f26d94c96b9684a4d9c8f375044783ede5e58eba20b18529a8cf0ae5798` |
| `p0_gate1_controller_live_entry.py` | `cefe955a2bcd95cf12696a6b970ee5cca39da7555b1d9abf2cf7cd3bb12b8051` |
| `run_p0_gate1_packet_preflight_canary.py` | `ce5952d24bfcf24949bf5a9853971118806f2d5ff219980334025306c3fa116a` |
| `p0_gate1_controller_supervisor_parent.py` | `05af4b8c40d4873fb29981d3340dfd35fd3e74c1e6d8f432cb460729ef5e6fc6` |
| `p0_gate1_controller_cli_canary_child.py` | `d2ff9c3ba2a199d0d1aa089868c495f30d2d75665a10cd327a78f3677a8421c8` |
| `run_p0_gate1_controller_production_cli_canary.py` | `4b786c68bdd5768ad2b8e73c0bff0eb590fa4f2aedc0bfaf329f944c38247932` |

Current unpublished protocol manifest: 318 files, aggregate SHA-256
`4f1f95fa8fc543cb592e0070727b3597518e82e1a412f62e22d5a087f237e909`.

## Verification

- 19 focused Gate 1 tests passed after the core repair.
- 21 focused tests passed after adding the exact packet canary and publication
  manifest binding.
- Full Supervisor discovery ran 381 tests. The restricted runner passed 379;
  its two expected local process/socket denials both passed separately with
  local permissions. There is no demonstrated regression: 381/381 checks pass
  in their required environments.
- Fresh zero-provider artifact
  `artifacts/p0-gate1-packet-preflight-canary-20260921-01` passed against the
  exact historical pretty-printed packet and receipt. It recorded both hashes,
  started no child, claimed no run ID, made zero provider calls, admitted no
  data and cost `$0`.
- `git diff --check` passes.
- The protected `RESEARCH_STATE.md` and append-only global journal were advanced
  together; the global active cycle remains null.
- Fresh production-path artifact
  `artifacts/p0-gate1-production-cli-canary-20260921-04` passed through the real
  parent process, exact production argument builder, child process identity,
  Supervisor claim, packet file/canonical checks, synthetic global state and
  synthetic budget reconciliation. Only the provider and Git publication
  lookup were replaced by explicit offline fixtures. It made zero provider
  calls, fetched no data, admitted no formal data and cost `$0`. The synthetic
  ledger recorded `$0.00005103`; that is fixture accounting, not a charge.
- Two early shell attempts never entered the canary: `-01` lacked the project
  import path and `-02` was denied local artifact write permission. Neither
  created an artifact, claim, provider call or cost. `-03` passed before the
  review restricted the child override to the one exact canary executable and
  synthetic tag; final source was then retested under fresh ID `-04`, which is
  the current admitted production-path canary.

## Remaining gates

1. Independently review the exact diff and the canary substitution boundary.
2. Obtain explicit authorization before committing, annotating a new immutable
   tag and pushing only to the user's fork.
3. Rerun the same zero-provider acceptance under those published bytes.
4. Obtain fresh user authorization before any new paid Gate 1 Controller
   decision. The original one-decision, no-retry authorization has been
   consumed by the preserved pre-provider failure.

No prediction run, public fetch, data admission, Dev/Final read or provider
spend is authorized by this review.
