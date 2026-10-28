# ATF — Automated Testing Framework & Playwright Studio

A modern local workbench for static codebase intelligence and real-browser automated testing. Built with **FastAPI**, **Playwright**, **SQLite**, **Docker**, and optional **Ollama**.

ATF bridges static source review with live browser regression journeys: import any local ZIP or public GitHub repository snapshot, automatically analyze its structure and security risks, and execute real end-to-end browser tests in an interactive visual studio with time-travel trace debugging.

---

## 🌟 Key Capabilities

### 1. Interactive Playwright Browser Lab
* **Multi-Language Testing**: Run journeys in **Guided Commands**, **JavaScript Playwright**, **TypeScript Playwright**, **Native Python**, or the repository's own **Test Suite**.
* **Dual Code Formats**:
  * **Commands inside one test (`body`)**: Write clean statements (`await page.goto('/')`, locators, assertions) with automated test harness wrapping.
  * **Complete test file (`file`)**: Write full, self-contained test modules with custom fixtures, hooks, and multiple `test()` declarations.
* **Deep Observability & Telemetry**:
  * Real-time step duration tracking and per-step viewport screenshots.
  * Browser console logging (`console.log`, `console.info`, uncaught errors).
  * Network request and response stream monitoring.
  * Full **Playwright Traces (`trace.zip`)** for DOM time-travel debugging on [trace.playwright.dev](https://trace.playwright.dev).
  * Auto-generated, reproducible **Python scripts (`test_browser.py`)**.

### 2. Static Codebase Intelligence & Quality Review
* **Multi-Language Inventory**: Scans Python, JavaScript/TypeScript, Java, C/C++, Go, Rust, and manifests.
* **AST Context-Aware Analysis**: Flags swallowed exceptions, mutable defaults, unsafe `eval`/`exec`, shell injection risks, hardcoded credentials, and oversized routines.
* **Architecture & Data Flow Mapping**: Extracts API routes, entry points, package dependencies, and module imports.
* **Automated Scenario Planning**: Proposes structural test cases with explicit boundary and edge-case criteria.
* **Exportable Audit Reports**: Export verified reports as **PDF**, **Markdown**, or raw **JSON**.

### 3. Isolated Sandboxed Execution
* **Docker Python Runner**: Runs existing Python unittest suites in a non-root, read-only container with CPU/memory limits and zero network access.
* **Subprocess Guardians**: Background workers execute with process timeouts, automated PID cleanup, and strict concurrency limits to prevent resource exhaustion.

---

## 🚀 Quick Start (Windows)

### Option A: One-Click Launcher (Recommended)
Double-click or run from PowerShell:
```cmd
start.bat
```
This automatically verifies dependencies, starts the FastAPI backend on `http://127.0.0.1:8010`, and opens the dashboard in your default browser.

### Option B: Interactive Playwright Codegen / Test Recorder
To record browser actions live and save them directly as pytest code:
```cmd
start_playwright_studio.bat
```

### Option C: Run End-to-End Test Suite
```cmd
start_e2e.bat
```

### Option D: Manual Startup
```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies & Playwright Chromium
python -m pip install -r requirements-demo.txt
python -m playwright install chromium

# 3. Start the backend server
python -m uvicorn main:app --host 127.0.0.1 --port 8010
```
Open **[http://127.0.0.1:8010](http://127.0.0.1:8010)** to access the dashboard.

---

## 🧭 Architecture

```
                          [ Client Browser / UI ]
                                     │
                             HTTP REST / JSON
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        FASTAPI BACKEND (main.py)                       │
 │  • Health checks (/health)         • Swagger OpenAPI docs (/docs)      │
 │  • Repository intake & ZIP reader  • PDF / JSON / Markdown exports    │
 └───────────────────┬────────────────────────────────┬───────────────────┘
                     │                                │
                     ▼                                ▼
     ┌──────────────────────────────┐ ┌──────────────────────────────────┐
     │ STATIC ANALYSIS ENGINE (atf/)│ │ PLAYWRIGHT RUNNER (browser_api.py)│
     │ • AST Syntax parsing         │ │ • ThreadPoolExecutor Queue        │
     │ • Security rule checks       │ │ • Semaphore concurrency limits   │
     │ • Test case planning         │ │ • Process timeouts & sandboxing  │
     └──────────────────────────────┘ └───────────────┬──────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │    ISOLATED SUBPROCESSES     │
                                       │ • browser_worker.py (Python) │
                                       │ • native_worker.py (Node.js) │
                                       │ • Real Chromium / WebKit     │
                                       └──────────────────────────────┘
```

---

## 🧪 Playwright Studio Guided Language

When using **Guided commands**, write one plain-text instruction per line. Quote values with spaces:

| Command | Example | Purpose |
| :--- | :--- | :--- |
| `goto` | `goto "http://127.0.0.1:8010/static/workshop.html"` | Navigate browser to URL |
| `click` | `click "#add"` | Click button, link, or locator |
| `fill` | `fill "#task" "My new task"` | Type text into an input field |
| `press` | `press "#task" "Enter"` | Dispatch keyboard key event |
| `check` | `check "label:has-text('Task') input"` | Toggle checkbox state |
| `select` | `select "#priority" "high"` | Choose dropdown select option |
| `hover` | `hover "h1"` | Hover pointer over an element |
| `expect-text` | `expect-text "#count" "1 completed"` | Assert locator text content |
| `expect-visible`| `expect-visible "#upload-form"` | Assert element is rendered and visible |
| `expect-title` | `expect-title "Workshop task board"` | Assert browser tab title |
| `expect-url` | `expect-url "http://127.0.0.1:8010/logs"` | Assert current page address |
| `screenshot` | `screenshot` | Capture current viewport snapshot |

---

## 📡 API Reference

Interactive OpenAPI documentation is available at: **[http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs)**

### Project Review Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/projects` | Upload a project ZIP for review |
| `POST` | `/api/repositories` | Ingest public GitHub repository snapshot |
| `POST` | `/api/demo` | Analyze bundled sample project |
| `GET` | `/api/projects` | List recent reviewed projects |
| `GET` | `/api/projects/{id}` | Retrieve project analysis summary |
| `GET` | `/api/projects/{id}/report` | Export report (Markdown, JSON, or PDF) |
| `GET` | `/api/projects/{id}/tests` | Download proposed unittest scaffold |
| `GET` | `/api/limits` | Current intake and decompression limits |
| `GET` | `/health` | Server liveness and engine readiness |

### Playwright Studio Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/playwright/status` | Playwright engine installation check |
| `POST` | `/api/playwright/runs` | Enqueue a new browser execution journey |
| `GET` | `/api/playwright/runs` | List recent browser execution journeys |
| `GET` | `/api/playwright/runs/{id}` | Inspect journey steps, console, network & status |
| `GET` | `/api/playwright/runs/{id}/artifacts/{name}` | Download run artifacts (`trace.zip`, PNGs, JSON) |

---

## 🛡️ Optional Integrations

### Docker Isolated Test Execution
Run test suites in a secured Linux container sandbox:
```bash
docker pull python:3.11-alpine
```
Select **Run Python tests in Docker** during project ingestion.

### Local AI Model (Ollama)
Enable qualitative AI code reviews using a local model:
```bash
ollama pull qwen2.5:3b
```
Select **Add local AI review (Ollama)** during project ingestion. Static analysis and Playwright testing operate independently without requiring Ollama.

---

## 🔬 Testing & Verification

Run the full automated test suite:
```powershell
# Run unit & API integration tests
.\.venv\Scripts\python -m pytest tests/test_atf.py tests/test_browser_commands.py tests/test_native_studio.py -v

# Run Playwright end-to-end browser tests
.\.venv\Scripts\python -m pytest tests/e2e/ -v
```

---

## 📄 License & Attribution

Developed as an educational and engineering workbench for automated testing, Playwright E2E verification, and static software quality auditing.
