"""Explicit four/eight company ceiling inside ONE owner; no new grant or ledger.

Only the parent touches the original writable budget connection. Model calls,
SIGALRM, Services, Native cases and raw clients stay in separate child processes.
The two grant-pinned financial implementations are not changed or reactivated.
"""
from copy import deepcopy
import multiprocessing as mp
from multiprocessing.connection import wait
import os
from pathlib import Path
import re
import time

import earnings_entry as e
from edgar_forecast_budget import BudgetStop
from supervisor_harness import capacity_feedback_engine as engine
from earnings_population_coevolution import followup_round, continuous_round, bound_continuous_round

POLICY = 'clean_frozen_company_processes4_v1'
ROLLING = 'clean_frozen_company_rolling4_v1'
ROLLING8 = 'clean_frozen_company_rolling8_v1'


def enabled(value):
    marker = value.get('clean_company_concurrency')
    if marker is None: return False
    if (marker not in (POLICY,ROLLING,ROLLING8) or value.get('clean_slate_policy') != 'round0_clean_slate_v1'
            or not (2 if marker==POLICY else 1) <= len(value.get('companies',[])) <= (4 if marker==POLICY else 25)):
        raise ValueError('Explicit clean frozen wave2..4 or rolling queue1..25 required')
    return True


def rolling(value):
    return enabled(value) and value['clean_company_concurrency'] in (ROLLING,ROLLING8)


def concurrency_limit(value):
    """A source-bound policy selects capacity; arbitrary numeric overrides cannot."""
    if not enabled(value):raise ValueError('Explicit company policy required')
    return 8 if value['clean_company_concurrency']==ROLLING8 else 4


def preparation_policy(rolling_refill, rolling_concurrency=4):
    if (type(rolling_refill) is not bool or type(rolling_concurrency) is not int
            or rolling_concurrency not in (4,8) or not rolling_refill and rolling_concurrency!=4):
        raise ValueError('Eight requires explicit rolling; supported ceilings are four/eight')
    return (ROLLING8 if rolling_concurrency==8 else ROLLING) if rolling_refill else POLICY


def window_yield_enabled(value):
    from earnings_population_clean_slate import followup_plan
    n=value.get('clean_learning_round')
    return (followup_round(n) and n>=4 and bound_continuous_round(value)
        and value.get('clean_company_concurrency')==ROLLING8 and followup_plan(n) in value.get('sources',{}))


def window_yield_authority(value):
    if continuous_round(value.get('clean_learning_round')):
        from earnings_population_coevolution import yield_authority
        return yield_authority(value)
    from earnings_population_clean_slate import WINDOW_YIELD_AUTHORITY, STABLE03A_YIELD_AUTHORITY, STABLE03A_ROUND6_YIELD_AUTHORITY, STABLE03A_ROUND7_YIELD_AUTHORITY
    if value.get('clean_learning_round')==7:return STABLE03A_ROUND7_YIELD_AUTHORITY
    if value.get('clean_learning_round')==6:return STABLE03A_ROUND6_YIELD_AUTHORITY
    return STABLE03A_YIELD_AUTHORITY if value.get('clean_learning_round')==5 else WINDOW_YIELD_AUTHORITY


def completed_companies(value,batch=None):
    """A normal yielded window closes a prefix, never scores an untouched suffix."""
    root=Path(value['root'])
    if batch is None:batch=engine.read(engine.pin(root/'company-batch-execution.json'))
    if 'normal_yield' not in batch:return value['companies']
    prefix=[r['company_id'] for r in batch['completed_results']];suffix=value['companies'][len(prefix):]
    if (not window_yield_enabled(value) or not prefix or not suffix or prefix!=value['companies'][:len(prefix)]
            or batch.get('normal_yield')!=dict(completed_prefix=prefix,remaining_suffix=suffix)
            or batch.get('failed_companies')!=[] or batch.get('not_measured')!=suffix
            or [w['company_id'] for w in batch['workers']]!=prefix
            or len([r for r in batch['events'] if r['kind']=='window_yield'])!=1):
        raise ValueError('Normal yield requires successful ordered prefix and untouched suffix')
    authority=window_yield_authority(value)
    event=next(r for r in batch['events'] if r['kind']=='window_yield')
    if (event.get('company_id')!=suffix[0] or event.get('authority')!=authority
            or event.get('reason') not in ('BUDGET_COMPLETION_BUFFER','ORIGINAL_WALL_HEADROOM')):
        raise ValueError('Original declared admission boundary differs')
    native=Path('/private/tmp')/('market-rsi-'+value['id'])
    for company,slot in zip(suffix,value['slots']['forecast'][len(prefix):]):
        if Path(slot).exists() or (native/Path(slot).name).exists():raise ValueError('Yielded suffix was already started')
        record=engine.read(engine.pin(root/'companies'/(company+'-not-measured.json')))
        if record!=dict(company_id=company,runtime=batch['runtime'],status='NOT_MEASURED_WINDOW_YIELD',retry_allowed=False):
            raise ValueError('Missing original never-started suffix receipt')
    return prefix


class OwnedReservations:
    """Parent-only adapter: original money caps, policy-bounded known loans.

    This is not a replacement budget. validate_cap/_reserve_check/settle/uncertain
    remain the original grant implementation; only the sole-pending predicate is
    replaced with an exact, durable company-owner membership predicate.
    """
    def __init__(self, budget, binding, value):
        if not enabled(value): raise ValueError('Batch authority required')
        self.budget,self.binding,self.value = budget,deepcopy(binding),deepcopy(value)
        self.assignments = {}
        self.slots = dict(zip(value['companies'],value['slots']['forecast']))
        self.directory = Path(value['root'])/'request-ownership'
        self.directory.mkdir(mode=0o700,exist_ok=False)

    def active(self):
        from earnings_population_budget import validate_cap, _liabilities, CAP
        from earnings_population_model_budget import dispatch_totals, MODEL
        from earnings_population_additional_budget import budget_liabilities,budget_totals
        b=self.budget
        if (validate_cap(b.db,amendment=b.amendment_binding) != CAP
                or b.db.execute('SELECT blocked FROM config WHERE id=1').fetchone() != (0,)):
            raise BudgetStop('Original budget blocked or changed')
        pending=b.db.execute("SELECT id,model,reserved,charged,status FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchall()
        companies=[]
        for request_id,model,reserved,charged,status in pending:
            item=self.assignments.get(request_id)
            if (item is None or status!='reserved' or charged!=0 or reserved!=item['reserved_nano_usd']
                    or model!=item['model'] or engine.read(item['receipt'])!=item['record']):
                raise BudgetStop('Unknown/uncertain request, changed ownership or reservation')
            companies.append(item['company_id'])
        if len(pending)>concurrency_limit(self.value) or len(companies)!=len(set(companies)):
            raise BudgetStop('Company ceiling exceeded or duplicate in-flight loan')
        budget_liabilities(b);b._boundary()
        total,_,_=budget_totals(b,MODEL)
        if total-b.baseline['charged_nano_usd']>b.additional_cap_nano_usd:
            raise BudgetStop('All in-flight liabilities share the one original window cap')

    def call(self, company, operation, args):
        if company not in self.slots or operation not in {'active','reserve','check_reserved','settle','uncertain','summary'}:
            raise ValueError('Declared company and narrow budget operation required')
        b=self.budget
        if operation=='summary':
            if args:raise ValueError('Unexpected summary arguments')
            return b.summary()
        if operation=='active':
            if args: raise ValueError('Unexpected active arguments')
            return self.active()
        if operation=='reserve':
            request_id,model,amount=args
            if (type(request_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id) is None
                    or model!=self.value['rates']['api_model'] or type(amount) is not int or amount<=0):
                raise ValueError('Exact fixed-model integer reservation required')
            with b.transaction():
                self.active()
                if (request_id in self.assignments or b.db.execute('SELECT 1 FROM requests WHERE id=?',(request_id,)).fetchone()
                        or any(a['company_id']==company for request,a in self.assignments.items()
                            if b.db.execute("SELECT 1 FROM requests WHERE id=? AND status='reserved'",(request,)).fetchone())):
                    raise BudgetStop('No retry or second company loan')
                if b.db.execute("SELECT COUNT(*) FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()[0]>=concurrency_limit(self.value):
                    raise BudgetStop('Policy company in-flight ceiling')
                b._reserve_check(model,amount)  # Includes ALL other pending full reservations.
                record=dict(schema='earnings_clean_company_request_owner_v1',runtime=self.binding,
                    company_id=company,slot=self.slots[company],request_id=request_id,model=model,
                    reserved_nano_usd=amount,retry_allowed=False)
                receipt=engine.save(self.directory/(request_id+'.json'),record)
                self.assignments[request_id]=dict(company_id=company,model=model,reserved_nano_usd=amount,
                    record=record,receipt=receipt)
                b.db.execute("INSERT INTO requests VALUES(?,?,?,0,'reserved')",(request_id,model,amount))
            return None
        request_id=args[0];item=self.assignments.get(request_id)
        if item is None or item['company_id']!=company or engine.read(item['receipt'])!=item['record']:
            raise BudgetStop('Cross-company or unknown reservation')
        if operation=='check_reserved':
            if tuple(args)!=(request_id,item['model'],item['reserved_nano_usd']):
                raise BudgetStop('Changed own reservation')
            with b.transaction():
                self.active()
                if b.db.execute('SELECT model,reserved,charged,status FROM requests WHERE id=?',(request_id,)).fetchone() != (
                        item['model'],item['reserved_nano_usd'],0,'reserved'):
                    raise BudgetStop('Own exact pending reservation required')
                b._reserve_check(item['model'],item['reserved_nano_usd'],own_request=request_id)
            return None
        if operation=='settle': return b.settle(*args)  # Original overcharge block, never refund.
        return b.uncertain(*args)  # Original uncertain block; never auto-reconcile/retry.

    def settled_company(self, company):
        """Other known companies may remain reserved; this company may not."""
        if company not in self.slots:raise ValueError('Undeclared company')
        result=[]
        for request_id,item in self.assignments.items():
            if item['company_id']!=company:continue
            row=self.budget.db.execute('SELECT model,reserved,charged,status FROM requests WHERE id=?',(request_id,)).fetchone()
            if (engine.read(item['receipt'])!=item['record'] or row is None
                    or row[0]!=item['model'] or row[1]!=item['reserved_nano_usd']
                    or row[3]!='settled' or type(row[2]) is not int or not 0<=row[2]<=row[1]):
                raise BudgetStop('Company fees are not durably settled')
            result.append(dict(request_id=request_id,charged_nano_usd=row[2],owner=item['receipt']))
        if not result:raise BudgetStop('Scored company has no owned paid-request evidence')
        self.active()
        return result

    def dispatch_yield(self,active):
        """Admission estimate only; original full-reservation checks stay binding."""
        if not window_yield_enabled(self.value):return None
        authority=window_yield_authority(self.value)
        from earnings_population_budget import CAP
        from earnings_population_model_budget import dispatch_totals, STAGE, STAGE_CAP
        from earnings_population_additional_budget import budget_caps,budget_totals
        from edgar_forecast_openai import unit
        from earnings_night_budget import utc_epoch
        policy=engine.read(authority);b=self.budget;v=self.value
        limits=v['limits']['forecast'];rates=v['rates']
        full=limits['max_input_tokens']*max(unit(rates[k]) for k in ('input','cached','write') if rates.get(k) is not None)
        full+=limits['max_output_tokens']*unit(rates['output'])
        buffer=max(full,policy['empirical_company_buffer_nano_usd'])
        with b.transaction():
            self.active()
            total,same,cap=budget_totals(b,rates['api_model'])
            global_cap,stage_cap=budget_caps(b)
            pending=b.db.execute("SELECT model,reserved FROM requests WHERE status='reserved'").fetchall()
            booked=total-sum(r[1] for r in pending);same_booked=same-sum(r[1] for r in pending if r[0]==rates['api_model'])
            headroom=min(global_cap-booked,cap-same_booked,stage_cap-(booked-STAGE['charged_nano_usd']),
                b.additional_cap_nano_usd-(booked-b.baseline['charged_nano_usd']))
            remaining=buffer
            for company in active:
                charged=sum(b.db.execute('SELECT charged FROM requests WHERE id=?',(rid,)).fetchone()[0]
                    for rid,item in self.assignments.items() if item['company_id']==company)
                remaining+=max(0,buffer-charged)
            seconds=min(utc_epoch(v['cutoff_utc'])-b.clock(),b.monotonic_deadline-b.monotonic())
            reason=('ORIGINAL_WALL_HEADROOM' if seconds<limits['wall_seconds']+policy['closing_admission_margin_seconds']
                else 'BUDGET_COMPLETION_BUFFER' if remaining>headroom else None)
            if reason is None:return None  # Known pending alone uses the existing wait path.
            return dict(reason=reason,empirical_buffer_nano_usd=buffer,required_completion_estimate_nano_usd=remaining,
                booked_headroom_nano_usd=headroom,full_pending_nano_usd=total-booked,remaining_original_seconds=seconds,
                estimate_not_hard_completion_guarantee=True,authority=authority)

    def reservation_wait(self, company, args):
        """Read-only admission wait, never a smaller reservation or HTTP retry.

        Only the source-bound logical3/4 rolling8 adapter uses this.
        Unknown/uncertain/changed ownership still fails active(). A request that
        cannot fit BOOKED liabilities is not waitable; the original reserve
        implementation supplies its fatal refusal. All full pending liabilities
        remain in the original checks when a wait is eventually admitted.
        """
        from earnings_population_clean_slate import followup_plan
        if (self.value.get('clean_company_concurrency')!=ROLLING8
                or type(self.value.get('clean_learning_round')) is not int
                or not followup_round(self.value['clean_learning_round'])
                or not bound_continuous_round(self.value)
                or self.value['clean_learning_round']>=5 and followup_plan(self.value['clean_learning_round']) not in self.value.get('sources',{})):
            return None
        from earnings_population_budget import CAP
        from earnings_population_model_budget import dispatch_totals, STAGE, STAGE_CAP
        from earnings_population_additional_budget import budget_caps,budget_totals
        if company not in self.slots or type(args) not in (list,tuple) or len(args)!=3:
            raise ValueError('Declared company and exact reservation arguments required')
        request_id,model,amount=args;b=self.budget
        if (type(request_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id) is None
                or model!=self.value['rates']['api_model'] or type(amount) is not int or amount<=0):
            raise ValueError('Exact fixed-model integer reservation required')
        with b.transaction():
            self.active()
            if (request_id in self.assignments or b.db.execute('SELECT 1 FROM requests WHERE id=?',(request_id,)).fetchone()
                    or any(a['company_id']==company for request,a in self.assignments.items()
                        if b.db.execute("SELECT 1 FROM requests WHERE id=? AND status='reserved'",(request,)).fetchone())):
                raise BudgetStop('No retry or second company loan')
            total,same,model_cap=budget_totals(b,model)
            global_cap,stage_cap=budget_caps(b)
            pending=b.db.execute("SELECT id,model,reserved FROM requests WHERE status='reserved'").fetchall()
            full=sum(r[2] for r in pending);same_full=sum(r[2] for r in pending if r[1]==model)
            ceilings=[(total,total-full,global_cap),(same,same-same_full,model_cap),
                (total-STAGE['charged_nano_usd'],total-full-STAGE['charged_nano_usd'],stage_cap),
                (total-b.baseline['charged_nano_usd'],total-full-b.baseline['charged_nano_usd'],b.additional_cap_nano_usd)]
            if (not pending or all(liability+amount<=cap for liability,_,cap in ceilings)
                    or any(booked+amount>cap for _,booked,cap in ceilings)):
                return None
            return dict(request_id=request_id,requested_full_nano_usd=amount,
                total_liability_nano_usd=total,booked_nano_usd=total-full,
                pending_full_nano_usd=full,pending_request_ids=[r[0] for r in pending],
                window_cap_nano_usd=b.additional_cap_nano_usd,
                reason='KNOWN_OWNED_NORMAL_PENDING_ONLY_NO_RESERVATION_CREATED')


class BudgetProxy:
    def __init__(self, connection): self.connection=connection
    def _call(self, operation, *args):
        self.connection.send(dict(kind='budget',operation=operation,args=args))
        reply=self.connection.recv()
        if reply.get('ok') is not True: raise BudgetStop('Parent accounting refused: '+reply.get('error_type','Unknown'))
        return reply.get('result')
    def active(self): return self._call('active')
    def reserve(self,*args): return self._call('reserve',*args)
    def check_reserved(self,*args): return self._call('check_reserved',*args)
    def settle(self,*args): return self._call('settle',*args)
    def uncertain(self,*args): return self._call('uncertain',*args)
    def summary(self): return self._call('summary')


def company_forecast_context(value, parent, company, slot):
    """One worker gets one slot; queued companies are not transport concurrency.

    Preserve the legacy forecast constructor and every resource/clock field.
    Only the explicitly authorized logical3/4 rolling8 path gains this projection.
    """
    if value.get('clean_company_concurrency') != ROLLING8:
        return deepcopy(parent)
    fields={'schema','source_commit','root','rates','limits','slots','cutoff_utc','cutoff_monotonic'}
    from earnings_population_clean_slate import followup_plan
    if (not enabled(value) or type(value.get('clean_learning_round')) is not int
            or not followup_round(value['clean_learning_round'])
            or not bound_continuous_round(value)
            or value['clean_learning_round']>=5 and followup_plan(value['clean_learning_round']) not in value.get('sources',{}) or set(parent)!=fields
            or parent['schema']!='earnings_capacity_forecast_transport_v1'
            or parent['root']!=value['root'] or parent['source_commit']!=value['source_commit']
            or parent['rates']!=value['rates'] or parent['limits']!=value['limits']['forecast']
            or parent['cutoff_utc']!=value['cutoff_utc'] or parent['slots']!=value['slots']['forecast']
            or dict(zip(value['slots']['forecast'],value['companies'])).get(slot)!=company):
        raise ValueError('Exact rolling8 parent transport and declared company slot required')
    return dict(deepcopy(parent),slots=[slot])


def company_context_evidence(binding, value, company, slot):
    """Rejoin the actual constructor input, without rerunning any worker/model."""
    if value.get('clean_company_concurrency')!=ROLLING8:return []
    root=Path(value['root']);parent=engine.pin(root/'context-forecast.json')
    child=engine.pin(root/'company-contexts'/(Path(slot).name+'.json'))
    record=engine.pin(root/'company-contexts'/(Path(slot).name+'-binding.json'))
    identity=engine.pin(Path(slot)/'identity.json')
    if (engine.read(child)!=company_forecast_context(value,engine.read(parent),company,slot)
            or engine.read(record)!=dict(schema='earnings_clean_single_company_transport_v1',runtime=binding,
                company_id=company,slot=slot,parent=parent,projected=child,changed_fields=['slots'])
            or engine.read(identity).get('context')!=child):
        raise ValueError('Company forecast context projection or actual consumption differs')
    return [parent,child,record,identity]


def _company_worker(connection, binding, candidate, company, slot, contexts, clock_binding, transport_policy):
    """Spawn target: no global owner, lock, new allowance or inherited SQLite."""
    from earnings_capacity_runtime import _OwnedHTTP, _read
    from earnings_population_runtime import preflight
    from earnings_population_live_guard import RoleValidation
    from earnings_population_services import Services
    from earnings_population_run import PYTHON
    from earnings_population_window import start_utc
    from earnings_http import RawOpenAIHTTP
    import earnings_clock as clock
    value=preflight(binding)
    if not enabled(value) or dict(zip(value['slots']['forecast'],value['companies'])).get(slot)!=company:
        raise ValueError('Exact declared isolated company worker required')
    budget=BudgetProxy(connection);root=Path(value['root']);original_contexts=deepcopy(contexts)
    projection=None
    if value.get('clean_company_concurrency')==ROLLING8:
        projected=company_forecast_context(value,engine.read(contexts['forecast']),company,slot)
        (root/'company-contexts').mkdir(mode=0o700,exist_ok=True)
        child=engine.save(root/'company-contexts'/(Path(slot).name+'.json'),projected)
        projection=engine.save(root/'company-contexts'/(Path(slot).name+'-binding.json'),dict(
            schema='earnings_clean_single_company_transport_v1',runtime=binding,company_id=company,slot=slot,
            parent=contexts['forecast'],projected=child,changed_fields=['slots']))
        contexts=dict(contexts,forecast=child)
    identity=e.digest(value['id'].encode())
    claim=engine.pin(Path(value['ledger']).parent/'.capacity-runtime-claims'/(identity+'.json'))
    seal=engine.pin(Path(clock_binding['path']).with_name('clock.binding.json'))
    captured=engine.read(clock_binding)
    live=[True]
    manager=None
    def guard(loan=None, selected_slot=None):
        if not live[0] or selected_slot is not None and str(selected_slot)!=slot:
            raise BudgetStop('Worker closed or another company slot')
        manager.check(slot)
        for bound in [claim,clock_binding,seal,*original_contexts.values(),*contexts.values(),
                *([projection] if projection is not None else [])]:_read(bound)
        config=dict(source_commit=value['source_commit'],new_request_cutoff_utc=value['cutoff_utc'],deadline_utc=value['deadline_utc'])
        if clock.capture_or_load(root,config,create=False)[1]!=clock_binding:
            raise BudgetStop('Original shared clock changed')
        if time.monotonic()>=captured['cutoff_monotonic']:raise BudgetStop('Original shared cutoff reached')
        if loan is None:budget.active()
        else:budget.check_reserved(*loan)
    manager=RoleValidation(binding,value,lambda:preflight(binding),owner_check=lambda s:guard(selected_slot=s))
    def factory():
        guard()
        class TracedRaw(RawOpenAIHTTP):
            def post(self,endpoint,payload):
                prefix=self.record_prefix;intent=engine.pin(prefix.with_suffix('.intent.json'))
                started=time.monotonic();error=None
                try:return super().post(endpoint,payload)
                except BaseException as caught:error=type(caught).__name__;raise
                finally:
                    engine.save(prefix.with_suffix('.company-send.json'),dict(
                        schema='earnings_clean_company_physical_interval_v1',runtime=binding,
                        company_id=company,slot=slot,worker_pid=os.getpid(),endpoint=endpoint,intent=intent,
                        start_monotonic=started,end_monotonic=time.monotonic(),error_type=error))
        client=TracedRaw(e.credential(),600)
        guard()
        return _OwnedHTTP(client,lambda loan:guard(loan),{slot:value['limits']['forecast']},value['rates'],
            efforts={slot:value['role_efforts']['forecast']},live_check=lambda loan,s:guard(loan,s))
    service=Services.company_worker(binding,native_root=Path('/private/tmp')/('market-rsi-'+value['id']),
        python_binding=PYTHON,company=company,slot=slot,contexts=contexts,clock_binding=clock_binding,
        transport_policy=transport_policy,budget=budget,client_factory=factory,register_case=manager.register_case)
    service.start_utc=start_utc(value)
    started=time.monotonic();error=None;row=None
    try:
        row=manager.wrap('forecast',service.forecast)(deepcopy(candidate),company,slot)
    except BaseException as caught:
        error=type(caught).__name__
        if service.pending:
            from earnings_native_failure import close_failed_work
            case,work_id=service.pending[-1]
            try:
                close_failed_work(case['capacity'].batch,runtime_binding=binding,work_id=work_id,
                    pair_sha256=case['pair_sha256'],output_root=root/'native-failure',error_type=error)
            except BaseException: pass  # Original failure and unresolved Native evidence remain, never retry.
    finally:
        live[0]=False
        checkpoint=engine.save(root/'companies'/(company+'.json'),dict(
            schema='earnings_clean_company_checkpoint_v1',runtime=binding,company_id=company,slot=slot,
            candidate_id=candidate['id'],worker_pid=os.getpid(),start_monotonic=started,end_monotonic=time.monotonic(),
            status='COMPLETED_SCORED' if error is None else 'FAILED_NO_RETRY',error_type=error,
            result=row,retry_allowed=False))
        connection.send(dict(kind='done',checkpoint=checkpoint,error_type=error,result=row))
        connection.close()
    if error is not None:raise RuntimeError('Company execution failed; see own checkpoint: '+error)


def run(services, live, candidate):
    """One bounded wave, not four independent owners or four new USD5 windows."""
    value=services.runtime
    if not enabled(value):raise ValueError('Explicit frozen company concurrency required')
    from earnings_population_clean_slate import read_task
    task,_=read_task(value)
    if task['mode']!='evaluate':raise ValueError('C/A/Review cannot be concurrent')
    root=Path(value['root']);(root/'companies').mkdir(mode=0o700,exist_ok=False)
    store=OwnedReservations(live['budget'],services.binding,value)
    if rolling(value):return _run_rolling(services,live,candidate,store)
    context=mp.get_context('spawn');jobs=[];events=[];started=time.monotonic()
    launch_failures=[];launch_error=None
    for company,slot in zip(value['companies'],value['slots']['forecast']):
        parent=child=process=None
        try:
            parent,child=context.Pipe()
            process=context.Process(target=_company_worker,args=(child,services.binding,candidate,company,slot,
                live['context_bindings'],live['clock_binding'],services.transport_policy),name='edgar-'+company)
            process.start()
            jobs.append(dict(company=company,slot=slot,process=process,connection=parent,done=None))
            child.close()
        except BaseException as caught:
            if process is not None and process.pid is not None and all(j['process'] is not process for j in jobs):
                jobs.append(dict(company=company,slot=slot,process=process,connection=parent,done=None))
            elif parent is not None:parent.close()
            if child is not None:child.close()
            launch_failures=value['companies'][len(jobs):]
            launch_error=dict(company_id=company,error_type=type(caught).__name__)
            break  # Still drain ALL already-started workers under the same owner.
    rows,workers,events,errors=serve(store,jobs)
    if launch_error is not None:
        engine.save(root/'companies'/(launch_error['company_id']+'-launch-failure.json'),dict(
            schema='earnings_clean_company_launch_failure_v1',runtime=services.binding,
            status='NOT_MEASURED_SETUP',**launch_error,retry_allowed=False))
    engine.save(root/'company-batch-execution.json',dict(schema='earnings_clean_company_batch_execution_v1',
        runtime=services.binding,policy=POLICY,companies=value['companies'],max_companies=4,workers=workers,
        start_monotonic=started,end_monotonic=time.monotonic(),events=events,
        completed_results=rows,failed_companies=sorted(set(errors+launch_failures)),retry_allowed=False))
    if errors or launch_failures:raise RuntimeError('Company batch failed; preserve all completed/failed evidence, no retry')
    store.active()
    return rows


def _rolling_closed(services,candidate,job):
    """Per-company original evidence, never scorer execution or snapshot repair."""
    import fcntl
    from earnings_population import validate_result
    from earnings_population_clean_slate import physical_requests, read_task
    from earnings_population_continuation import _Reader
    import earnings_population_completed as completed
    from earnings_native_failure import _owned_requests, _cleanup
    from earnings_population_run import PYTHON
    value=services.runtime;slot=Path(job['slot']);company=job['company'];root=Path(value['root'])
    checkpoint=engine.read(job['done']['checkpoint']);result=validate_result(job['done']['result'])
    if (checkpoint.get('runtime')!=services.binding or checkpoint.get('company_id')!=company
            or checkpoint.get('slot')!=str(slot) or checkpoint.get('candidate_id')!=candidate['id']
            or checkpoint.get('worker_pid')!=job['process'].pid or checkpoint.get('status')!='COMPLETED_SCORED'
            or checkpoint.get('error_type') is not None or checkpoint.get('result')!=result
            or checkpoint.get('retry_allowed') is not False or result['version_id']!=candidate['id']):
        raise ValueError('Exact scored company checkpoint required')
    guard=engine.pin(root/'role-validation'/(slot.name+'.json'));report=engine.read(guard)
    if (report.get('runtime')!=services.binding or report.get('role')!='forecast' or report.get('slot')!=str(slot)
            or report.get('selected_version_id')!=candidate['id']
            or any(report.get(k)!='PASS' for k in ('entry_full_audit','exit_full_audit','exit_current_guard'))
            or report.get('output_accepted') is not True):raise ValueError('Original company role guard failed')
    public=engine.read(engine.pin(slot/'population-public-feedback.json'))
    scores=public['target_scores']
    if (public.get('company_id')!=company or public.get('version_id')!=candidate['id']
            or public.get('points')!=result['points'] or [s['target_id'] for s in scores]!=[f'T{i:03d}' for i in range(1,6)]
            or any(type(s.get('points_awarded')) not in (int,float) or s['points_awarded'] not in (0,.5,1) for s in scores)
            or sum(s['points_awarded'] for s in scores)!=result['points']):raise ValueError('Original public five-target score differs')
    evidence=company_context_evidence(services.binding,value,company,str(slot))+physical_requests(slot)
    projected=deepcopy(value);projected['slots']={r:([str(slot)] if r=='forecast' else []) for r in value['slots']}
    fees=_owned_requests(projected)
    if not fees or any(f['status']!='settled' for f in fees):raise BudgetStop('Company fee evidence incomplete')
    cleanup=_cleanup(root,runtime=value,selected_slot=slot.name)
    _,scope=read_task(value);selected=dict(role='forecast',company_id=company,version=candidate,forecast_result=result)
    native=Path('/private/tmp')/('market-rsi-'+value['id'])/slot.name;path=native/'context.json'
    reader=_Reader(root.parent.parent,Path(value['ledger']),e.REPO,value['id']);reader.register_sources(value)
    context=reader.read(reader.pin(path))
    if (context.get('authority')!=services.binding or context.get('source_commit')!=value['source_commit']
            or context.get('pool_version')!=candidate or context.get('company',{}).get('cik')!=company):
        raise ValueError('Original Native company identity differs')
    fixed=completed._native_identity(reader,path,context,selected,services.binding,value,
        completed.tasks.resident(company),PYTHON,training_scope=scope)
    batch=completed.ContinuousDiscoveryBatch(native/'batch',allow_temporary=True)
    with batch.lock_path.open('rb') as stream:
        fcntl.flock(stream,fcntl.LOCK_SH|fcntl.LOCK_NB)
        replayed=batch._replay(batch._read_records())
        if (batch._read_snapshot()!=replayed or not replayed['initialized'] or replayed['attempts_claimed']!=0
                or replayed['active_attempt_ids'] or replayed['active_attempt_id'] is not None
                or replayed['micro_evolution']['pending'] is not None
                or replayed['micro_evolution']['fixed_context']!=fixed
                or replayed['micro_evolution']['active_pair']!=engine.activation.pair(context['manifest'])):
            raise ValueError('Original company Native journal is not durably idle')
        completed._native_work(reader,path,context,selected,value,replayed)
    return engine.save(root/'companies'/(company+'-rolling-closed.json'),dict(
        schema='earnings_clean_rolling_company_closed_v1',runtime=services.binding,company_id=company,
        checkpoint=job['done']['checkpoint'],role_guard=guard,fees=fees,cleanup=cleanup,physical=evidence,
        native_context=reader.pin(path),native_snapshot=reader.pin(batch.snapshot_path),retry_allowed=False))


def _run_rolling(services,live,candidate,store):
    value=services.runtime;root=Path(value['root']);context=mp.get_context('spawn');started=time.monotonic()
    from earnings_population_live_guard import RoleValidation
    from earnings_population_runtime import preflight
    from earnings_capacity_runtime import _read
    import earnings_clock as clock
    manager=RoleValidation(services.binding,value,lambda:preflight(services.binding))
    claim=engine.pin(Path(value['ledger']).parent/'.capacity-runtime-claims'/(e.digest(value['id'].encode())+'.json'))
    seal=engine.pin(Path(live['clock_binding']['path']).with_name('clock.binding.json'))
    def guard():
        manager.check_owner()
        for bound in (claim,seal,live['clock_binding'],*live['context_bindings'].values()):_read(bound)
        if engine.read(claim).get('runtime')!=services.binding:raise BudgetStop('Original owner changed')
        config=dict(source_commit=value['source_commit'],new_request_cutoff_utc=value['cutoff_utc'],deadline_utc=value['deadline_utc'])
        if clock.capture_or_load(root,config,create=False)[1]!=live['clock_binding']:
            raise BudgetStop('Original shared clock changed')
        if time.monotonic()>=engine.read(live['clock_binding'])['cutoff_monotonic']:
            raise BudgetStop('Original shared cutoff reached')
    def factory(company,slot):
        parent,child=context.Pipe()
        process=context.Process(target=_company_worker,args=(child,services.binding,candidate,company,slot,
            live['context_bindings'],live['clock_binding'],services.transport_policy),name='edgar-'+company)
        return dict(company=company,slot=slot,process=process,connection=parent,child=child,done=None)
    rows,workers,events,errors,unstarted=serve_rolling(store,list(store.slots.items()),factory,
        lambda job:_rolling_closed(services,candidate,job),guard)
    yielded=bool(unstarted and not errors and any(r['kind']=='window_yield' for r in events))
    for company in unstarted:
        engine.save(root/'companies'/(company+'-not-measured.json'),dict(company_id=company,runtime=services.binding,
            status='NOT_MEASURED_WINDOW_YIELD' if yielded else 'NOT_MEASURED_STOPPED_DISPATCH',retry_allowed=False))
    engine.save(root/'company-batch-execution.json',dict(schema='earnings_clean_company_batch_execution_v1',
        runtime=services.binding,policy=value['clean_company_concurrency'],companies=value['companies'],max_companies=concurrency_limit(value),workers=workers,
        start_monotonic=started,end_monotonic=time.monotonic(),events=events,completed_results=rows,
        failed_companies=sorted(set(errors)),not_measured=unstarted,retry_allowed=False,
        **(dict(normal_yield=dict(completed_prefix=[r['company_id'] for r in rows],remaining_suffix=unstarted)) if yielded else {})))
    if errors:raise RuntimeError('Rolling dispatch stopped; completed results and unattempted queue preserved, no retry')
    store.active()
    return rows


def serve_rolling(store,queue,factory,verify,guard):
    started=[];events=[];began=time.monotonic()
    try:return _serve_rolling(store,queue,factory,verify,guard,started,events)
    except BaseException as caught:
        # An unexpected parent-control exception still cannot release the owner
        # while a started child is alive. Preserve ordinary RPC settlements first.
        drain_error=None
        for job in started:
            if job.pop('reserve_wait',None) is not None:
                try:job['connection'].send(dict(ok=False,result=None,error_type='ParentControlStoppedWhileWaiting'))
                except (BrokenPipeError,EOFError,ConnectionError,OSError):pass
        try:serve(store,started)
        except BaseException as failed:
            drain_error=type(failed).__name__
            for job in started:
                try:job['connection'].close()
                except BaseException:pass
        finally:
            for job in started:
                while job['process'].exitcode is None:
                    try:job['process'].join(timeout=.25)
                    except BaseException:continue
                try:job['connection'].close()
                except BaseException:pass
        # Preserve a failed, NOT fully verified terminal inventory even when the
        # normal _run_rolling return path is bypassed. No success/adoption credit.
        workers=[];rows=[];closed={r['company_id']:r['closure'] for r in events if r['kind']=='closed'}
        for job in started:
            done=job['done'] or {};company=job['company'];process=job['process']
            worker=dict(company_id=company,slot=job['slot'],pid=process.pid,true_exit_code=process.exitcode,
                checkpoint=done.get('checkpoint'))
            if company in closed:worker['closure']=closed[company]
            path=Path(store.value['root'])/'companies'/(company+'-process-'+str(process.pid)+'.json')
            if path.is_file():worker['process_exit_receipt']=engine.pin(path)
            workers.append(worker)
            if process.exitcode==0 and done.get('error_type') is None and done.get('result') is not None:
                rows.append(dict(arm='candidate',company_id=company,result=done['result']))
        try:
            engine.save(Path(store.value['root'])/'company-batch-execution.json',dict(
                schema='earnings_clean_company_batch_execution_v1',runtime=store.binding,policy=store.value['clean_company_concurrency'],
                companies=store.value['companies'],max_companies=concurrency_limit(store.value),workers=workers,start_monotonic=began,
                end_monotonic=time.monotonic(),events=events,completed_results=rows,
                failed_companies=[j['company'] for j in started if j['company'] not in closed],
                not_measured=[c for c,_ in queue if c not in {j['company'] for j in started}],
                parent_control_error=type(caught).__name__,drain_error=drain_error,
                status='FAILED_PARENT_CONTROL_NO_RETRY',retry_allowed=False))
        except BaseException as failed:caught.add_note('Terminal inventory write failed: '+type(failed).__name__)
        raise


def _serve_rolling(store,queue,factory,verify,guard,started,events):
    """Same owner/RPC/ledger; only reaped, closed companies release capacity."""
    if (not rolling(store.value) or queue!=list(store.slots.items())
            or len({c for c,_ in queue})!=len(queue)):raise ValueError('Exact declared unique rolling queue required')
    active=[];finished={};errors=[];cursor=0;stopped=False;yielding=False;spawn_wait_until=0
    event_dir=Path(store.value['root'])/'rolling-events';event_dir.mkdir(mode=0o700,exist_ok=False)
    def event(kind,company=None,**extra):
        nonlocal stopped
        row=dict(sequence=len(events),kind=kind,company_id=company,monotonic=time.monotonic(),**extra);events.append(row)
        try:engine.save(event_dir/f'{row["sequence"]:04d}.json',row)
        except BaseException as caught:
            stopped=True;errors.append('EventWrite:'+type(caught).__name__)
    def stop(company,reason):
        nonlocal stopped
        stopped=True;errors.append(company or reason);event('stop_dispatch',company,error_type=reason)
    def notifications():
        return any(not j['process'].is_alive() or j['done'] is None and j['connection'].poll() for j in active)
    def budget_reply(job,operation,args):
        result=None;error=None;message=None
        try:
            pressure=store.reservation_wait(job['company'],args) if operation=='reserve' else None
            if pressure is not None:
                if job.get('reserve_wait') is None:
                    guard()
                    job['reserve_wait']=tuple(args)
                    event('reservation_wait',job['company'],**pressure)
                job['reserve_wait_check']=time.monotonic()+.5
                return  # Keep the original unsent RPC, service OTHER settlements.
            result=store.call(job['company'],operation,args)
        except BaseException as caught:
            error=type(caught).__name__;message=str(caught)[:500];stop(job['company'],error)
        if job.pop('reserve_wait',None) is not None:
            event('reservation_wait_finished',job['company'],request_id=args[0],error_type=error)
        event('budget',job['company'],operation=operation,error_type=error,error_message=message)
        job['connection'].send(dict(ok=error is None,result=result,error_type=error))
    while active or cursor<len(queue) and not stopped and not yielding:
        # Refill occurs only after the previous loop processed ALL ready errors/exits.
        while (not stopped and not yielding and len(active)<concurrency_limit(store.value) and cursor<len(queue)
                and time.monotonic()>=spawn_wait_until and not notifications()):
            company,slot=queue[cursor];job=None
            try:
                guard();store.active()
                admission=store.dispatch_yield([j['company'] for j in active])
                if admission is not None:
                    if not started:raise BudgetStop('No company admitted before window yield')
                    yielding=True;event('window_yield',company,**admission);break
                try:store.budget._reserve_check(store.value['rates']['api_model'],1)
                except BudgetStop:
                    # Admission-only probe, NOT a generation/request/reservation.
                    pressure=store.reservation_wait(company,('unreserved-spawn-probe-'+company,store.value['rates']['api_model'],1))
                    if pressure is None:raise
                    spawn_wait_until=time.monotonic()+.5
                    event('dispatch_capacity_wait',company,pending_full_nano_usd=pressure['pending_full_nano_usd'],
                        probe_only_no_request_or_reservation=True)
                    break
                if notifications():break  # Current guards may take time; recheck before spawn.
                job=factory(company,slot);job['process'].start();started.append(job);active.append(job);cursor+=1
                job['child'].close();event('dispatch',company,pid=job['process'].pid,active_count=len(active))
            except BaseException as caught:
                if job is not None:
                    if job['process'].pid is not None and job not in active:
                        if job not in started:started.append(job)
                        active.append(job);cursor+=1
                    job['child'].close()
                    if job not in active:job['connection'].close()
                stop(company,type(caught).__name__)
        waiting=[j for j in active if j['done'] is None]
        try:ready=wait([j['connection'] for j in waiting],timeout=.02) if waiting else []
        except BaseException as caught:
            stop(None,type(caught).__name__);ready=[]
            for job in waiting:job['connection'].close();job['done']=dict(error_type='ParentWaitFailure',result=None)
        if not waiting:time.sleep(.005)
        for job in waiting:
            if job['connection'] not in ready:continue
            try:
                message=job['connection'].recv()
                if type(message) is not dict:raise ValueError('UnknownWorkerMessage')
                if message.get('kind')=='budget':
                    if set(message)!={'kind','operation','args'} or type(message['args']) not in (list,tuple):
                        raise ValueError('UnknownBudgetMessage')
                    if job.get('reserve_wait') is not None:raise ValueError('SecondRPCWhileReservationWaiting')
                    budget_reply(job,message['operation'],message['args'])
                elif message.get('kind')=='done' and {'error_type','result','checkpoint'}<=set(message):
                    if job.pop('reserve_wait',None) is not None:
                        event('reservation_wait_cancelled',job['company'],reason='WorkerFinishedBeforeAdmission')
                        if message['error_type'] is None:raise ValueError('UnadmittedWorkerCannotSucceed')
                    job['done']=message;event('worker_done',job['company'])
                    if message['error_type'] is not None:stop(job['company'],message['error_type'])
                else:raise ValueError('UnknownWorkerMessage')
            except BaseException as caught:
                job['connection'].close();job['done']=dict(error_type=type(caught).__name__,result=None)
                stop(job['company'],type(caught).__name__)
        for job in list(active):
            if job['process'].is_alive():continue
            # A pipe can hold the final message after process death; consume it next pass.
            if job['done'] is None and job['connection'].poll():continue
            job['process'].join(timeout=0);job['connection'].close()
            done=job['done'] or dict(error_type='MissingCheckpoint',result=None)
            worker=dict(company_id=job['company'],slot=job['slot'],pid=job['process'].pid,
                true_exit_code=job['process'].exitcode,checkpoint=done.get('checkpoint'))
            event('process_exit',job['company'],pid=worker['pid'],true_exit_code=worker['true_exit_code'])
            try:
                worker['process_exit_receipt']=engine.save(Path(store.value['root'])/'companies'/(
                    job['company']+'-process-'+str(worker['pid'])+'.json'),dict(
                        schema='earnings_clean_company_process_exit_v1',runtime=store.binding,company_id=job['company'],
                        pid=worker['pid'],true_exit_code=worker['true_exit_code'],worker_checkpoint=worker['checkpoint'],
                        error_type=done['error_type'],retry_allowed=False))
                if worker['true_exit_code']!=0 or done['error_type'] is not None or done['result'] is None:
                    raise ValueError('CompanyFailedOrMissingResult')
                job['done']=done;store.settled_company(job['company']);guard()
                worker['closure']=verify(job)
                event('closed',job['company'],closure=worker['closure'])
            except BaseException as caught:stop(job['company'],type(caught).__name__)
            finished[job['company']]=(worker,done.get('result'));active.remove(job)
        # Ready errors/exits are processed before any waiting unsent admission.
        # Original company alarms and the unchanged window clock keep running.
        for job in list(active):
            args=job.get('reserve_wait')
            if args is None or job['done'] is not None:continue
            try:
                if stopped:
                    job.pop('reserve_wait');event('reservation_wait_cancelled',job['company'],reason='DispatchStopped')
                    job['connection'].send(dict(ok=False,result=None,error_type='DispatchStoppedWhileWaiting'))
                elif time.monotonic()>=job['reserve_wait_check']:
                    guard()
                    if not notifications():budget_reply(job,'reserve',args)
            except BaseException as caught:
                stop(job['company'],type(caught).__name__)
                job.pop('reserve_wait',None)
                try:job['connection'].send(dict(ok=False,result=None,error_type=type(caught).__name__))
                except (BrokenPipeError,EOFError,ConnectionError,OSError):pass
    rows=[dict(arm='candidate',company_id=c,result=finished[c][1]) for c,_ in queue
        if c in finished and finished[c][1] is not None]
    workers=[finished[c][0] for c,_ in queue if c in finished]
    return rows,workers,events,errors,[c for c,_ in queue[cursor:]]


def verify_rolling_events(companies,events,workers=None,*,limit=4):
    if type(limit) is not int or limit not in (4,8):raise ValueError('Supported ceiling is four or eight')
    active=set();exited=set();closed=set();launched=[];stopped=False;yielded=False;last=-1
    actual=None if workers is None else {w['company_id']:w for w in workers}
    for index,row in enumerate(events):
        company=row['company_id'];kind=row['kind']
        if row['sequence']!=index or row['monotonic']<last:raise ValueError('Rolling event sequence/time differs')
        last=row['monotonic']
        if kind=='dispatch':
            if stopped or yielded or company in launched or company not in companies:raise ValueError('Repeated/unsafe rolling dispatch')
            active.add(company);launched.append(company)
            if len(active)>limit or row['active_count']!=len(active):raise ValueError('Rolling process concurrency exceeds policy')
            if actual is not None and row['pid']!=actual[company]['pid']:raise ValueError('Dispatch PID differs')
        elif kind=='process_exit':
            if company not in active or row['true_exit_code']!=0:raise ValueError('Company process did not exit successfully')
            exited.add(company)
            if actual is not None and (row['pid']!=actual[company]['pid'] or row['true_exit_code']!=actual[company]['true_exit_code']):
                raise ValueError('Process exit differs from original worker')
        elif kind=='closed':
            if company not in exited or company not in active:raise ValueError('Refill before process exit/closure')
            active.remove(company);closed.add(company)
            if actual is not None and row['closure']!=actual[company]['closure']:raise ValueError('Close receipt differs')
        elif kind=='stop_dispatch':stopped=True
        elif kind=='window_yield':
            if yielded or row.get('reason') not in ('BUDGET_COMPLETION_BUFFER','ORIGINAL_WALL_HEADROOM'):
                raise ValueError('Invalid repeated window yield')
            yielded=True
    if active or set(companies)!=closed or launched!=companies or stopped:raise ValueError('Rolling evidence is incomplete or stopped')


def _rolling_event_evidence(root,value,batch):
    if any(r['kind']=='window_yield' for r in batch['events'])!=('normal_yield' in batch):
        raise ValueError('Yield event and normal-window inventory differ')
    verify_rolling_events(completed_companies(value,batch),batch['events'],batch['workers'],limit=concurrency_limit(value))
    events=sorted((root/'rolling-events').glob('*.json'));evidence=[]
    if [p.name for p in events]!=[f'{i:04d}.json' for i in range(len(batch['events']))]:
        raise ValueError('Missing/extra rolling events')
    for path,row in zip(events,batch['events']):
        saved=engine.pin(path)
        if engine.read(saved)!=row:raise ValueError('Persistent rolling event differs')
        evidence.append(saved)
    return evidence


def serve(store,jobs):
    """Parent single-thread RPC loop; separately testable with synthetic workers."""
    errors=[];events=[]
    while any(j['done'] is None for j in jobs):
        waiting=[j for j in jobs if j['done'] is None]
        try:ready=wait([j['connection'] for j in waiting],timeout=.25)
        except BaseException:
            # An owner/control failure stops RPC but never kills in-flight
            # inference. Keep the owner lock and join every started process.
            for job in waiting:
                job['connection'].close();job['done']=dict(error_type='ParentWaitFailure')
                errors.append(job['company'])
            break
        for job in waiting:
            if job['connection'] in ready:
                try:message=job['connection'].recv()
                except (EOFError,ConnectionError,OSError):
                    job['done']=dict(error_type='WorkerExitedWithoutCheckpoint');errors.append(job['company']);continue
                if (type(message) is not dict or message.get('kind') not in {'budget','done'}
                        or message.get('kind')=='budget' and (set(message)!={'kind','operation','args'}
                            or type(message['args']) not in (list,tuple))
                        or message.get('kind')=='done' and not {'error_type','result'}<=set(message)):
                    job['connection'].close();job['done']=dict(error_type='UnknownWorkerMessage')
                    errors.append(job['company']);continue
                if message.get('kind')=='budget':
                    error=None;result=None
                    try:result=store.call(job['company'],message['operation'],message['args'])
                    except BaseException as caught:error=type(caught).__name__
                    try:pending=store.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchone()[0]
                    except BaseException:pending=None;error=error or 'AccountingReadFailure'
                    events.append(dict(company_id=job['company'],operation=message['operation'],
                        request_id=message['args'][0] if message['args'] else None,
                        monotonic=time.monotonic(),error_type=error,
                        pending_count=pending))
                    try:job['connection'].send(dict(ok=error is None,result=result,error_type=error))
                    except (BrokenPipeError,EOFError,ConnectionError,OSError):
                        job['connection'].close()
                        job['done']=dict(error_type='WorkerDisconnectedAfterBudgetOperation')
                        errors.append(job['company'])
                elif message.get('kind')=='done':
                    job['done']=message
                    if message['error_type'] is not None:errors.append(job['company'])
                else:
                    job['connection'].close();job['done']=dict(error_type='UnknownWorkerMessage')
                    errors.append(job['company'])
            elif not job['process'].is_alive():
                job['done']=dict(error_type='WorkerExitedWithoutCheckpoint');errors.append(job['company'])
    # Join EVERY child before any terminal file write can fail. The shared
    # owner must never unwind with another company still alive/in-flight.
    for job in jobs:
        while job['process'].is_alive():
            try:job['process'].join(timeout=.25)
            except BaseException:errors.append(job['company'])
        job['process'].join(timeout=0);job['connection'].close()
    rows=[];workers=[]
    for job in jobs:
        workers.append(dict(company_id=job['company'],slot=job['slot'],pid=job['process'].pid,
            true_exit_code=job['process'].exitcode,checkpoint=job['done'].get('checkpoint')))
        # Parent's actual OS exit is separate from the worker's own science/
        # Native closure. A missing checkpoint is never manufactured as success.
        if hasattr(store,'value'):
            workers[-1]['process_exit_receipt']=engine.save(Path(store.value['root'])/'companies'/(
                job['company']+'-process-'+str(job['process'].pid)+'.json'),dict(schema='earnings_clean_company_process_exit_v1',
                    runtime=store.binding,company_id=job['company'],pid=job['process'].pid,
                    true_exit_code=job['process'].exitcode,worker_checkpoint=job['done'].get('checkpoint'),
                    error_type=job['done'].get('error_type'),retry_allowed=False))
        if job['process'].exitcode!=0:errors.append(job['company'])
        elif job['done'].get('result') is not None:
            rows.append(dict(arm='candidate',company_id=job['company'],result=job['done']['result']))
    return rows,workers,events,errors


def verify_closed(binding,value,results):
    """Join company true exits, checkpoints, every UUID and actual send intervals."""
    if not enabled(value):raise ValueError('Exact company batch required')
    root=Path(value['root']);bound=engine.pin(root/'company-batch-execution.json');batch=engine.read(bound)
    companies=completed_companies(value,batch)
    if (batch.get('runtime')!=binding or batch.get('policy')!=value['clean_company_concurrency'] or batch.get('failed_companies')!=[]
            or batch.get('parent_control_error') is not None
            or batch.get('companies')!=value['companies'] or batch.get('completed_results')!=results
            or batch.get('max_companies')!=concurrency_limit(value) or batch.get('retry_allowed') is not False
            or [w.get('company_id') for w in batch['workers']]!=companies
            or not rolling(value) and len({w['pid'] for w in batch['workers']})!=len(value['companies'])):
        raise ValueError('Original complete isolated-company execution required')
    evidence=[bound];requests={};intervals=[]
    if rolling(value):
        evidence+=_rolling_event_evidence(root,value,batch)
    for worker,company,slot,result in zip(batch['workers'],companies,value['slots']['forecast'],results):
        evidence+=company_context_evidence(binding,value,company,slot)
        checkpoint=engine.read(worker['checkpoint'])
        if (worker['true_exit_code']!=0 or worker['slot']!=slot or checkpoint.get('runtime')!=binding
                or checkpoint.get('company_id')!=company or checkpoint.get('slot')!=slot
                or checkpoint.get('worker_pid')!=worker['pid'] or checkpoint.get('status')!='COMPLETED_SCORED'
                or checkpoint.get('result')!=result['result'] or checkpoint.get('retry_allowed') is not False):
            raise ValueError('Original company checkpoint/true exit/result differs')
        evidence.append(worker['checkpoint'])
        process_exit=engine.read(worker['process_exit_receipt'])
        if (process_exit.get('runtime')!=binding or process_exit.get('company_id')!=company
                or process_exit.get('true_exit_code')!=0 or process_exit.get('pid')!=worker['pid']
                or process_exit.get('worker_checkpoint')!=worker['checkpoint']):
            raise ValueError('Parent OS-exit receipt differs')
        evidence.append(worker['process_exit_receipt'])
        if rolling(value):
            closure=engine.read(worker['closure'])
            if (closure.get('runtime')!=binding or closure.get('company_id')!=company
                    or closure.get('checkpoint')!=worker['checkpoint'] or not closure.get('fees')
                    or closure.get('retry_allowed') is not False):raise ValueError('Rolling close receipt differs')
            evidence.append(worker['closure'])
        for path in sorted(Path(slot).glob('[0-9][0-9]-request.json')):
            request=engine.read(engine.pin(path));request_id=request['request_id']
            if request_id in requests:raise ValueError('Cross-company duplicate UUID')
            owner=engine.pin(root/'request-ownership'/(request_id+'.json'));record=engine.read(owner)
            if record!=dict(schema='earnings_clean_company_request_owner_v1',runtime=binding,
                    company_id=company,slot=slot,request_id=request_id,model=request['payload']['model'],
                    reserved_nano_usd=request['reserved_nano_usd'],retry_allowed=False):
                raise ValueError('Original slot/UUID/reservation owner differs')
            requests[request_id]=company;evidence.append(owner)
        for path in sorted(Path(slot).glob('*.company-send.json')):
            interval=engine.read(engine.pin(path));intent=engine.read(interval['intent'])
            if (interval.get('runtime')!=binding or interval.get('company_id')!=company
                    or interval.get('slot')!=slot or interval.get('worker_pid')!=worker['pid']
                    or interval.get('error_type') is not None
                    or interval['end_monotonic']<interval['start_monotonic']):
                raise ValueError('Original physical company interval differs')
            evidence.append(engine.pin(path))
            if interval['endpoint']=='/v1/responses':
                if requests.get(intent.get('budget_request_id'))!=company:
                    raise ValueError('Physical send UUID belongs to another company')
                intervals.append(interval)
    if {p.stem for p in (root/'request-ownership').glob('*.json')}!=set(requests):
        raise ValueError('Extra or missing owned request records')
    if len(intervals)!=len(requests):raise ValueError('Each generation needs one physical interval')
    active=set();maximum=0
    for _,kind,company in sorted((t,k,r['company_id']) for r in intervals
            for k,t in ((1,r['start_monotonic']),(0,r['end_monotonic']))):
        if kind:
            if company in active:raise ValueError('More than one physical generation per company')
            active.add(company);maximum=max(maximum,len(active))
        else:active.remove(company)
        if maximum>concurrency_limit(value):raise ValueError('Physical generation concurrency exceeds policy')
    return dict(evidence=evidence,peak_physical_generations=maximum,
        elapsed_seconds=batch['end_monotonic']-batch['start_monotonic'],
        sum_company_seconds=sum(engine.read(w['checkpoint'])['end_monotonic']-
            engine.read(w['checkpoint'])['start_monotonic'] for w in batch['workers']),
        comparison_qualification='Sum of company intervals is a serial-equivalent work proxy, not a matched serial rerun.')
