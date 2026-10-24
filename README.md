# ATF — Automated Testing Framework

A local project-analysis workbench for reviewing a source ZIP or public GitHub repository snapshot, planning tests and edge cases, running existing Python unittest suites in Docker, and producing review reports. Built with FastAPI, SQLite, Docker and optional Ollama, with a responsive browser dashboard.

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
- Python AST syntax checks and context-aware rules for mutable defaults, swallowed exceptions, assertions, long functions, possible credentials, dynamic evaluation, shell execution and debug configuration. Non-Python files receive inventory only.
- Architecture inventory: Python imports and route decorators, common entry points, requirements.txt and package.json dependencies.
- Evidence-linked proposed scenarios for up to 80 production functions, balanced across source files with explicit selection and omission counts. These are planning suggestions, not executed tests or measured coverage. Downloadable unittest **scaffolds are skipped until you implement assertions**.
- Existing Python **standard-library unittest** execution in a non-root Docker container with no network, a read-only root, bounded tmpfs, memory/CPU/process limits, rotating logs and a 20-second execution deadline. No host execution fallback and no automatic installation of uploaded dependencies.
- Optional real local-model review through Ollama, with explicit availability and context-limit reporting.
- Persistent project history; PDF, Markdown and JSON report exports; a sample project with reproducible failures.

This is a single-user local demonstration, not a hosted multi-tenant service. It does not prove correctness, measure coverage, audit dependency CVEs, or execute arbitrary language/framework test suites. Static findings are review candidates. AI suggestions require human verification. No artificial quality score or fabricated passing tests.

## Upload a ZIP or import a GitHub repository

Choose **Upload ZIP** for a local project (up to 100 MB), or **GitHub repository** and paste a repository root URL such as `https://github.com/Shashwat-911/Sandboxed-Algorithmic-Judge-AI-Code-Reviewer`.

Leave the ref field empty for the default branch, or enter a branch, tag, or commit SHA. Branch names containing slashes are supported. The app downloads a bounded ZIP snapshot into a temporary file and applies the same filtering and analysis pipeline as an upload. The report records the repository URL and requested ref. Use a commit SHA for reproducibility; a branch name or HEAD can change.

Only **public GitHub repositories** are supported in this version. Private repositories can be uploaded as ZIPs; no credentials are requested or stored. GitLab, Bitbucket, arbitrary Git servers, SSH URLs, submodule contents and Git LFS objects are not imported. Downloads do not run Git hooks, install dependencies, or execute source on the host. Downloads time out after approximately two minutes (plus an in-flight read timeout) and reject redirects to other destinations.

Limits are configurable with positive integer environment variables before starting the API:

```powershell
$env:ATF_MAX_UPLOAD_MB='100'
$env:ATF_MAX_EXPANDED_MB='500'
$env:ATF_MAX_SOURCE_MB='50'
$env:ATF_MAX_FILE_MB='5'
$env:ATF_MAX_ARCHIVE_ENTRIES='20000'
.\start.ps1
```

Values use 1,048,576-byte units, displayed as MB. Zero/unlimited is intentionally unsupported: decompression and Python AST analysis consume memory. Larger source budgets require enough local RAM. Files excluded as binaries/dependencies count toward the expanded metadata limit but are never decompressed by the analyzer. Uploads use FastAPI's disk-backed spool; the archive is not copied into a second full-size in-memory buffer. This remains a local single-user app, not an Internet-facing upload service with proxy-level request quotas.

## Enable real isolated tests

Start Docker Desktop (Linux containers), then provision the runner:

```powershell
docker pull python:3.11-alpine
```

Select **Run Python tests in Docker** before submitting. Tests must follow unittest discovery (`test_*.py`); test directories without `__init__.py` are also discovered. The runner uses Python 3.11 and the standard library only. Missing third-party imports are reported as `blocked_dependencies`; dependencies are not installed automatically. An entirely skipped suite is `all_skipped`, never passed. A suite with zero discovered tests is reported as `no_tests`, not passed. Docker execution is skipped for projects over 20 MB of accepted source or 2,000 files, preserving its memory/tmpfs budget; static analysis still completes.

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

Select **Add local AI review**. Only supported source text is considered; environment files are excluded and basic credential assignments are redacted on a best-effort basis. AI context is bounded to 28,000 characters total and 1,400 per file, prioritizing production source across modules and excerpts near findings; the report identifies included and omitted files. Large repositories are not fully visible to the model. Python static analysis examines accepted Python files; other accepted files contribute inventory. AI is optional and its absence does not erase static results.

## Limits and operation

- Compressed ZIP / repository snapshot: **100 MB**; expanded archive: **500 MB**; supported source for analysis: **50 MB**; archive: **20,000 entries**. Supported files larger than **5 MB** are skipped and listed in the report. Large binaries and dependency directories are filtered before decompression.
- UTF-8 text only. Dependencies, build directories, binary formats, oversized files and `.env*` are excluded. Increasing the ZIP limit does not enlarge the AI context window.
- Two concurrent analysis workers; at most six running/queued jobs. Excess work returns HTTP 429.
- Restarted queued/running jobs become `interrupted`; resubmit them. There is no durable queue retry in the local ATF mode.
- Keep the server bound to loopback. Authentication and authorization are not implemented. The Docker daemon is privileged; resource limits are defense in depth, not a security boundary for a public hostile-code service.
- Local storage can be relocated with `ATF_DATA_DIR`. The old `.env` belongs to the legacy judge, not ATF.

## API

Interactive reference: http://127.0.0.1:8000/docs

| Endpoint | Purpose |
| --- | --- |
| `POST /api/projects` | Multipart `file`, `run_tests`, `use_ai`; returns job ID |
| `POST /api/repositories` | JSON `url`, optional `ref`, `run_tests`, `use_ai`; import public GitHub snapshot |
| `GET /api/limits` | Configured upload and analysis limits used by the dashboard |
| `POST /api/demo` | Submit bundled sample; optional query flags |
| `GET /api/projects` | Recent 100 projects |
| `GET /api/projects/{id}` | Status and complete report |
| `GET /api/projects/{id}/report?format=markdown` | Markdown export |
| `GET /api/projects/{id}/report?format=json` | JSON export |
| `GET /api/projects/{id}/report?format=pdf` | Download printable PDF report |
| `GET /api/projects/{id}/tests` | Proposed unittest scaffold |
| `GET /health` | API liveness, not integration readiness |

## Report interpretation

Every completed report displays verification status. Completion means analysis finished; unavailable, unrequested, empty, skipped or dependency-blocked execution does not establish correctness. Even a passing suite is labeled `tests_passed_with_limits`. Reports include an analyzer version and accepted-source digest. See [the finance report accuracy audit](docs/REPORT_ACCURACY_AUDIT.md) for an evidence-based example. Use **Download PDF** in a completed report to share it.

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
