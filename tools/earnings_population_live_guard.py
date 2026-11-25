"""Explicit role-bound closed-history admission, never a historical cache.

Archived semantic drift is detected at the next full role boundary. Current
authority, selected code and public-data bytes remain live at every HTTP send.
"""
from copy import deepcopy
from pathlib import Path
import re
from weakref import WeakKeyDictionary

import earnings_entry as e
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

POLICY = 'role_scoped_history_v1'
_WRAPPERS = WeakKeyDictionary()
DEV = frozenset({'CIK0000003545', 'CIK0000004457', 'CIK0000017313'})
_PANEL_FIELDS = frozenset({'frozen_panel_policy', 'frozen_panel', 'frozen_panel_window'})


def enabled(value):
    if 'validation_policy' not in value:
        return False
    if (type(value['validation_policy']) is not str or value['validation_policy'] != POLICY
            or value.get('schema') != 'earnings_population_runtime_v1'
            or type(value.get('budget_amendment')) is not dict
            or set(value['budget_amendment']) != {'path', 'sha256'}
            or type(value['budget_amendment']['path']) is not str
            or type(value['budget_amendment']['sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', value['budget_amendment']['sha256']) is None):
        raise ValueError('Exact cumulative400 population role-validation policy required')
    return True


def _checked(bound):
    from earnings_capacity_runtime import _read
    return _read(bound)


def service_identity(call):
    original = _WRAPPERS.get(call)
    identity = engine.source_of(call)
    if original is not None:
        role, callback = original
        identity.update(validation_policy=POLICY, role=role, original=engine.source_of(callback))
    return identity


def _role_boundary(manager, role, callback):
    def invoke(*args, **kwargs):
        return manager.invoke(role, callback, args, kwargs)
    _WRAPPERS[invoke] = (role, callback)
    return invoke


class RoleValidation:
    def __init__(self, binding, value, full_check, *, owner_check=None):
        if not enabled(value) or not callable(full_check):
            raise ValueError('Explicit admitted role-validation owner required')
        self.binding, self.value, self.full_check = deepcopy(binding), deepcopy(value), full_check
        if owner_check is not None and not callable(owner_check):
            raise ValueError('Explicit current owner guard required')
        self.owner_check = owner_check
        self.root = Path(value['root'])
        self.native = Path('/private/tmp') / ('market-rsi-' + value['id'])
        self.current = None

    def wrap(self, role, callback):
        if role not in self.value['slots'] or not callable(callback):
            raise ValueError('Declared original role required')
        return _role_boundary(self, role, callback)

    def _full(self):
        if self.full_check() != self.value:
            raise ValueError('Original full admission result changed')

    def _panel_selection(self, role, args, slot):
        """Use the original full admission, then the exact independent slice."""
        if role != 'forecast':
            raise ValueError('Frozen panel evaluates forecasts only; no new mutation roles')
        from earnings_population_runtime import panel_selection
        selected = panel_selection(self.value, str(slot))
        if type(selected) is not dict or set(selected) != {'company_id', 'arm', 'window', 'version', 'bindings'}:
            raise ValueError('Exact independently admitted panel selection required')
        company, version = selected['company_id'], selected['version']
        arms, arm, window = ('control', 'parent', 'candidate'), selected['arm'], selected['window']
        if (arm not in arms or slot.name != f'forecast-01-{arms.index(arm):02d}'
                or type(window) is not dict or window.get('company_id') != company):
            raise ValueError('Forecast slot differs from frozen panel arm')
        if (type(version) is not dict or args[:2] != (version, company)
                or any(type(version.get(a)) is not dict for a in ('R', 'H'))
                or version.get('id') != digest({a: version[a].get('sha256') for a in ('R', 'H')})
                or type(selected['bindings']) is not list or not selected['bindings']):
            raise ValueError('Forecast arguments differ from frozen panel selection')
        from earnings_population_public_predictions import runtime_scope
        from earnings_population_training25 import admit
        scope = runtime_scope(self.value)
        if scope is None or self.value['companies'] != [company]:
            raise ValueError('One independently admitted training company required')
        admit(scope, company)  # BEFORE original resident/body access.
        resident = tasks.resident(company)
        study = e.strict_json(_checked(self.value['forecast_study']))
        link_binding = study['training_state_link']
        link = e.strict_json(_checked(link_binding))
        bindings = [self.binding, self.value['forecast_study'], self.value['initial_population'],
            self.value['population_plan'], self.value['review'],
            *[study[k] for k in ('campaign', 'campaign_origin', 'campaign_resume', 'prior_batch')],
            link_binding, link['split'], link['comparator'], self.value['model_budget_amendment'],
            *deepcopy(selected['bindings']), tasks.FULL_PLAN, tasks.METADATA, tasks.MANIFEST,
            tasks.RUNTIME, tasks.SCORER, resident['kernel']['qa'], version['R'], version['H']]
        for item in resident['company']['allowed_files']:
            bindings.append(dict(path=str(Path(resident['company']['visible_root']) / item['path']),
                                 sha256=item['sha256']))
        return dict(role=role, slot=str(slot), version=deepcopy(version), company=company,
            resident=resident, bindings=bindings, registered=False, extra_contexts={})

    def _selection(self, role, args, kwargs):
        if 'clean_slate_policy' in self.value:
            from earnings_population_clean_slate import selection
            return selection(self,role,args,kwargs)
        if kwargs or len(args) != (2 if role == 'controller' else 3):
            raise ValueError('Exact original population service call required')
        slot = Path(args[-1])
        if str(slot) not in self.value['slots'][role]:
            raise ValueError('Role outside exact admitted slot')
        match = re.fullmatch(role + r'-([0-9]{2})(?:-[0-9]{2})?', slot.name)
        if match is None:
            raise ValueError('Original role/round slot required')
        if _PANEL_FIELDS & set(self.value):
            return self._panel_selection(role, args, slot)
        packet_path = self.root / ('packet-' + match[1] + '.json')
        packet_binding = engine.pin(packet_path)
        packet = e.strict_json(_checked(packet_binding))
        company = packet['company_id']
        from earnings_population_public_predictions import runtime_scope
        scope = runtime_scope(self.value)
        if scope is not None:
            from earnings_population_training25 import admit
            admit(scope, company)
        if company not in self.value['companies'] or scope is None and company not in DEV:
            raise ValueError('Only admitted development company allowed')
        if role == 'controller':
            if args[0] != packet:
                raise ValueError('Controller must receive exact current packet')
            version = packet['population']['versions'][packet['population']['stable_id']]
        elif role == 'author':
            chosen, state = args[:2]
            if state != packet['population']:
                raise ValueError('Author must use exact current packet population')
            version = state['versions'][chosen['parent_pair_sha256']]
            if chosen['feedback_sha256'] != digest(packet['feedback']):
                raise ValueError('Author feedback differs from actual round')
        elif role == 'review':
            version = args[0]
            if args[1] != packet['population']:
                raise ValueError('Review must use exact current packet population')
            if version['parent'] not in [packet['population']['stable_id'], *packet['population']['explorers']]:
                raise ValueError('Review child must derive from an active current parent')
        else:
            version = args[0]
            if args[1] != company:
                raise ValueError('Forecast company differs from actual round')
            frozen_binding = engine.pin(self.root / ('frozen-pool-' + match[1] + '.json'))
            frozen = e.strict_json(_checked(frozen_binding))
            if frozen['versions'].get(version['id']) != version:
                raise ValueError('Forecast must use exact frozen selected version')
        if version['id'] != digest({axis: version[axis]['sha256'] for axis in ('R', 'H')}):
            raise ValueError('Exact independently selected R/H identity required')
        resident = tasks.resident(company)
        study = e.strict_json(_checked(self.value['forecast_study']))
        if study.get('campaign_resume') is None:
            raise ValueError('Role-scoped policy requires a resumed campaign')
        bindings = [self.binding, self.value['forecast_study'], self.value['initial_population'],
            self.value['population_plan'], self.value['review'], packet_binding, packet['feedback'],
            *[study[k] for k in ('campaign', 'campaign_origin', 'campaign_resume', 'prior_batch')],
            tasks.FULL_PLAN, tasks.METADATA, tasks.MANIFEST, tasks.RUNTIME, tasks.SCORER,
            resident['kernel']['qa'], version['R'], version['H']]
        prior = None
        if scope is not None:
            link_binding = study['training_state_link']
            link = e.strict_json(_checked(link_binding))
            bindings += [link_binding, link['split'], link['comparator'], self.value['model_budget_amendment']]
            feedback = e.strict_json(_checked(packet['feedback']))
            admit(scope, feedback.get('company_id'))
            if feedback['company_id'] != company:
                prior = tasks.resident(feedback['company_id'])['company']
        if role == 'forecast': bindings.append(frozen_binding)
        for descriptor in [resident['company'], *([] if prior is None else [prior])]:
            for item in descriptor['allowed_files']:
                bindings.append(dict(path=str(Path(descriptor['visible_root']) / item['path']),
                                     sha256=item['sha256']))
        return dict(role=role, slot=str(slot), version=deepcopy(version), company=company,
            resident=resident, bindings=bindings, registered=False, extra_contexts={})

    def register_case(self, case):
        current = self.current
        if current is None or current['registered']:
            raise ValueError('One trusted Native case per active role required')
        bound = case['context']; path = self.native / Path(current['slot']).name / 'context.json'
        if bound.get('path') != str(path):
            raise ValueError('Native registration is outside selected role')
        value = e.strict_json(_checked(bound)); resident = current['resident']
        if (value.get('pool_version') != current['version'] or value.get('authority') != self.binding
                or value.get('source_commit') != self.value['source_commit']
                or any(value.get(k) != resident[k] for k in ('company', 'runtime', 'kernel', 'case'))
                or value.get('data') != resident['data_binding']
                or value.get('manifest') != case['manifest'] or case['company'] != resident['company']
                or case['kernel'] != resident['kernel'] or value.get('initial_state') != case['initial_state']):
            raise ValueError('Native case differs from independently selected role/data')
        expected = dict(researcher_v0=current['version']['R']['sha256'],
            harness_v0=current['version']['H']['sha256'], evaluation_scorer=resident['kernel']['scorer']['sha256'],
            evaluation_qa=resident['kernel']['qa']['sha256'], predictor=self.value['sources']['forecaster']['sha256'])
        for name, token in expected.items():
            extension = '.json' if name == 'evaluation_qa' else '.py'
            current['bindings'].append(dict(path=str(path.parent/'source'/(name+extension)), sha256=token))
        current['bindings'] += [deepcopy(bound), deepcopy(case['initial_state'])]
        match = re.search(r'-([0-9]{2})(?:-[0-9]{2})?$', Path(current['slot']).name)
        reference = self.native / ('controller-' + match[1] + '-reference-context.json')
        if reference.exists():
            current['bindings'].append(engine.pin(reference))
        current['registered'] = True

    def check_owner(self):
        """Current inputs only between full role audits; never a history cache."""
        if 'clean_slate_policy' not in self.value:
            raise ValueError('Optimization requires explicit clean-slate admission')
        from earnings_population_runtime import _sources, _ledger
        from earnings_population_clean_slate import enabled, read_task, SPLIT, ROUND0
        enabled(self.value)
        if self.current is not None and self.current['registered']:
            return self.check(self.current['slot'])
        if e.strict_json(_checked(self.binding)) != self.value:
            raise ValueError('Current reviewed runtime changed')
        _sources(self.value)
        for key in ('forecast_study','initial_population','population_plan','review','model_budget_amendment'):
            _checked(self.value[key])
        task, _ = read_task(self.value)
        for bound in (SPLIT,ROUND0,task['feedback'],*self.value['sources'].values()):
            _checked(bound)
        if task['frozen_candidate'] is not None: _checked(task['frozen_candidate'])
        _ledger(self.value)

    def check(self, slot):
        current = self.current
        if current is None or str(slot) != current['slot'] or not current['registered']:
            raise ValueError('Physical HTTP requires its active registered original role')
        # Exact current inputs/code/data only; deliberately NOT a complete
        # historical semantic-dependency witness. Full replay is at boundaries.
        from earnings_population_runtime import _sources, _ledger
        if e.strict_json(_checked(self.binding)) != self.value:
            raise ValueError('Current reviewed runtime changed')
        _sources(self.value)
        for bound in current['bindings']:
            _checked(bound)  # Includes opaque DEV QA bytes, never decoded.
        context = self.native / (Path(slot).name + '-context.json')
        if context.exists() and str(context) not in current['extra_contexts']:
            current['extra_contexts'][str(context)] = engine.pin(context)
        for bound in current['extra_contexts'].values():
            _checked(bound)
        _ledger(self.value)

    def invoke(self, role, callback, args, kwargs):
        if self.current is not None:
            raise ValueError('Nested real role is not allowed')
        self._full()
        current = self._selection(role, args, kwargs)
        self.current = current
        error = audit_error = None
        full_exit = current_exit = False
        try:
            try:
                result = callback(*args, **kwargs)
            except BaseException as caught:
                error = type(caught).__name__
                try:
                    self._full()
                    full_exit = True
                    (self.check if self.owner_check is None else self.owner_check)(current['slot'])
                    current_exit = True
                except BaseException as failed:
                    audit_error = type(failed).__name__
                raise  # Preserve the original exception and liabilities.
            try:
                self._full()
                full_exit = True
                (self.check if self.owner_check is None else self.owner_check)(current['slot'])
                current_exit = True
            except BaseException as caught:
                audit_error = type(caught).__name__
                raise  # No returned output may be accepted after audit failure.
            return result
        finally:
            self.current = None
            receipt = dict(schema='earnings_population_role_validation_v1', validation_policy=POLICY,
                role=role, slot=current['slot'], selected_version_id=current['version']['id'],
                original=engine.source_of(callback), runtime=self.binding, entry_full_audit='PASS',
                exit_full_audit='PASS' if full_exit else 'FAILED',
                exit_current_guard='PASS' if current_exit else 'NOT_PASSED',
                original_error=error, audit_error=audit_error, output_accepted=error is None and audit_error is None,
                archive_semantics='Full at role boundaries; not per-HTTP archived semantic freshness', retry_allowed=False)
            try:
                directory = self.root/'role-validation'
                directory.mkdir(exist_ok=True)
                if directory.resolve() != directory or not directory.is_dir():
                    raise ValueError('Canonical own validation receipt root required')
                e.durable_json(directory/(Path(current['slot']).name+'.json'), receipt)
            except BaseException:
                if error is None and audit_error is None:
                    raise
