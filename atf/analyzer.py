"""Syntax-aware rules and contextual test planning; uploaded source is never imported."""
import ast
import hashlib
from collections import Counter
from pathlib import PurePosixPath
from atf.architecture import architecture
from atf.planning import build_plan, project_scope

LANGUAGES = {'.py':'Python','.js':'JavaScript','.jsx':'JavaScript','.ts':'TypeScript','.tsx':'TypeScript','.java':'Java','.cpp':'C++','.go':'Go','.rs':'Rust','.c':'C'}


def is_test(path):
    p = PurePosixPath(path)
    return bool(set(p.parts) & {'tests','test','__tests__'}) or p.name.startswith('test_') or p.name.endswith('_test.py') or '.test.' in p.name or '.spec.' in p.name


def call_name(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute): return call_name(node.value) + '.' + node.attr
    return ''


def analyze(files):
    findings, symbols, inventory, checks = [], [], [], []
    def add(severity, title, path, line, recommendation, rule, evidence, confidence='high'):
        findings.append(dict(severity=severity,title=title,file=path,line=line,recommendation=recommendation,
            rule=rule,origin='static',context='test' if is_test(path) else 'source',confidence=confidence,
            evidence=evidence,assessment='review candidate; exploitability and business correctness not established'))
    for path, source in sorted(files.items()):
        suffix=PurePosixPath(path).suffix.lower()
        inventory.append(dict(path=path,language=LANGUAGES.get(suffix,'Configuration / documentation'),
                              lines=len(source.splitlines()),bytes=len(source.encode()),sha256=hashlib.sha256(source.encode()).hexdigest()))
        if suffix!='.py': continue
        try:
            tree=ast.parse(source,filename=path)
            checks.append(dict(file=path,status='passed',check='Python syntax (AST parse)'))
        except (SyntaxError,RecursionError) as exc:
            add('high','Python syntax could not be parsed',path,getattr(exc,'lineno',1) or 1,
                'Check syntax against the project Python version.','PY001',type(exc).__name__)
            checks.append(dict(file=path,status='failed',check='Python syntax (AST parse)'))
            continue
        test=is_test(path)
        class Functions(ast.NodeVisitor):
            def __init__(self): self.scope=[]
            def visit_ClassDef(self,node):
                self.scope.append(node.name);self.generic_visit(node);self.scope.pop()
            def visit_FunctionDef(self,node):
                qualified='.'.join(self.scope+[node.name])
                args=node.args.posonlyargs+node.args.args+node.args.kwonlyargs
                parameters=[a.arg for a in args if a.arg not in {'self','cls'}]
                symbols.append(dict(file=path,name=qualified,line=node.lineno,end_line=node.end_lineno,
                    parameters=parameters,asynchronous=isinstance(node,ast.AsyncFunctionDef),is_test=test,
                    signals=function_signals(node)))
                defaults=node.args.defaults+[d for d in node.args.kw_defaults if d is not None]
                if any(isinstance(d,(ast.List,ast.Dict,ast.Set)) for d in defaults):
                    add('medium','Mutable default argument',path,node.lineno,'Default to None and create a fresh collection inside the function.','PY002','Function has a collection literal in a default argument.')
                if (node.end_lineno or node.lineno)-node.lineno>60 and not test:
                    add('low','Long function (maintainability observation)',path,node.lineno,'Review responsibilities before extracting helpers; length alone is not a correctness defect.','MAINT001',f'{qualified} spans {node.end_lineno-node.lineno+1} lines, including comments and blank lines.')
                self.scope.append(node.name);self.generic_visit(node);self.scope.pop()
            visit_AsyncFunctionDef=visit_FunctionDef
        Functions().visit(tree)
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=call_name(node.func)
                if name in {'eval','exec','builtins.eval','builtins.exec'}:
                    compiled=bool(node.args and isinstance(node.args[0],ast.Call) and call_name(node.args[0].func)=='compile')
                    harness=test and compiled
                    add('medium' if harness else 'high','Dynamic evaluation in test harness' if harness else 'Dynamic code evaluation',path,node.lineno,
                        'Confirm only trusted local source is compiled. AST-based test isolation can be intentional; this is not evidence of an exploitable production path.' if harness else 'Trace input provenance; replace dynamic evaluation where untrusted input can reach this call.',
                        'SEC002','exec/eval receives compile(...) in a test file.' if harness else f'Executable call to {name}; input trust is not resolved.', 'medium')
                if name.startswith('subprocess.') and any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords):
                    add('high','Shell execution requires input review',path,node.lineno,'Use an argument list and validate user-controlled arguments.','SEC003','subprocess call explicitly sets shell=True.','medium')
                if name.endswith('.run') and any(k.arg=='debug' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords):
                    add('medium','Debug mode enabled',path,node.lineno,'Disable debug mode outside local development.','CFG001','run(...) explicitly sets debug=True.','medium')
            if isinstance(node,(ast.Assign,ast.AnnAssign)):
                value=node.value
                targets=node.targets if isinstance(node,ast.Assign) else [node.target]
                names=[call_name(t).lower() for t in targets]
                if isinstance(value,ast.Constant) and isinstance(value.value,str) and len(value.value)>=8:
                    suspicious=any(n.split('.')[-1] in {'api_key','secret_key','password','access_token'} for n in names)
                    placeholder=any(x in value.value.lower() for x in ('placeholder','example','changeme','your_','dummy','redacted'))
                    if suspicious and not placeholder:
                        add('low' if test else 'high','Possible hardcoded credential',path,node.lineno,'Determine whether this is a fixture or real secret; use a secret store and rotate real exposed credentials. Value omitted.','SEC001','Credential-named assignment contains a string literal; value intentionally omitted.','medium')
            if isinstance(node,ast.ExceptHandler) and (node.type is None or isinstance(node.type,ast.Name) and node.type.id=='Exception') and all(isinstance(n,ast.Pass) for n in node.body):
                add('medium','Exception silently discarded',path,node.lineno,'Determine whether this is optional display/cleanup or a critical failure path. Log, propagate or document the intended fallback.','PY003','Broad exception handler has only pass; surrounding recovery logic must be reviewed.')
            if isinstance(node,ast.Assert) and not test:
                add('low','Assertion used outside tests',path,node.lineno,'Use an explicit exception for required runtime validation; optimized Python removes assertions.','PY004','Assert statement in a non-test file.')
    test_files=[p for p in files if is_test(p)]
    if not test_files: add('medium','No conventional test files detected','',0,'Add regression tests for public interfaces and failures.','TEST001','No matching test path names detected.')
    if not any(PurePosixPath(p).name.lower().startswith('readme') for p in files):
        add('low','README missing','',0,'Document setup, architecture and a reproducible demo.','DOC001','No README filename detected.')
    rank={'high':0,'medium':1,'low':2}
    findings.sort(key=lambda f:(rank[f['severity']],f['file'],f['line'],f['rule']))
    plans,coverage=build_plan(symbols,findings)
    digest=hashlib.sha256(''.join(f"{f['path']}\0{f['sha256']}\n" for f in inventory).encode()).hexdigest()
    arch=architecture(files)
    return dict(analyzer_version='2.1',source_digest=digest,architecture=arch,inventory=inventory,findings=findings,symbols=symbols,checks=checks,test_plan=plans,planning_coverage=coverage,
        summary=dict(files=len(files),lines=sum(i['lines'] for i in inventory),languages=dict(Counter(i['language'] for i in inventory)),test_files=len(test_files),severity=dict(Counter(f['severity'] for f in findings))),
        suggestions=[f"{f['file']}:{f['line']} - {f['title']}: {f['recommendation']}" for f in findings[:12]],
        future_scope=project_scope(arch),limitations=['Static findings are contextual review candidates, not proven vulnerabilities.',
        'Only Python receives syntax-aware rules. Other languages receive inventory only.',
        'Syntax parsing is not runtime validation; parser and target Python versions may differ.',
        'Plans are structural proposals, not implemented assertions or measured coverage. Selection limits are reported.',
        'Business logic, trading profitability, dependency CVEs and deployment readiness are not certified.'])


def function_signals(node):
    nodes=[]
    def visit(n):
        nodes.append(n)
        for child in ast.iter_child_nodes(n):
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): continue
            visit(child)
    visit(node)
    calls={call_name(n.func) for n in nodes if isinstance(n,ast.Call)}
    return dict(division=any(isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Div,ast.FloorDiv,ast.Mod)) for n in nodes),
        branching=any(isinstance(n,ast.If) for n in nodes),iteration=any(isinstance(n,(ast.For,ast.While,ast.comprehension)) for n in nodes),
        exceptions=any(isinstance(n,ast.Try) for n in nodes),calls=sorted(calls))
