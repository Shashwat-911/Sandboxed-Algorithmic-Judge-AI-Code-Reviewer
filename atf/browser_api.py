"""Persistent local browser runs with a bounded queue and process deadline."""
import importlib.util
import json
import os
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from atf.browser_commands import parse_commands, python_script

router = APIRouter(prefix='/api/playwright', tags=['Playwright Studio'])
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('ATF_DATA_DIR', str(ROOT / '.atf'))) / 'browser-runs'
POOL = ThreadPoolExecutor(max_workers=1)
SLOTS = threading.BoundedSemaphore(4)


class RunRequest(BaseModel):
    mode: Literal['commands', 'python', 'javascript', 'typescript', 'suite'] = 'commands'
    script_style: Literal['body', 'file'] = 'body'
    trusted: bool = False
    commands: str = Field(default='', max_length=100000)
    browser: Literal['chromium', 'firefox', 'webkit'] = 'chromium'
    project_id: str | None = None


def folder_for(run_id):
    try:
        if str(uuid.UUID(run_id)) != run_id: raise ValueError()
    except ValueError:
        raise HTTPException(404, 'Run not found.')
    folder = DATA / run_id
    if not (folder / 'result.json').is_file(): raise HTTPException(404, 'Run not found.')
    return folder


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    for path in DATA.glob('*/result.json'):
        result = json.loads(path.read_text(encoding='utf-8'))
        if result['status'] in ('queued', 'running'):
            result.update(status='interrupted', error='Server restarted. Run the commands again.')
            path.write_text(json.dumps(result), encoding='utf-8')


def execute(folder):
    process = None
    try:
        with (folder / 'worker.log').open('w', encoding='utf-8') as log:
            request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
            native = request.get('mode') in ('javascript', 'typescript', 'suite')
            process = subprocess.Popen([sys.executable, '-m', 'atf.native_worker' if native else 'atf.browser_worker', str(folder.resolve())],
                                       cwd=ROOT, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                       start_new_session=os.name != 'nt')
            try:
                process.wait(timeout=1200 if native else 120)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise TimeoutError('Run exceeded its execution deadline. Child processes were stopped.')
            if process.returncode:
                raise RuntimeError('Browser worker exited unexpectedly. Check local worker.log.')
    except Exception as exc:
        result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        result.update(status='error', error=str(exc))
        (folder / 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finally:
        SLOTS.release()


@router.get('/status')
def readiness():
    available = importlib.util.find_spec('playwright') is not None
    return {'installed': available, 'note': 'Browser binaries must also be installed. Each run checks launch readiness.',
            'setup': '.\\.venv\\Scripts\\python -m playwright install chromium', 'max_commands': 40, 'deadline_seconds': 120}


@router.post('/runs', status_code=202)
def create_run(request: RunRequest):
    if request.mode != 'commands' and not request.trusted:
        raise HTTPException(400, 'Confirm that you trust this code and repository. Native runs execute locally with your user permissions.')
    native = request.mode in ('javascript', 'typescript', 'suite')
    if native and not request.project_id:
        raise HTTPException(400, 'Select an imported repository before running native JavaScript, TypeScript or its suite.')
    try:
        if request.mode == 'python':
            compile(request.commands, 'studio.py', 'exec')
            steps = [{'command': 'python', 'args': [], 'line': 1}]
        elif native:
            if request.mode != 'suite' and not request.commands.strip(): raise ValueError('Enter Playwright code.')
            steps = []
        else:
            steps = parse_commands(request.commands)
    except SyntaxError as exc: raise HTTPException(400, f'Python line {exc.lineno}: {exc.msg}')
    except ValueError as exc: raise HTTPException(400, str(exc))
    if request.project_id:
        from main import project
        attached = project(request.project_id)
        if native and not (DATA.parent / 'project-sources' / request.project_id / 'files.json').exists():
            raise HTTPException(400, 'Reimport this repository to retain its source for native execution.')
    if not SLOTS.acquire(blocking=False): raise HTTPException(429, 'Browser queue is full. Try again shortly.')
    try:
        run_id = str(uuid.uuid4())
        folder = DATA / run_id
        folder.mkdir(parents=True)
        payload = {**request.model_dump(), 'steps': steps, 'created_at': datetime.now(timezone.utc).isoformat()}
        if request.project_id:
            payload.update(source_digest=(attached.get('report') or {}).get('source_digest'), source=(attached.get('report') or {}).get('source'))
        (folder / 'request.json').write_text(json.dumps(payload), encoding='utf-8')
        (folder / 'test_browser.py').write_text(request.commands if request.mode == 'python' else python_script(steps, request.browser), encoding='utf-8')
        (folder / 'result.json').write_text(json.dumps({'id': run_id, 'status': 'queued',
            'project_id': request.project_id, 'browser': request.browser, 'created_at': payload['created_at'],
            'steps': [], 'console': [], 'network': [], 'artifacts': []}), encoding='utf-8')
        POOL.submit(execute, folder)
    except Exception:
        SLOTS.release()
        raise
    return {'id': run_id, 'status': 'queued'}


@router.get('/runs')
def runs(project_id: str | None = None):
    results = []
    for path in DATA.glob('*/result.json'):
        value = json.loads(path.read_text(encoding='utf-8'))
        if project_id is None or value.get('project_id') == project_id:
            results.append({key: value.get(key) for key in ('id', 'status', 'project_id', 'browser', 'created_at')})
    return sorted(results, key=lambda x: x['created_at'], reverse=True)[:50]


@router.get('/runs/{run_id}')
def get_run(run_id: str):
    folder = folder_for(run_id)
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    result['commands'] = json.loads((folder / 'request.json').read_text(encoding='utf-8'))['commands']
    result['mode'] = json.loads((folder / 'request.json').read_text(encoding='utf-8')).get('mode','commands')
    result['script_style'] = json.loads((folder / 'request.json').read_text(encoding='utf-8')).get('script_style','body')
    log = folder / 'execution.log'
    if log.exists():
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-24000))
            result['output']=stream.read().decode('utf-8',errors='replace')
    return result


@router.get('/runs/{run_id}/artifacts/{name:path}')
def artifact(run_id: str, name: str):
    folder = folder_for(run_id)
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    if not (folder/name).resolve().is_relative_to(folder.resolve()) or name not in result.get('artifacts', []) + ['test_browser.py', 'result.json', 'execution.log'] or not (folder / name).is_file():
        raise HTTPException(404, 'Artifact not available.')
    return FileResponse(folder / name, filename=None if name.endswith(('.png','.html','.js','.css')) else Path(name).name)
