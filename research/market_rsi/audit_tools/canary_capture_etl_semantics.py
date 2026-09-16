"""Synthetic checks of four already-reviewed functions from the current D10 ETL.

Reads code only, never capture rows. Extracts just the reviewed function ASTs;
does not execute the ETL module, its main, filesystem readers or HTTP resolver.
The artifact reports behavior, NOT historical incidence or source admission.
"""
import argparse
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

EXPECTED='584c7682d9d6ed331bc192da31e75890b7fc4158f4082137f2e2c028b6b1bf8b'
NAMES={'iso','emit_tob','write_depth','run_polymarket'}


class Writer:
    def __init__(self):self.records=[]
    def writerow(self,row):self.records.append(row)


class MemoryOut:
    def __init__(self):self.writers={}
    def csv(self,name,header):return self.writers.setdefault(name,Writer())


def run_checks(source):
    if hashlib.sha256(source).hexdigest()!=EXPECTED:raise ValueError('reviewed ETL source changed')
    tree=ast.parse(source)
    selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
    if {n.name for n in selected}!=NAMES or len(selected)!=len(NAMES):raise ValueError('reviewed functions missing')
    code=compile(ast.Module(body=selected,type_ignores=[]),'<reviewed-etl-functions>','exec')
    def rest(t,bid='0.4',ask='0.6'):
        return {'t':t,'src':'rest','m':{'asset_id':'fixture-a','bids':[{'price':bid,'size':'2'}],
            'asks':[{'price':ask,'size':'3'}]}}
    def delta(t,side='BUY',price='0.4',size='4'):
        return {'t':t,'src':'ws','m':{'event_type':'price_change','market':'fixture-m',
            'price_changes':[{'asset_id':'fixture-a','price':price,'size':size,'side':side}]}}
    book={'t':0,'src':'ws','m':{'event_type':'book','market':'fixture-m',**rest(0)['m']}}
    anchored=rest(0);anchored['m']['asks'].append({'price':'0.8','size':'3'})
    changes=delta(1000,'BUY','0.7','2')
    changes['m']['price_changes'].append(delta(1000,'SELL','0.6','0')['m']['price_changes'][0])
    cases=[('rest_snapshot_only',[rest(0)],0,0),
        ('websocket_book_then_delta',[book,delta(1000)],0,0),
        ('empty_ask_invalidation_not_emitted',[rest(0),delta(1000),delta(2000,'SELL','0.6','0')],1,0),
        ('rest_reanchor_not_emitted',[rest(0),delta(1000),rest(2000,'0.8','0.9')],1,0),
        ('one_frame_transient_cross_before_uncrossed_final_state',[anchored,changes],2,1)]
    results=[]
    for name,frames,expected_rows,expected_crossed in cases:
        ns={'datetime':datetime,'timezone':timezone,'glob':SimpleNamespace(glob=lambda p:['fixture']),
            'rows':lambda p:iter(frames),'TOB_HEADER':[],'TRADE_HEADER':[],'DEPTH_HEADER':[]}
        exec(code,ns);out=MemoryOut()
        ns['run_polymarket']('/unused','2026-01-01',out,60,{},set())
        observed=len(out.writers['topofbook'].records)
        crossed=sum(float(r[5])>float(r[7]) for r in out.writers['topofbook'].records)
        results.append({'case':name,'synthetic_input_frames':len(frames),'observed_quote_rows':observed,
            'observed_crossed_quote_rows':crossed,
            'source_behavior_reproduced':observed==expected_rows and crossed==expected_crossed})
    return {'schema':'capture_etl_semantics_canary_v1','etl_source_sha256':EXPECTED,
        'functions_executed':sorted(NAMES),'evidence_mode':'synthetic_code_behavior',
        'cases':results,'all_expected_behaviors_reproduced':all(r['source_behavior_reproduced'] for r in results),
        'real_market_rows_read':0,'source_mutated':False,'source_admitted':False,'fits':0,
        'historical_error_frequency_proven':False,
        'limitations':['Current source only; not a replay of actual historical messages.',
            'Omitted CSV states are unsafe for unrestricted forward fill; actual downstream incidence remains unmeasured.',
            'No target, exclusion, horizon, trainer or source pass is chosen by this check.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--remote',action='store_true')
    p.add_argument('--output',type=Path);a=p.parse_args()
    if a.remote:
        print(json.dumps(run_checks(Path('/opt/d10/bin/etl.py').read_bytes())));sys.exit(0)
    if not a.output or a.output.exists():raise ValueError('fresh output required')
    response=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',
        'timeout 30s python3 - --remote'],input=Path(__file__).read_bytes(),capture_output=True,timeout=45)
    if response.returncode or len(response.stdout)>100_000:raise RuntimeError('synthetic ETL check failed')
    value=json.loads(response.stdout)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from market_rsi import fresh_json,digest,file_hash
    value['canary_reader_sha256']=file_hash(__file__);value['result_sha256']=digest(value)
    a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,value)
    print(json.dumps(value))
