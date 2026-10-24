"""Explicit verification boundaries for report consumers."""
def verification(report):
    execution=report.get('execution',{}).get('status','not_requested')
    ai=report.get('ai',{}).get('status','not_requested')
    issues=[]
    if execution!='passed': issues.append(f'Runtime correctness not established: execution status is {execution}.')
    if ai!='completed': issues.append(f'No completed model review: AI status is {ai}.')
    failed=sum(c['status']=='failed' for c in report.get('checks',[]))
    if failed: issues.append(f'{failed} source files failed syntax parsing.')
    coverage=report.get('planning_coverage',{})
    if coverage.get('omitted_functions'): issues.append(f"Scenario planning omitted {coverage['omitted_functions']} functions because of its selection limit.")
    label='tests_passed_with_limits' if execution=='passed' and not failed else 'not_verified'
    return dict(status=label,headline='Existing suite passed; project correctness is not certified.' if label=='tests_passed_with_limits' else 'Incomplete verification - this is not a project correctness verdict.',
                execution=execution,ai=ai,gaps=issues,note='A completed report means analysis finished, not that the project passed testing. Static findings and proposed scenarios are not test results.')
