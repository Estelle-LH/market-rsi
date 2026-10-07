"""Static admission for versioned, pure-context research policies/tools.

No imports or generated tests execute here. This narrows permitted Python;
it is not OS containment, correctness review, benefit evidence or activation.
"""
import ast
import re

BUILTINS = {"len", "range", "enumerate", "zip", "float", "int", "bool", "str", "list", "tuple",
    "dict", "set", "sorted", "reversed", "min", "max", "sum", "abs", "all", "any", "isinstance",
    "ValueError", "TypeError", "RuntimeError", "AssertionError"}
METHODS = {"get", "items", "keys", "values", "copy", "append", "extend", "count", "index", "sort",
    "split", "strip", "lower", "upper", "replace", "join", "startswith", "endswith"}
MATH = {"sqrt", "log", "log1p", "exp", "tanh", "isfinite", "fsum", "floor", "ceil", "pi", "e"}


def validate_source(source, *, is_test=False, module_name="capacity"):
    if (type(source) is not str or not 1 <= len(source.encode()) <= 24576
            or type(module_name) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", module_name)
            or module_name == "math"):
        raise ValueError("bounded source and ordinary capacity module name required")
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if len(nodes) > 3000:
        raise ValueError("bounded capacity AST required")
    functions = {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    aliases = {}
    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Global, ast.Nonlocal, ast.With, ast.Delete)):
            raise ValueError("dynamic/context/global capacity behavior not admitted")
        if isinstance(node, ast.Name) and "__" in node.id and node.id != "__name__":
            raise ValueError("private capacity names not admitted")
        if isinstance(node, ast.Import):
            if any(item.name != "math" for item in node.names):
                raise ValueError("only pure math imports admitted")
            aliases.update({item.asname or item.name: "math" for item in node.names})
        if isinstance(node, ast.ImportFrom):
            if (not is_test or node.level or node.module != module_name
                    or len(node.names) != 1 or node.names[0].name != "apply"):
                raise ValueError("test may import only the exact reviewed capacity apply")
            aliases[node.names[0].asname or "apply"] = "apply"
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr not in METHODS | MATH):
            raise ValueError("private or unknown capacity attribute")
        if isinstance(node, ast.FunctionDef):
            evaluated = [*node.args.defaults, *(v for v in node.args.kw_defaults if v is not None),
                *(arg.annotation for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                  if arg.annotation is not None), *([node.returns] if node.returns is not None else [])]
            if node.decorator_list or any(isinstance(item, ast.Call) for value in evaluated for item in ast.walk(value)):
                raise ValueError("dynamic capacity defaults/annotations/decorators not admitted")
        if isinstance(node, ast.AnnAssign) and any(isinstance(item, ast.Call) for item in ast.walk(node.annotation)):
            raise ValueError("dynamic capacity annotation not admitted")
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name) and target.id in BUILTINS | functions | {k for k, v in aliases.items() if v == "apply"}:
            continue
        if isinstance(target, ast.Attribute):
            if isinstance(target.value, ast.Name) and aliases.get(target.value.id) == "math" and target.attr in MATH:
                continue
            if target.attr in METHODS:
                continue
        raise ValueError("unknown/dynamic capacity call")
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)) or isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            try: ast.literal_eval(node.value)
            except (ValueError, TypeError): raise ValueError("capacity module constants must be literal") from None
            if any(not isinstance(target, ast.Name) for target in (node.targets if isinstance(node, ast.Assign) else [node.target])):
                raise ValueError("capacity module constant targets must be names")
            continue
        if (is_test and isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
                and len(node.body) == 1 and ast.unparse(node.body[0]) == "test_capacity()" and not node.orelse):
            continue
        raise ValueError("capacity import must not execute behavior")
    if is_test:
        if "test_capacity" not in functions or not any(isinstance(node, ast.If) for node in tree.body):
            raise ValueError("standalone synthetic test_capacity required")
    else:
        entry = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "apply"]
        if (len(entry) != 1 or [arg.arg for arg in entry[0].args.args] != ["context"]
                or entry[0].args.posonlyargs or entry[0].args.kwonlyargs or entry[0].args.vararg
                or entry[0].args.kwarg or entry[0].args.defaults):
            raise ValueError("exact pure apply(context) API required")
    return {"passed": True, "kind": "test" if is_test else "capacity", "bytes": len(source.encode()),
        "ast_nodes": len(nodes), "imports": aliases, "source_executed": False, "arbitrary_code_containment": False}
