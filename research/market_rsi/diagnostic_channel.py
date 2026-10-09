"""Sequential channel with candidate-only stderr preserved, never a score.

Same exchange/cleanup semantics as the frozen canary channel. Production uses
this only inside E2B with the existing endpoint's 10 MiB hard RLIMIT_FSIZE and
exact whole-sandbox cleanup. It is not a standalone OS isolation boundary.
Local tests launch human-authored fixtures only, never generated candidate code.
"""
import hashlib
import os
from pathlib import Path
import stat
import subprocess

from prediction_stream import LineChannel


MAX_STDERR_BYTES = 10 * 1024 * 1024


def stderr_receipt(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("symlink stderr file")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_STDERR_BYTES:
        raise ValueError("stderr exceeds the fixed endpoint file limit")
    with path.open("rb") as stream:
        raw = stream.read(MAX_STDERR_BYTES + 1)
    after = path.stat()
    if (len(raw) > MAX_STDERR_BYTES or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns or len(raw) != before.st_size):
        raise ValueError("candidate stderr changed during read")
    try:
        text, encoding = raw.decode(), "utf-8"
    except UnicodeDecodeError:
        text, encoding = raw.decode("utf-8", "replace"), "utf-8-replace; original bytes preserved separately"
    return {"origin": "candidate_controlled_stderr", "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "encoding": encoding, "text": text,
            "truncated": False, "independent_diagnosis": False}


class DiagnosticLineChannel(LineChannel):
    def __init__(self, command, cwd, stderr_path, max_response_bytes=16384):
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ValueError("positive response bound required")
        self.limit, self.events, self.closed = max_response_bytes, [], False
        self.stderr_path = Path(stderr_path)
        fd = os.open(self.stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.stderr_stream = os.fdopen(fd, "wb")
        try:
            self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.stderr_stream, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                start_new_session=True, bufsize=0)
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
        except BaseException:
            self.stderr_stream.close()
            raise

    def close(self):
        try:
            super().close()
        finally:
            if not self.stderr_stream.closed:
                self.stderr_stream.flush()
                os.fsync(self.stderr_stream.fileno())
                self.stderr_stream.close()

    def diagnostic(self):
        if not self.closed or self.process.poll() is None or not self.stderr_stream.closed:
            raise ValueError("close/reap before inspecting candidate diagnostics")
        return stderr_receipt(self.stderr_path)
