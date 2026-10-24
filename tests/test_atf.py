import io
import stat
import time
import zipfile
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from atf.archive import read_archive
from atf.analyzer import analyze
from atf.ai import redact, review
from atf.runner import execute_tests
import main


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for path, source in files.items(): z.writestr(path, source)
    return buffer.getvalue()

@pytest.mark.parametrize('path', ['../escape.py', '/abs.py', 'C:/escape.py', 'a/../../x.py', '..\\x.py'])
def test_archive_rejects_traversal(path):
    with pytest.raises(ValueError, match='unsafe'): read_archive(zipped({path: 'pass'}))

def test_archive_limits(monkeypatch):
    import atf.archive as archive
    monkeypatch.setattr(archive, 'MAX_EXPANDED', 100)
    with pytest.raises(ValueError, match='size'): read_archive(zipped({'large.py': 'x'*101}))
    monkeypatch.setattr(archive, 'MAX_ENTRIES', 2)
    with pytest.raises(ValueError, match='entries'): read_archive(zipped({f'{i}.py': '' for i in range(3)}))

def test_symlinks_rejected():
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        info=zipfile.ZipInfo('link.py');info.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(info,'/etc/passwd')
    with pytest.raises(ValueError, match='Symbolic'): read_archive(buffer.getvalue())

def test_archive_filters_and_normalizes():
    files, skipped=read_archive(zipped({'repo/main.py':'pass','repo/.env':'SECRET=1','repo/node_modules/a.js':'x'}))
    assert files=={'main.py':'pass'}
    assert len(skipped)==2

def test_archive_bad_zip_and_empty():
    for data in [b'no zip',zipped({'image.png':'binary'})]:
        with pytest.raises(ValueError): read_archive(data)

def test_static_evidence_and_syntax():
    report=analyze({'a.py':'def add(x=[]):\n    return eval(input())\n','broken.py':'def !','README.md':'readme'})
    assert {f['rule'] for f in report['findings']} >= {'SEC002','PY001','PY002','TEST001'}
    assert next(f for f in report['findings'] if f['rule']=='PY002')['line']==1
    assert report['planning_coverage']['selected_functions']==1
    assert all(t['target']=='add' for t in report['test_plan'])
    assert {c['status'] for c in report['checks']}=={'passed','failed'}

def test_credentials_not_in_findings():
    report=analyze({'a.py':'password = "supersecretvalue"'})
    assert 'supersecretvalue' not in str(report)
    assert 'supersecretvalue' not in redact('password = "supersecretvalue"')

def test_ai_disabled_and_unavailable():
    assert review({}, {}, False)['status']=='not_requested'
    with patch('atf.ai.httpx.Client',side_effect=RuntimeError):
        assert review({}, {}, True)['status']=='unavailable'

def test_runner_no_host_fallback():
    with patch('atf.runner.docker.from_env',side_effect=RuntimeError):
        assert execute_tests({'test_x.py':'pass'},True)['status']=='unavailable'
    assert execute_tests({},True)['status']=='skipped'
    assert execute_tests({},False)['status']=='not_requested'

@pytest.mark.parametrize('code,expected',[(0,'passed'),(1,'failed'),(5,'no_tests')])
def test_runner_contract_and_cleanup(code,expected):
    client=MagicMock(); container=client.containers.create.return_value
    container.status='exited';container.attrs={'State':{'ExitCode':code}};container.logs.return_value=b'test output'
    with patch('atf.runner.docker.from_env',return_value=client):
        result=execute_tests({'test_x.py':'import unittest'},True)
    assert result['status']==expected
    kwargs=client.containers.create.call_args.kwargs
    assert kwargs['network_mode']=='none' and kwargs['read_only']
    assert kwargs['user']=='65534:65534' and kwargs['cap_drop']==['ALL']
    container.remove.assert_called_once_with(force=True)
    client.close.assert_called_once()

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'reports.db')
    with TestClient(main.app) as client: yield client

def wait_report(api,id):
    for _ in range(100):
        row=api.get('/api/projects/'+id).json()
        if row['status'] not in ('running','queued'): return row
        time.sleep(.02)
    pytest.fail('Job did not finish')

def test_end_to_end_upload_and_exports(api):
    response=api.post('/api/projects',files={'file':('example.zip',zipped({'main.py':'def f(x):\n return x','README.md':'hello'}),'application/zip')})
    assert response.status_code==202
    id=response.json()['id'];row=wait_report(api,id)
    assert row['status']=='completed'
    assert row['report']['summary']['files']==2
    assert row['report']['execution']['status']=='not_requested'
    assert api.get('/api/projects').json()[0]['id']==id
    assert api.get(f'/api/projects/{id}/report?format=json').json()['id']==id
    assert '# ATF report' in api.get(f'/api/projects/{id}/report').text
    assert api.get(f'/api/projects/{id}/report?format=invalid').status_code==400

def test_demo(api):
    id=api.post('/api/demo').json()['id'];row=wait_report(api,id)
    assert row['status']=='completed'
    assert any(f['rule']=='PY002' for f in row['report']['findings'])
    assert row['report']['summary']['test_files']==1

def test_errors_and_ui(api, monkeypatch):
    assert api.get('/').status_code==200
    assert api.get('/static/app.js').status_code==200
    assert api.get('/health').json()['status']=='ok'
    assert api.get('/api/projects/missing').status_code==404
    assert api.post('/api/projects',files={'file':('bad.zip',b'bad')}).status_code==400
    monkeypatch.setattr(main, 'MAX_UPLOAD', 1024)
    assert api.post('/api/projects',files={'file':('big.zip',b'x'*1025)}).status_code==413

def test_queue_backpressure(api):
    acquired=[]
    try:
        for _ in range(6):
            assert main.SLOTS.acquire(blocking=False);acquired.append(True)
        assert api.post('/api/demo').status_code==429
    finally:
        for _ in acquired: main.SLOTS.release()


def test_architecture_and_scaffold(api):
    from atf.architecture import architecture
    r=architecture({'main.py':'import os\n@app.get("/health")\ndef health(): pass','requirements.txt':'fastapi==0.1\n# comment','package.json':'{"dependencies":{"react":"19"}}'})
    assert r['routes'][0]['path']=='/health'
    assert r['imports'][0]['module']=='os'
    assert len(r['dependencies'])==2
    id=api.post('/api/demo').json()['id'];wait_report(api,id)
    scaffold=api.get(f'/api/projects/{id}/tests')
    assert scaffold.status_code==200
    import ast
    ast.parse(scaffold.text)
    assert 'self.skipTest' in scaffold.text

@pytest.mark.skipif(__import__('os').getenv('ATF_INTEGRATION')!='1',reason='Set ATF_INTEGRATION=1 with Docker running')
def test_real_container_isolation_and_success():
    source='''import unittest,os,socket
class Isolation(unittest.TestCase):
 def test_nonroot(self): self.assertNotEqual(os.getuid(),0)
 def test_readonly(self):
  with self.assertRaises(OSError): open('/unauthorized','w')
 def test_no_network(self):
  with self.assertRaises(OSError): socket.create_connection(('1.1.1.1',80),timeout=1)
'''
    result=execute_tests({'test_isolation.py':source},True)
    assert result['status']=='passed',result

@pytest.mark.skipif(__import__('os').getenv('ATF_INTEGRATION')!='1',reason='Set ATF_INTEGRATION=1 with Docker running')
def test_real_timeout_and_zero_tests():
    assert execute_tests({'test_empty.py':'# empty'},True)['status']=='no_tests'
    assert execute_tests({'test_loop.py':'while True: pass'},True)['status']=='timeout'
