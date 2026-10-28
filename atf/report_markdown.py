"""Readable report with measured evidence first; full detail remains in JSON."""
def render(result):
    r=result['report'];q=r.get('quality_review',{});v=r['verification']
    lines=[f"# ATF report: {result['name']}",'Playwright execution review',f"Report created: {result['created_at']}",
           '## Verification status',v['headline']]
    if v.get('gaps'): lines.append('\n'.join('- ' + g for g in v['gaps']))
    if q.get('headline'): lines.append(q['headline'])
    lines += ['## Analysis provenance',f"Source: {r.get('source',{})}",f"Source digest: `{r.get('source_digest','unknown')}`",
              f"planning_coverage: {r.get('planning_coverage',{})}",'## Next actions']
    lines += ['- '+x for x in q.get('actions',[])]
    lines += ['## Measured Playwright execution']
    runs=r.get('browser_evidence',[])
    if not runs: lines.append('No linked browser execution exists. Static analysis and proposed scenarios do not count as passing tests.')
    for run in runs:
        lines += [f"### {run['mode'] if 'mode' in run else 'commands'} / {run['browser']} / {run['status']}",
                  f"Run: `{run['id']}` · {run.get('duration_ms',0)} ms · source digest `{run.get('source_digest','not recorded')}`",
                  f"Outcomes: {run.get('counts',{})}"]
        if run.get('error'): lines.append('Execution problem: '+run['error'])
        for test in run.get('tests',[]):
            lines.append(f"- **{test['status']}** — {test['title']} — `{test['file']}:{test['line']}` ({test['duration_ms']} ms)")
            for error in test.get('errors',[]): lines.append('```text\n'+error.get('message','')[:6000]+'\n```')
        lines.append('Evidence: '+', '.join('`'+p+'`' for p in run.get('artifacts',[]) if p.endswith(('.zip','.png','.json','.log'))))
        lines.append('Open this run in the browser workspace to download artifacts or view the Playwright HTML report.')
    lines += ['## Priority source review', 'These are static review candidates, not confirmed runtime defects.']
    findings=r.get('findings',[])
    chosen=sorted(findings,key=lambda f:({'high':0,'medium':1,'low':2}[f['severity']],f.get('context')=='test'))[:40]
    for f in chosen:
        lines += [f"- [{f['severity'].upper()}] **{f['title']}** — `{f['file']}:{f['line']}` ({f['rule']})",
                  f"  Context: {f.get('context','source')}; confidence: {f.get('confidence','unknown')}. Evidence: {f.get('evidence','')}",
                  '  Action: '+f['recommendation']]
    if len(findings)>len(chosen): lines.append(f'{len(findings)-len(chosen)} additional observations are available in the JSON report and browser Findings tab.')
    lines += ['## Application structure']
    a=r.get('architecture',{})
    lines += ['Entry points: '+', '.join('`'+p+'`' for p in a.get('entrypoints',[]))]
    for route in a.get('routes',[])[:30]: lines.append(f"- {route['method']} {route['path']} — {route['file']}:{route['line']}")
    lines += ['## Proposed test cases', 'These are unexecuted structural proposals. Exact expected outcomes must come from requirements.']
    for t in r.get('test_plan',[])[:60]:
        lines.append(f"- `{t['file']}:{t['line']}` **{t['target']} / {t['category']}**: {t['scenario']} Expected: {t['expected']} (basis: {t.get('basis','unknown')})")
    lines.append(f"Showing up to 60 proposals of {len(r.get('test_plan',[]))}; the complete plan is retained in JSON.")
    if r.get('ai', {}).get('status') == 'completed':
        lines += ['## AI review', r['ai']['text']]
    lines += ['## Recommendations']
    lines += ['- '+s for s in r.get('future_scope',[])]
    lines += ['## Boundaries']+['- '+s for s in q.get('boundaries',r.get('limitations',[]))]
    return '\n\n'.join(lines)
