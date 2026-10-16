"""Trusted JSON guest bootstrap, executed ONLY inside the restricted container."""
import contextlib
import hashlib
import json
import resource
import sys

MAX_RESULT_BYTES = 131_072

def diagnostic(error):
    """Candidate-only bounded text/line; never serialize a host traceback."""
    line, frame = None, error.__traceback__
    while frame is not None:
        if frame.tb_frame.f_code.co_filename == '<research-candidate>':
            line = frame.tb_lineno
        frame = frame.tb_next
    if isinstance(error, SyntaxError) and error.filename == '<research-candidate>':
        line = error.lineno
    try:
        message = ''.join(c if c.isprintable() else ' ' for c in str(error))[:512]
    except Exception:
        message = 'Candidate exception message unavailable'
    return {'error_type':type(error).__name__[:80], 'message':message, 'source_line':line}


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1_048_576, 1_048_576))
    candidate_phase = False
    try:
        raw = sys.stdin.buffer.read(2_200_001)
        if len(raw) > 2_200_000:
            raise ValueError('Guest input limit')
        request = json.loads(raw)
        if set(request) != {'source', 'payload'} or type(request['source']) is not str:
            raise ValueError('Exact code/input protocol required')
        namespace = {'__name__': 'research_candidate'}
        # A Docker CLI process alone does not establish candidate execution.
        # Flush this trusted-bootstrap marker before compile/exec.
        sys.stderr.write('market-rsi-candidate-start-v1:'+
                         hashlib.sha256(request['source'].encode()).hexdigest()+'\n')
        sys.stderr.flush()
        with contextlib.redirect_stdout(sys.stderr):
            candidate_phase = True
            exec(compile(request['source'], '<research-candidate>', 'exec'), namespace)
            candidate_phase = False
            if not callable(namespace.get('run')):
                raise ValueError('Candidate must define run(payload)')
            candidate_phase = True
            value = namespace['run'](request['payload'])
            candidate_phase = False
        encoded = json.dumps({'ok': True, 'value': value}, allow_nan=False)
        if len(encoded.encode()) > MAX_RESULT_BYTES:
            raise ValueError('Guest result limit')
        print(encoded)
    except BaseException as error:
        if candidate_phase and isinstance(error,Exception):
            print(json.dumps({'ok':False,'candidate_exception':diagnostic(error)},allow_nan=False))
        else:
            # Control interrupts, input/bootstrap and output-protocol failures
            # are not normal candidate exceptions and cannot be recovered.
            print(json.dumps({'ok': False, 'error_type': type(error).__name__}))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
