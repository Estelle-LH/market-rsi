"""One durable dispatch intent per key; uncertain acknowledgements never resend."""
import hashlib
import json
import os
from pathlib import Path
import re


class JournalError(ValueError):
    pass


class DispatchUnknown(JournalError):
    pass


def _root(root, key):
    root = Path(root)
    if (not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir()
            or root.stat().st_mode & 0o077 or type(key) is not str
            or re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', key) is None):
        raise JournalError('canonical private journal and bounded key required')
    return root


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _new(path, value):
    raw = _bytes(value)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def _read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise JournalError('bounded ordinary journal file required')
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _identity(value):
    return (type(value) is dict and set(value) == {'command_id', 'target'}
            and all(type(value[k]) is str and 0 < len(value[k]) <= 128 for k in value))


def submit_once(root, key, payload_sha256, submit):
    root = _root(root, key)
    if type(payload_sha256) is not str or re.fullmatch('[0-9a-f]{64}', payload_sha256) is None:
        raise JournalError('exact payload digest required')
    intent = {'schema': 'dispatch-intent-v1', 'key': key, 'payload_sha256': payload_sha256}
    pin = _new(root / (key + '.intent.json'), intent)  # Durable BEFORE submission.
    try:
        identity = submit()
        if not _identity(identity):
            raise JournalError('invalid acknowledgement identity')
        ack = {'schema': 'dispatch-ack-v1', 'key': key, 'intent_sha256': pin, **identity}
        _new(root / (key + '.ack.json'), ack)
    except Exception:
        raise DispatchUnknown('dispatch acknowledgement unknown; do not resend') from None
    return ack


def observe(root, key, query):
    root = _root(root, key)
    intent, pin = _read(root / (key + '.intent.json'))
    if (type(intent) is not dict or set(intent) != {'schema', 'key', 'payload_sha256'}
            or intent['schema'] != 'dispatch-intent-v1' or intent['key'] != key
            or type(intent['payload_sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', intent['payload_sha256']) is None):
        raise JournalError('invalid dispatch intent')
    path = root / (key + '.ack.json')
    if not path.exists() and not path.is_symlink():
        return {'status': 'ACK_UNKNOWN', 'terminal': False, 'success': False}
    ack, _ = _read(path)
    if (type(ack) is not dict or set(ack) != {'schema', 'key', 'intent_sha256', 'command_id', 'target'}
            or ack['schema'] != 'dispatch-ack-v1' or ack['key'] != key or ack['intent_sha256'] != pin
            or not _identity({k: ack[k] for k in ('command_id', 'target')})):
        raise JournalError('acknowledgement does not bind to original intent')
    value = query(ack['command_id'], ack['target'])
    allowed = {'Pending', 'InProgress', 'Delayed', 'Success', 'Failed', 'Cancelled',
               'Cancelling', 'TimedOut', 'Undeliverable', 'Terminated'}
    if (type(value) is not dict or set(value) != {'command_id', 'target', 'status', 'response_code'}
            or value['command_id'] != ack['command_id'] or value['target'] != ack['target']
            or value['status'] not in allowed or type(value['response_code']) is not int
            or value['status'] == 'Success' and value['response_code'] != 0):
        raise JournalError('command observation identity or status mismatch')
    terminal = value['status'] in {'Success', 'Failed', 'Cancelled', 'TimedOut', 'Undeliverable', 'Terminated'}
    return dict(value, terminal=terminal, success=value['status'] == 'Success')
