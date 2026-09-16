"""Consumer-owned pin for a local, reviewed subset of the shared core.

Never import from another checkout or silently upgrade/fall back. Old frozen
workspaces keep their original code; a new workspace freezes this dependency.
"""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/Estelle-LH/data-scientist-harness"
REVISION = "df963b02f8e1fae7db4f4d99d34507e1f339b416"
CORE_FILES = {
    "__init__.py": "206574586e94a459948a9e405da65629f29c27497feae9cc417869b9fd08e5d7",
    "feature_batch.py": "18aba45dc4628ddf2720ec5aaea755659debd23f5d7abc0bd681f3e2c4726037",
    "moments.py": "ceb081786a6863b6a9a758894ed26149c35fd73de3128390cda148226a7024e6",
    "quality_checks.py": "b26ed43ef6261e34f277ef2f5a0d34aedbeac060e1fab7fd7be94efd0c626f9c",
    "research_gate.py": "b838d2caa64c6ad30cca9330f99952f64a5859fded1d1e2b7d9d931928b121a6",
}


def dependency_identity():
    directory = ROOT / "ds_harness_core"
    if directory.is_symlink() or directory.resolve() != directory:
        raise ValueError("shared core must be resident in this consumer snapshot")
    for name, expected in CORE_FILES.items():
        path = directory / name
        if (path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError(f"pinned shared core changed or missing: {name}")
    spec = importlib.util.find_spec("ds_harness_core")
    if spec is None or spec.origin != str(directory / "__init__.py"):
        raise ValueError("shared core import resolves outside this consumer snapshot")
    for name in CORE_FILES:
        qualified = "ds_harness_core" + ("." + name[:-3] if name != "__init__.py" else "")
        module = sys.modules.get(qualified)
        if module is not None and getattr(module, "__file__", None) != str(directory / name):
            raise ValueError("loaded shared core resolves outside this consumer snapshot")
    return {"repository": REPOSITORY, "revision": REVISION,
            "delivery": "consumer_local_source_subset", "files": dict(CORE_FILES),
            "active_api": "moments_and_guarded_research", "feature_batch_adapter_adopted": "explicit_grid_adapter",
            "upstream_release_status": "explicit_prerelease_commit"}


def load_moments():
    dependency_identity()  # Check source and origin BEFORE executing the dependency.
    return importlib.import_module("ds_harness_core.moments").moments
