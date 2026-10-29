"""Normalize only the OS header byte of a known zero-mtime level9 GZIP writer.

Payload authentication remains the caller's independent archive/manifest SHA.
No compression, Source data rewriting or validator/installer bound changes.
"""
def canonical_gzip_os(archive):
    if type(archive) is not bytes or len(archive)<18 or archive[:9]!=bytes.fromhex('1f8b08000000000002'):
        raise ValueError('known zero-mtime level9 GZIP writer format required')
    return archive[:9]+b'\xff'+archive[10:]
