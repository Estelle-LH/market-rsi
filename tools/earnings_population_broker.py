"""Paged exact pool sources and label-free original feedback projections."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from edgar_forecast_tools import function
from earnings_entry import checked
from earnings_open_broker import ResearchBroker
from earnings_open_program import arguments
from earnings_population_diagnostics import from_trial
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class PopulationBroker(ResearchBroker):
    def __init__(self, *args, versions, population_context_binding=None, prior_company=None, **kwargs):
        from edgar_forecast_tools import FilingTools
        self.population_context_binding = deepcopy(population_context_binding)
        self.prior_company = deepcopy(prior_company)
        self.prior_files = None if prior_company is None else FilingTools(prior_company)
        self.versions = deepcopy(versions)
        for row in self.versions.values():
            for axis in ('R', 'H'):
                checked(row[axis])
        super().__init__(*args, **kwargs)

    def research_context(self, *, include_source=False):
        if self.population_context_binding is None:
            return super().research_context(include_source=include_source)
        value = engine.read(self.population_context_binding)
        if (type(include_source) is not bool
                or value.get('schema') != 'earnings_population_author_context_v1'
                or value.get('parent_version_id') not in self.versions
                or value.get('parent_programs') != self.references()[value['parent_version_id']]):
            raise ValueError('Exact feedback-bound population Author context required')
        return value

    def _definitions(self):
        result = super()._definitions() + [function('read_population_program',
            'Read an exact page of an active pool version, never execute it. Start offset0; use next_offset.',
            {'version_id': {'type': 'string', 'enum': sorted(self.versions)},
             'axis': {'type': 'string', 'enum': ['R', 'H']},
             'offset': {'type': 'integer', 'minimum': 0, 'maximum': 65536},
             'characters': {'type': 'integer', 'minimum': 1, 'maximum': 4000}})]
        if self.prior_files is not None:
            result.append(function('read_prior_file',
                'Read exact prior-company public evidence to diagnose the reported failure. Same original cutoff/files/read bounds; not hidden answers. Use prior feedback original_questions and filing_index.tsv to locate filings.',
                {'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
                 'characters': {'type': 'integer', 'minimum': 1, 'maximum': 20000}}))
        return result

    def references(self):
        return {ident: {axis: {'sha256': row[axis]['sha256'],
            'read_tool': 'read_population_program', 'arguments': {
                'version_id': ident, 'axis': axis, 'offset': 0, 'characters': 4000}}
                for axis in ('R', 'H')} for ident, row in self.versions.items()}

    def dispatch(self, name, args):
        if name not in {'read_population_program', 'read_prior_file'}:
            return super().dispatch(name, args)
        if (self.root.resolve() != self.root or self.root.is_symlink()
                or (self.root.stat().st_dev, self.root.stat().st_ino) != self.identity
                or self.definitions != self._definitions() or self.calls >= 64):
            raise ValueError('Original research action identity/budget drift')
        definition = next((t for t in self.definitions if t['name'] == name), None)
        if definition is None:
            raise ValueError('Prior public evidence is not registered in this role')
        arguments(args, definition['parameters'])
        key = digest({'name': name, 'arguments': args})
        if key in self.failed:
            raise ValueError('Failed source page stays closed; no automatic retry')
        slot = self.root/f'{self.calls + 1:04d}'
        slot.mkdir(mode=0o700)
        self.calls += 1
        engine.save(slot/'intent.json', {'name': name, 'arguments': args, 'retry_allowed': False})
        try:
            if name == 'read_prior_file':
                value = self.prior_files.dispatch('read_file', deepcopy(args))
                value = dict(value, prior_company_id=self.prior_company['cik'],
                    source_sha256=hashlib.sha256(self.prior_files.files[args['path']].encode()).hexdigest())
            else:
                bound = self.versions[args['version_id']][args['axis']]
                text = checked(bound).decode()
                offset, count = args['offset'], args['characters']
                if offset > len(text):
                    raise ValueError('Source page starts beyond exact source')
                end = min(offset + count, len(text))
                value = dict(version_id=args['version_id'], axis=args['axis'], source_sha256=bound['sha256'],
                    offset=offset, next_offset=end, total_characters=len(text), text=text[offset:end])
            self.returned += len(json.dumps(value, allow_nan=False).encode())
            if self.returned > 2_000_000:
                raise ValueError('Original research return budget exhausted')
            receipt = engine.save(slot/'result.json', {'value': value, 'untrusted_evidence': True})
            return dict(value=value, research_receipt=receipt)
        except Exception as error:
            self.failed.add(key)
            engine.save(slot/'failure.json', {'error_type': type(error).__name__, 'retry_allowed': False})
            raise


def public_feedback(feedback, versions):
    """Copy only verified original public trial awards, never raw scorer JSON."""
    if feedback.get('schema') == 'earnings_population_seed_v1':
        return deepcopy(feedback)
    original = engine.read(feedback)
    if original.get('schema') != 'earnings_population_feedback_v1':
        raise ValueError('Actual preceding population feedback required')
    result = {k: original[k] for k in ('schema', 'company_id', 'round_index', 'stable_id', 'scope')}
    reviewed = original.get('exploration_review')
    if reviewed is not None:
        result['exploration_review'] = {key: reviewed[key] for key in ('candidate_id', 'accepted_for_exploration')}
        outcomes = [b for b in reviewed['evidence'] if Path(b['path']).name.endswith('-outcome.json')]
        if reviewed['candidate_id'] is not None:
            if len(outcomes) != 1:
                raise ValueError('Actual proposal outcome required, including rejection')
            outcome = engine.read(outcomes[0])
            if (outcome.get('schema') != 'earnings_population_exploration_review_v1'
                    or outcome.get('candidate_id') != reviewed['candidate_id']
                    or outcome.get('accepted_for_exploration') is not reviewed['accepted_for_exploration']
                    or type(outcome.get('rationale')) is not str or not 1 <= len(outcome['rationale']) <= 1000):
                raise ValueError('Exploration outcome differs from actual review')
            result['exploration_review']['rationale'] = outcome['rationale']
    result['results'] = []
    for row in original['results']:
        rows = [b for b in row['evidence'] if Path(b['path']).name == 'population-public-feedback.json']
        if len(rows) != 1:
            raise ValueError('Exactly one verified public forecast projection required')
        public = engine.read(rows[0])
        if (public.get('schema') != 'earnings_population_public_trial_v1'
                or public.get('version_id') != row['version_id'] or public.get('points') != row['points']
                or public.get('company_id') != original['company_id']
                or public.get('pool_sources') != {axis: versions[row['version_id']][axis]['sha256'] for axis in ('R', 'H')}):
            raise ValueError('Public feedback does not join actual original trial/source')
        targets = public['target_scores']
        if (type(targets) is not list or len(targets) != 5
                or any(type(t) is not dict or set(t) != {'target_id', 'points_awarded'}
                    or type(t['target_id']) is not str or type(t['points_awarded']) not in (int, float)
                    or t['points_awarded'] not in (0, .5, 1) for t in targets)
                or len({t['target_id'] for t in targets}) != 5
                or sum(t['points_awarded'] for t in targets) != row['points']):
            raise ValueError('Exact original five-target public awards required')
        projected = dict(version_id=row['version_id'], points=row['points'], target_scores=deepcopy(targets))
        program = [b for b in row['evidence'] if b.get('path') ==
                   str(Path(rows[0]['path']).parent/'program-executions.json')]
        if program:
            from earnings_population_tasks import resident
            from edgar_forecast_tools import FilingTools
            company = resident(original['company_id'])['company']
            projected['research_diagnostics'] = from_trial(rows[0], row['evidence'],
                versions[row['version_id']], company)
            result['original_questions'] = FilingTools(company).files['questions.md']
        else:
            projected['research_diagnostics'] = {'availability': 'unavailable_missing_execution_evidence'}
        result['results'].append(projected)
    return result
