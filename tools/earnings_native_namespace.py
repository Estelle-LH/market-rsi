"""Owned durable Native state, separate from original financial run records.

These helpers are read-only. They neither admit data nor create a batch, and
the existing Native ancestry protections remain authoritative.
"""
from pathlib import Path
import re

from supervisor_harness.continuous_discovery_batch import _safe_root

NATIVE_RUNTIME_ROOT = Path.home() / 'Library/Application Support/MarketRSI/co-evo-earnings/episodes'


def _canonical(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or path.resolve() != path:
        raise ValueError('Canonical non-aliased owned path required')
    if any(p.exists() and not p.is_dir() for p in (path, *path.parents)):
        raise ValueError('Owned directory ancestry contains a non-directory')
    return path


def validate_native_root(episode_root, native_root, episode_id):
    """Validate an exact prospective namespace without weakening either guard."""
    if type(episode_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', episode_id) is None:
        raise ValueError('Bounded canonical episode ID required')
    episode, configured, native = map(_canonical, (episode_root, NATIVE_RUNTIME_ROOT, native_root))
    if (native != configured/episode_id or native == episode
            or native.is_relative_to(episode) or episode.is_relative_to(native)
            or any(part.casefold() in {'.codex', '.git', '.agents', 'worktrees'} for part in native.parts)):
        raise ValueError('Exact external episode-owned Native namespace required')
    # Production defaults are durable. Tests can bind a separate owned runtime
    # root in temporary storage; this does not change the original guard.
    _safe_root(native, allow_temporary=configured != Path.home() / 'Library/Application Support/MarketRSI/co-evo-earnings/episodes')
    return native


def native_paths(episode_root, episode_id):
    root = validate_native_root(episode_root, Path(NATIVE_RUNTIME_ROOT)/episode_id, episode_id)
    paths = {'native_root': root, 'source_root': root/'source',
             'registry_root': root/'versions', 'batch_root': root/'batch',
             'probe_root': root/'probe-scratch'}
    for path in paths.values():
        _canonical(path)
    return paths


def probe_paths(capacity, output_root):
    """Derive a fresh cold-copy namespace next to this owned Native registry.

    Existing test Native fixtures also use a private registry parent. No real
    batch or registry is relocated, recovered, or rewritten by this helper.
    """
    import hashlib
    output = _canonical(output_root)
    registry = _canonical(capacity.registry)
    parent = registry.parent
    if any(part.casefold() in {'.codex', '.git', '.agents'} for part in parent.parts):
        raise ValueError('Native scratch cannot use protected ancestry')
    root = parent/'probe-scratch'/hashlib.sha256(str(output).encode()).hexdigest()
    _canonical(root)
    _safe_root(root, allow_temporary=True)
    if root.exists() or root.is_symlink():
        raise ValueError('Consumed Native probe namespace stays closed')
    return {'native_root': root, 'batch_root': root/'cold-batch', 'registry_root': root/'cold-versions'}
