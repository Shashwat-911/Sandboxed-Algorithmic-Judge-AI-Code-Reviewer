"""Run trusted repository Playwright suites using their real configuration."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def bounded_process(args, cwd, env, log, timeout):
    process=subprocess.Popen(args,cwd=cwd,env=env,stdout=log,stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
        start_new_session=os.name!='nt')
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal
            os.killpg(process.pid,signal.SIGKILL)
        process.wait()
        raise TimeoutError(f'Process exceeded {timeout} seconds; its child processes were stopped.')
    return process


def run(folder):
    request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    started = time.monotonic()
    result.update(status='running', phase='Preparing repository', errors=[], tests=[], setup=[], mode=request['mode'])
    def save():
        result['duration_ms'] = round((time.monotonic()-started)*1000)
        # Readers retry while this small result is replaced.
        temp = folder / 'native.tmp'
        temp.write_text(json.dumps(result), encoding='utf-8')
        for attempt in range(40):
            try:
                temp.replace(folder / 'result.json')
                break
            except PermissionError:
                time.sleep(.025)
    save()
    try:
        sources = folder.parent.parent / 'project-sources' / request['project_id'] / 'files.json'
        files = json.loads(sources.read_text(encoding='utf-8'))
        workspace = sources.parent / 'workspace'
        workspace.mkdir(exist_ok=True)
        for name, content in files.items():
            target = (workspace / name).resolve()
            if not target.is_relative_to(workspace.resolve()):
                raise ValueError('Unsafe source path')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        result['source_digest'] = request.get('source_digest')
        result['source'] = request.get('source')
        env = os.environ.copy()
        env.update(CI='1', PYTHONUTF8='1', PLAYWRIGHT_HTML_OPEN='never')
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        node = shutil.which('node')
        if not npm or not node:
            raise RuntimeError('Node.js and npm are required. Install Node.js, then restart ATF.')
        def command(args, phase, timeout=300):
            result['phase'] = phase
            save()
            tick = time.monotonic()
            with (folder / 'execution.log').open('a', encoding='utf-8') as log:
                log.write('\n' + phase + '\n'); log.flush()
                completed = bounded_process(args, workspace, env, log, timeout)
            result['setup'].append({'phase': phase, 'exit_code': completed.returncode, 'duration_ms': round((time.monotonic()-tick)*1000)})
            save()
            if completed.returncode:
                raise RuntimeError(f'{phase} failed (exit {completed.returncode}). See execution.log.')
        if 'package.json' not in files:
            raise ValueError('This repository needs a root package.json with @playwright/test and a Playwright configuration.')
        fingerprint = hashlib.sha256((files.get('package-lock.json','')+files['package.json']).encode()).hexdigest()
        marker = workspace / '.atf-node-ready'
        if not marker.exists() or marker.read_text()!=fingerprint or not (workspace/'node_modules/@playwright/test').exists():
            command([npm, 'ci' if 'package-lock.json' in files else 'install', '--ignore-scripts', '--no-audit', '--no-fund'], 'Install Node dependencies')
            marker.write_text(fingerprint)
        python = sys.executable
        if 'requirements-playwright.txt' in files:
            venv = workspace / '.atf-venv'
            python = str(venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
            if not Path(python).exists(): command([sys.executable, '-m', 'venv', str(venv)], 'Create repository Python environment')
            req_hash = hashlib.sha256(files['requirements-playwright.txt'].encode()).hexdigest()
            req_marker = workspace / '.atf-python-ready'
            if not req_marker.exists() or req_marker.read_text()!=req_hash:
                command([python, '-m', 'pip', 'install', '-r', 'requirements-playwright.txt'], 'Install browser-server Python dependencies')
                req_marker.write_text(req_hash)
        env['PLAYWRIGHT_PYTHON'] = python
        cli = workspace / 'node_modules/@playwright/test/cli.js'
        if not cli.is_file(): raise ValueError('The repository does not provide @playwright/test.')
        command([node, str(cli), 'install', request['browser']], 'Prepare browser')
        configs = [name for name in files if '/' not in name and name.startswith('playwright.config.')]
        if len(configs)!=1: raise ValueError('Exactly one root playwright.config file is required.')
        config = workspace / 'atf-run.config.ts'
        extra = ''
        if request['mode'] != 'suite':
            is_ts = request['mode'] == 'typescript'
            extension = 'ts' if is_ts else 'js'
            for old in workspace.glob('atf-editor.spec.*'):
                try: old.unlink()
                except Exception: pass
            spec = workspace / f'atf-editor.spec.{extension}'
            code = request['commands']
            has_test_decl = any(kw in code for kw in ('test(', 'test.only(', 'test.skip(', 'test.describe('))
            if request.get('script_style') == 'body' or not has_test_decl:
                code = "import {test, expect} from '@playwright/test';\ntest('Studio script', async ({page, context, browser, request, baseURL}) => {\n" + code + '\n});\n'
            elif 'from \'@playwright/test\'' not in code and 'require(\'@playwright/test\')' not in code:
                code = "import {test, expect} from '@playwright/test';\n" + code
            spec.write_text(code, encoding='utf-8')
            shutil.copyfile(spec, folder / spec.name)
            extra = f'testDir: {json.dumps(str(workspace))}, testMatch: {json.dumps(spec.name)},'
        config.write_text("import original from './"+configs[0]+"';\nexport default {...original, "+extra+" workers:1, retries:0, globalTimeout:300000, outputDir:"+json.dumps(str(folder/'test-results'))+", reporter:[['list'],['json',{outputFile:"+json.dumps(str(folder/'playwright.json'))+"}],['html',{outputFolder:"+json.dumps(str(folder/'html-report'))+",open:'never'}]], use:{...original.use,trace:'on',screenshot:'on',video:'retain-on-failure'}};", encoding='utf-8')
        result['phase']='Running Playwright (repository webServer starts automatically)'; save()
        with (folder/'execution.log').open('a',encoding='utf-8') as log:
            completed = bounded_process([node,str(cli),'test','--config',str(config),'--project',request['browser']], workspace,env,log,360)
        result['exit_code']=completed.returncode
        report_path=folder/'playwright.json'
        if not report_path.exists(): raise RuntimeError('Playwright did not produce a report. Inspect execution.log for configuration or startup errors.')
        report=json.loads(report_path.read_text(encoding='utf-8'))
        result['errors']=report.get('errors',[])
        def walk(suites):
            for suite in suites:
                for spec in suite.get('specs',[]):
                    for test in spec.get('tests',[]):
                        attempts=test.get('results',[])
                        latest=attempts[-1] if attempts else {}
                        row={'title':spec['title'],'file':spec.get('file'),'line':spec.get('line'), 'project':test.get('projectName'),'status':latest.get('status','skipped'),'expected_status':test.get('expectedStatus'),'duration_ms':sum(a.get('duration',0) for a in attempts),'errors':latest.get('errors',[])}
                        result['tests'].append(row)
                        screenshot=next((a.get('path') for a in latest.get('attachments',[]) if a.get('contentType')=='image/png'),None)
                        step={'command':spec['title'],'args':[], 'line':spec.get('line',0),'status':row['status'],'duration_ms':row['duration_ms']}
                        if row['errors']: step['error']='\n'.join(e.get('message','') for e in row['errors'])
                        if screenshot and Path(screenshot).resolve().is_relative_to(folder.resolve()): step['screenshot']=Path(screenshot).resolve().relative_to(folder.resolve()).as_posix()
                        result['steps'].append(step)
                walk(suite.get('suites',[]))
        walk(report.get('suites',[]))
        counts={key:sum(t['status']==key for t in result['tests']) for key in ('passed','failed','skipped','timedOut','interrupted')}
        result['counts']=counts
        result['status']=('passed' if completed.returncode==0 and any(t['status']!='skipped' for t in result['tests']) else
                          'all_skipped' if completed.returncode==0 and result['tests'] else
                          'error' if result['errors'] or not result['tests'] else 'failed')
        result['phase']='Finished'
        if result['status']!='passed': result['error']='Playwright did not pass. Inspect test errors and execution.log.'
    except Exception as exc:
        result.update(status='error',error=str(exc),phase='Stopped')
    finally:
        result['artifacts']=[p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.name not in {'result.json','native.tmp','request.json','worker.log'}]
        log=folder/'execution.log'
        if log.exists(): result['output']=log.read_text(encoding='utf-8',errors='replace')[-24000:]
        result['note']='Repository tests and native code run locally with your user permissions. Passing tests cover their assertions only; fixture-based tests do not validate live services or AI accuracy.'
        save()


if __name__=='__main__': run(Path(sys.argv[1]).resolve())
