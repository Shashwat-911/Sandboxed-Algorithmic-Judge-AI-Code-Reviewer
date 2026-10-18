# ATF — Automated Testing Framework

A local project-analysis workbench for reviewing a complete source archive, planning tests and edge cases, running existing Python unittest suites in Docker, and producing review reports. Built with FastAPI, SQLite, Docker and optional Ollama, with a responsive browser dashboard.

## Start the demo (Windows)

```powershell
.\start.ps1
```

Open http://127.0.0.1:8000 and select **Try sample project**. Static analysis works immediately without Docker or Ollama. The startup script creates a virtual environment and installs the demo dependencies if needed.

Manual setup (Python 3.11 or newer):

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-demo.txt
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

On Linux/macOS use `.venv/bin/python` for the equivalent commands. Run a single API process; the demo queue is in-process. Reports persist in `.atf/reports.sqlite3`. Uploaded source is held in memory for processing and is not persisted by ATF. Reports, execution output and AI responses can contain project information.

## What is implemented

- ZIP ingestion with traversal and symlink rejection, size limits, source filtering, and enclosing-folder normalization.
- Inventory across Python, JS/TS, Java, C/C++, Go and Rust, plus configuration and documentation.
- Python AST syntax checks and evidence-linked rules for mutable defaults, swallowed exceptions, assertions and long functions; text rules for possible credentials, dynamic evaluation, shell execution and debug configuration.
- Architecture inventory: Python imports and route decorators, common entry points, requirements.txt and package.json dependencies.
- Function-linked test plans covering normal, boundary, invalid and repeated calls. Downloadable unittest **scaffolds are skipped until you implement assertions**.
- Existing Python **standard-library unittest** execution in a non-root Docker container with no network, a read-only root, bounded tmpfs, memory/CPU/process limits, rotating logs and a 20-second execution deadline. No host execution fallback and no automatic installation of uploaded dependencies.
- Optional real local-model review through Ollama, with explicit availability and context-limit reporting.
- Persistent project history; Markdown and JSON report exports; a sample project with reproducible failures.

This is a single-user local demonstration, not a hosted multi-tenant service. It does not prove correctness, measure coverage, audit dependency CVEs, or execute arbitrary language/framework test suites. Static findings are review candidates. AI suggestions require human verification. No artificial quality score or fabricated passing tests.

## Enable real isolated tests

Start Docker Desktop (Linux containers), then provision the runner:

```powershell
docker pull python:3.11-alpine
```

Select **Run Python tests in Docker** before submitting. Tests must follow unittest discovery (`test_*.py`); subdirectories should be importable packages with `__init__.py`. The runner uses Python 3.11 and the standard library only. Missing third-party imports appear as test failures rather than silently installing arbitrary dependencies. A suite with zero discovered tests is reported as `no_tests`, not passed.

The sample has **3 tests: 1 pass, 1 failure, 1 error**. `add_item` shares a mutable default list; `average_price([])` divides by zero. These defects are intentional demonstration fixtures, not defects in ATF itself.

## Enable local AI

Run Ollama locally and provision a model:

```powershell
ollama pull qwen2.5:3b
```

The default endpoint is `http://127.0.0.1:11434` and the default model is `qwen2.5:3b`. Override before starting the API:

```powershell
$env:ATF_OLLAMA_URL='http://127.0.0.1:11434'
$env:ATF_OLLAMA_MODEL='qwen2.5-coder:3b'
.\start.ps1
```

Select **Add local AI review**. Only supported source text is considered; environment files are excluded and basic credential assignments are redacted on a best-effort basis. AI context is bounded to 28,000 characters total and 5,000 per file; the report identifies included files. Large repositories are not fully visible to the model. Static analysis still examines all accepted files. AI is optional and its absence does not erase static results.

## Limits and operation

- Compressed ZIP: 10 MB; expanded files: 20 MB total; single file: 1 MB; archive: 1,000 entries.
- UTF-8 text only. Dependencies, build directories, binary formats and `.env*` are excluded.
- Two concurrent analysis workers; at most six running/queued jobs. Excess work returns HTTP 429.
- Restarted queued/running jobs become `interrupted`; resubmit them. There is no durable queue retry in the local ATF mode.
- Keep the server bound to loopback. Authentication and authorization are not implemented. The Docker daemon is privileged; resource limits are defense in depth, not a security boundary for a public hostile-code service.
- Local storage can be relocated with `ATF_DATA_DIR`. The old `.env` belongs to the legacy judge, not ATF.

## API

Interactive reference: http://127.0.0.1:8000/docs

| Endpoint | Purpose |
| --- | --- |
| `POST /api/projects` | Multipart `file`, `run_tests`, `use_ai`; returns job ID |
| `POST /api/demo` | Submit bundled sample; optional query flags |
| `GET /api/projects` | Recent 100 projects |
| `GET /api/projects/{id}` | Status and complete report |
| `GET /api/projects/{id}/report?format=markdown` | Markdown export |
| `GET /api/projects/{id}/report?format=json` | JSON export |
| `GET /api/projects/{id}/tests` | Proposed unittest scaffold |
| `GET /health` | API liveness, not integration readiness |

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
# Include real Docker isolation, timeout and zero-test checks:
$env:ATF_INTEGRATION='1'
.\.venv\Scripts\python -m pytest -q
```

See [docs/VERIFICATION.md](docs/VERIFICATION.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/DEMO.md](docs/DEMO.md).

## Original distributed judge

The original FastAPI → PostgreSQL → Redis/Celery → Docker → Ollama architecture is retained in `legacy_api.py`, `worker.py`, `sandbox.py`, and `docker-compose.yml`. It is a separate optional service, exposed on loopback port **8001** to avoid the ATF dashboard. Start with `docker compose up --build -d` after reviewing `.env.example`. Its dependencies remain in `requirements.txt` and its image in `Dockerfile`. Pre-pull language images from `sandbox.py` before execution. The legacy distributed stack is not required for the ATF demo and has not been verified end to end in this update.

Corrected legacy defects include log retrieval after container deletion, UUID/string mismatch, detached ORM result access, sandbox construction outside error handling, C++ compiler selection, workspace permissions, and queue-dispatch error reporting. The socket proxy is an API routing restriction, not protection against a compromised worker making dangerous container-create requests.

## Resume description

“Built a local automated project-review framework using FastAPI, SQLite, Docker and Ollama, combining bounded ZIP ingestion, AST-based findings, test-scenario generation, isolated unittest execution and downloadable engineering reports.”

Describe only the supported scope. Do not claim all-language execution, full coverage, vulnerability certification, or production-scale throughput.
