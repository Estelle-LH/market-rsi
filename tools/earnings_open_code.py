"""Generic code through the existing pinned Docker boundary, never host exec."""
import hashlib
import json
from pathlib import Path
import selectors
import subprocess
import time
import uuid

from earnings_http import save_bytes, strict_json
from earnings_open_guest import MAX_RESULT_BYTES
from minimal_prediction_loop.container_adapter import (
    DOCKER_CLI_SHA256, IMAGE, freeze_docker_client, _verify_docker_client,
)

GUEST = Path(__file__).with_name('earnings_open_guest.py')


class CandidateExecutionFailure(RuntimeError):
    """Known ordinary guest exception, with immutable evidence for a broker.

    This exact type is not permission to retry the failed source/input. Public
    diagnostic text remains candidate-controlled and untrusted.
    """
    def __init__(self, receipt):
        self.receipt = dict(receipt)
        super().__init__('Ordinary candidate exception; immutable receipt retained')


def start_marker(source_sha256):
    return ('market-rsi-candidate-start-v1:'+source_sha256+'\n').encode()


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def canonical(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise ValueError('Canonical non-aliased owned code root required')
    return path


class DockerRunner:
    def __init__(self, root, *, binding=None, timeout_seconds=20, max_calls=80,
                 control_run=subprocess.run, process_factory=subprocess.Popen):
        self.root = canonical(root)
        if (type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 30
                or type(max_calls) is not int or not 1 <= max_calls <= 256):
            raise ValueError('Bounded code time/call count required')
        self.root.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.root_identity = (self.root.stat().st_dev,self.root.stat().st_ino)
        self.guest_sha256 = hashlib.sha256(GUEST.read_bytes()).hexdigest()
        self.control, self.process = control_run, process_factory
        self.binding = binding or freeze_docker_client(expected_cli_sha256=DOCKER_CLI_SHA256)
        self.timeout, self.maximum, self.calls, self.blocked = timeout_seconds, max_calls, 0, False

    def _control(self, args):
        return self.control([self.binding.cli, *args], capture_output=True, text=True,
                            timeout=8, check=False, env=self.binding.environment_dict())

    def _remaining_container(self, name, token):
        result = self._control(['ps', '-a', '--filter', 'name=^/'+name+'$',
                                '--format', '{{.Names}}|{{.Label "market-rsi-open-run"}}'])
        if result.returncode != 0:
            raise RuntimeError('Owned container cleanup state unknown')
        rows = result.stdout.strip().splitlines()
        if rows and rows != [name+'|'+token]:
            raise RuntimeError('Container identity collision; do not remove')
        return bool(rows)

    def run(self, source, payload):
        if self.blocked or self.calls >= self.maximum:
            raise ValueError('Code runner closed or call budget exhausted')
        if type(source) is not str or not 1 <= len(source.encode()) <= 65_536:
            raise ValueError('Bounded nonempty candidate Python required')
        request = encoded({'source': source, 'payload': payload})
        if len(request) > 2_200_000:
            raise ValueError('Public code input byte budget exceeded')
        if (canonical(self.root)!=self.root or
                (self.root.stat().st_dev,self.root.stat().st_ino)!=self.root_identity):
            raise RuntimeError('Owned code root drift before execution')
        _verify_docker_client(self.binding, run=self.control)
        token = uuid.uuid4().hex
        name = 'market-rsi-open-'+token[:20]
        call = self.root/('call-'+token)
        call.mkdir(mode=0o700)
        self.calls += 1
        save_bytes(call/'input.json', request)
        guest = GUEST.read_bytes()
        if hashlib.sha256(guest).hexdigest()!=self.guest_sha256:
            raise RuntimeError('Trusted guest source drift before execution')
        command = [self.binding.cli, 'create', '--rm', '--pull', 'never', '--name', name,
            '-i', '--label', 'market-rsi-open-run='+token, '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--ipc', 'none',
            '--pids-limit', '32', '--memory', '512m', '--cpus', '1', '--user', '65534:65534',
            '--log-driver', 'none', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=64m', IMAGE,
            '/usr/bin/env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/nonexistent',
            'LANG=C.UTF-8', 'PYTHONDONTWRITEBYTECODE=1', 'PYTHONHASHSEED=0',
            '/usr/local/bin/python', '-I', '-B', '-u', '-c', guest.decode()]
        intent = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'input_sha256': hashlib.sha256(request).hexdigest(), 'image': IMAGE,
            'guest_sha256': hashlib.sha256(guest).hexdigest(), 'command': command,
            'docker': self.binding.public_receipt(), 'timeout_seconds': self.timeout,
            'container_name': name, 'container_token': token, 'retry_allowed': False,
            'start_command': [self.binding.cli, 'start', '-a', '-i', name]}
        save_bytes(call/'intent.json', encoded(intent))
        process, output, error, failed = None, bytearray(), bytearray(), None
        candidate_diagnostic = None
        started = time.monotonic()
        try:
            if self._remaining_container(name, token):
                raise RuntimeError('New owned container name already exists')
            created = self._control(command[1:])
            save_bytes(call/'create.stdout', created.stdout.encode()[:65_536])
            save_bytes(call/'create.stderr', created.stderr.encode()[:65_536])
            if created.returncode or not self._remaining_container(name, token):
                raise RuntimeError('Owned container creation failed before execution')
            with (call/'input.json').open('rb') as stdin:
                process = self.process(intent['start_command'], stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=self.binding.environment_dict(), start_new_session=True)
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stderr, selectors.EVENT_READ, error)
                    selector.register(process.stdout, selectors.EVENT_READ, output)
                    while selector.get_map():
                        if time.monotonic()-started >= self.timeout:
                            raise TimeoutError('Candidate exceeded its wall time')
                        for key, _ in selector.select(min(.1, self.timeout)):
                            data = key.fileobj.read1(8192)
                            if not data:
                                selector.unregister(key.fileobj)
                                continue
                            remaining = (MAX_RESULT_BYTES+1 if key.data is output else 65_536)-len(key.data)
                            key.data.extend(data[:remaining])
                            if len(data) > remaining:
                                raise ValueError('Candidate output byte limit exceeded')
                process.wait(timeout=max(.01, self.timeout-(time.monotonic()-started)))
            value = strict_json(output)
            if (process.returncode==2 and type(value) is dict
                    and set(value)=={'ok','candidate_exception'} and value['ok'] is False):
                detail = value['candidate_exception']
                if (type(detail) is dict and set(detail)=={'error_type','message','source_line'}
                        and type(detail['error_type']) is str and 1<=len(detail['error_type'])<=80
                        and detail['error_type'] not in {'KeyboardInterrupt','SystemExit','GeneratorExit'}
                        and type(detail['message']) is str and len(detail['message'])<=512
                        and all(c.isprintable() for c in detail['message'])
                        and (detail['source_line'] is None or type(detail['source_line']) is int
                             and 1<=detail['source_line']<=len(source.splitlines()))):
                    candidate_diagnostic = dict(detail)
                    raise ValueError('Guest reported an ordinary candidate exception')
            if (process.returncode != 0 or type(value) is not dict
                    or set(value) != {'ok', 'value'} or value['ok'] is not True):
                raise ValueError('Candidate failed or returned an invalid protocol')
        except BaseException as exception:
            failed = exception
        finally:
            cleanup, integrity = False, False
            try:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=2)
                if self._remaining_container(name, token):
                    removed = self._control(['rm', '-f', name])
                    if removed.returncode or self._remaining_container(name, token):
                        raise RuntimeError('Owned container cleanup failed')
                cleanup = True
            except BaseException as exception:
                cleanup, self.blocked = False, True
                failed = failed or exception
            finally:
                if process is not None:
                    for stream in (process.stdout,process.stderr):
                        try:
                            if stream is not None: stream.close()
                        except BaseException as exception:
                            cleanup,self.blocked = False,True
                            failed = failed or exception
            try:
                _verify_docker_client(self.binding,run=self.control)
                data_path = call/'input.json'
                intent_path = call/'intent.json'
                if (canonical(self.root)!=self.root or
                        (self.root.stat().st_dev,self.root.stat().st_ino)!=self.root_identity or
                        GUEST.read_bytes()!=guest or data_path.resolve()!=data_path or
                        not data_path.is_file() or data_path.read_bytes()!=request or
                        intent_path.resolve()!=intent_path or not intent_path.is_file() or
                        intent_path.read_bytes()!=encoded(intent)):
                    raise RuntimeError('Host-owned source/input/root drift after execution')
                integrity = True
            except BaseException as exception:
                self.blocked = True
                failed = failed or exception
            execution_started = bytes(error).startswith(start_marker(intent['source_sha256']))
            recoverable = (candidate_diagnostic is not None and type(failed) is ValueError
                           and execution_started and cleanup and integrity)
            save_bytes(call/'stdout.bin', bytes(output))
            save_bytes(call/'stderr.bin', bytes(error))
            receipt = dict(intent, status='COMPLETED' if failed is None else 'FAILED_NO_RETRY',
                exit_code=None if process is None else process.returncode, cleanup_verified=cleanup,
                error_type=None if failed is None else type(failed).__name__,
                failure_classification=('RECOVERABLE_GUEST_EXCEPTION' if recoverable
                    else 'FATAL_EXECUTION_FAILURE' if failed is not None else None),
                execution_started=execution_started, source_integrity_verified=integrity,
                candidate_diagnostic=candidate_diagnostic if recoverable else None,
                wall_seconds=time.monotonic()-started, host_candidate_execution=False,
                stdout_sha256=hashlib.sha256(output).hexdigest(),
                stderr_sha256=hashlib.sha256(error).hexdigest())
            save_bytes(call/'result.json', encoded(receipt))
        if failed is not None:
            if recoverable:
                raise CandidateExecutionFailure({'path':str(call/'result.json'),
                    'sha256':hashlib.sha256((call/'result.json').read_bytes()).hexdigest()}) from failed
            if not isinstance(failed,Exception):
                raise failed
            raise RuntimeError('Isolated code failed once; inspect '+str(call)) from failed
        return {'value': value['value'], 'receipt': {'path': str(call/'result.json'),
                'sha256': hashlib.sha256((call/'result.json').read_bytes()).hexdigest()}}
