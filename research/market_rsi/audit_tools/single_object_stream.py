"""Bounded one-pass compressed identity + decoded-line transport, no finance rules.

Reuses the project's streamed SHA256, line limits, stat checks and owned-decoder
cleanup. Unlike the old audit it hashes while feeding the decoder, not in a
separate raw-file pass. Caller must validate the exact controller-selected path
and limits, set OS wall/address-space limits and supply its reviewed processor.
"""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import threading
import time


def signature(s):
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def open_source(path, advertised_bytes, max_input_bytes):
    path=Path(path)
    if (not path.is_absolute() or path.resolve()!=path or path.is_symlink()
            or type(advertised_bytes) is not int or not 0<advertised_bytes<=max_input_bytes):
        raise ValueError('canonical bounded source required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size!=advertised_bytes
                or signature(path.stat())!=signature(before)):
            raise ValueError('source type/size/identity mismatch')
        return os.fdopen(fd,'rb'),before
    except BaseException:
        os.close(fd);raise


def stream_object(path, *, advertised_bytes, max_input_bytes, max_decoded_bytes,
                  wall_seconds, consume, decoder_command=('zstd','-dc'), max_line_bytes=1024*1024,
                  decoder_memory_bytes=None):
    if (any(type(x) is not int or x<=0 for x in (max_input_bytes,max_decoded_bytes,wall_seconds,max_line_bytes))
            or not decoder_command):raise ValueError('positive explicit transport limits required')
    if decoder_memory_bytes is not None and (type(decoder_memory_bytes) is not int or decoder_memory_bytes<=0):
        raise ValueError('positive decoder address-space limit required')
    began=time.monotonic();deadline=began+wall_seconds
    stream,before=open_source(path,advertised_bytes,max_input_bytes)
    source_hash=hashlib.sha256();decoded_hash=hashlib.sha256()
    source_bytes=decoded_bytes=rows=0;feeder_error=[];stop=threading.Event()
    process=None;feeder=None;code=None;complete=False;error=None
    def feed():
        nonlocal source_bytes
        try:
            while not stop.is_set():
                if time.monotonic()>deadline:raise TimeoutError('input deadline')
                block=stream.read(min(65536,max_input_bytes-source_bytes+1))
                if not block:break
                source_bytes+=len(block)
                if source_bytes>max_input_bytes:raise ValueError('compressed byte limit')
                source_hash.update(block);process.stdin.write(block)
        except BaseException as exc:feeder_error.append(type(exc).__name__)
        finally:
            try:process.stdin.close()
            except (BrokenPipeError,OSError):pass
    try:
        def decoder_limit():
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(decoder_memory_bytes,decoder_memory_bytes))
        # No thread exists yet; production Linux runner divides its memory cap
        # between itself and this decoder instead of granting each the full cap.
        process=subprocess.Popen(list(decoder_command),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            preexec_fn=decoder_limit if decoder_memory_bytes is not None else None)
        feeder=threading.Thread(target=feed,daemon=True);feeder.start()
        while True:
            if time.monotonic()>deadline:raise TimeoutError('decode deadline')
            line=process.stdout.readline(min(max_line_bytes+1,max_decoded_bytes-decoded_bytes+1))
            if not line:break
            decoded_bytes+=len(line)
            if decoded_bytes>max_decoded_bytes or len(line)>max_line_bytes:raise ValueError('decoded line/byte limit')
            decoded_hash.update(line);rows+=1;consume(line,rows)
        code=process.wait(timeout=max(0.01,deadline-time.monotonic()))
        feeder.join(timeout=2)
        if feeder.is_alive() or feeder_error or code!=0:raise ValueError('decoder/feed incomplete')
        if source_bytes!=advertised_bytes:raise ValueError('input byte count differs')
        if signature(os.fstat(stream.fileno()))!=signature(before) or signature(Path(path).stat())!=signature(before):
            raise ValueError('source changed during read')
        complete=True
    except BaseException as exc:error=type(exc).__name__
    finally:
        stop.set()
        if process is not None:
            if process.poll() is None:process.terminate()
            try:code=process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();code=process.wait(timeout=3)
            if feeder is not None:feeder.join(timeout=3)
            process.stdout.close()
        stream.close()
    feeder_reaped=feeder is None or not feeder.is_alive()
    if not feeder_reaped:complete=False;error='FeederCleanupFailure'
    return {'schema':'single_object_stream_v1','complete':complete,'failure_type':error,
        'compressed_bytes_read':source_bytes,'compressed_sha256':source_hash.hexdigest(),
        'compressed_hash_is_complete':complete,'decoded_bytes':decoded_bytes,'decoded_sha256':decoded_hash.hexdigest(),
        'decoded_records':rows,'decoder_exit_code':code,'decoder_reaped':process is None or process.poll() is not None,
        'feeder_reaped':feeder_reaped,'feeder_errors':feeder_error,'elapsed_seconds':time.monotonic()-began,
        'source_initial_stat':dict(zip(('device','inode','bytes','mtime_ns','ctime_ns'),signature(before))),
        'source_unchanged_verified':complete,'source_open_passes':1,'raw_rows_exported':0,
        'decoder_address_space_limit_bytes':decoder_memory_bytes,
        'source_admitted':False,'capture_provenance_attested':False,'fits':0,'provider_calls':0,
        'partial_diagnostic_only':not complete}
