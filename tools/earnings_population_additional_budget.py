"""One explicit +100 financial overlay on the original ledger and grants.

Legacy SQL config400/model100 and grant files remain historical commitments,
as named300 already overlaid config.model100. Only an exact new runtime opt-in
can use effective global500/named400/stage300. No model/resource/window change.
The operator activation writes once under the ORIGINAL idle serialization.
"""
from contextlib import closing
from copy import deepcopy
import fcntl
import hashlib
from pathlib import Path
import re

from edgar_forecast_budget import BudgetStop, PilotBudget
import earnings_population_budget as old
import earnings_population_model_budget as model
from earnings_http import save_bytes, strict_json
from earnings_night_budget import history_snapshot

GRANT = 'edgar-train25-additional100-20261023'
NAME = 'population-additional100-20261023-grant.json'
TABLE = 'population_additional_budget_amendments'
PLAN = 'configs/earnings_coevolution/training25_additional100_authority.json'
KEY = 'additional_budget_amendment'
GLOBAL, NAMED, STAGE_CAP = 500_000_000_000, 400_000_000_000, 300_000_000_000
ROOT = old.LEDGER.parent.parent.parent/'edgar-population-20261016'
HUMAN = dict(path=str(ROOT/'TRAIN25-DIRECT-ADDITIONAL100-CAPS-CONFIRMED-20261023.json'),
    sha256='8ca783de15fd604c01aa737fe4c7f0affcb70aa53ac2444ad7307080d1a7e19f')
IMPLEMENTATIONS = ('tools/earnings_population_additional_budget.py',
    'tools/earnings_population_runtime.py','tools/earnings_capacity_runtime.py',
    'tools/earnings_population_company_batch.py','tools/earnings_population_completed.py')
TERMS = dict(stage_additional_ceiling_nano_usd=STAGE_CAP,cumulative_ceiling_nano_usd=GLOBAL,
    gpt61_ceiling_nano_usd=NAMED,other_models_ceiling_nano_usd=model.OLD,
    window_ceiling_nano_usd=model.WINDOW_CAP,window_minutes=90)


def _authority(bound, commit, *, current=False):
    from earnings_population_source_history import source_name
    if (type(bound) is not dict or set(bound)!={'path','sha256'}
            or type(commit) is not str or re.fullmatch('[0-9a-f]{40}',commit) is None
            or source_name(bound.get('path'),old.REPO)!=PLAN
            or current and bound['path']!=str(old.REPO/PLAN)):
        raise ValueError('Exact committed additional100 authority required')
    raw=old._git(commit,PLAN)
    if hashlib.sha256(raw).hexdigest()!=bound['sha256'] or current and old.checked(bound)!=raw:
        raise ValueError('Additional100 authority differs from committed bytes')
    expected=dict(schema='edgar25_additional100_financial_authority_v1',grant_id=GRANT,
        direct_human=HUMAN,sole_ledger=str(old.LEDGER),**TERMS,
        preserve_legacy_config_and_grants=True,explicit_prospective_optin_required=True,
        no_reset_refund_reactivation_or_resource_change=True,heldout_authorized=False)
    if old._encoded(strict_json(raw))!=old._encoded(expected):
        raise ValueError('Only typed stage300/global500/named400/other100/window5 authority is valid')
    human=strict_json(old.checked(HUMAN))
    if (human.get('verbatim_answer')!='是，仅同步这两个金额上限'
            or human.get('stage_start_booked_nano_usd')!=model.STAGE['charged_nano_usd']
            or any(type(human.get(k)) is not type(v) or human[k]!=v for k,v in TERMS.items())
            or human.get('no_reset_refund_new_ledger_or_reactivation') is not True
            or human.get('heldout_authorized') is not False):
        raise ValueError('Original direct human additional100 confirmation differs')
    previous=strict_json(old.checked(human['previous_instruction']))
    if previous.get('verbatim')!='+100 usd' or previous.get('authorized_budget_increment_nano_usd')!=100_000_000_000:
        raise ValueError('Original direct +100 instruction missing')


def binding():
    return old._pin(old.LEDGER.parent/NAME)


def read_grant(db, *, required_binding=None):
    path=old.LEDGER.parent/NAME
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone()
    if not exists and not path.exists() and not path.is_symlink() and required_binding is None:return None
    old._ledger(db)
    if (not exists or not path.is_file() or path.is_symlink() or path.resolve()!=path
            or path.stat().st_nlink!=1 or path.stat().st_size>100_000 or path.stat().st_mode&0o077):
        raise BudgetStop('Incomplete/aliased additional100 activation; diagnose, never retry/reset')
    bound=binding()
    if required_binding is not None and required_binding!=bound:raise BudgetStop('Additional100 opt-in differs')
    raw=old.checked(bound)
    if db.execute('SELECT grant_id,receipt_sha256,record_json FROM '+TABLE).fetchall()!=[(GRANT,bound['sha256'],raw.decode())]:
        raise BudgetStop('Original ledger row and additional100 receipt differ')
    value=strict_json(raw)
    expected=dict(schema='earnings_population_additional_budget_amendment_v1',grant_id=GRANT,
        ledger=str(old.LEDGER),stage=model.STAGE,**TERMS)
    extra={'authority','source_commit','implementations','prefix','reconciliations',
        'cumulative_amendment','model_amendment'}
    if set(value)!=set(expected)|extra or old._encoded({k:value[k] for k in expected})!=old._encoded(expected):
        raise BudgetStop('Exact typed additional100 record required')
    if (old.validate_cap(db,amendment=value['cumulative_amendment'])!=old.CAP
            or model.read_grant(db,required_binding=value['model_amendment']) is None):
        raise BudgetStop('Original immutable cumulative400/named300 grants required')
    _authority(value['authority'],value['source_commit'])
    if (type(value['implementations']) is not dict or set(value['implementations'])!=set(IMPLEMENTATIONS)
            or any(hashlib.sha256(old._git(value['source_commit'],name)).hexdigest()!=sha
                   for name,sha in value['implementations'].items())):
        raise BudgetStop('Committed additional100 guard implementation differs')
    old._prefix(value['prefix'])
    reconc=value['reconciliations']
    if (type(reconc) is not dict or set(reconc)!={'max_rowid','count','sha256'}
            or any(type(reconc[k]) is not int or reconc[k]<0 for k in ('max_rowid','count'))
            or type(reconc['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',reconc['sha256']) is None):
        raise BudgetStop('Exact integer original reconciliation prefix required')
    if (history_snapshot(db,model.STAGE['max_rowid'])!=model.STAGE
            or history_snapshot(db,value['prefix']['max_rowid'])!=value['prefix']
            or old._reconciliations(db,value['reconciliations']['max_rowid'])!=value['reconciliations']):
        raise BudgetStop('Original stage/activation/reconciliation prefixes changed')
    return value


def liabilities(db, *, cap=GLOBAL, named=NAMED, stage=STAGE_CAP):
    total,models=model._totals(db)
    if (total>cap or total-model.STAGE['charged_nano_usd']>stage
            or any(amount>(named if name==model.MODEL else model.OLD) for name,amount in models.items())):
        raise BudgetStop('All charged/full pending liabilities exceed effective financial ceilings')
    return total,models


def legacy_sources(db,sources,commit,*,historical_reader=None):
    """Keep the ORIGINAL model300 authority and inherited code Source joins."""
    grant=model.read_grant(db,required_binding=model.binding())
    if grant is None or sources.get(model.PLAN)!=grant['authority']:
        raise ValueError('Original model300 authority Source join differs')
    model._authority(grant['authority'],commit,current=historical_reader is None)
    for name,sha in grant['implementations'].items():
        bound=sources.get(name)
        if bound!=dict(path=str(old.REPO/name),sha256=sha):
            raise ValueError('Original inherited financial implementation Source join differs')
        raw=old.checked(bound) if historical_reader is None else historical_reader.read(bound,binary=True)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Inherited financial source bytes differ')


def runtime_grant(db, value, *, historical_reader=None):
    from earnings_population_window import minutes
    bound=value.get(KEY)
    if (type(bound) is not dict or set(bound)!={'path','sha256'}
            or value.get('ledger')!=str(old.LEDGER) or value.get('schema')!='earnings_population_runtime_v1'
            or minutes(value)!=90 or type(value.get('additional_cap_nano_usd')) is not int
            or not 1<=value['additional_cap_nano_usd']<=model.WINDOW_CAP
            or 'panel_window_budget_authority' in value):
        raise ValueError('Explicit original window5/90min additional100 runtime required')
    grant=read_grant(db,required_binding=bound)
    if (grant is None or value.get('budget_amendment')!=grant['cumulative_amendment']
            or value.get('model_budget_amendment')!=grant['model_amendment']
            or value['baseline']['max_rowid']<grant['prefix']['max_rowid']
            or value['sources'].get(PLAN)!=grant['authority']):
        raise ValueError('Runtime additional100 authority/original grants/prefix differ')
    _authority(grant['authority'],value['source_commit'],current=historical_reader is None)
    legacy_sources(db,value['sources'],value['source_commit'],historical_reader=historical_reader)
    for name,sha in grant['implementations'].items():
        source=value['sources'].get(name)
        if source!=dict(path=str(old.REPO/name),sha256=sha):
            raise ValueError('Additional100 financial implementation changed')
        raw=old.checked(source) if historical_reader is None else historical_reader.read(source,binary=True)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Financial source commitment differs')
    return grant


def historical_grant(db, reader, value, summary, maximum):
    grant=runtime_grant(db,value,historical_reader=reader)
    if (summary.get(KEY)!=value[KEY] or summary.get('cap_usd')!=500
            or summary.get('dispatch_model_caps_usd')!={model.MODEL:400,'other_models':100}
            or summary.get('stage_additional_cap_usd')!=300
            or summary.get('model_budget_optin')!=value['model_budget_amendment']):
        raise ValueError('Closed additional100 summary differs')
    if maximum is not None:
        prefix=history_snapshot(db,maximum)
        amounts=db.execute('SELECT model,SUM(charged) FROM requests WHERE rowid<=? GROUP BY model',(maximum,)).fetchall()
        if (prefix['charged_nano_usd']>GLOBAL or prefix['charged_nano_usd']-model.STAGE['charged_nano_usd']>STAGE_CAP
                or any(n>(NAMED if name==model.MODEL else model.OLD) for name,n in amounts)):
            raise ValueError('Closed prefix exceeds additional100 ceilings')
    evidence=[value[KEY],value['budget_amendment'],value['model_budget_amendment'],HUMAN]
    for bound in evidence:
        reader.extra.add(Path(bound['path']));reader.read(bound,binary=True)
    return evidence


def dispatch_totals(db, selected_model, amount, optin, *, own_request=None):
    if (selected_model not in old.MODELS or type(amount) is not int or amount<0
            or type(optin) is not dict or set(optin)!={'path','sha256'}):
        raise BudgetStop('Exact model/integer reservation and additional100 opt-in required')
    if read_grant(db,required_binding=optin) is None:raise BudgetStop('Additional100 not activated')
    total,models=model._totals(db)
    if own_request is not None:
        if (type(own_request) is not str or not own_request or db.execute(
                'SELECT model,reserved,charged,status FROM requests WHERE id=?',(own_request,)).fetchone()!=(selected_model,amount,0,'reserved')):
            raise BudgetStop('Only exact own pending reservation may be excluded once')
        total-=amount;models[selected_model]-=amount
    cap=NAMED if selected_model==model.MODEL else model.OLD
    if (total+amount>GLOBAL or total+amount-model.STAGE['charged_nano_usd']>STAGE_CAP
            or any(n>(NAMED if name==model.MODEL else model.OLD) for name,n in models.items())
            or models.get(selected_model,0)+amount>cap):
        raise BudgetStop('Global500/named400/other100/stage300 full reservation exceeds ceiling')
    return total,models.get(selected_model,0),cap


def activate(path, *, authority_binding, source_commit, expected_prefix):
    """Operator-only, once; no runtime automatically activates or repairs this."""
    if str(path)!=str(old.LEDGER) or Path(path).resolve()!=old.LEDGER:raise ValueError('Original sole ledger required')
    old._prefix(expected_prefix);_authority(authority_binding,source_commit,current=True)
    implementations={}
    for name in IMPLEMENTATIONS:
        raw=(old.REPO/name).read_bytes()
        if old._git(source_commit,name)!=raw:raise ValueError('Commit reviewed implementation before activation')
        implementations[name]=hashlib.sha256(raw).hexdigest()
    lockpath=old.LEDGER.parent/'.capacity-runtime.lock'
    if lockpath.resolve()!=lockpath or not lockpath.is_file() or lockpath.is_symlink():raise BudgetStop('Original idle lock required')
    with lockpath.open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with closing(old.connect_existing(old.LEDGER)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if read_grant(db) is not None:raise BudgetStop('Additional100 already consumed; validate only')
                if old.validate_cap(db)!=old.CAP or model.read_grant(db) is None:raise BudgetStop('Original grants required')
                PilotBudget.active(type('Idle',(),{'db':db})())
                if history_snapshot(db)!=expected_prefix:raise BudgetStop('Current activation prefix differs')
                old._liabilities(db,old.CAP)
                model.dispatch_totals(db,model.MODEL,0,model.binding())  # Oldstage200 was never exceeded.
                legacy_sources(db,{name:old._pin(old.REPO/name) for name in (model.PLAN,*model.IMPLEMENTATIONS)},source_commit)
                record=dict(schema='earnings_population_additional_budget_amendment_v1',grant_id=GRANT,
                    ledger=str(old.LEDGER),stage=deepcopy(model.STAGE),**TERMS,
                    authority=deepcopy(authority_binding),source_commit=source_commit,implementations=implementations,
                    prefix=history_snapshot(db),reconciliations=old._reconciliations(db),
                    cumulative_amendment=old.amendment_binding(),model_amendment=model.binding())
                raw=old._encoded(record)+b'\n'
                save_bytes(old.LEDGER.parent/NAME,raw)  # Interrupted file survives: no automatic retry.
                bound=binding()
                db.execute('CREATE TABLE '+TABLE+' (grant_id TEXT PRIMARY KEY,receipt_sha256 TEXT NOT NULL,record_json TEXT NOT NULL)')
                db.execute('INSERT INTO '+TABLE+' VALUES(?,?,?)',(GRANT,bound['sha256'],raw.decode()))
                read_grant(db,required_binding=bound);liabilities(db)
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK');raise
    return bound


class AdditionalBudget(old.PopulationBudget):
    def __init__(self,path,*,additional_amendment_binding,**kwargs):
        if (type(additional_amendment_binding) is not dict or set(additional_amendment_binding)!={'path','sha256'}
                or additional_amendment_binding.get('path')!=str(old.LEDGER.parent/NAME)
                or type(additional_amendment_binding.get('sha256')) is not str
                or re.fullmatch('[0-9a-f]{64}',additional_amendment_binding['sha256']) is None):
            raise ValueError('Explicit exact additional100 opt-in required')
        self.additional_amendment_binding=deepcopy(additional_amendment_binding)
        if kwargs.get('model_amendment_binding') is None:raise ValueError('Original named grant required')
        super().__init__(path,**kwargs)

    def active(self):
        PilotBudget.active(self)
        grant=read_grant(self.db,required_binding=self.additional_amendment_binding)
        if (grant is None or self.amendment_binding!=grant['cumulative_amendment']
                or self.model_amendment_binding!=grant['model_amendment']
                or self.baseline['max_rowid']<grant['prefix']['max_rowid']):
            raise BudgetStop('Explicit activated additional100 owner required')
        liabilities(self.db);self._boundary()

    def _reserve_check(self,selected_model,amount,*,own_request=None):
        self._boundary()
        if self.additional_cap_nano_usd>model.WINDOW_CAP:raise BudgetStop('Window5 unchanged')
        total,_,_=dispatch_totals(self.db,selected_model,amount,self.additional_amendment_binding,own_request=own_request)
        if total-self.baseline['charged_nano_usd']+amount>self.additional_cap_nano_usd:raise BudgetStop('Original shared window5 exceeded')

    def summary(self):
        result=super().summary()
        if read_grant(self.db,required_binding=self.additional_amendment_binding) is None:raise BudgetStop('Additional100 grant missing')
        result.update(cap_usd=500,dispatch_model_caps_usd={model.MODEL:400,'other_models':100},
            stage_additional_cap_usd=300,allocation='explicit_additional100_prior_charges_included',
            **{KEY:deepcopy(self.additional_amendment_binding)})
        return result


def budget_caps(budget):
    return (GLOBAL,STAGE_CAP) if hasattr(budget,'additional_amendment_binding') else (old.CAP,model.STAGE_CAP)


def budget_totals(budget,selected_model,amount=0):
    if hasattr(budget,'additional_amendment_binding'):
        return dispatch_totals(budget.db,selected_model,amount,budget.additional_amendment_binding)
    return model.dispatch_totals(budget.db,selected_model,amount,budget.model_amendment_binding)


def budget_liabilities(budget):
    if hasattr(budget,'additional_amendment_binding'):
        if read_grant(budget.db,required_binding=budget.additional_amendment_binding) is None:raise BudgetStop('Explicit grant missing')
        return liabilities(budget.db)
    return old._liabilities(budget.db,old.CAP)
