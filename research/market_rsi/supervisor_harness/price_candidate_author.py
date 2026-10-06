"""Real text-only candidate implementation; source review precedes every import.

This trusted adapter implements the original Controller recipe, not a scientific
menu. AST checks reduce permitted behavior; they are not OS-hard containment.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

from supervisor_harness import price_loop_handoff as h

IMPORTS = {
    "numpy": None, "math": None,
    "sklearn.linear_model": {"Ridge", "LinearRegression", "ElasticNet", "HuberRegressor"},
    "sklearn.ensemble": {"HistGradientBoostingRegressor", "RandomForestRegressor", "ExtraTreesRegressor"},
    "sklearn.preprocessing": {"StandardScaler", "PolynomialFeatures", "RobustScaler"},
    "sklearn.pipeline": {"Pipeline", "make_pipeline"}, "sklearn.svm": {"SVR"},
    "sklearn.kernel_ridge": {"KernelRidge"}, "sklearn.isotonic": {"IsotonicRegression"}}
FORBIDDEN = {"open", "eval", "exec", "compile", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "dir", "input", "help", "breakpoint", "memoryview", "type", "object", "super"}
METHODS = {"fit", "predict", "transform", "fit_transform", "reshape", "ravel", "flatten", "copy", "astype",
    "sum", "mean", "std", "var", "min", "max", "clip", "all", "any", "tolist", "dot", "transpose"}
NP = {"array", "asarray", "zeros", "ones", "full", "full_like", "zeros_like", "ones_like", "empty", "empty_like", "arange",
    "linspace", "column_stack", "hstack", "vstack", "stack", "concatenate", "clip", "sqrt", "log", "log1p", "exp",
    "abs", "sign", "maximum", "minimum", "where", "isfinite", "nan_to_num", "sum", "mean", "median", "std", "var",
    "min", "max", "all", "any", "dot", "einsum", "quantile", "percentile", "unique", "argsort", "argmax", "argmin", "average",
    "power", "square", "tanh", "multiply", "divide", "float64", "int64", "pi", "inf", "nan", "linalg", "testing"}
BUILTINS = {"len", "range", "enumerate", "zip", "float", "int", "min", "max", "sum", "abs", "list", "tuple",
    "dict", "sorted", "all", "any", "ValueError", "RuntimeError", "AssertionError"}


def validate_source(source, *, is_test=False):
    """Pure static allowlist; generated source/tests are never imported here."""
    if type(source) is not str or not 1 <= len(source.encode()) <= 24576:
        raise ValueError("nonempty source at most24KiB required")
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if len(nodes) > 3000:
        raise ValueError("bounded AST required")
    aliases, functions = {}, {n.name for n in nodes if isinstance(n, ast.FunctionDef)}
    object_dtypes = {id(k.value) for n in nodes if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id in {i.asname or i.name for node in nodes if isinstance(node, ast.Import) for i in node.names if i.name == "numpy"}
        and n.func.attr in {"array", "asarray", "full", "full_like", "zeros", "ones"}
        for k in n.keywords if is_test and k.arg == "dtype" and isinstance(k.value, ast.Name) and k.value.id == "object"}
    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Global, ast.Nonlocal, ast.With, ast.Delete)):
            raise ValueError("classes/async/global/nonlocal/context/delete not admitted")
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN and id(node) not in object_dtypes or "__" in node.id and node.id != "__name__"):
            raise ValueError("dynamic execution or private names not admitted")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in FORBIDDEN):
            raise ValueError("private/dynamic attributes not admitted")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for item in node.names:
                    if item.name not in {"numpy", "math"}:
                        raise ValueError("only numeric module imports admitted")
                    aliases[item.asname or item.name] = item.name
            else:
                admitted = {**IMPORTS, **({"candidate": {"fit_predict"}} if is_test else {})}
                if node.level or node.module not in admitted:
                    raise ValueError("non-numeric import not admitted")
                for item in node.names:
                    permitted = admitted[node.module]
                    if item.name == "*" or item.name.startswith("_") or permitted is None or item.name not in permitted:
                        raise ValueError("explicit bounded numeric symbols required")
                    aliases[item.asname or item.name] = node.module + "." + item.name
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or any(isinstance(n, ast.Call) for v in
                [*node.args.defaults, *(v for v in node.args.kw_defaults if v is not None)] for n in ast.walk(v))):
            raise ValueError("decorators/dynamic defaults not admitted")
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        if any(k.arg == "n_jobs" and (not isinstance(k.value, ast.Constant) or type(k.value.value) is not int or k.value.value != 1) for k in node.keywords):
            raise ValueError("explicit parallel jobs must remain one")
        target = node.func
        if isinstance(target, ast.Name):
            if target.id not in BUILTINS | functions | set(aliases):
                raise ValueError("unknown call target")
        elif isinstance(target, ast.Attribute):
            chain, base = [], target
            while isinstance(base, ast.Attribute):
                chain.insert(0, base.attr); base = base.value
            module = aliases.get(base.id) if isinstance(base, ast.Name) else None
            if module == "numpy":
                if chain[0] not in NP or len(chain) > 1 and chain not in (
                        ["linalg", "solve"], ["linalg", "lstsq"], ["linalg", "pinv"],
                        ["testing", "assert_allclose"], ["testing", "assert_array_equal"]):
                    raise ValueError("non-numeric NumPy call")
            elif module == "math":
                if len(chain) != 1 or chain[0] not in {"sqrt", "log", "log1p", "exp", "tanh", "isfinite", "fsum"}:
                    raise ValueError("non-numeric math call")
            elif target.attr not in METHODS:
                raise ValueError("unknown object method")
        else:
            raise ValueError("dynamic call expression not admitted")
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)) or isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and not any(isinstance(n, (ast.Call, ast.Attribute)) for n in ast.walk(node)):
            continue
        if is_test and isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'":
            continue
        raise ValueError("module import must not execute candidate behavior")
    if not is_test:
        main = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "fit_predict"]
        if len(main) != 1 or [a.arg for a in main[0].args.args] != ["x", "y", "weights", "xc", "history", "check_history"] or [a.arg for a in main[0].args.kwonlyargs] != ["seed"] or main[0].args.vararg or main[0].args.kwarg:
            raise ValueError("exact past-only fit_predict API required")
    elif "test_candidate" not in functions or not any(isinstance(n, ast.If) and
            ast.unparse(n.test) == "__name__ == '__main__'" and len(n.body) == 1 and
            ast.unparse(n.body[0]) == "test_candidate()" and not n.orelse for n in tree.body):
        raise ValueError("standalone synthetic test_candidate invocation required")
    return {"passed": True, "kind": "test" if is_test else "candidate", "ast_nodes": len(nodes),
            "bytes": len(source.encode()), "imports": aliases, "candidate_imported": False}


def _schema(decision):
    text = {"type": "string", "minLength": 1}
    return h.t.c._object({"candidate_id": {"type": "string", "const": decision["candidate"]["candidate_id"]},
        "decision_sha256": {"type": "string", "const": h.t.c._digest(decision)}, "method_family": text,
        "candidate_source": text, "test_source": text, "implementation_notes": text})


def _completed_recovery(runtime, binding, digest, original_id, source):
    h._binding(binding)
    value = h.t.c._read(binding)
    if set(value) != {"schema", "round_index", "original_decision_sha256", "original_author_id", "fresh_local_id", "original_failure", "original_input", "original_response", "original_completion", "review"} or value["schema"] != "price_completed_author_admission_recovery_v1" or type(value["round_index"]) is not int or value["round_index"] != 1 or value["original_decision_sha256"] != digest or value["original_author_id"] != original_id or value["fresh_local_id"] != original_id + "-admission-v2":
        raise ValueError("exact reviewed round1 completed-author recovery required")
    role = runtime.root / "role_calls/author" / original_id
    for key, path in {"original_failure": runtime.root / original_id / "failure.json", "original_input": role / "input.json", "original_response": role / "response.json", "original_completion": role / "completion.json"}.items():
        if h._binding(value[key]) != path:
            raise ValueError("recovery escaped original author evidence")
    failure, completion = h.t.c._read(value["original_failure"]), h.t.c._read(value["original_completion"])
    if source.exists() or (runtime.root / original_id / "implementation.json").exists() or failure != {"stage": "implementation", "original_decision_sha256": digest, "error": "ValueError: non-numeric NumPy call", "retry_allowed": False, "scientific_evidence": False} or completion.get("exit_code") != 0 or completion.get("timed_out") is not False or completion.get("hashes", {}).get("response.json") != value["original_response"]["sha256"]:
        raise ValueError("only completed pre-source admission failure recoverable")
    h._binding(value["review"])
    review = h.t.c._read(value["review"])
    if any(type(review.get(k)) is not type(v) or review.get(k) != v for k, v in {"passed": True, "author_source_sha256": h.w.sha(__file__), "original_failure_sha256": value["original_failure"]["sha256"], "original_completion_sha256": value["original_completion"]["sha256"], "original_decision_sha256": digest}.items()):
        raise ValueError("independent exact admission repair review required")
    return value["fresh_local_id"], h.t.c._read(value["original_input"])["payload"]


class CandidateAuthor:
    def __init__(self, runtime, source_files, role_grant_binding, *, timeout_seconds=120, role_call=None, completed_author_recovery=None):
        self.runtime, self.files, self.grant, self.timeout = runtime, source_files, role_grant_binding, timeout_seconds
        self.call, self.recovery = role_call, completed_author_recovery

    def author(self, ctx):
        decision = ctx["outputs"]["controller"]["decision"]
        h.t.c._validate(decision, h.t.SCHEMA)
        if decision["candidate"]["action"] != "propose_candidate" or not self.runtime.admit({"stage": "implement"}):
            raise ValueError("original candidate decision and open admission required")
        digest = h.t.c._digest(decision)
        ledger = h.t._file(self.runtime.root / "ledger.json")
        if len([d for d in ledger["controller_decisions"] if d.get("status") == "completed" and d.get("decision_sha256") == digest]) != 1:
            raise ValueError("exact completed original decision required before author call")
        h.b._identifier(self.runtime.fixed_grant["batch_id"], "batch ID")
        if type(ctx["round_index"]) is not int or ctx["round_index"] < 1 or type(self.files) is not dict or not self.files:
            raise ValueError("positive round and pinned inherited files required")
        if self.runtime.repo.resolve() != self.runtime.repo or subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=self.runtime.repo, text=True).strip():
            raise ValueError("canonical repo and no unrelated staged source required before author call")
        for relative, expected in self.files.items():
            path = self.runtime.repo / relative
            if Path(relative).is_absolute() or ".." in Path(relative).parts or path.resolve() != path or h.w.sha(path) != expected:
                raise ValueError("inherited source drift before author call")
            if hashlib.sha256(subprocess.check_output(["git", "show", "HEAD:" + relative], cwd=self.runtime.repo)).hexdigest() != expected:
                raise ValueError("inherited source not checkpointed before author call")
        ident = f"author-r{ctx['round_index']:04d}-{digest[:12]}"
        original_id, recovered_packet = ident, None
        original_source = self.runtime.repo / "research/market_rsi/experiments/price_candidates" / self.runtime.fixed_grant["batch_id"] / ident
        if self.recovery is not None and ctx["round_index"] == 1:
            ident, recovered_packet = _completed_recovery(self.runtime, self.recovery, digest, ident, original_source)
        directory = self.runtime.root / ident
        source = self.runtime.repo / "research/market_rsi/experiments/price_candidates" / self.runtime.fixed_grant["batch_id"] / ident
        if directory.exists():
            raise FileExistsError("author attempt exists; uncertain/failed call cannot be retried")
        if source.resolve() != source or source.exists():
            raise ValueError("fresh canonical bounded source directory required before author call")
        directory.mkdir()
        try:
            packet = {"schema": "price_candidate_implementation_input_v1", "original_controller_decision": decision,
                "context": {k: h.t.c._read(ctx["previous_result"][k]) for k in ("feedback", "memory", "source_context")},
                "instructions": "Implement the exact original recipe, no scientific substitution. Return plain source strings, no commands; combinedsource/test<=12KiB, concise notes. fit_predict(x,y,weights,xc,history,check_history,*,seed) sees only past13features/history<=900s and fitlabels; return finite 1Dlen(xc) changes. Frozen300s target/scorer/folds unchanged. One bounded model fit per invocation, n_jobs=1; no inner CV/refits. Imports limited to NumPy/math and numeric sklearn classes. No file/network/process/dynamic execution. Test code imports from candidate import fit_predict, defines test_candidate() using synthetic13feature arrays/history, and executes only under __name__ == '__main__'. No decorators/classes/fixtures/rawTrain. Synthetic tests are not scientific fits.",
                "allowed_imports": {k: sorted(v) if v is not None else "numeric module" for k, v in IMPORTS.items()}}
            if len(json.dumps(packet, sort_keys=True, allow_nan=False).encode()) > 32768:
                raise ValueError("author compact context exceeds32KiB")
            if recovered_packet is not None:
                if packet != recovered_packet:
                    raise ValueError("completed author input changed; no replay or retry")
                packet = recovered_packet
            call = self.call
            if call is None:
                from supervisor_harness.price_account_roles import role_call
                call = role_call
            result = call("author", packet, _schema(decision), root=self.runtime.root,
                grant_binding=self.grant, role_id=original_id, timeout_seconds=self.timeout)
            response = result["response"]; h.t.c._validate(response, _schema(decision))
            if len((response["candidate_source"] + response["test_source"]).encode()) > 12288:
                raise ValueError("combined candidate/test must fit bounded source review payload")
            h.b._identifier(response["method_family"], "method family")
            checks = {"candidate": validate_source(response["candidate_source"]),
                      "test": validate_source(response["test_source"], is_test=True)}
            source.mkdir(parents=True)
            for name, text in (("candidate.py", response["candidate_source"]), ("test_candidate.py", response["test_source"])):
                with (source / name).open("x", encoding="utf-8") as stream:
                    stream.write(text)
            h.w.save(directory / "checks.json", checks)
            receipt = {"schema": "price_candidate_author_receipt_v1", "original_decision_sha256": digest,
                "candidate_id": response["candidate_id"], "method_family": response["method_family"],
                "candidate": h.r.pin(source / "candidate.py"), "test": h.r.pin(source / "test_candidate.py"),
                "role_call": {k: v for k, v in result.items() if k != "response"},
                "checks": h.r.pin(directory / "checks.json"), "implementation_notes": response["implementation_notes"],
                "generated_tests_executed": False, "awaiting_independent_source_review": True,
                "completed_author_recovery": self.recovery if recovered_packet is not None else None}
            h.w.save(source / "author_receipt.json", receipt)
            paths = [str((source / name).relative_to(self.runtime.repo)) for name in ("candidate.py", "test_candidate.py", "author_receipt.json")]
            if subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=self.runtime.repo, text=True).strip():
                raise ValueError("unrelated staged source prevents clean local checkpoint")
            subprocess.run(["git", "add", "--", *paths], cwd=self.runtime.repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "candidate(price): " + response["candidate_id"], "--", *paths], cwd=self.runtime.repo, check=True, capture_output=True)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.runtime.repo, text=True).strip()
            files = {**self.files, **{p: h.w.sha(self.runtime.repo / p) for p in paths}}
            authored = {"candidate_binding": receipt["candidate"], "source_commit": commit, "files": files,
                        "method_family": response["method_family"]}
            h.w.save(directory / "implementation.json", {"authored": authored, "author_receipt": h.r.pin(source / "author_receipt.json")})
            return authored
        except Exception as exc:
            h.w.save(directory / "failure.json", {"stage": "implementation", "original_decision_sha256": digest,
                "error": type(exc).__name__ + ": " + str(exc), "retry_allowed": False, "scientific_evidence": False})
            raise
