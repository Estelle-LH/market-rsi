"""Prospective named-model grant; old grants/config and dispatch stay unchanged.

Only activate() writes, once under the existing idle lock. A prepared file left
after SQL rollback blocks reuse; no automatic repair, inference or reconciliation.
"""
from contextlib import closing
from copy import deepcopy
import fcntl
import hashlib
from pathlib import Path
import re

from edgar_forecast_budget import BudgetStop, PilotBudget
from earnings_http import save_bytes, strict_json
from earnings_night_budget import history_snapshot

MODEL = 'gpt-6.1-sol'
OLD, NAMED, STAGE_CAP, WINDOW_CAP = 100_000_000_000, 300_000_000_000, 200_000_000_000, 5_000_000_000
GRANT = 'edgar-train25-gpt61-model300-20261019'
NAME = 'population-gpt61-model300-20261019-grant.json'
TABLE = 'population_model_budget_amendments'
PLAN = 'configs/earnings_coevolution/training25_model300_authority.json'
IMPLEMENTATIONS = ('tools/earnings_population_model_budget.py', 'tools/earnings_population_budget.py')
STAGE = dict(max_rowid=6401, request_count=6401, charged_nano_usd=187429960800,
    rows_sha256='0c343c36c21c496b7f6263ba4ec9afb8ffb5dcb347b0e4195e63349112ce252a')
ANSWER = '允许仅提高该模型分项到 $300，其余预算上限不变'


def _budget():
    import earnings_population_budget
    return earnings_population_budget


def _authority(binding, commit, *, current=False):
    p = _budget()
    from earnings_population_source_history import source_name
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(commit) is not str or not re.fullmatch('[0-9a-f]{40}', commit)
            or source_name(binding.get('path'), p.REPO) != PLAN
            or current and binding['path'] != str(p.REPO/PLAN)):
        raise ValueError('Exact committed model-specific human authority required')
    raw = p._git(commit, PLAN)
    if hashlib.sha256(raw).hexdigest() != binding['sha256'] or current and p.checked(binding) != raw:
        raise ValueError('Model-specific authority Git bytes differ')
    value = strict_json(raw)
    expected = dict(model=MODEL, old_model_cap_nano_usd=OLD, new_model_cap_nano_usd=NAMED,
        other_models_cap_nano_usd=OLD, stage_additional_ceiling_nano_usd=STAGE_CAP,
        cumulative_cap_nano_usd=p.CAP, window_ceiling_nano_usd=WINDOW_CAP,
        stage_start_rows=STAGE['request_count'], stage_start_booked_nano_usd=STAGE['charged_nano_usd'])
    if (value.get('schema') != 'edgar_train25_specific_model_cap_authority_v1'
            or value.get('status') != 'AUTHORIZED_NOT_ACTIVATED_STAGING_ONLY'
            or value.get('direct_human_answer') != ANSWER or value.get('sole_ledger') != str(p.LEDGER)
            or value.get('stage_start_prefix_sha256') != STAGE['rows_sha256']
            or any(value.get(k) != v or type(value.get(k)) is not type(v) for k, v in expected.items())
            or any(value.get(k) is not True for k in ('no_global_model_cap_raise',
                'no_refund_reset_new_ledger_or_inference_budget', 'preserve_historical100_grants_receipts',
                'explicit_prospective_runtime_optin_required'))
            or value.get('heldout_authorization') is not False or value.get('other_Supervisor_access') is not False):
        raise ValueError('Only explicit named300/other100/stage200/global400/window5 authority is valid')


def binding():
    p = _budget()
    return p._pin(p.LEDGER.parent/NAME)


def read_grant(db, *, required_binding=None):
    """Validate historical liability authority, not new dispatch permission."""
    p = _budget()
    path = p.LEDGER.parent/NAME
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
    if not exists and not path.exists() and not path.is_symlink() and required_binding is None:
        return None
    p._ledger(db)
    if (not exists or not path.is_file() or path.is_symlink() or path.resolve() != path
            or path.stat().st_nlink != 1 or path.stat().st_size > 100_000 or path.stat().st_mode & 0o077):
        raise BudgetStop('Incomplete/aliased model grant; diagnose without repair or retry')
    bound = p._pin(path)
    if required_binding is not None and required_binding != bound:
        raise BudgetStop('Prospective runtime model opt-in differs from exact grant')
    raw = p.checked(bound)
    if db.execute('SELECT grant_id,receipt_sha256,record_json FROM '+TABLE).fetchall() != [(GRANT, bound['sha256'], raw.decode())]:
        raise BudgetStop('Model grant and original ledger row differ')
    value = strict_json(raw)
    expected = dict(schema='earnings_population_model_budget_amendment_v1', grant_id=GRANT,
        ledger=str(p.LEDGER), model=MODEL, old_model_cap_nano_usd=OLD,
        new_model_cap_nano_usd=NAMED, other_models_cap_nano_usd=OLD,
        stage_additional_ceiling_nano_usd=STAGE_CAP, cumulative_cap_nano_usd=p.CAP,
        window_ceiling_nano_usd=WINDOW_CAP, stage=STAGE)
    extra = {'authority', 'source_commit', 'implementations', 'prefix', 'reconciliations', 'cumulative_amendment'}
    if (set(value) != set(expected)|extra
            or p._encoded({k:value[k] for k in expected}) != p._encoded(expected)):
        raise BudgetStop('Exact typed model grant required; original global/config cap must stay unchanged')
    if p.validate_cap(db, amendment=value['cumulative_amendment']) != p.CAP:
        raise BudgetStop('Existing cumulative400 grant required')
    _authority(value['authority'], value['source_commit'])
    if (type(value['implementations']) is not dict or set(value['implementations']) != set(IMPLEMENTATIONS)
            or any(hashlib.sha256(p._git(value['source_commit'], name)).hexdigest() != sha
                   for name, sha in value['implementations'].items())):
        raise BudgetStop('Committed model-budget implementation differs')
    p._prefix(value['prefix'])
    reconciliations = value['reconciliations']
    if (type(reconciliations) is not dict or set(reconciliations) != {'max_rowid','count','sha256'}
            or any(type(reconciliations[k]) is not int or reconciliations[k] < 0 for k in ('max_rowid','count'))
            or type(reconciliations['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', reconciliations['sha256'])):
        raise BudgetStop('Exact typed original reconciliation prefix required')
    if (history_snapshot(db, STAGE['max_rowid']) != STAGE
            or history_snapshot(db, value['prefix']['max_rowid']) != value['prefix']
            or p._reconciliations(db, value['reconciliations']['max_rowid']) != value['reconciliations']):
        raise BudgetStop('Original stage/activation/reconciliation prefixes changed')
    return value


def _totals(db):
    rows = db.execute('SELECT model,reserved,charged,status FROM requests').fetchall()
    total, models = 0, {}
    for model, reserved, charged, status in rows:
        if (type(reserved) is not int or type(charged) is not int or reserved <= 0
                or not 0 <= charged <= reserved or status not in {'reserved','uncertain','settled','settled_upper_bound'}):
            raise BudgetStop('Malformed original liability')
        amount = charged + (reserved if status not in {'settled','settled_upper_bound'} else 0)
        total += amount
        models[model] = models.get(model, 0) + amount
    return total, models


def authorized_liabilities(db, cap):
    """False preserves the exact no-grant legacy check. Grants count pending."""
    if read_grant(db) is None:
        return False
    total, models = _totals(db)
    if total > cap or any(amount > (NAMED if model == MODEL else OLD) for model, amount in models.items()):
        raise BudgetStop('Liability exceeds global400 or valid named300/other100 grant')
    return True


def dispatch_totals(db, model, amount, optin, *, own_request=None):
    """Only exact opt-in may dispatch named300; all models share stage200."""
    p = _budget()
    if (model not in p.MODELS or type(amount) is not int or amount < 0
            or own_request is not None and (type(own_request) is not str or not own_request)):
        raise BudgetStop('Exact fixed-model integer liability required')
    if (type(optin) is not dict or set(optin) != {'path','sha256'}
            or optin.get('path') != str(p.LEDGER.parent/NAME)
            or type(optin.get('sha256')) is not str or not re.fullmatch('[0-9a-f]{64}', optin['sha256'])):
        raise BudgetStop('Explicit exact prospective model opt-in required')
    if read_grant(db, required_binding=optin) is None:
        raise BudgetStop('Explicit prospective activated model grant required')
    total, models = _totals(db)
    if own_request is not None:
        if db.execute('SELECT model,reserved,charged,status FROM requests WHERE id=?', (own_request,)).fetchone() != (model, amount, 0, 'reserved'):
            raise BudgetStop('Exact own reservation required; never exclude another pending liability')
        total -= amount
        models[model] -= amount
    if total + amount - STAGE['charged_nano_usd'] > STAGE_CAP:
        raise BudgetStop('Fixed stage200 incremental ceiling exceeded')
    return total, models.get(model, 0), NAMED if model == MODEL else OLD


def activate(path, *, authority_binding, source_commit, expected_prefix):
    """Explicit operator, safe idle, file+SQL once only; never called by runtime."""
    p = _budget()
    if str(path) != str(p.LEDGER) or Path(path).resolve() != p.LEDGER:
        raise ValueError('Original sole ledger only')
    p._prefix(expected_prefix)
    _authority(authority_binding, source_commit, current=True)
    implementations = {}
    for name, file in zip(IMPLEMENTATIONS, (Path(__file__), Path(p.__file__))):
        raw = file.read_bytes()
        if p._git(source_commit, name) != raw:
            raise ValueError('Uncommitted model-budget source cannot activate')
        implementations[name] = hashlib.sha256(raw).hexdigest()
    lockpath = p.LEDGER.parent/'.capacity-runtime.lock'
    if lockpath.resolve() != lockpath or not lockpath.is_file() or lockpath.is_symlink():
        raise BudgetStop('Existing canonical shared lock required')
    with lockpath.open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with closing(p.connect_existing(p.LEDGER)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if read_grant(db) is not None:
                    raise BudgetStop('Model amendment already consumed; do not reactivate')
                if p.validate_cap(db) != p.CAP:
                    raise BudgetStop('Original cumulative400 grant required')
                PilotBudget.active(type('ExistingBudget', (), {'db':db})())
                if history_snapshot(db) != expected_prefix or history_snapshot(db, STAGE['max_rowid']) != STAGE:
                    raise BudgetStop('Frozen stage or activation prefix differs')
                p._liabilities(db, p.CAP)
                record = dict(schema='earnings_population_model_budget_amendment_v1', grant_id=GRANT,
                    ledger=str(p.LEDGER), model=MODEL, old_model_cap_nano_usd=OLD,
                    new_model_cap_nano_usd=NAMED, other_models_cap_nano_usd=OLD,
                    stage_additional_ceiling_nano_usd=STAGE_CAP, cumulative_cap_nano_usd=p.CAP,
                    window_ceiling_nano_usd=WINDOW_CAP, stage=deepcopy(STAGE),
                    authority=deepcopy(authority_binding), source_commit=source_commit,
                    implementations=implementations, prefix=history_snapshot(db),
                    reconciliations=p._reconciliations(db), cumulative_amendment=p.amendment_binding())
                raw = p._encoded(record)+b'\n'
                save_bytes(p.LEDGER.parent/NAME, raw)
                bound = binding()
                db.execute('CREATE TABLE '+TABLE+' (grant_id TEXT PRIMARY KEY,receipt_sha256 TEXT NOT NULL,record_json TEXT NOT NULL)')
                db.execute('INSERT INTO '+TABLE+' VALUES (?,?,?)', (GRANT, bound['sha256'], raw.decode()))
                read_grant(db, required_binding=bound)
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
    return bound
