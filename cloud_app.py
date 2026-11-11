"""Public deployment: private visitor workspaces and bounded workshop execution.

Run the unrestricted local developer workbench with main:app instead.
"""
import hashlib
import os
import secrets
import time
from contextlib import asynccontextmanager

os.environ['ATF_PUBLIC_DEMO'] = '1'
os.environ.setdefault('ATF_MAX_UPLOAD_MB', '5')
os.environ.setdefault('ATF_MAX_EXPANDED_MB', '20')
os.environ.setdefault('ATF_MAX_SOURCE_MB', '5')
os.environ.setdefault('ATF_MAX_FILE_MB', '1')
os.environ.setdefault('ATF_MAX_ARCHIVE_ENTRIES', '1500')

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import main
from atf import browser_api
from atf.browser_commands import parse_commands

COOKIE = 'sandbox_workspace'
TARGET = 'https://sandbox-demo.invalid/workshop'

@asynccontextmanager
async def lifespan(app):
    main.initialize()
    browser_api.initialize()
    with main.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS public_owners (id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL, created REAL NOT NULL)')
    yield

app = FastAPI(title='Sandbox AI — Project Review & Browser Testing', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=main.ROOT / 'static'), name='static')

class BodyLimit:
    """Bound multipart uploads before parsing, including chunked requests."""
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            chunk = message.get('body', b'')
            total += len(chunk)
            if total > 6 * 1024 * 1024:
                return await JSONResponse({'detail': 'Upload exceeds the public demo limit.'}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body'): break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)

app.add_middleware(BodyLimit)

@app.middleware('http')
async def workspace(request: Request, call_next):
    token = request.cookies.get(COOKIE, '')
    fresh = len(token) != 64 or any(c not in '0123456789abcdef' for c in token)
    if fresh: token = secrets.token_hex(32)
    request.state.owner = hashlib.sha256(token.encode()).hexdigest()
    if request.method == 'POST':
        from urllib.parse import urlsplit
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and urlsplit(origin).netloc != request.headers.get('host')):
            return JSONResponse({'detail': 'Use the application on this site to submit jobs.'}, status_code=403)
        with main.connection() as db:
            recent = db.execute('SELECT COUNT(*) FROM public_owners WHERE owner=? AND created>?', (request.state.owner, time.time()-60)).fetchone()[0]
            total = db.execute('SELECT COUNT(*) FROM public_owners').fetchone()[0]
        if recent >= 4 or total >= 250:
            return JSONResponse({'detail': 'Demo capacity reached. Please try again later.'}, status_code=429)
    response = await call_next(request)
    if fresh:
        response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme == 'https' or bool(os.getenv('RENDER')), samesite='lax', max_age=86400)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

def own(request, result, kind):
    with main.connection() as db:
        db.execute('INSERT INTO public_owners VALUES (?,?,?,?)', (result['id'], request.state.owner, kind, time.time()))
    return result

def check(request, identifier, kind):
    with main.connection() as db:
        found = db.execute('SELECT 1 FROM public_owners WHERE id=? AND owner=? AND kind=?', (identifier, request.state.owner, kind)).fetchone()
    if not found: raise HTTPException(404, 'Item not found in this browser workspace.')

def visible(request, kind):
    with main.connection() as db:
        return {row['id'] for row in db.execute('SELECT id FROM public_owners WHERE owner=? AND kind=?', (request.state.owner, kind))}

def integrations(run_tests, use_ai):
    if run_tests or use_ai:
        raise HTTPException(422, 'Docker execution and Ollama require a provisioned private runtime. Public demo supports source review and real Chromium workshop journeys.')

@app.get('/', response_class=HTMLResponse)
def index():
    html = (main.ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
    html = html.replace('ATF · Playwright Studio', 'Sandbox AI · Code Review & Browser Testing')
    html = html.replace('Local workspace', 'Public demo').replace('Your code. Your environment.', 'Your browser. Your workspace.').replace('LOCAL FIRST', 'LIVE DEMO')
    html = html.replace('</body>', '<script src="/static/cloud.js"></script></body>')
    return html

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'Sandbox AI', 'mode': 'public demo', 'browser_execution': 'Chromium workshop', 'docker_execution': False, 'local_ai': False}

@app.get('/api/limits')
def limits(): return main.limits()

@app.get('/api/projects')
def projects(request: Request):
    ids = visible(request, 'project')
    return [row for row in main.projects() if row['id'] in ids]

@app.get('/api/projects/{job_id}')
def project(job_id: str, request: Request):
    check(request, job_id, 'project')
    return main.project(job_id)

@app.post('/api/projects', status_code=202)
async def upload(request: Request, file: UploadFile = File(...), run_tests: bool = Form(False), use_ai: bool = Form(False)):
    integrations(run_tests, use_ai)
    return own(request, await main.upload(file, False, False), 'project')

@app.post('/api/repositories', status_code=202)
def repository(body: main.RepositoryRequest, request: Request):
    integrations(body.run_tests, body.use_ai)
    return own(request, main.import_repository(body), 'project')

@app.post('/api/demo', status_code=202)
def demo(request: Request, run_tests: bool = False, use_ai: bool = False):
    integrations(run_tests, use_ai)
    return own(request, main.demo(False, False), 'project')

@app.get('/api/projects/{job_id}/report')
def report(job_id: str, request: Request, format: str = 'markdown'):
    check(request, job_id, 'project')
    return main.export(job_id, format)

@app.get('/api/projects/{job_id}/tests')
def scaffold(job_id: str, request: Request):
    check(request, job_id, 'project')
    return main.test_scaffold(job_id)

@app.get('/api/playwright/status')
def readiness(): return browser_api.readiness()

@app.post('/api/playwright/runs', status_code=202)
def create_run(body: browser_api.RunRequest, request: Request):
    if body.mode != 'commands' or body.browser != 'chromium':
        raise HTTPException(422, 'The public demo runs guided Chromium journeys. Native repository code requires a private execution environment.')
    try: steps = parse_commands(body.commands)
    except ValueError as exc: raise HTTPException(400, str(exc))
    if any(s['command'] in ('goto', 'expect-url') and s['args'][0] != TARGET for s in steps):
        raise HTTPException(422, 'Use Load workshop example. Public journeys are restricted to the included task board.')
    if body.project_id: check(request, body.project_id, 'project')
    return own(request, browser_api.create_run(body), 'browser')

@app.get('/api/playwright/runs')
def runs(request: Request, project_id: str | None = None):
    if project_id: check(request, project_id, 'project')
    ids = visible(request, 'browser')
    return [row for row in browser_api.runs(project_id) if row['id'] in ids]

@app.get('/api/playwright/runs/{run_id}')
def run(run_id: str, request: Request):
    check(request, run_id, 'browser')
    return browser_api.get_run(run_id)

@app.get('/api/playwright/runs/{run_id}/artifacts/{name:path}')
def artifact(run_id: str, name: str, request: Request):
    check(request, run_id, 'browser')
    return browser_api.artifact(run_id, name)

