"""Read hash-pinned, runner-owned metadata proof files without label access.

The caller must supply the manifest hash from the runner's independent review,
never from the controller. Hashes prove unchanged bytes, NOT factual truth or
that review occurred. No production proof builder or evaluator is wired here;
the resulting gate is informational and never grants execution authority.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from independent_validation import PROOF_KINDS, sha, validate_proposal, check_runner_evidence
from market_rsi import digest

MAX_PROOF_BYTES = 2_000_000
TOP_FIELDS = {
    'source_compatibility': {'source_compatible', 'model_sha256', 'selected_plan_sha256',
                             'objective_sha256', 'source_contract_sha256'},
    'exposure_history': {'exposure_audit_complete', 'new_labels_exposed_to_controller', 'cohort_never_scored'},
    'whole_market_split': {'whole_market_isolation', 'opened_market_groups'},
    'coverage': set(),
    'causal_timestamps': {'causal_timestamps_verified', 'latest_learning_label_available_ms'},
    'full_population': {'quiet_rows_retained', 'same_evaluation_population',
        'policy_frozen_before_new_label_access', 'source_values_imputed', 'future_value_filter', 'refit_requested'},
    'cost_bound': {'budget_authorization_sha256', 'runner_cost_upper_usd',
        'new_download_bytes_upper', 'authorized_download_headroom_bytes', 'vendor_purchase_usd'},
}
SESSION_FIELDS = {'exposure_history': {'exposure_state'},
                  'whole_market_split': {'market_groups'},
                  'coverage': {'closed', 'coverage_fraction'},
                  'causal_timestamps': {'first_feature_available_ms'}}


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON object key')
        value[key] = item
    return value


def read_pinned_json(root, relative, expected_sha256):
    """Walk below a runner-owned directory using no-follow directory handles."""
    sha(expected_sha256)
    path = Path(relative)
    if (not isinstance(relative, str) or path.is_absolute() or not relative
            or '..' in path.parts or str(path) != relative):
        raise ValueError('normalized runner-relative proof path required')
    root = Path(root).absolute()
    # Reject symlinked ancestors too; no implicit resolve into a different root.
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('runner proof root has a symlink ancestor')
    handles = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); handles.append(directory)
        for part in path.parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            handles.append(directory)
        fd = os.open(path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        handles.append(fd); before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_PROOF_BYTES:
            raise ValueError('bounded regular proof file required')
        chunks = []; size = 0
        while size <= MAX_PROOF_BYTES:
            data = os.read(fd, min(65536, MAX_PROOF_BYTES + 1 - size))
            if not data:
                break
            chunks.append(data); size += len(data)
        after = os.fstat(fd); raw = b''.join(chunks)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != before.st_size:
            raise ValueError('proof changed while reading')
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError('proof bytes changed from runner commitment')
        value = json.loads(raw, object_pairs_hook=_object,
                           parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite JSON number')))
        if not isinstance(value, dict):
            raise ValueError('proof JSON object required')
        return value
    finally:
        for fd in reversed(handles):
            os.close(fd)


def load_evidence(root, manifest_relative, expected_manifest_sha256, proposal, context):
    checked = validate_proposal(proposal, context)
    manifest = read_pinned_json(root, manifest_relative, expected_manifest_sha256)
    if (set(manifest) != {'schema', 'context_sha256', 'proposal_sha256', 'proofs'}
            or manifest['schema'] != 'historical_runner_proof_manifest_v1'
            or manifest['context_sha256'] != context['context_sha256']
            or manifest['proposal_sha256'] != checked['proposal_sha256']
            or set(manifest['proofs']) != PROOF_KINDS):
        raise ValueError('exact context/proposal-bound independent proof set required')
    runner = {'schema': 'historical_validation_runner_evidence_v1',
              'context_sha256': context['context_sha256'], 'proposal_sha256': digest(proposal),
              'reviewed_proof_hashes': {}}
    session_records = {day: {'utc_date': day} for day in proposal['utc_dates']}
    paths = set()
    for kind in sorted(PROOF_KINDS):
        entry = manifest['proofs'][kind]
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256'} or entry['path'] in paths:
            raise ValueError('distinct exact proof references required')
        paths.add(entry['path']); proof = read_pinned_json(root, entry['path'], entry['sha256'])
        if (set(proof) != {'schema', 'kind', 'context_sha256', 'proposal_sha256', 'payload'}
                or proof['schema'] != 'historical_runner_metadata_proof_v1' or proof['kind'] != kind
                or proof['context_sha256'] != context['context_sha256']
                or proof['proposal_sha256'] != digest(proposal)):
            raise ValueError('proof is bound to another kind/context/proposal')
        payload = proof['payload']; expected = TOP_FIELDS[kind] | ({'sessions'} if kind in SESSION_FIELDS else set())
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError('exact per-kind proof payload required')
        for field in TOP_FIELDS[kind]:
            if field in runner:
                raise ValueError('proofs cannot overwrite another proof')
            runner[field] = payload[field]
        if kind in SESSION_FIELDS:
            records = payload['sessions']
            if (not isinstance(records, list) or any(not isinstance(s, dict) for s in records)
                    or [s.get('utc_date') for s in records] != proposal['utc_dates']):
                raise ValueError('proof sessions must exactly match the frozen dates')
            for record in records:
                if set(record) != SESSION_FIELDS[kind] | {'utc_date'}:
                    raise ValueError('exact per-kind session fields required')
                for key in SESSION_FIELDS[kind]:
                    session_records[record['utc_date']][key] = record[key]
        runner['reviewed_proof_hashes'][kind] = entry['sha256']
    runner['sessions'] = [session_records[d] for d in proposal['utc_dates']]
    return runner


def inspect_bundle(root, manifest_relative, expected_manifest_sha256, proposal, context, budget):
    runner = load_evidence(root, manifest_relative, expected_manifest_sha256, proposal, context)
    checked = check_runner_evidence(proposal, context, runner, budget)
    return {**checked, 'proof_file_integrity_verified': True,
            'runner_manifest_sha256': expected_manifest_sha256,
            'proof_truth_proven_by_hashes': False, 'production_proof_builders_wired': False,
            'execution_admitted': False, 'dispatch_token_created': False,
            'next_required': 'Independent factual proof builders/review, immutable one-shot cohort claim, '
                'budget reservation and immediate recheck before any label access. This module does not execute.'}
