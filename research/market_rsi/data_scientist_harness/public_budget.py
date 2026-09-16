"""Durable body-read reservations. Unknown attempts retain their full bound.

Not a network bill: excludes HTTP headers, TLS and lower-level buffering.
The broker owns its workspace lock, and this journal also serializes transports.
"""
import hashlib
import os
from pathlib import Path

from market_rsi import Journal, digest
from data_scientist_harness import literature

UPPER = literature.MAX_BYTES + 1  # Includes the single-byte oversize probe.


class PublicBudget:
    def __init__(self, root, cap, manifest_sha256):
        self.root = Path(root)
        if self.root.is_symlink(): raise ValueError('public ledger symlink')
        self.root.mkdir(exist_ok=True)
        fd = os.open(self.root.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
        if type(cap) is not int or cap < 0: raise ValueError('invalid public byte cap')
        self.cap, self.manifest = cap, manifest_sha256
        for name in ('journal.jsonl', '.lock'):
            if (self.root/name).is_symlink(): raise ValueError('public ledger symlink')
        self.journal = Journal(self.root)

    def _state(self):
        rows = self.journal.read()
        binding = {'cap': self.cap, 'manifest_sha256': self.manifest, 'per_request_upper': UPPER}
        if not rows:
            self.journal.append('authorized', binding)
            fd = os.open(self.root, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
            rows = self.journal.read()
        if rows[0]['event'] != 'authorized' or rows[0]['payload'] != binding:
            raise ValueError('public ledger binding changed')
        jobs = {}
        for row in rows[1:]:
            p = row['payload']; key = p['id']
            if row['event'] == 'reserved':
                if key in jobs or p['upper'] != UPPER: raise ValueError('duplicate/invalid public reserve')
                jobs[key] = {'charged_bytes': UPPER, 'state': 'reserved'}
            elif row['event'] == 'settled':
                if key not in jobs or jobs[key]['state'] != 'reserved': raise ValueError('invalid public settlement')
                n = p['body_bytes']
                if type(n) is not int or not 0 <= n <= UPPER: raise ValueError('invalid actual body bytes')
                jobs[key] = {'charged_bytes': n, 'state': 'settled'}
            else: raise ValueError('unknown public ledger event')
        used = sum(j['charged_bytes'] for j in jobs.values())
        if used > self.cap: raise ValueError('public body cap exceeded')
        return jobs, used

    def snapshot(self):
        with self.journal.locked():
            jobs, used = self._state()
            return {'body_cap_bytes': self.cap, 'charged_or_reserved_bytes': used,
                    'pending_attempts': sum(j['state'] == 'reserved' for j in jobs.values()),
                    'attempts': len(jobs), 'scope': 'application_body_reads_not_network_invoice'}

    def fetch(self, url, transport):
        literature.public_url(url)  # Denied URL/arguments never reserve or dispatch.
        with self.journal.locked():
            jobs, used = self._state()
            if used + UPPER > self.cap:
                raise RuntimeError('public-literature body-byte reservation cap; no implicit expansion')
            key = f'fetch-{len(jobs)+1:06d}'
            self.journal.append('reserved', {'id': key, 'upper': UPPER, 'url_sha256': digest(url)})
            # A kill/timeout/HTTP failure or bad receipt leaves this durable upper.
            raw, receipt = transport(url)
            if (not isinstance(raw, bytes) or len(raw) > literature.MAX_BYTES
                or receipt.get('body_bytes') != len(raw)
                or receipt.get('body_sha256') != hashlib.sha256(raw).hexdigest()
                or receipt.get('requested_url') != url):
                raise ValueError('public-read metering receipt mismatch')
            self.journal.append('settled', {'id': key, 'body_bytes': len(raw),
                                           'receipt_sha256': digest(receipt)})
            return raw, {**receipt, 'public_budget_attempt': key,
                         'charged_or_reserved_bytes_after': used + len(raw)}
