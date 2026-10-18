"""Local single-process ATF API; durable SQLite reports, bounded background jobs."""
import io
import json
import os
import sqlite3
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from atf.archive import read_archive, MAX_UPLOAD
from atf.analyzer import analyze
from atf.runner import execute_tests
from atf.ai import review

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv('ATF_DATA_DIR', str(ROOT / '.atf')))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'reports.sqlite3'
POOL = ThreadPoolExecutor(max_workers=2)
SLOTS = threading.BoundedSemaphore(6)

def connection():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def initialize():
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, name TEXT, created_at TEXT, status TEXT, report TEXT)')
        db.execute("UPDATE reports SET status='interrupted' WHERE status IN ('queued','running')")

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield

app = FastAPI(title='ATF — Project Intelligence', version='2.0.0', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'atf', 'mode': 'local single-user', 'execution': 'Docker only', 'ai': 'optional Ollama'}

@app.get('/api/projects')
def projects():
    with connection() as db:
        return [dict(row) for row in db.execute('SELECT id,name,created_at,status FROM reports ORDER BY created_at DESC LIMIT 100')]

@app.get('/api/projects/{job_id}')
def project(job_id: str):
    with connection() as db:
        row = db.execute('SELECT * FROM reports WHERE id=?', (job_id,)).fetchone()
    if not row: raise HTTPException(404, 'Project not found.')
    result = dict(row)
    result['report'] = json.loads(result['report']) if result['report'] else None
    return result

def process(job_id, files, skipped, run_tests, use_ai):
    try:
        with connection() as db:
            db.execute("UPDATE reports SET status='running' WHERE id=?", (job_id,))
        report = analyze(files)
        report['skipped_files'] = skipped
        report['execution'] = execute_tests(files, run_tests)
        report['ai'] = review(files, report, use_ai)
        with connection() as db:
            db.execute("UPDATE reports SET status='completed',report=? WHERE id=?", (json.dumps(report), job_id))
    except Exception as exc:
        with connection() as db:
            db.execute("UPDATE reports SET status='failed',report=? WHERE id=?", (json.dumps({'error': f'Analysis failed ({type(exc).__name__}).'}), job_id))
    finally:
        SLOTS.release()

def enqueue(data, name, run_tests, use_ai):
    try: files, skipped = read_archive(data)
    except ValueError as exc: raise HTTPException(400, str(exc))
    if not SLOTS.acquire(blocking=False): raise HTTPException(429, 'Analysis queue is full. Try again shortly.')
    job_id = str(uuid.uuid4())
    try:
        with connection() as db:
            db.execute('INSERT INTO reports VALUES (?,?,?,?,?)', (job_id, name[:120], datetime.now(timezone.utc).isoformat(), 'queued', None))
        POOL.submit(process, job_id, files, skipped, run_tests, use_ai)
    except Exception:
        SLOTS.release()
        raise
    return {'id': job_id, 'status': 'queued'}

@app.post('/api/projects', status_code=202)
async def upload(file: UploadFile = File(...), run_tests: bool = Form(False), use_ai: bool = Form(False)):
    try: data = await file.read(MAX_UPLOAD + 1)
    finally: await file.close()
    if len(data) > MAX_UPLOAD: raise HTTPException(413, 'Upload exceeds 10 MB.')
    return enqueue(data, file.filename or 'Uploaded project', run_tests, use_ai)

@app.post('/api/demo', status_code=202)
def demo(run_tests: bool = False, use_ai: bool = False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for path in sorted((ROOT / 'examples' / 'cart').rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path, path.relative_to(ROOT / 'examples' / 'cart'))
    return enqueue(stream.getvalue(), 'Cart service · sample project', run_tests, use_ai)

@app.get('/api/projects/{job_id}/report')
def export(job_id: str, format: str = 'markdown'):
    result = project(job_id)
    if result['status'] != 'completed': raise HTTPException(409, 'Report is not ready.')
    if format == 'json':
        return Response(json.dumps(result, indent=2), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="atf-{job_id}.json"'})
    if format != 'markdown': raise HTTPException(400, 'Choose markdown or json.')
    r = result['report']
    lines = [f"# ATF report: {result['name']}", f"Created: {result['created_at']}", '\n## Summary', json.dumps(r['summary'], indent=2), '\n## Architecture', json.dumps(r['architecture'], indent=2), '\n## Findings']
    for f in r['findings']:
        lines.append(f"- [{f['severity'].upper()}] {f['title']} — {f['file']}:{f['line']} ({f['rule']})\n  {f['recommendation']}")
    lines += ['\n## Execution', r['execution']['status'], r['execution']['detail'], '```text\n'+r['execution']['output']+'\n```', '\n## Proposed test cases']
    for t in r['test_plan']:
        lines.append(f"- {t['id']} / {t['target']} / {t['category']}: {t['scenario']} Expected: {t['expected']} ({t['status']})")
    lines += ['\n## Local AI review', r['ai']['status'], r['ai']['text'], '\n## Future scope', *['- '+s for s in r['future_scope']], '\n## Limitations', *['- '+s for s in r['limitations']]]
    return Response('\n\n'.join(lines), media_type='text/markdown', headers={'Content-Disposition': f'attachment; filename="atf-{job_id}.md"'})


@app.get('/api/projects/{job_id}/tests')
def test_scaffold(job_id: str):
    result = project(job_id)
    if result['status'] != 'completed': raise HTTPException(409, 'Report is not ready.')
    lines = ['"""Generated test scaffold. Replace each skip with domain-specific assertions."""', 'import unittest', '', 'class ProposedTests(unittest.TestCase):']
    for case in result['report']['test_plan']:
        lines += [f"    def test_{case['id'].replace('-', '_').lower()}(self):", '        # ' + case['target'].replace('\n',' ') + ': ' + case['category'], '        # ' + case['scenario'], '        self.skipTest("Implement the expected behavior from your project specification")', '']
    lines += ['', 'if __name__ == "__main__":', '    unittest.main()']
    return Response('\n'.join(lines), media_type='text/plain', headers={'Content-Disposition': f'attachment; filename="test_plan_{job_id}.py"'})
