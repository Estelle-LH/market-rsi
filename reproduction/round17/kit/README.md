# Round 17 reproduction kit

This directory turns the handover into executable, public-safe controls. It does not contain the private archive required for a paid live run.

## Included

- `environment.json`: observed successful software/runtime versions.
- `requirements-observed.txt`: exact package inventory observed in the successful pinned Python runtime.
- `reproduction-summary.json`: sanitized historical and fresh aggregate result.
- `check_environment.py`: offline verification and optional strict-live source/Python/Docker checks.
- `verify_local_manifest.py`: verifies the local-only source, Python, credential permissions, ledger schema and artifact hashes without printing secrets or paths.
- `run_reviewed_runtime.py`: always runs preflight first and launches only an unchanged reviewed runtime; live execution requires two explicit flags.
- `aggregate_closures.py`: verifies disjoint formal closure rows and writes a public-safe aggregate without rerunning model or scorer.
- `schemas/local-artifact-manifest.schema.json`: contract for the private local manifest.
- `templates/local-artifact-manifest.example.json`: path-free example to copy outside Git.

## 1. Public offline check

```sh
python3.12 reproduction/round17/kit/check_environment.py
python3.12 reproduction/round17/verify.py
```

## 2. Local-only readiness check

Copy the example manifest outside the repository, fill it with absolute local paths and exact SHA-256 values, then restrict it:

```sh
cp reproduction/round17/kit/templates/local-artifact-manifest.example.json \
  /path/to/private/LOCAL_ARTIFACT_MANIFEST.json
chmod 600 /path/to/private/LOCAL_ARTIFACT_MANIFEST.json

python3.12 reproduction/round17/kit/verify_local_manifest.py \
  /path/to/private/LOCAL_ARTIFACT_MANIFEST.json --require-idle
```

The credential file is checked for owner-only `0600` permissions and exactly one non-empty `OPENAI_API_KEY` entry. The key value is never printed.

## 3. Strict-live environment check

```sh
python3.12 reproduction/round17/kit/check_environment.py --strict-live \
  --source-root /path/to/exact/historical/source \
  --python-bin /path/to/pinned/python3.12
```

The exact historical checkout is distinct from this path-anonymized public export.

## 4. Preflight and run one reviewed runtime

Preflight only:

```sh
python3.12 reproduction/round17/kit/run_reviewed_runtime.py \
  --source-root /path/to/exact/historical/source \
  --python-bin /path/to/pinned/python3.12 \
  --runtime /path/to/runtime-reviewed.json \
  --expected-runtime-sha256 <64-hex-sha256>
```

Paid execution requires both explicit flags:

```sh
python3.12 reproduction/round17/kit/run_reviewed_runtime.py \
  --source-root /path/to/exact/historical/source \
  --python-bin /path/to/pinned/python3.12 \
  --runtime /path/to/runtime-reviewed.json \
  --expected-runtime-sha256 <64-hex-sha256> \
  --local-manifest /path/to/private/LOCAL_ARTIFACT_MANIFEST.json \
  --execute --acknowledge-fees
```

For paid execution the wrapper re-verifies the local manifest and requires zero pending ledger requests. It refuses the already closed reproduction IDs 242, 243 and 244. It does not create or approve a runtime. Runtime assembly, independent review, input checkpoint and prelaunch admission remain formal local control-plane steps.

## 5. Aggregate closed windows

```sh
python3.12 reproduction/round17/kit/aggregate_closures.py \
  --frozen /path/to/TRAIN25-CLEAN154-FROZEN-CANDIDATE.json \
  --historical /path/to/TRAIN25-CLEAN-ROUND17-FINAL-COMPARISON.json \
  --closure /path/to/window-1-closure.json \
  --closure /path/to/window-2-closure.json \
  --closure /path/to/window-3-closure.json \
  --output /path/to/new-public-safe-aggregate.json
```

## Remaining non-public dependency

A true live rerun still requires a securely transferred local archive containing the exact frozen descriptor, point-in-time SEC corpus, scorer/QA bindings, ledger/grants, runtime Python, campaign authorities and independent review/checkpoint machinery. The local manifest verifies that archive but deliberately does not publish it.

The public export contains anonymized absolute paths. Do not silently rewrite it and call the result the original Source. Either use the exact historical checkout with its authenticated local archive, or create and review a new portable Source as a separate experiment.
