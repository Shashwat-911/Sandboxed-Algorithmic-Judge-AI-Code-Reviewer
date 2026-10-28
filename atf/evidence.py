"""Attach measured browser results to source reports without inventing coverage."""
import json


def enrich(report, project_id, data):
    if report.get('playwright'):
        report['playwright']['note']='Static discovery identifies suites. Use Repository test suite to execute them; measured outcomes appear in the linked runs below.'
    runs=[]
    for path in (data/'browser-runs').glob('*/result.json'):
        try:
            run=json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if run.get('project_id')==project_id:
            runs.append(run)
    runs.sort(key=lambda r:r.get('created_at',''),reverse=True)
    report['browser_evidence']=runs[:20]
    latest=next((r for r in runs if r.get('mode') in {'suite','javascript','typescript'} and r.get('source_digest')==report.get('source_digest')),None)
    suite=next((r for r in runs if r.get('mode')=='suite' and r.get('source_digest')==report.get('source_digest')),None)
    report['quality_review']={
        'headline': 'No native Playwright run recorded for this snapshot.' if not latest else f"Latest native Playwright run: {latest['status']}.",
        'latest_run_id':latest['id'] if latest else None,
        'measured_tests':latest.get('counts',{}) if latest else {},
        'latest_mode':latest.get('mode') if latest else None,
        'repository_suite':{'run_id':suite['id'],'status':suite['status'],'counts':suite.get('counts',{})} if suite else None,
        'source_digest':report.get('source_digest'),
        'priority_findings':[f for f in report.get('findings',[]) if f['severity'] in {'high','medium'} and f.get('context')!='test'][:20],
        'actions':(['Select this repository in Playwright, trust the code, and run its suite to collect runtime evidence.'] if not latest else
                   ['Review failing test errors, server logs and traces before changing assertions.'] if latest['status']!='passed' else
                   ['Review the exercised scenarios and add missing acceptance cases. Passing tests do not measure untested behavior.']),
        'boundaries':['Native Playwright counts are test outcomes, not line or branch coverage.',
                      'Static findings are review candidates, not confirmed defects.',
                      'AI review availability does not change measured test outcomes.',
                      'Fixture servers validate UI contracts; they do not establish live trading, retrieval quality or medical model accuracy.'],
    }
    return report
