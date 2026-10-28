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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from atf.limits import MAX_EXPANDED, MAX_SOURCE, MAX_FILE, MAX_ENTRIES, MIB
from atf.repository import repository_archive, parse_repository
from atf.archive import read_archive, MAX_UPLOAD
from atf.analyzer import analyze
from atf.runner import execute_tests
from atf.ai import review
from atf.verification import verification
from atf import browser_api
from atf.playwright_inventory import inspect_playwright

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
    browser_api.initialize()
    yield

app = FastAPI(title='ATF â€” Project Intelligence', version='3.0.0', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
app.include_router(browser_api.router)

@app.middleware('http')
async def protect_local_execution(request: Request, call_next):
    if request.url.path.startswith('/api/playwright') and request.method=='POST':
        origin=request.headers.get('origin')
        from urllib.parse import urlsplit
        if origin and urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail':'Cross-origin execution is not allowed.'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'detail':'Cross-site execution is not allowed.'},status_code=403)
        if not request.headers.get('content-type','').startswith('application/json'):
            return JSONResponse({'detail':'Execution requests require application/json.'},status_code=415)
    return await call_next(request)

@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'atf', 'mode': 'local single-user', 'execution': 'Python unittest: Docker; browser journeys: local Playwright worker', 'ai': 'optional Ollama'}

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
    if result['report'] and result['status']=='completed':
        from atf.evidence import enrich
        enrich(result['report'], job_id, DATA)
        result['report']['verification'] = verification(result['report'])
    return result

def process(job_id, files, skipped, run_tests, use_ai, source=None):
    try:
        with connection() as db:
            db.execute("UPDATE reports SET status='running' WHERE id=?", (job_id,))
        report = analyze(files)
        source_folder = DATA / 'project-sources' / job_id
        source_folder.mkdir(parents=True, exist_ok=True)
        (source_folder / 'files.json').write_text(json.dumps(files), encoding='utf-8')
        report['playwright'] = inspect_playwright(files)
        report['source'] = source or {'kind': 'zip'}
        report['skipped_files'] = skipped
        report['execution'] = execute_tests(files, run_tests)
        report['ai'] = review(files, report, use_ai)
        report['verification'] = verification(report)
        with connection() as db:
            db.execute("UPDATE reports SET status='completed',report=? WHERE id=?", (json.dumps(report), job_id))
    except Exception as exc:
        with connection() as db:
            db.execute("UPDATE reports SET status='failed',report=? WHERE id=?", (json.dumps({'error': f'Analysis failed ({type(exc).__name__}).'}), job_id))
    finally:
        SLOTS.release()

def enqueue(data, name, run_tests, use_ai, source=None, reserved=False):
    if not reserved and not SLOTS.acquire(blocking=False):
        raise HTTPException(429, 'Analysis queue is full. Try again shortly.')
    job_id = str(uuid.uuid4())
    try:
        try: files, skipped = read_archive(data)
        except ValueError as exc: raise HTTPException(400, str(exc))
        with connection() as db:
            db.execute('INSERT INTO reports VALUES (?,?,?,?,?)', (job_id, name[:120], datetime.now(timezone.utc).isoformat(), 'queued', None))
        POOL.submit(process, job_id, files, skipped, run_tests, use_ai, source)
    except Exception:
        SLOTS.release()
        raise
    return {'id': job_id, 'status': 'queued'}

@app.get('/api/limits')
def limits():
    return {'upload_bytes': MAX_UPLOAD, 'upload_mb': MAX_UPLOAD // MIB,
            'expanded_mb': MAX_EXPANDED // MIB, 'source_mb': MAX_SOURCE // MIB,
            'file_mb': MAX_FILE // MIB, 'entries': MAX_ENTRIES}

@app.post('/api/projects', status_code=202)
async def upload(file: UploadFile = File(...), run_tests: bool = Form(False), use_ai: bool = Form(False)):
    try:
        # Inspect the spooled file without copying the whole upload into memory.
        file.file.seek(0, 2)
        if file.file.tell() > MAX_UPLOAD:
            raise HTTPException(413, f'Upload exceeds {MAX_UPLOAD // MIB} MB.')
        file.file.seek(0)
        return await run_in_threadpool(enqueue, file.file, file.filename or 'Uploaded project', run_tests, use_ai)
    finally:
        await file.close()

class RepositoryRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    ref: str = Field(default='', max_length=200)
    run_tests: bool = False
    use_ai: bool = False

@app.post('/api/repositories', status_code=202)
def import_repository(request: RepositoryRequest):
    try: parse_repository(request.url, request.ref)
    except ValueError as exc: raise HTTPException(400, str(exc))
    if not SLOTS.acquire(blocking=False):
        raise HTTPException(429, 'Analysis queue is full. Try again shortly.')
    transferred = False
    try:
        with repository_archive(request.url, request.ref) as (archive, source):
            # enqueue/process owns and releases the reservation from this point.
            transferred = True
            return enqueue(archive, source['url'].removeprefix('https://github.com/'),
                           request.run_tests, request.use_ai, source, reserved=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    finally:
        if not transferred: SLOTS.release()

@app.post('/api/demo', status_code=202)
def demo(run_tests: bool = False, use_ai: bool = False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for path in sorted((ROOT / 'examples' / 'cart').rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path, path.relative_to(ROOT / 'examples' / 'cart'))
    return enqueue(stream.getvalue(), 'Cart service - sample project', run_tests, use_ai)

@app.get('/api/projects/{job_id}/report')
def export(job_id: str, format: str = 'markdown'):
    result = project(job_id)
    if result['status'] != 'completed': raise HTTPException(409, 'Report is not ready.')
    if format == 'pdf':
        from atf.pdf_report import render_report
        return Response(render_report(result), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="atf-{job_id}.pdf"'})
    if format == 'json':
        return Response(json.dumps(result, indent=2), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="atf-{job_id}.json"'})
    if format != 'markdown': raise HTTPException(400, 'Choose markdown, json or pdf.')
    from atf.report_markdown import render as render_markdown
    return Response(render_markdown(result), media_type='text/markdown', headers={'Content-Disposition': f'attachment; filename="atf-{job_id}.md"'})


@app.get('/api/projects/{job_id}/tests')
def test_scaffold(job_id: str):
    result = project(job_id)
    if result['status'] != 'completed': raise HTTPException(409, 'Report is not ready.')
    lines = ['"""Generated test scaffold. Replace each skip with domain-specific assertions."""', 'import unittest', '', 'class ProposedTests(unittest.TestCase):']
    for case in result['report']['test_plan']:
        lines += [f"    def test_{case['id'].replace('-', '_').lower()}(self):", '        # ' + case['target'].replace('\n',' ') + ': ' + case['category'], '        # ' + case['scenario'], '        self.skipTest("Implement the expected behavior from your project specification")', '']
    lines += ['', 'if __name__ == "__main__":', '    unittest.main()']
    return Response('\n'.join(lines), media_type='text/plain', headers={'Content-Disposition': f'attachment; filename="test_plan_{job_id}.py"'})
