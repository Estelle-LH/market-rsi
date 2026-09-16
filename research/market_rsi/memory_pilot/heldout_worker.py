"""Packaged runner-only later-data operation; never exposed as a researcher tool."""
import json
import os
from pathlib import Path
import resource
import signal
import time
from memory_materialize import CacheProfile,write_cache
from single_object_stream import stream_object
from market_rsi import fresh_json


def run(spec):
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    def stop(*_):raise TimeoutError('held-out materialization deadline')
    signal.signal(signal.SIGALRM,stop);signal.signal(signal.SIGTERM,stop);signal.alarm(590)
    def emit(v):print(json.dumps(v,sort_keys=True,allow_nan=False),flush=True)
    start=time.monotonic();failure=None;t=h=None;p=CacheProfile(spec['contract'],spec['day_start_ms'])
    output=Path(spec['output']);output.parent.mkdir(parents=True,exist_ok=True)
    fresh_json(output.with_suffix('.claim.json'),dict(spec=spec,pid=os.getpid()))
    emit(dict(stage='started',pid=os.getpid(),date=spec['date'],role=spec['role']))
    def consume(line,n):
        p.consume(line,n)
        if n%100000==0:emit(dict(stage='decode',records=n,elapsed_seconds=time.monotonic()-start))
    try:
        t=stream_object(spec['path'],advertised_bytes=spec['compressed_bytes'],max_input_bytes=spec['compressed_bytes'],
            max_decoded_bytes=2147483648,wall_seconds=570,consume=consume,decoder_memory_bytes=256*1024**2)
        if not t['complete']:raise ValueError('incomplete source')
        h=write_cache(p,output,lambda a,b:emit(dict(stage='samples',entities_done=a,entities_total=b)))
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc)[:500])
    finally:signal.alarm(0)
    emit(dict(stage='terminal',report=dict(schema='memory_heldout_materialize_v1',complete=failure is None,
        failure=failure,transport=t,header=h,spec=spec,elapsed_seconds=time.monotonic()-start,
        fits=0,provider_calls=0,raw_rows_exported=0,role=spec['role'],controller_access=False)))


if __name__=='__main__':run(SPEC)
