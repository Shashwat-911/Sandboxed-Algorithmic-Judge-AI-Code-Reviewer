import io
import ast
import copy
from unittest.mock import patch
from atf.analyzer import analyze
from atf.verification import verification
from atf.ai import review
from test_atf import api,wait_report


def test_python_rules_ignore_comments_strings_and_unrelated_methods():
    r=analyze({'app.py':'''# eval(input()) shell=True
text = "exec(data) password = 'notasecret'"
obj.eval(data)
obj.run(shell=True)
'''})
    assert not {f['rule'] for f in r['findings']} & {'SEC001','SEC002','SEC003'}


def test_harness_is_contextual_but_input_eval_remains_high():
    r=analyze({'tests/test_broker.py':'''def load():
 exec(compile(tree, "local-methods", "exec"), ns)
 eval(input())
''','main.py':'exec(compile(tree,"x","exec"))'})
    findings=[f for f in r['findings'] if f['rule']=='SEC002']
    assert [(f['file'],f['severity']) for f in findings]==[('main.py','high'),('tests/test_broker.py','high'),('tests/test_broker.py','medium')]
    assert 'not evidence' in findings[-1]['recommendation']


def test_contextual_plans_include_late_modules_and_no_test_helpers():
    files={'aaa.py':'\n'.join(f'def f{i}(x):\n return x' for i in range(90)),
           'risk/manager.py':'class Risk:\n def size(self, capital, price):\n  return capital/price',
           'tests/test_helpers.py':'def helper(): pass'}
    r=analyze(files)
    assert r['planning_coverage']['eligible_functions']==91
    assert r['planning_coverage']['omitted_functions']==0
    assert r['planning_coverage']['selected_functions']==91
    assert any(t['target']=='Risk.size' and t['category']=='arithmetic boundary' for t in r['test_plan'])
    assert not any(t['file'].startswith('tests/') for t in r['test_plan'])
    assert all(t['basis'] for t in r['test_plan'])


def test_kwonly_mutable_and_test_assertions():
    r=analyze({'a.py':'def f(*, cache={}):\n pass', 'tests/helpers.py':'assert True'})
    assert any(f['rule']=='PY002' for f in r['findings'])
    assert not any(f['rule']=='PY004' for f in r['findings'])


def test_unavailable_execution_never_means_verified():
    r=analyze({'main.py':'pass'})
    r.update(execution={'status':'unavailable'},ai={'status':'unavailable'})
    v=verification(r)
    assert v['status']=='not_verified' and len(v['gaps'])==2
    for state in ['no_tests','blocked_dependencies','all_skipped','failed','timeout','not_requested']:
        r['execution']['status']=state
        assert verification(r)['status']=='not_verified'


def test_source_digest_and_project_roadmap():
    r=analyze({'app.py':'import alpaca\nimport sklearn'})
    assert any('broker' in s for s in r['future_scope'])
    assert not any('JavaScript' in s for s in r['future_scope'])
    assert r['source_digest']!=analyze({'app.py':'import alpaca'})['source_digest']


def test_ai_selects_source_before_large_docs():
    files={'.docs.md':'padding'*6000,'broker/orders.py':'def submit(): pass','risk/manager.py':'def check(): pass'}
    with patch('atf.ai.httpx.Client') as client:
        client.return_value.__enter__.return_value.post.return_value.json.return_value={'response':'Review.'}
        r=review(files,{},True)
    assert r['files_in_context'][:2]==['broker/orders.py','risk/manager.py']
    assert r['characters_in_context']<=28000


def test_exports_explain_verification(api):
    id=api.post('/api/demo').json()['id'];r=wait_report(api,id)
    assert r['report']['verification']['status']=='not_verified'
    md=api.get(f'/api/projects/{id}/report').text
    assert '## Verification status' in md and 'planning_coverage' in md
    assert 'Context:' in md and 'basis:' in md


def test_pdf_existing_feature(api):
    from pypdf import PdfReader
    id=api.post('/api/demo').json()['id'];wait_report(api,id)
    response=api.get(f'/api/projects/{id}/report?format=pdf')
    assert response.status_code==200 and response.content.startswith(b'%PDF-')
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(response.content)).pages)
    assert 'not_verified' in text and 'Mutable default' in text


def test_runner_discovery_and_environment_outcomes(tmp_path):
    # Execute only these authored fixtures locally to test the discovery protocol.
    # Uploaded finance/project code is never imported by this test.
    import json,subprocess,sys
    from atf.runner import RUNNER
    root=str(tmp_path/'sandbox').replace('\\','/')
    runner=RUNNER.replace('/workspace/project',root)
    cases=[
        ({'tests/test_plain.py':'import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+2,4)'},0),
        ({'tests/test_plain.py':'import atf_missing_dependency_xyz'},6),
        ({'tests/test_plain.py':'# no tests'},5),
        ({'tests/test_plain.py':'import unittest\nclass T(unittest.TestCase):\n @unittest.skip("pending")\n def test_skip(self): pass'},7),
    ]
    for files,expected in cases:
        payload=json.dumps(files).encode()
        result=subprocess.run([sys.executable,'-B','-c',runner],input=str(len(payload)).encode()+b'\n'+payload,capture_output=True,timeout=10)
        assert result.returncode==expected,result.stderr.decode()
