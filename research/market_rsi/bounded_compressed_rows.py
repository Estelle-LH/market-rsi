"""Lossless deterministic gzip with separate logical and stored-byte guards."""
import gzip

from market_rsi import canonical


class ByteBound:
    def __init__(self, file, limit):
        self.file=file;self.limit=limit;self.count=0

    def write(self, value):
        if self.count+len(value)>self.limit:raise ValueError('compressed stored-byte cap exceeded')
        n=self.file.write(value);self.count+=n
        return n

    def flush(self):self.file.flush()


class CompressedRows:
    def __init__(self, path, *, max_logical_bytes, max_stored_bytes):
        if type(max_logical_bytes) is not int or type(max_stored_bytes) is not int or min(max_logical_bytes,max_stored_bytes)<=0:
            raise ValueError('positive integer storage guards required')
        self.file=path.open('xb')
        self.bound=ByteBound(self.file,max_stored_bytes)
        self.gzip=gzip.GzipFile(filename='',mode='wb',fileobj=self.bound,mtime=0,compresslevel=6)
        self.logical=0;self.rows=0;self.limit=max_logical_bytes

    def write_row(self, row):
        data=(canonical(row)+'\n').encode()
        if self.logical+len(data)>self.limit:raise ValueError('logical-byte cap exceeded; no row truncation accepted')
        self.gzip.write(data);self.logical+=len(data);self.rows+=1

    def __enter__(self):return self

    def __exit__(self, *args):
        try:self.gzip.close()
        finally:self.file.close()

