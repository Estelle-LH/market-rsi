"""Explicit prospective panel-window overlay; original grants stay immutable.

This module selects no candidate and activates no grant. The original budget
opens at5; only this separately authenticated instance then receives50 before
any reservation. Transaction, settlement and operator boundaries are inherited.
"""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import stat

import earnings_population_budget as original
import earnings_population_model_budget as model
from earnings_http import strict_json
from earnings_night_budget import utc_epoch

LEGACY_CAP, PANEL_CAP = 5_000_000_000, 50_000_000_000
ROOT = original.LEDGER.parent.parent.parent/'edgar-population-20261016'
SOURCE = 'tools/earnings_population_panel_budget.py'
AUTHORITY = dict(path=str(ROOT/'TRAIN25-DIRECT-WINDOW50-AUTHORITY.json'),
    sha256='6996d8ef270b45cd2eb9dcbb15c644674b3650f33c4a3459f2f61fd358525447')
POLICY = 'frozen_training25_panel_v1'


def _binding(bound, expected=None):
    if (type(bound) is not dict or set(bound) != {'path','sha256'}
            or type(bound['path']) is not str or type(bound['sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}',bound['sha256']) is None):
        raise ValueError('Exact immutable panel-budget binding required')
    path = Path(bound['path'])
    if (not path.is_absolute() or str(path) != bound['path']
            or expected is not None and path != expected or path.resolve() != path):
        raise ValueError('Exact canonical panel-budget path required before read')
    return path


def _read(bound, expected=None, *, binary=False):
    path = _binding(bound,expected)
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16_000_000:
            raise ValueError('Bounded single-link original panel-budget file required')
        raw = stream.read(16_000_001)
    if hashlib.sha256(raw).hexdigest() != bound['sha256']:
        raise ValueError('Panel-budget original bytes differ')
    return raw if binary else strict_json(raw)


def ceiling(value, *, historical_reader=None):
    """Typed overlay ceiling, not admission, activation or renewed time credit."""
    if type(value) is not dict:
        raise ValueError('Exact runtime required for panel-window ceiling')
    if 'panel_window_budget_authority' not in value:
        return LEGACY_CAP
    _binding(value['panel_window_budget_authority'],Path(AUTHORITY['path']))
    import earnings_population_training25 as training
    from earnings_population_window import minutes
    if (value['panel_window_budget_authority'] != AUTHORITY
            or value.get('schema') != 'earnings_population_runtime_v1'
            or value.get('training_policy') != training.POLICY
            or value.get('frozen_panel_policy') != POLICY or minutes(value) != 90
            or type(value.get('companies')) is not list or len(value['companies']) != 1
            or type(value.get('additional_cap_nano_usd')) is not int
            or value['additional_cap_nano_usd'] != PANEL_CAP
            or value.get('ledger') != str(original.LEDGER)
            or type(value.get('id')) is not str
            or re.fullmatch('edgar-population-20261016-[0-9]{2}',value['id']) is None
            or value.get('root') != str(ROOT/'attempts'/value['id'])):
        raise ValueError('Explicit frozen-training panel50/90-minute authority required')
    for key,name in (('budget_amendment',original.NAME),('model_budget_amendment',model.NAME)):
        _binding(value.get(key),original.LEDGER.parent/name)
    if type(value.get('sources')) is not dict:
        raise ValueError('Exact panel-budget source bindings required')
    source = value['sources'].get(SOURCE)
    reader = historical_reader
    if reader is None:
        _read(source,Path(__file__).resolve(),binary=True)
    else:
        from earnings_population_continuation import _Reader
        from earnings_population_source_history import source_name
        if (not isinstance(reader,_Reader) or reader.root != ROOT or reader.repo != original.REPO
                or reader.ledger != original.LEDGER or value['id'] not in reader.ids
                or reader.commit != value.get('source_commit')
                or type(source) is not dict or source_name(source.get('path'),reader.repo) != SOURCE):
            raise ValueError('Original registered historical reader required')
        reader.read(source,binary=True)  # Registered original Git bytes, not current Source.
    authority = _read(AUTHORITY,Path(AUTHORITY['path']))  # Always fresh, including within epochs.
    if (authority.get('schema') != 'earnings_training25_direct_panel_window_cap_authority_v1'
            or authority.get('Root_selected_window_cap_nano_usd') != PANEL_CAP
            or authority.get('old_window_cap_nano_usd') != LEGACY_CAP
            or authority.get('sole_ledger') != str(original.LEDGER)):
        raise ValueError('Original direct panel50 authority differs')
    directory = ROOT/'inputs'/value['id']
    study = _read(value.get('forecast_study'),directory/'study.json')
    if (type(study) is not dict or study.get('training_stage_attachment') is not None
            or study.get('panel_window_budget_authority') != AUTHORITY
            or any(study.get(key) != value.get(key) or key not in value
                for key in ('frozen_panel_policy','frozen_panel','frozen_panel_window'))):
        raise ValueError('Exact companion frozen-panel study required')
    _binding(value['frozen_panel'])
    if not Path(value['frozen_panel']['path']).is_relative_to(ROOT):
        raise ValueError('Owned frozen-panel descriptor required')
    link = _read(study.get('training_state_link'),directory/'training-state-link.json')
    scope = training.load_scope(link['split'])
    training.admit(scope,value['companies'][0])  # Before panel/body or backend admission.
    descriptor = _read(value['frozen_panel'])
    selected = _read(value.get('frozen_panel_window'),directory/'frozen-panel-window.json')
    if (type(descriptor) is not dict or descriptor.get('schema') != 'earnings_training25_frozen_panel_v1'
            or descriptor.get('policy') != POLICY or descriptor.get('split') != scope['split']
            or type(selected) is not dict or selected.get('schema') != 'earnings_training25_frozen_panel_window_v1'
            or selected.get('policy') != POLICY or selected.get('descriptor') != value['frozen_panel']
            or selected.get('company_id') != value['companies'][0]):
        raise ValueError('Exact admitted frozen-panel company window required')
    if reader is not None:
        reader.extra.add(Path(AUTHORITY['path']))  # One exact file, never a root allowlist.
        reader.read(AUTHORITY,binary=True)
    return PANEL_CAP


def _runtime(bound):
    path = _binding(bound)
    ident = path.parent.name
    if (re.fullmatch('edgar-population-20261016-[0-9]{2}',ident) is None
            or path != ROOT/'inputs'/ident/'runtime-reviewed.json'):
        raise ValueError('Exact own reviewed runtime required before backend open')
    value = _read(bound,path)
    if value.get('id') != ident or ceiling(value) != PANEL_CAP:
        raise ValueError('Exact prospective panel50 runtime required')
    return value


class PanelBudget(original.PopulationBudget):
    """Separately authorized local allowance; no inherited operator authority."""
    def __init__(self, path, *, runtime_binding, **kwargs):
        value = _runtime(runtime_binding)
        expected = dict(baseline=value['baseline'],deadline_utc=value['cutoff_utc'],
            amendment_binding=value['budget_amendment'],model_amendment_binding=value['model_budget_amendment'],
            additional_cap_nano_usd=PANEL_CAP)
        if (str(path) != value['ledger'] or type(kwargs.get('additional_cap_nano_usd')) is not int
                or any(kwargs.get(k) != v for k,v in expected.items())):
            raise ValueError('Original panel ledger/history/cutoff/grants/allowance differ')
        self.runtime_binding = deepcopy(runtime_binding)
        self._panel_terms = deepcopy(expected)
        kwargs['additional_cap_nano_usd'] = LEGACY_CAP
        super().__init__(path,**kwargs)  # Original5 initialization, no reserve or send.
        try:
            if _runtime(self.runtime_binding) != value:
                raise ValueError('Panel runtime changed during original budget initialization')
            self.additional_cap_nano_usd = PANEL_CAP
        except BaseException:
            self.close()
            raise

    def _reserve_check(self, model_name, amount, *, own_request=None):
        value = _runtime(self.runtime_binding)
        expected = dict(baseline=self.baseline,deadline_utc=value['cutoff_utc'],
            amendment_binding=self.amendment_binding,model_amendment_binding=self.model_amendment_binding,
            additional_cap_nano_usd=self.additional_cap_nano_usd)
        if (expected != self._panel_terms or self.deadline != utc_epoch(value['cutoff_utc'])
                or any(value[key] != expected[key] for key in ('baseline','additional_cap_nano_usd'))
                or value['budget_amendment'] != self.amendment_binding
                or value['model_budget_amendment'] != self.model_amendment_binding):
            raise original.BudgetStop('Panel instance accounting authority changed')
        self._boundary()
        original._liabilities(self.db,original.CAP)
        total,same,model_cap = model.dispatch_totals(self.db,model_name,amount,
            self.model_amendment_binding,own_request=own_request)
        if (total+amount > original.CAP or same+amount > model_cap
                or total-self.baseline['charged_nano_usd']+amount > self.additional_cap_nano_usd):
            raise original.BudgetStop('Original global/model/stage or explicit panel50 window exceeded')
