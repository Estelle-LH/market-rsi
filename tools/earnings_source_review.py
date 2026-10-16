"""Materialize unchanged literal Author bytes and return a pending data spec."""
from copy import deepcopy
from pathlib import Path
import os

from earnings_capacity_adapter import author_payload, author_candidate, profile, micro_delta
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class SourceReview:
    def __init__(self, source_root, *, slots, proposer_id, reviewer_id, micro_policy=None):
        if micro_policy not in {None, "earnings_micro_v1"}:
            raise ValueError('Unknown explicit micro policy')
        self.micro_policy = micro_policy
        self.root, self.slots = Path(source_root), deepcopy(slots)
        if (not self.root.is_absolute() or self.root.resolve(strict=True) != self.root
                or type(slots) is not dict or not slots
                or type(proposer_id) is not str or not proposer_id
                or type(reviewer_id) is not str or not reviewer_id or proposer_id == reviewer_id):
            raise ValueError('Canonical host source root and distinct actors required')
        self.proposer, self.reviewer = proposer_id, reviewer_id
        names, candidates = [], []
        for slot, row in slots.items():
            path = Path(slot)
            if (not path.is_absolute() or path.resolve() != path
                    or type(row) is not dict or set(row) != {'candidate_id', 'R', 'H'}
                    or type(row['candidate_id']) is not str or not row['candidate_id']):
                raise ValueError('Exact prospective review slots/source paths required')
            candidates.append(row['candidate_id'])
            for axis in ('R', 'H'):
                name = engine.identity.path(row[axis])
                if not name.endswith('.py') or (self.root/name).resolve() != self.root/name:
                    raise ValueError('Canonical new literal source path required')
                names.append(name)
        if len(set(names)) != len(names) or len(set(candidates)) != len(candidates):
            raise ValueError('Distinct source paths and candidate IDs required')

    def review(self, chosen, author_original, descriptor, slot):
        if slot not in self.slots or Path(slot).exists() or Path(slot).resolve() != Path(slot):
            raise ValueError('Undeclared or consumed source review slot')
        before = engine.identity.validate(descriptor['parent_identity'])
        axis = chosen['axis']
        if (axis not in {'R', 'H'} or chosen['parent_pair_sha256'] != descriptor['parent_pair_sha256']
                or chosen['parent_pair_sha256'] != digest(engine.activation.pair(before))
                or chosen['parent_pair_sha256'] != digest(descriptor['micro_evolution']['active_pair'])):
            raise ValueError('Current exact source-review decision required')
        name = descriptor['parent_entrypoints'][axis]
        old = profile(engine.activation._read({'path': str(self.root/name),
            'sha256': before['components'][axis]['sources'][name]}), axis)
        candidate = author_candidate(author_original, old, chosen)
        if self.micro_policy is not None:
            micro_delta(old, candidate['profile'], axis)
        if (candidate != engine.read(descriptor['candidate'])
                or engine.read(descriptor['author_original']) != author_original
                or descriptor['decision_sha256'] != digest(chosen)):
            raise ValueError('Unchanged Author/decision/candidate originals required')
        authored = author_payload(author_original)
        row = self.slots[slot]
        new_name = row[axis]
        target = self.root/new_name
        if target.exists() or target.resolve() != target:
            raise ValueError('Literal source target is consumed or aliased')
        parts = deepcopy(before['components'])
        parts[axis] = {'sources': {new_name: candidate['source_sha256']},
                       'configuration_sha256': parts[axis]['configuration_sha256']}
        after = engine.identity.manifest(kernel=parts['K'], predictor=parts['C'], harness=parts['H'],
            researcher=parts['R'], model=before['model'], memory=before['memory_sha256'], runtime=before['runtime'])
        entries = dict(descriptor['parent_entrypoints'], **{axis: new_name})
        proposal = {'candidate_id': row['candidate_id'], 'proposer_id': self.proposer,
            'axis': {'R': 'researcher', 'H': 'harness'}[axis], 'component': chosen['component'],
            'behavior_change': chosen['expected_effect'], 'problem_evidence_sha256': chosen['feedback_sha256'],
            'parent_pair_sha256': chosen['parent_pair_sha256'], 'pair': engine.activation.pair(after),
            'fixed_context': descriptor['micro_evolution']['fixed_context'],
            'write_paths': sorted(set(before['components'][axis]['sources']) | {new_name}),
            'patch_sha256': engine.activation.patch_digest(before, after)}
        micro = descriptor['micro_evolution']
        if (micro['reviewer_id'] != self.reviewer or row['candidate_id'] in micro['used_candidate_ids']
                or micro['pending'] is not None
                or not set(proposal['write_paths']).issubset(micro['allowed_write_paths'][proposal['axis']])):
            raise ValueError('Exact current independent actor and approved write scope required before materialization')
        # The caller's Native preview still validates exact write permission;
        # this host writer cannot overwrite any prior source or run model code.
        output = Path(slot)
        output.mkdir(parents=True, exist_ok=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(authored['source_text'].encode()); stream.flush(); os.fsync(stream.fileno())
        static = engine.save(output/'static-review.json', {'passed': True,
            'reviewer_id': self.reviewer, 'proposer_id': self.proposer,
            'identity_sha256': digest(after), 'entrypoints': entries,
            'scope': 'Literal one-field configuration/source admission only; CASES not executed'})
        body = {'schema': 'capacity_review_spec_v1', 'after': after, 'proposal': proposal,
                'entrypoints': entries, 'static_review': static, 'review_receipt': None}
        original = engine.save(output/'response.json', body)
        return dict(body, original=original, artifacts=[static, engine.pin(target)])
