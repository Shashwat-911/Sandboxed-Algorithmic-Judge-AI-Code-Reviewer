"""Explicit verification boundaries for report consumers."""
def verification(report):
    execution=report.get('execution',{}).get('status','not_requested')
    ai=report.get('ai',{}).get('status','not_requested')
    issues=[]
    native=next((r for r in report.get('browser_evidence',[]) if r.get('mode') in {'suite','javascript','typescript'} and r.get('source_digest')==report.get('source_digest')),None)
    if native:
        execution=native['status']
    if execution not in ('passed','not_requested'):
        issues.append(f'Execution status: {execution}.')
    failed=sum(c['status']=='failed' for c in report.get('checks',[]))
    if failed: issues.append(f'{failed} source files failed syntax parsing.')
    coverage=report.get('planning_coverage',{})
    if coverage.get('omitted_functions'): issues.append(f"Scenario planning omitted {coverage['omitted_functions']} functions because of its selection limit.")
    label='tests_passed' if execution=='passed' and not failed else 'analysis_complete'
    if execution=='passed':
        headline=('Playwright tests passed.' if native and native.get('mode')!='suite' else 'Existing suite passed.')
    else:
        headline='Analysis complete.'
    return dict(status=label,headline=headline,
                execution=execution,ai=ai,gaps=issues,note='Static and dynamic analysis complete.')
