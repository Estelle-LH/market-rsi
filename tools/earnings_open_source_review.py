"""Preserve exact model code, run its cases in Docker, prepare Native proposal."""
from copy import deepcopy
from pathlib import Path

from earnings_capacity_adapter import author_payload
from earnings_source_review import SourceReview
from earnings_open_program import candidate, program, run_cases
from earnings_http import save_bytes
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class ProgramSourceReview(SourceReview):
    def __init__(self, *args, runner, **kwargs):
        super().__init__(*args, **kwargs)
        self.runner = runner

    def review(self, chosen, author_original, descriptor, slot):
        if slot not in self.slots or Path(slot).exists() or Path(slot).resolve() != Path(slot):
            raise ValueError('Undeclared or consumed program review slot')
        before = engine.identity.validate(descriptor['parent_identity'])
        axis = chosen['axis']
        if (axis not in {'R','H'} or chosen['parent_pair_sha256'] != descriptor['parent_pair_sha256']
                or chosen['parent_pair_sha256'] != digest(engine.activation.pair(before))
                or descriptor['decision_sha256'] != digest(chosen)):
            raise ValueError('Exact current program decision/parent required')
        old_name = descriptor['parent_entrypoints'][axis]
        old = program(engine.activation._read({'path':str(self.root/old_name),
            'sha256':before['components'][axis]['sources'][old_name]}), axis)
        decoded = candidate(author_original, old, chosen)
        if (engine.read(descriptor['candidate']) != decoded
                or engine.read(descriptor['author_original']) != author_original):
            raise ValueError('Unchanged program Author/candidate originals required')
        authored, row = author_payload(author_original), self.slots[slot]
        name = row[axis]
        target = self.root/name
        micro = descriptor['micro_evolution']
        kind = {'R':'researcher','H':'harness'}[axis]
        writes = sorted(set(before['components'][axis]['sources']) | {name})
        if (target.exists() or target.resolve() != target or micro['pending'] is not None
                or micro['reviewer_id'] != self.reviewer or row['candidate_id'] in micro['used_candidate_ids']
                or not set(writes).issubset(micro['allowed_write_paths'][kind])):
            raise ValueError('Exact idle prospective program source scope required')
        output = Path(slot)
        output.mkdir(parents=True, exist_ok=False)
        save_bytes(target, authored['source_text'].encode())
        tests = []
        test_error = None
        try:
            tests = run_cases(self.runner, authored['source_text'], decoded['cases'])
        except RuntimeError as error:
            if self.runner.blocked:
                raise
            test_error = type(error).__name__
        case_receipt = engine.save(output/'program-cases.json',
            {'source_sha256':decoded['source_sha256'],'cases':tests,'error_type':test_error,
             'passed':test_error is None and all(item['passed'] for item in tests),
             'scope':'Actual candidate-authored cases in container, not independent financial quality proof'})
        parts = deepcopy(before['components'])
        parts[axis] = {'sources':{name:decoded['source_sha256']},
                       'configuration_sha256':parts[axis]['configuration_sha256']}
        after = engine.identity.manifest(kernel=parts['K'],predictor=parts['C'],harness=parts['H'],
            researcher=parts['R'],model=before['model'],memory=before['memory_sha256'],runtime=before['runtime'])
        entries = dict(descriptor['parent_entrypoints'], **{axis:name})
        proposal = {'candidate_id':row['candidate_id'],'proposer_id':self.proposer,'axis':kind,
            'component':chosen['component'],'behavior_change':chosen['expected_effect'],
            'problem_evidence_sha256':chosen['feedback_sha256'],'parent_pair_sha256':chosen['parent_pair_sha256'],
            'pair':engine.activation.pair(after),'fixed_context':micro['fixed_context'],
            'write_paths':writes,'patch_sha256':engine.activation.patch_digest(before,after)}
        static = engine.save(output/'static-review.json', {'passed':True,'reviewer_id':self.reviewer,
            'proposer_id':self.proposer,'identity_sha256':digest(after),'entrypoints':entries,
            'scope':'AST metadata/exact source/permission review only; code runs solely in container',
            'program_cases':case_receipt})
        rejection = None
        if not engine.read(case_receipt)['passed']:
            rejection = engine.save(output/'failed-cases-review.json', {'review':{
                'reviewer_id':self.reviewer,'proposal_sha256':digest(proposal),
                'decision':'reject','reason':'PROGRAM_CASES_FAILED','tested_pair_sha256':digest(proposal['pair']),
                'anchor_pair_sha256':digest(micro['anchor_pair']),'checks':{},'benefit_observed':False,
                'benefit_evidence_sha256':None,'actual_write_paths':writes},'evidence':{}})
        body = {'schema':'capacity_review_spec_v1','after':after,'proposal':proposal,
                'entrypoints':entries,'static_review':static,'review_receipt':rejection}
        original = engine.save(output/'response.json',body)
        return dict(body, original=original, artifacts=[static,case_receipt,engine.pin(target),
            *([] if rejection is None else [rejection])])
