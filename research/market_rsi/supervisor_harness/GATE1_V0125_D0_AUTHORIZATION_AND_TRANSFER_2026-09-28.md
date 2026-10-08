# Gate 1 v0.1.25 D0 standing authorization and allocation receipt

## Authority

On 2026-09-28 the user authorized the Supervisor, within the existing `$200` Market RSI cap, to transfer allocation between the non-Final `repair` and `setup` buckets up to `$0.10` per transfer and `$1` cumulatively. Final allocation may not be touched. The user also granted standing authority for one-shot Controller D0 calls only when the version is published, independently reviewed and freshly canaried: every call needs a fresh permanent ID, at most one sample, at most `$0.05`, no retry and independent terminal review.

Fetch, purchase, Train/Dev/Final read or admission, training and new releases remain separate authorization gates.

## Allocation transfer

Supervisor first reproduced the operation on a disposable copy, then appended exactly one authoritative `allocation_transfer` of `$0.006` from `repair` to `setup`.

- Transfer event hash: `4c3c98586f6058c2e1c05eb50a29391ce656ea58a6bcddc94b22258b981d0155`.
- Budget journal SHA-256 immediately after transfer: `b82e3ad984bb71bfba822a77a152a16ab2c0decf79504ef1d13a71d753ed12c8`.
- Setup allocation/available: `$10.606` / `$0.050036812`.
- Repair allocation/available: `$19.394` / `$19.39176197`.
- Total cap: unchanged at `$200`.
- Effective cost: unchanged at `$91.508603342`.
- Reserved total: unchanged at `$2.30`.
- Every existing job: unchanged.
- New reservation, dispatch or charge: none.

## Durable decision binding

A disposable-copy revision passed before the real append-only decision revision.

- Decision document SHA-256: `6142cd3979d15288b3bda21f288bdd7a93d6bcde13802655d276c5d2e48ed4d6`.
- Global-state head: `75782ed35c36e7bac5107147598089a653575e74d22d2c8b121c81191b3aa6ce`.
- Global-state journal SHA-256: `790e97e42ca3b8180f6bc475037634d31237d7655726cb586f55b984f571352b`.
- `active_cycle=null`.

The paid D0 ID remained unused at this checkpoint. No credential was read; no provider call, fetch, protected-data access or training occurred. Two fresh independent launch rechecks remain mandatory before the one-shot execution.
