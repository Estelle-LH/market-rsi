"""Exact historical source labels, never a filesystem relocation fallback.

Old source receipts keep their original tmp label. Authenticated historical
Readers obtain only their registered Git blobs from the active repository;
data, model programs, receipts and current source admission do not use this.
"""
from pathlib import Path, PurePosixPath
import re

LEGACY_REPO = Path('/private/tmp/market-rsi-earnings-overnight-FGRfBI/checkout')
RUNTIME_NAME = 'benchmarks/edgar_forecast/openai_runtime.json'
RUNTIME_SHA256 = '6327387abaeea7ecf3d2f86a3f5be8a7f300b0056d784206284defc8d24bce8b'


def source_name(path, repo):
    """Return an exact source-relative Git name without touching old paths."""
    text = str(path)
    value = PurePosixPath(text)
    if (not value.is_absolute() or str(value) != text or '..' in value.parts
            or not isinstance(repo, Path)):
        raise ValueError('Exact lexical historical source path required')
    for root in (Path(repo), LEGACY_REPO):
        if value != root and value.is_relative_to(root):
            return str(value.relative_to(root))
    raise ValueError('Historical source outside exact current or original checkout')


def bindings(sources, repo):
    """Validate one original runtime's complete single-root source namespace."""
    if type(sources) is not dict or not sources:
        raise ValueError('Nonempty original historical source bindings required')
    result, roots = set(), set()
    for bound in sources.values():
        if (type(bound) is not dict or set(bound) != {'path', 'sha256'}
                or type(bound['path']) is not str or type(bound['sha256']) is not str
                or re.fullmatch('[0-9a-f]{64}', bound['sha256']) is None):
            raise ValueError('Exact original historical source binding required')
        name = source_name(bound['path'], repo)
        roots.add(str(PurePosixPath(bound['path']).parents[len(PurePosixPath(name).parts)-1]))
        result.add((bound['path'], bound['sha256']))
    if len(roots) != 1:
        raise ValueError('Mixed historical source checkout namespaces refused')
    return result


def runtime_metadata(bound, repo):
    """Only the fixed original runtime JSON may supplement registered code."""
    return (bound['sha256'] == RUNTIME_SHA256
            and source_name(bound['path'], repo) == RUNTIME_NAME)
