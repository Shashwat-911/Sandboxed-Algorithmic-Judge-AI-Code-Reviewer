"""One fresh Playwright process and browser context per studio run."""
import json
import sys
import time
from pathlib import Path
from atf.browser_commands import validate_url


def run(folder):
    request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    result = {'id': folder.name, 'status': 'running', 'project_id': request.get('project_id'),
              'browser': request['browser'], 'steps': [], 'console': [], 'network': [], 'artifacts': [],
              'created_at': request['created_at'], 'error': None}
    started = time.monotonic()

    def save():
        result['duration_ms'] = round((time.monotonic() - started) * 1000)
        temp = folder / 'result.tmp'
        temp.write_text(json.dumps(result), encoding='utf-8')
        # Windows readers briefly lock the destination during dashboard polling.
        for attempt in range(20):
            try:
                temp.replace(folder / 'result.json')
                break
            except PermissionError:
                if attempt == 19: raise
                time.sleep(.025)

    def record(bucket, item):
        if len(result[bucket]) < 200:
            result[bucket].append(item)

    save()
    try:
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = getattr(p, request['browser']).launch(headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 800}, accept_downloads=False)
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(('http://', 'https://')) else route.abort())
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = context.new_page()
            page.set_default_timeout(5000)
            page.set_default_navigation_timeout(15000)
            page.on('console', lambda msg: record('console', {'type': msg.type, 'text': msg.text[:2000]}))
            page.on('pageerror', lambda err: record('console', {'type': 'error', 'text': str(err)[:2000]}))
            page.on('response', lambda res: record('network', {'status': res.status, 'method': res.request.method, 'url': res.url[:1000]}))
            page.on('requestfailed', lambda req: record('network', {'status': 'failed', 'method': req.method, 'url': req.url[:1000]}))
            try:
                for index, step in enumerate(request['steps']):
                    row = {**step, 'status': 'running'}
                    result['steps'].append(row)
                    save()
                    tick = time.monotonic()
                    try:
                        name, args = step['command'], step['args']
                        if name == 'python':
                            project_files = {}
                            if request.get('project_id'):
                                import uuid
                                project_id = str(uuid.UUID(request['project_id']))
                                source_path = folder.parent.parent / 'project-sources' / project_id / 'files.json'
                                if not source_path.exists():
                                    raise ValueError('Reimport this project to make its source files available to native scripts.')
                                project_files = json.loads(source_path.read_text(encoding='utf-8'))
                            _orig_goto = page.goto
                            def _safe_goto(url, *g_args, **g_kwargs):
                                if isinstance(url, str) and url.startswith('/'):
                                    url = 'http://127.0.0.1:8010' + url
                                return _orig_goto(url, *g_args, **g_kwargs)
                            page.goto = _safe_goto
                            globs = {'page': page, 'context': context, 'browser': browser, 'playwright': p, 'expect': expect, 'project_files': project_files, '__name__': '__studio__'}
                            exec(compile(request['commands'], 'studio.py', 'exec'), globs)
                            for k, v in list(globs.items()):
                                if k.startswith('test_') and callable(v):
                                    import inspect
                                    sig = inspect.signature(v)
                                    call_kwargs = {param: globs[param] for param in sig.parameters if param in globs}
                                    v(**call_kwargs)
                        elif name == 'goto': page.goto(validate_url(args[0]), wait_until='domcontentloaded')
                        elif name == 'expect-text': expect(page.locator(args[0])).to_contain_text(args[1])
                        elif name == 'expect-visible': expect(page.locator(args[0])).to_be_visible()
                        elif name == 'expect-title': expect(page).to_have_title(args[0])
                        elif name == 'expect-url': expect(page).to_have_url(args[0])
                        elif name != 'screenshot':
                            method = 'select_option' if name == 'select' else name
                            getattr(page.locator(args[0]), method)(*args[1:])
                        row['status'] = 'passed'
                    except Exception as exc:
                        row.update(status='failed', error=str(exc)[:4000])
                    row['duration_ms'] = round((time.monotonic() - tick) * 1000)
                    try:
                        filename = f'step-{index + 1}.png'
                        page.screenshot(path=str(folder / filename), timeout=3000)
                        row['screenshot'] = filename
                        result['artifacts'].append(filename)
                    except Exception as exc:
                        row['screenshot_error'] = str(exc)[:500]
                    save()
                    if row['status'] == 'failed':
                        break
                result['status'] = 'failed' if any(s['status'] == 'failed' for s in result['steps']) else 'passed'
                for step in request['steps'][len(result['steps']):]:
                    result['steps'].append({**step, 'status': 'skipped'})
            finally:
                try:
                    context.tracing.stop(path=str(folder / 'trace.zip'))
                    result['artifacts'].append('trace.zip')
                finally:
                    browser.close()
    except Exception as exc:
        result.update(status='error', error=str(exc)[:4000])
    finally:
        save()


if __name__ == '__main__':
    run(Path(sys.argv[1]))
