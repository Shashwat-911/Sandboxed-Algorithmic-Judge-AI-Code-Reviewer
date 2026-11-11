"""Exercise public API privacy, restrictions, reports and real browser execution."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
workspace = tempfile.TemporaryDirectory(prefix='sandbox-cloud-check-')
os.environ['ATF_DATA_DIR'] = workspace.name
os.environ.pop('RENDER', None)
from fastapi.testclient import TestClient
from cloud_app import app, TARGET

def wait(client, path):
    for _ in range(180):
        response = client.get(path)
        assert response.status_code == 200, response.text
        row = response.json()
        if row['status'] not in ('queued', 'running'): return row
        time.sleep(.5)
    raise AssertionError('Job did not finish')

with TestClient(app) as first, TestClient(app) as second:
    assert 'cloud.js' in first.get('/').text
    second.get('/')
    result = first.post('/api/demo')
    assert result.status_code == 202, result.text
    identifier = result.json()['id']
    report = wait(first, f'/api/projects/{identifier}')
    assert report['status'] == 'completed', report
    assert report['report']['summary']['files'] > 0
    assert second.get('/api/projects').json() == []
    assert second.get(f'/api/projects/{identifier}').status_code == 404
    assert second.get(f'/api/projects/{identifier}/report').status_code == 404
    assert first.get(f'/api/projects/{identifier}/report?format=pdf').content.startswith(b'%PDF')
    assert first.get(f'/api/projects/{identifier}/report?format=json').json()['id'] == identifier
    assert first.post('/api/demo', headers={'Origin': 'https://untrusted.example'}).status_code == 403
    assert second.post('/api/demo?use_ai=true').status_code == 422
    assert second.post('/api/playwright/runs', json={'mode':'python','trusted':True,'commands':'print(1)'}).status_code == 422
    assert second.post('/api/playwright/runs', json={'commands':'goto "http://127.0.0.1/"'}).status_code == 422
    commands = f'goto "{TARGET}"\nfill "#task" "Live browser check"\nclick "#add"\nexpect-text "#tasks" "Live browser check"\ncheck "#tasks input"\nexpect-text "#count" "1 completed"\nscreenshot'
    result = first.post('/api/playwright/runs', json={'mode':'commands','commands':commands,'project_id':identifier})
    assert result.status_code == 202, result.text
    run_id = result.json()['id']
    run = wait(first, f'/api/playwright/runs/{run_id}')
    assert run['status'] == 'passed', run
    assert len(run['steps']) == 7
    assert first.get(f'/api/playwright/runs/{run_id}/artifacts/trace.zip').status_code == 200
    assert second.get(f'/api/playwright/runs/{run_id}').status_code == 404
    assert second.get(f'/api/playwright/runs/{run_id}/artifacts/step-1.png').status_code == 404
    print('PASS: sample analysis, PDF/JSON export, visitor isolation, cross-origin protection, native-code and network restrictions, seven live Chromium steps, trace download.')
workspace.cleanup()
