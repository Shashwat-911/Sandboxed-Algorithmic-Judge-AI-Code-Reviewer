import json
from atf.evidence import enrich
from atf.verification import verification
from test_atf import api, zipped
from atf.archive import read_archive


def test_native_execution_requires_trust_and_project(api):
    r=api.post('/api/playwright/runs',json={'mode':'javascript','commands':'await page.goto("/")'})
    assert r.status_code==400 and 'trust' in r.json()['detail'].lower()
    r=api.post('/api/playwright/runs',json={'mode':'suite','trusted':True})
    assert r.status_code==400 and 'repository' in r.json()['detail']


def test_cross_origin_execution_rejected(api):
    r=api.post('/api/playwright/runs',headers={'Origin':'https://unrelated.example'},json={'commands':'screenshot'})
    assert r.status_code==403


def test_commonjs_startup_files_survive_import():
    files,_=read_archive(zipped({'repo/package.json':'{}','repo/scripts/server.cjs':'console.log(1)','repo/config.mts':'export default {}'}))
    assert 'scripts/server.cjs' in files and 'config.mts' in files


def test_results_do_not_transfer_between_snapshots(tmp_path):
    folder=tmp_path/'browser-runs'/'run1';folder.mkdir(parents=True)
    base={'source_digest':'current','execution':{'status':'not_requested'},'ai':{'status':'not_requested'}}
    run={'id':'run1','project_id':'p','mode':'suite','status':'passed','source_digest':'old','created_at':'2026','counts':{'passed':4}}
    (folder/'result.json').write_text(json.dumps(run))
    assert verification(enrich(base,'p',tmp_path))['status']=='not_verified'
    run['source_digest']='current';run['status']='failed'
    (folder/'result.json').write_text(json.dumps(run))
    assert verification(enrich(base,'p',tmp_path))['status']=='not_verified'
    run['status']='passed';(folder/'result.json').write_text(json.dumps(run))
    assert verification(enrich(base,'p',tmp_path))['status']=='tests_passed_with_limits'
