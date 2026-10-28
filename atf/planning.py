"""Bounded, module-balanced scenario proposals. No fabricated expected values."""
from collections import defaultdict, deque


def build_plan(symbols, findings, limit=None):
    candidates=[s for s in symbols if not s['is_test']]
    groups=defaultdict(list)
    def priority(s):
        return -sum({'high':4,'medium':2,'low':1}[f['severity']] for f in findings if f['file']==s['file'] and s['line']<=f['line']<=(s['end_line'] or s['line']))
    for s in sorted(candidates,key=lambda s:(priority(s),s['file'],s['line'])): groups[s['file']].append(s)
    queue=deque((name,deque(rows)) for name,rows in sorted(groups.items()))
    selected=[]
    while queue and (limit is None or len(selected)<limit):
        name,rows=queue.popleft();selected.append(rows.popleft())
        if rows: queue.append((name,rows))
    plans=[]
    for s in selected:
        params=', '.join(s['parameters']) or 'no explicit input parameters'
        cases=[('contract',f"Exercise {s['name']} with documented valid values ({params}).",'Assert the specified return value and side effects; derive exact assertions from the project contract.','Function signature')]
        signals=s['signals']
        if signals['division']:
            cases.append(('arithmetic boundary','Drive each divisor to zero, near zero and non-finite values where supported.','Assert deliberate rejection or documented behavior; do not assume zero is the correct result.','Division/modulo expression'))
        if signals['branching']:
            cases.append(('branch boundary','Exercise both sides of each condition, including equality at threshold boundaries.','Assert branch-specific behavior from the contract and validate side effects.','If statement'))
        if signals['iteration']:
            cases.append(('collection boundary','Use empty, single-item, repeated-item and large collections.','Check termination, ordering and duplicate handling against requirements.','Loop/comprehension'))
        if signals['exceptions']:
            cases.append(('dependency failure','Inject an exception into each protected dependency call using mocks.','Check intended propagation, fallback and logging; verify failures are not mistaken for successful empty results.','Try/except structure'))
        if any(any(k in p.lower() for k in ('time','date','session')) for p in s['parameters']):
            cases.append(('time boundary','Use timezone-aware and naive timestamps, boundary times and daylight-saving transitions where relevant.','Assert the documented timezone policy; use fixed clocks instead of wall time.','Timestamp-like parameter name (heuristic)'))
        if len(cases)==1:
            cases.append(('repeatability',f"Repeat {s['name']} and reuse input objects ({params}).",'Check documented mutation and state isolation.','Function signature; behavior requires specification'))
        for category,scenario,expected,basis in cases:
            plans.append(dict(id=f'TC-{len(plans)+1:03}',target=s['name'],file=s['file'],line=s['line'],category=category,scenario=scenario,expected=expected,basis=basis,status='proposed - not executed; assertions require project requirements'))
    if not plans:
        plans=[dict(id='TC-001',target='Project interface',file='',line=0,category='manual contract',scenario='Identify the documented public interface and its valid and invalid inputs.',expected='Define observable outcomes from requirements.',basis='No eligible Python functions',status='proposed - manual refinement required')]
    return plans,dict(eligible_functions=len(candidates),selected_functions=len(selected),omitted_functions=len(candidates)-len(selected),function_limit=limit,
        eligible_files=len(groups),selected_files=len({s['file'] for s in selected}),method='Round-robin across source files; risk-ranked functions within each file. Test helpers excluded. Not coverage measurement.')


def project_scope(arch):
    modules={i['module'].split('.')[0] for i in arch['imports']}
    ideas=['Define acceptance criteria for this project and connect each critical workflow to regression tests.',
           'Measure branch coverage in the project-specific test environment; investigate uncovered error paths.']
    if modules & {'alpaca','yfinance'}:
        ideas += ['Extend offline broker-contract tests for partial fills, duplicate events, rejected orders and clock outages; no live trading is needed.',
                  'Verify reconciliation invariants and timestamp boundaries with deterministic fixtures; this analysis does not assess returns or suitability.']
    if modules & {'lightgbm','sklearn','optuna'}:
        ideas.append('Validate chronological train/test separation and preprocessing consistency with reproducible data fixtures.')
    if modules & {'requests','httpx','urllib'}:
        ideas.append('Exercise external-service timeouts, retries and malformed responses with mocks.')
    return ideas
