"""Explicit prospective cumulative400 amendment; legacy budgets stay unchanged.

Only activate() writes the sole ledger, under its existing shared idle lock.
A grant file without its committed SQLite row is incomplete and fails closed;
never remove it or retry activation automatically after an interrupted write.
"""
from contextlib import closing
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_full_budget import FULL_MODEL_CAP, MODELS, connect_existing
from earnings_entry import checked
from earnings_http import save_bytes, strict_json
from earnings_night_budget import NightBudget, history_snapshot

REPO = Path(__file__).resolve().parents[1]
LEDGER = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-model-scoring-20261007/pilot-01/api-budget.sqlite3')
PLAN = 'configs/earnings_coevolution/population_400_plan.json'
GRANT = 'earnings-population-cumulative400-20261016'
NAME = 'population-cumulative400-20261016-grant.json'
OLD_CAP, CAP = 200_000_000_000, 400_000_000_000
ORIGINAL_PREFIX = dict(max_rowid=5800, request_count=5800, charged_nano_usd=169_028_921_000,
    rows_sha256='f26689051e0d3167ca02bc7b6114a717ca41477edd348f05651cea6e319c28b3')
AUTHORIZATION = '对，就把累计预算上限改成 $400，原来花的费用照算。直接启动真实 co-evolving：让 Author 收到失败片段、修复代码，过真实财报测试后预测并跟父版比较，再把反馈传到下一轮。training/dev 可以自由探索，最终 held-out 公司不能看。中间不用逐步问我，失败先诊断，持续推进，最后给我真实结果。'


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _pin(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _ledger(db):
    names = db.execute('PRAGMA database_list').fetchall()
    if (len(names) != 1 or names[0][1:] != ('main', str(LEDGER))
            or LEDGER.resolve() != LEDGER or not LEDGER.is_file() or LEDGER.is_symlink()):
        raise BudgetStop('Only the existing canonical sole ledger is admitted')


def _git(commit, name):
    return subprocess.run(['git', 'show', commit+':'+name], cwd=REPO,
                          check=True, capture_output=True).stdout


def _authority(binding, commit, *, current=False):
    from earnings_population_source_history import source_name
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding['path']) is not str or type(commit) is not str
            or not re.fullmatch('[0-9a-f]{40}', commit)):
        raise ValueError('Exact source-bound cumulative400 authority required')
    if (source_name(binding['path'], REPO) != PLAN
            or current and binding['path'] != str(REPO/PLAN)):
        raise ValueError('Exact source-bound cumulative400 authority required')
    raw = _git(commit, PLAN)
    if hashlib.sha256(raw).hexdigest() != binding['sha256'] or current and checked(binding) != raw:
        raise ValueError('Committed human budget authority differs')
    value = strict_json(raw)
    expected = dict(grant_id=GRANT, sole_ledger=str(LEDGER), old_cap_nano_usd=OLD_CAP,
                    new_cap_nano_usd=CAP, model_cap_nano_usd=FULL_MODEL_CAP)
    if (value.get('schema') != 'supervisor_bottleneck_plan_v1' or value.get('id') != GRANT
            or value.get('human_authorization') != AUTHORIZATION
            or value.get('budget_authority') != expected
            or any(type(value['budget_authority'].get(k)) is not int
                   for k in ('old_cap_nano_usd', 'new_cap_nano_usd', 'model_cap_nano_usd'))):
        raise ValueError('Exact direct-human400/model100/sole-ledger authority required')


def _reconciliations(db, maximum=None):
    if maximum is None:
        maximum = db.execute('SELECT COALESCE(MAX(rowid),0) FROM reconciliations').fetchone()[0]
    rows = db.execute('SELECT rowid,* FROM reconciliations WHERE rowid<=? ORDER BY rowid', (maximum,)).fetchall()
    return dict(max_rowid=maximum, count=len(rows), sha256=hashlib.sha256(_encoded(rows)).hexdigest())


def _prefix(value):
    if (type(value) is not dict or set(value) != set(ORIGINAL_PREFIX)
            or any(type(value[k]) is not int or value[k] < 0
                   for k in ('max_rowid', 'request_count', 'charged_nano_usd'))
            or type(value['rows_sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', value['rows_sha256'])):
        raise BudgetStop('Exact integer historical prefix required')


def _liabilities(db, cap):
    from earnings_population_model_budget import authorized_liabilities
    if authorized_liabilities(db, cap):
        return
    if (db.execute("SELECT 1 FROM requests WHERE typeof(reserved)!='integer' OR typeof(charged)!='integer' OR reserved<=0 OR charged<0 OR charged>reserved").fetchone()
            or db.execute('SELECT COALESCE(SUM(charged),0) FROM requests').fetchone()[0] > cap
            or db.execute('SELECT 1 FROM requests GROUP BY model HAVING SUM(charged)>?', (FULL_MODEL_CAP,)).fetchone()):
        raise BudgetStop('Prior liability is invalid or exceeds unchanged accounting guards')


def amendment_binding():
    """Fixed immutable receipt location; no new ledger or caller-picked grant."""
    return _pin(LEDGER.parent/NAME)


def validate_cap(db, *, amendment=None):
    """Read-only historical cap check, never new spending/activation authority.

    Existing200 remains valid.400 requires exact historical grant/authority and
    intact old request/reconciliation prefixes; later rows remain chargeable.
    Current pending/blocked handling belongs active()/the original owner.
    """
    _ledger(db)
    config = db.execute('SELECT cap,model_cap,blocked FROM config WHERE id=1').fetchone()
    if config not in ((OLD_CAP, FULL_MODEL_CAP, 0), (OLD_CAP, FULL_MODEL_CAP, 1),
                      (CAP, FULL_MODEL_CAP, 0), (CAP, FULL_MODEL_CAP, 1)):
        raise BudgetStop('Cumulative/model accounting configuration changed')
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='population_budget_amendments'").fetchone()
    path = LEDGER.parent/NAME
    if config[0] == OLD_CAP:
        if exists or path.exists() or amendment is not None:
            raise BudgetStop('Incomplete or mismatched amendment; diagnose, never reset/retry')
        return OLD_CAP
    if (not exists or path.resolve() != path or not path.is_file() or path.is_symlink()
            or path.stat().st_nlink != 1 or path.stat().st_size > 100_000
            or path.stat().st_mode & 0o077):
        raise BudgetStop('Immutable cumulative400 grant missing or aliased')
    bound = _pin(path)
    if amendment is not None and amendment != bound:
        raise BudgetStop('Runtime amendment binding differs from activated grant')
    raw = checked(bound)
    rows = db.execute('SELECT grant_id,receipt_sha256,record_json FROM population_budget_amendments').fetchall()
    if rows != [(GRANT, bound['sha256'], raw.decode())]:
        raise BudgetStop('Ledger and immutable cumulative400 receipt differ')
    grant = strict_json(raw)
    expected = {'schema', 'grant_id', 'ledger', 'old_cap_nano_usd', 'new_cap_nano_usd',
                'model_cap_nano_usd', 'authority', 'source_commit', 'implementation_sha256', 'prefix', 'reconciliations'}
    if (set(grant) != expected or grant['schema'] != 'earnings_population_budget_amendment_v1'
            or grant['grant_id'] != GRANT or grant['ledger'] != str(LEDGER)
            or (grant['old_cap_nano_usd'], grant['new_cap_nano_usd'], grant['model_cap_nano_usd'])
                != (OLD_CAP, CAP, FULL_MODEL_CAP)):
        raise BudgetStop('Exact prospective grant record required')
    _authority(grant['authority'], grant['source_commit'])  # historical Git, not mutable checkout prose
    if hashlib.sha256(_git(grant['source_commit'], 'tools/earnings_population_budget.py')).hexdigest() != grant['implementation_sha256']:
        raise BudgetStop('Activation implementation commitment differs')
    _prefix(grant['prefix'])
    if (history_snapshot(db, ORIGINAL_PREFIX['max_rowid']) != ORIGINAL_PREFIX
            or history_snapshot(db, grant['prefix']['max_rowid']) != grant['prefix']
            or _reconciliations(db, grant['reconciliations']['max_rowid']) != grant['reconciliations']):
        raise BudgetStop('Original requests/reconciliations changed; no refund/reset')
    return CAP


def activate(path, *, authority_binding, source_commit, expected_prefix):
    """Operator-only one-time amendment; caller must hold explicit human authority.

    File/SQLite cannot commit together: an interrupted prepared receipt remains
    visible and blocks reuse. SQLite cap+record transition itself is atomic.
    """
    if str(path) != str(LEDGER) or Path(path).resolve() != LEDGER:
        raise ValueError('Original sole ledger only')
    _prefix(expected_prefix)
    _authority(authority_binding, source_commit, current=True)
    implementation = Path(__file__).read_bytes()
    if _git(source_commit, 'tools/earnings_population_budget.py') != implementation:
        raise ValueError('Activation implementation must be independently reviewed committed bytes')
    lockpath = LEDGER.parent/'.capacity-runtime.lock'
    if lockpath.resolve() != lockpath or not lockpath.is_file() or lockpath.is_symlink():
        raise BudgetStop('Existing canonical shared lock required')
    with lockpath.open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with closing(connect_existing(LEDGER)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if validate_cap(db) != OLD_CAP:
                    raise BudgetStop('Amendment already consumed; use read-only validation')
                PilotBudget.active(type('ExistingBudget', (), {'db': db})())
                if (history_snapshot(db, ORIGINAL_PREFIX['max_rowid']) != ORIGINAL_PREFIX
                        or history_snapshot(db) != expected_prefix):
                    raise BudgetStop('Frozen activation accounting prefix differs')
                _liabilities(db, OLD_CAP)
                grant = dict(schema='earnings_population_budget_amendment_v1', grant_id=GRANT,
                    ledger=str(LEDGER), old_cap_nano_usd=OLD_CAP, new_cap_nano_usd=CAP,
                    model_cap_nano_usd=FULL_MODEL_CAP, authority=deepcopy(authority_binding),
                    source_commit=source_commit, implementation_sha256=hashlib.sha256(implementation).hexdigest(),
                    prefix=history_snapshot(db), reconciliations=_reconciliations(db))
                raw = _encoded(grant)+b'\n'
                save_bytes(LEDGER.parent/NAME, raw)  # write-once0600; preserve on any later failure
                bound = amendment_binding()
                db.execute('CREATE TABLE population_budget_amendments (grant_id TEXT PRIMARY KEY,receipt_sha256 TEXT NOT NULL,record_json TEXT NOT NULL)')
                db.execute('INSERT INTO population_budget_amendments VALUES(?,?,?)', (GRANT, bound['sha256'], raw.decode()))
                db.execute('UPDATE config SET cap=? WHERE id=1', (CAP,))
                validate_cap(db, amendment=bound)
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
    return bound


class PopulationBudget(NightBudget):
    """Opt-in runtime owner: original deadline/tranche/model guards, total400."""
    def __init__(self, path, *, amendment_binding, model_amendment_binding=None, **kwargs):
        amount = kwargs.get('additional_cap_nano_usd', 20_000_000_000)
        if type(amount) is not int or not 1 <= amount <= 20_000_000_000:
            raise ValueError('Original per-window maximum20 remains unchanged')
        if (str(path) != str(LEDGER) or Path(path).resolve() != LEDGER
                or type(amendment_binding) is not dict or set(amendment_binding) != {'path', 'sha256'}
                or amendment_binding['path'] != str(LEDGER.parent/NAME)
                or type(amendment_binding['sha256']) is not str
                or not re.fullmatch('[0-9a-f]{64}', amendment_binding['sha256'])):
            raise ValueError('Explicit sole-ledger activated amendment binding required')
        self.model_amendment_binding = deepcopy(model_amendment_binding)
        if model_amendment_binding is not None:
            from earnings_population_model_budget import NAME as MODEL_NAME, WINDOW_CAP
            from earnings_night_budget import utc_epoch
            import time
            if (type(model_amendment_binding) is not dict or set(model_amendment_binding) != {'path','sha256'}
                    or model_amendment_binding.get('path') != str(LEDGER.parent/MODEL_NAME)
                    or type(model_amendment_binding.get('sha256')) is not str
                    or not re.fullmatch('[0-9a-f]{64}', model_amendment_binding['sha256'])
                    or amount > WINDOW_CAP
                    or not 0 < utc_epoch(kwargs.get('deadline_utc')) - kwargs.get('clock', time.time)() <= 5400):
                raise ValueError('Exact prospective model grant, window5 and finite90-minute deadline required')
        self.amendment_binding = deepcopy(amendment_binding)
        super().__init__(path, **kwargs)

    def active(self):
        PilotBudget.active(self)
        if validate_cap(self.db, amendment=self.amendment_binding) != CAP:
            raise BudgetStop('Explicit activated cumulative400 runtime required')
        _liabilities(self.db, CAP)
        self._boundary()
        if self.model_amendment_binding is not None:
            from earnings_population_model_budget import dispatch_totals, MODEL
            dispatch_totals(self.db, MODEL, 0, self.model_amendment_binding)

    def _reserve_check(self, model, amount, *, own_request=None):
        self._boundary()
        _liabilities(self.db, CAP)
        total, same = self.db.execute('SELECT COALESCE(SUM(charged),0),COALESCE(SUM(CASE WHEN model=? THEN charged ELSE 0 END),0) FROM requests', (model,)).fetchone()
        model_cap = FULL_MODEL_CAP
        if self.model_amendment_binding is not None:
            from earnings_population_model_budget import dispatch_totals, WINDOW_CAP
            if self.additional_cap_nano_usd > WINDOW_CAP:
                raise BudgetStop('Prospective model window5 ceiling changed')
            total, same, model_cap = dispatch_totals(self.db, model, amount,
                self.model_amendment_binding, own_request=own_request)
        if (total+amount > CAP or same+amount > model_cap
                or total-self.baseline['charged_nano_usd']+amount > self.additional_cap_nano_usd):
            raise BudgetStop('Cumulative400/model100/original window allowance exceeded')

    def reserve(self, request_id, model, amount):
        if (type(request_id) is not str or not request_id or model not in MODELS
                or type(amount) is not int or amount <= 0):
            raise ValueError('Exact fixed-model new reservation required')
        with self.transaction():
            self.active()
            if self.db.execute('SELECT 1 FROM requests WHERE id=?', (request_id,)).fetchone():
                raise BudgetStop('Old request ID remains closed; no retry')
            self._reserve_check(model, amount)
            self.db.execute("INSERT INTO requests VALUES(?,?,?,0,'reserved')", (request_id, model, amount))

    def check_reserved(self, request_id, model, amount):
        if (type(request_id) is not str or not request_id or type(model) is not str
                or model not in MODELS or type(amount) is not int or amount <= 0):
            raise ValueError('Exact own in-flight reservation required')
        with self.transaction():
            if (validate_cap(self.db, amendment=self.amendment_binding) != CAP
                    or self.db.execute('SELECT blocked FROM config WHERE id=1').fetchone() != (0,)
                    or self.db.execute("SELECT id,model,reserved,charged,status FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchall()
                        != [(request_id, model, amount, 0, 'reserved')]):
                raise BudgetStop('Only the exact own single reservation may dispatch')
            self._reserve_check(model, amount, own_request=request_id)

    def summary(self):
        result = PilotBudget.summary(self)
        result.update(cap_usd=validate_cap(self.db, amendment=self.amendment_binding)/1e9,
            model_cap_usd=100, allocation='explicit_cumulative400_prior_charges_included',
            night_cap_usd=self.additional_cap_nano_usd/1e9,
            night_charged_upper_bound_usd=result['charged_upper_bound_usd']-self.baseline['charged_nano_usd']/1e9,
            prior_history_sha256=self.baseline['rows_sha256'], deadline_epoch=self.deadline)
        if self.model_amendment_binding is not None:
            result.update(model_budget_optin=deepcopy(self.model_amendment_binding),
                dispatch_model_caps_usd={'gpt-6.1-sol':300, 'other_models':100})
        return result

