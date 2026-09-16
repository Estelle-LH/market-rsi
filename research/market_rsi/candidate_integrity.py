"""Static, fail-closed integrity checks for controller-written predictors.

The candidate still runs inside the independent E2B sandbox.  This check is a
separate control-plane gate: it rejects files that are not recognizably a small
fit/predict program, contain control-language payloads, import unsafe modules,
or carry unused module-level metadata.  It does not judge scientific merit.
"""
from __future__ import annotations

import ast
import hashlib
import re

from market_rsi import digest


SCHEMA = "market_controller_candidate_integrity_v1"
MAX_SOURCE_BYTES = 131_072
MAX_DOCSTRING_CHARS = 4_096
MAX_STRING_CHARS = 512

SAFE_IMPORT_ROOTS = {
    "bisect", "collections", "decimal", "fractions", "functools", "heapq",
    "itertools", "math", "operator", "statistics",
}
DANGEROUS_CALLS = {
    "__import__", "breakpoint", "compile", "eval", "exec", "globals",
    "input", "locals", "open", "vars",
}
DANGEROUS_ATTRIBUTES = {
    "connect", "fork", "getenv", "popen", "remove", "request", "rmdir",
    "spawn", "system", "unlink", "urlopen", "write_bytes", "write_text",
}
CONTROL_LANGUAGE = (
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"hidden[\s_-]*reward",
        r"self[\s_-]*prompt",
        r"system[\s_-]*prompt",
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions?",
        r"proof[\s_-]*obligation",
        r"archive[\s_-]*disclosure",
        r"jailbreak",
        r"password[\s_-]*(charset|secret|value)?",
        r"api[\s_-]*key",
        r"credential(s)?",
        r"\benemy\b",
    )
)
CONTROL_LANGUAGE = tuple(CONTROL_LANGUAGE)


def policy_contract() -> dict:
    payload = {
        "schema": SCHEMA,
        "required_functions": {"fit": 2, "predict": 2},
        "safe_import_roots": sorted(SAFE_IMPORT_ROOTS),
        "dangerous_calls": sorted(DANGEROUS_CALLS),
        "dangerous_attributes": sorted(DANGEROUS_ATTRIBUTES),
        "module_assignments": "used_uppercase_immutable_constants_only",
        "top_level_executable_statements": False,
        "control_language_patterns": [item.pattern for item in CONTROL_LANGUAGE],
        "scientific_merit_verified": False,
    }
    return {**payload, "policy_sha256": digest(payload)}


def _plain_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (type(None), bool, int, float, str))
    if isinstance(node, (ast.Tuple, ast.List)):
        return len(node.elts) <= 128 and all(_plain_constant(item) for item in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return isinstance(node.operand, ast.Constant) and isinstance(
            node.operand.value, (int, float)
        )
    return False


def _function_signature(tree: ast.Module, name: str, arguments: int) -> None:
    matches = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError(f"candidate must define exactly one {name} function")
    node = matches[0]
    positional = node.args.posonlyargs + node.args.args
    if (len(positional) != arguments or node.args.kwonlyargs or node.args.vararg
            or node.args.kwarg or node.args.defaults or node.args.kw_defaults):
        raise ValueError(f"candidate {name} interface changed")


def _string_checks(tree: ast.Module) -> None:
    module_doc = ast.get_docstring(tree, clean=False)
    module_doc_node = (
        tree.body[0].value
        if tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
        else None
    )
    if module_doc is not None and len(module_doc) > MAX_DOCSTRING_CHARS:
        raise ValueError("candidate module docstring exceeds integrity bound")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value
        if node is not module_doc_node and len(text) > MAX_STRING_CHARS:
            raise ValueError("candidate contains oversized string payload")
        if any(pattern.search(text) for pattern in CONTROL_LANGUAGE):
            raise ValueError("candidate contains unrelated control-language payload")


def validate_candidate_source(source: str) -> dict:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("nonempty candidate source required")
    raw = source.encode("utf-8")
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("candidate source exceeds integrity bound")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("candidate source syntax invalid") from error

    _function_signature(tree, "fit", 2)
    _function_signature(tree, "predict", 2)
    _string_checks(tree)

    imports = set()
    assigned_constants = set()
    for index, node in enumerate(tree.body):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str) and index == 0):
            continue
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
            imports.update(roots)
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                raise ValueError("relative candidate imports are forbidden")
            imports.add(node.module.split(".", 1)[0])
            continue
        if isinstance(node, ast.Assign):
            if (len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)
                    or not node.targets[0].id.isupper() or not _plain_constant(node.value)):
                raise ValueError("candidate module metadata or executable statement is forbidden")
            assigned_constants.add(node.targets[0].id)
            continue
        if isinstance(node, ast.AnnAssign):
            if (not isinstance(node.target, ast.Name) or not node.target.id.isupper()
                    or node.value is None or not _plain_constant(node.value)):
                raise ValueError("candidate module metadata or executable statement is forbidden")
            assigned_constants.add(node.target.id)
            continue
        raise ValueError("candidate top-level executable statement is forbidden")

    if not imports <= SAFE_IMPORT_ROOTS:
        raise ValueError("candidate imports a module outside the safe standard-library set")

    loaded_names = {node.id for node in ast.walk(tree)
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    unused = assigned_constants - loaded_names
    if unused:
        raise ValueError("candidate contains unused module-level metadata")

    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.Global, ast.Nonlocal,
                             ast.Yield, ast.YieldFrom)):
            raise ValueError("candidate contains unsupported stateful control flow")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            roots = ({alias.name.split(".", 1)[0] for alias in node.names}
                     if isinstance(node, ast.Import)
                     else {node.module.split(".", 1)[0]} if node.module else set())
            if not roots <= SAFE_IMPORT_ROOTS:
                raise ValueError("candidate imports a module outside the safe standard-library set")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_CALLS:
                raise ValueError("candidate contains a forbidden dynamic or I/O call")
            if (isinstance(node.func, ast.Attribute)
                    and node.func.attr in DANGEROUS_ATTRIBUTES):
                raise ValueError("candidate contains a forbidden I/O or process call")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("candidate dunder introspection is forbidden")

    contract = policy_contract()
    ast_dump = ast.dump(tree, annotate_fields=True, include_attributes=False)
    return {
        "schema": SCHEMA,
        "valid": True,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "ast_sha256": hashlib.sha256(ast_dump.encode()).hexdigest(),
        "policy_sha256": contract["policy_sha256"],
        "imports": sorted(imports),
        "module_constants": sorted(assigned_constants),
        "required_functions": ["fit", "predict"],
        "scientific_merit_verified": False,
    }
