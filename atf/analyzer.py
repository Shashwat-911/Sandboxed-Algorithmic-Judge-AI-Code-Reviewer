"""Evidence-based static review; no user code is evaluated."""
import ast
from atf.architecture import architecture
import re
from collections import Counter
from pathlib import PurePosixPath

LANGUAGES = {'.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TypeScript', '.java': 'Java', '.cpp': 'C++', '.go': 'Go', '.rs': 'Rust', '.c': 'C'}

def analyze(files):
    findings, symbols, inventory, checks = [], [], [], []
    def add(severity, title, path, line, recommendation, rule):
        findings.append(dict(severity=severity, title=title, file=path, line=line, recommendation=recommendation, rule=rule, origin='static'))
    for path, source in sorted(files.items()):
        suffix = PurePosixPath(path).suffix
        language = LANGUAGES.get(suffix, 'Configuration / documentation')
        inventory.append(dict(path=path, language=language, lines=len(source.splitlines()), bytes=len(source.encode())))
        for number, line in enumerate(source.splitlines(), 1):
            if re.search(r'(?i)(?:api_key|secret_key|password|access_token)\s*[:=]\s*[\x22\x27][^\x22\x27]{8,}[\x22\x27]', line):
                add('high', 'Possible hardcoded credential', path, number, 'Use environment variables or a secret store. Rotate any real credential. Value omitted from this report.', 'SEC001')
            if re.search(r'\b(?:eval|exec)\s*\(', line) and suffix in {'.py', '.js', '.ts'}:
                add('high', 'Dynamic code evaluation', path, number, 'Trace input provenance; replace dynamic evaluation with parsing or a fixed dispatch table.', 'SEC002')
            if 'shell=True' in line:
                add('high', 'Shell execution requires input review', path, number, 'Use an argument list with shell=False and validate user-controlled arguments.', 'SEC003')
            if re.search(r'\bdebug\s*=\s*True', line):
                add('medium', 'Debug mode enabled', path, number, 'Disable debug mode outside local development.', 'CFG001')
        if suffix != '.py':
            continue
        try:
            tree = ast.parse(source, filename=path)
            checks.append(dict(file=path, status='passed', check='Python syntax (AST parse)'))
        except (SyntaxError, RecursionError) as exc:
            add('high', 'Python syntax could not be parsed', path, getattr(exc, 'lineno', 1) or 1, str(exc), 'PY001')
            checks.append(dict(file=path, status='failed', check='Python syntax (AST parse)'))
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(dict(file=path, name=node.name, line=node.lineno, parameters=[a.arg for a in node.args.args], asynchronous=isinstance(node, ast.AsyncFunctionDef)))
                if any(isinstance(d, (ast.List, ast.Dict, ast.Set)) for d in node.args.defaults):
                    add('medium', 'Mutable default argument', path, node.lineno, 'Default to None and create a fresh collection inside the function.', 'PY002')
                if (node.end_lineno or node.lineno) - node.lineno > 60:
                    add('low', 'Function has more than 60 lines', path, node.lineno, 'Extract focused helpers and test each responsibility separately.', 'MAINT001')
            if isinstance(node, ast.ExceptHandler) and (node.type is None or isinstance(node.type, ast.Name) and node.type.id == 'Exception'):
                if all(isinstance(n, ast.Pass) for n in node.body):
                    add('medium', 'Exception silently discarded', path, node.lineno, 'Catch specific exceptions and record or propagate unexpected failures.', 'PY003')
            if isinstance(node, ast.Assert) and not PurePosixPath(path).name.startswith('test'):
                add('low', 'Assertion used outside tests', path, node.lineno, 'Use an explicit exception for runtime validation; optimized Python removes assertions.', 'PY004')
    test_files = [p for p in files if PurePosixPath(p).name.startswith('test_') or '.test.' in p or '.spec.' in p]
    if not test_files:
        add('medium', 'No conventional test files detected', '', 0, 'Add a regression suite for public interfaces and failure paths.', 'TEST001')
    if not any(PurePosixPath(p).name.lower().startswith('readme') for p in files):
        add('low', 'README missing', '', 0, 'Document installation, architecture, configuration, and a reproducible demo.', 'DOC001')
    plans = []
    for symbol in [s for s in symbols if not s['name'].startswith('test')][:50]:
        for category, scenario, expected in [
            ('happy path', 'Representative valid values', 'Assert the documented return value and side effects.'),
            ('boundary', 'Empty, zero, negative, and maximum-size values where relevant', 'Confirm the specified boundary behavior without crashes or unbounded work.'),
            ('invalid input', 'None, wrong types, malformed values, and missing arguments', 'Assert a deliberate validation error and no partial mutation.'),
            ('repeatability', 'Repeat calls and reuse the same input object', 'Verify state does not leak between calls; document intended mutations.'),
        ]:
            plans.append(dict(id=f'TC-{len(plans)+1:03}', target=symbol['name'], file=symbol['file'], line=symbol['line'], category=category, scenario=scenario, expected=expected, status='proposed — requires domain-specific assertions'))
    if not plans:
        for category in ['startup', 'valid input', 'invalid input', 'boundary values', 'dependency failure']:
            plans.append(dict(id=f'TC-{len(plans)+1:03}', target='Project public interface', file='', line=0, category=category, scenario=f'Exercise {category} through the documented entry point.', expected='Define expected behavior from the project specification.', status='proposed — manual refinement required'))
    counts = Counter(f['severity'] for f in findings)
    languages = dict(Counter(i['language'] for i in inventory))
    return dict(architecture=architecture(files), inventory=inventory, findings=findings, symbols=symbols, checks=checks, test_plan=plans,
        summary=dict(files=len(files), lines=sum(i['lines'] for i in inventory), languages=languages, test_files=len(test_files), severity=dict(counts)),
        suggestions=[f"{f['title']}: {f['recommendation']}" for f in findings[:12]],
        future_scope=['Add isolated runners for JavaScript, Java, and C++ project suites.', 'Add coverage instrumentation and baseline comparisons.', 'Integrate pull-request reviews with authentication and per-project access control.', 'Add specification-driven assertion generation and human approval before execution.'],
        limitations=['Static rules flag review candidates, not proven vulnerabilities.', 'Python AST checks validate syntax, not runtime correctness.', 'Generated test plans are proposals, not executed or passing tests.', 'Non-Python source receives text rules and inventory only.', 'Dependency vulnerability scanning and coverage measurement are not implemented.'])
