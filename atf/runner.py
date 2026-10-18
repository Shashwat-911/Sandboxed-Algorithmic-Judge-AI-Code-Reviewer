"""Execute existing Python unittest suites in a constrained Docker container only."""
import json
import logging
import time
import docker
from docker.types import LogConfig

RUNNER = '''import os,json,unittest,sys
from pathlib import Path
size=int(sys.stdin.buffer.readline())
files=json.loads(sys.stdin.buffer.read(size))
for name,source in files.items():
 path=Path('/workspace/project')/name
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(source,encoding='utf-8')
os.chdir('/workspace/project')
sys.path.insert(0,os.getcwd())
suite=unittest.defaultTestLoader.discover('.')
count=suite.countTestCases()
print('Discovered tests:',count,flush=True)
if count == 0: sys.exit(5)
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
'''

def execute_tests(files, enabled=False):
    if not enabled:
        return dict(status='not_requested', detail='Enable isolated tests to execute an existing Python unittest suite. No source was executed.', output='')
    if not any(p.rsplit('/', 1)[-1].startswith('test_') and p.endswith('.py') for p in files):
        return dict(status='skipped', detail='No Python test_*.py suite found. Other test frameworks require a future runner.', output='')
    if sum(len(source.encode()) for source in files.values()) > 20 * 1024 * 1024 or len(files) > 2000:
        return dict(status='skipped', detail='Project exceeds the isolated runner budget (20 MB source / 2,000 files). Static analysis remains available.', output='')
    client = container = stream = None
    started = time.monotonic()
    try:
        client = docker.from_env(timeout=5)
        client.ping()
        # Images are provisioned by the operator, never pulled as an upload side effect.
        client.images.get('python:3.11-alpine')
        container = client.containers.create('python:3.11-alpine',
            command=['python', '-B', '-c', RUNNER], network_mode='none', read_only=True, stdin_open=True,
            tmpfs={'/workspace': 'rw,size=48m,mode=1777', '/tmp': 'rw,size=16m,mode=1777'},
            user='65534:65534', cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
            mem_limit='256m', memswap_limit='256m', nano_cpus=1_000_000_000, pids_limit=64,
            log_config=LogConfig(type='local', config={'max-size': '64k', 'max-file': '2'}))
        stream = container.attach_socket(params={'stdin': 1, 'stream': 1})
        container.start()
        payload = json.dumps(files).encode()
        getattr(stream, '_sock', stream).sendall(str(len(payload)).encode() + b'\n' + payload)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            container.reload()
            if container.status in ('exited', 'dead'):
                break
            time.sleep(.2)
        else:
            container.kill()
            return dict(status='timeout', detail='Suite exceeded the 20 second execution deadline.', output='', duration_ms=round((time.monotonic()-started)*1000))
        code = container.attrs['State']['ExitCode']
        output = container.logs(tail=150).decode('utf-8', errors='replace')[-16000:]
        status = 'passed' if code == 0 else 'no_tests' if code == 5 else 'failed'
        return dict(status=status, detail='Existing Python unittest suite; no dependencies installed. Output is untrusted project output.', exit_code=code, output=output, duration_ms=round((time.monotonic()-started)*1000))
    except docker.errors.ImageNotFound:
        return dict(status='unavailable', detail='Runner image missing. Run: docker pull python:3.11-alpine', output='')
    except Exception as exc:
        logging.getLogger(__name__).exception("Isolated runner failed")
        return dict(status='unavailable', detail=f'Docker execution unavailable ({type(exc).__name__}). Start Docker Desktop and provision the runner image.', output='')
    finally:
        if stream is not None:
            try: stream.close()
            except Exception: pass
        if container is not None:
            try: container.remove(force=True)
            except Exception: pass
        if client is not None:
            client.close()
