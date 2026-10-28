# Playwright Studio workshop

ATF now has two connected workflows: source review and real browser journeys. Playwright drives the browser journeys. FastAPI serves the command editor and results; a dedicated worker process owns each fresh browser context.

## Start

Run `./start.ps1` on Windows. It provisions demo dependencies and Chromium, then serves the workspace at http://127.0.0.1:8000. For an existing environment, run:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-demo.txt
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Firefox and WebKit are available in the browser selector but require their own binaries: `python -m playwright install firefox webkit`. Missing browsers produce an error with installation guidance; they are never reported as passing runs.

## Five-minute demonstration

1. Open the workspace, click **Load workshop example**, and press **Run journey**. The preloaded example opens the bundled task board, adds a task, checks it, and asserts the completed count.
2. Inspect **Steps**, select a step screenshot, and show **Console** and **Network**. These are actual browser events.
3. Open **Artifacts**, download the Python script and trace. Open the trace with `python -m playwright show-trace trace.zip`, or drop it into https://trace.playwright.dev.
4. Change the expected completed count to `2 completed`. Run again. The failed assertion retains a screenshot and trace; later commands are skipped.
5. Upload a source ZIP, import a public GitHub repository, or choose **Try sample project**. The selected report has **Playwright**, **Critical tasks**, **Test plan**, **Execution**, **AI review**, **Files**, **Data flow**, and **Future recommendations** tabs.
6. Run a journey with a project selected. It is linked to that project's Playwright tab. Reselect the report to refresh its linked run list.

The bundled cart project demonstrates Python static findings. The browser task board is a separate local target designed for a deterministic browser demo.

## Testing your own project

Import the repository using its `playwright` branch, then select it in Recent Projects. In the editor choose:

- **Repository test suite** to run its existing tests.
- **JavaScript Playwright** or **TypeScript Playwright** to write native Playwright code. Choose “Commands inside one test” for `await page.goto('/')`, loops, locators and assertions, or “Complete test file” for imports, fixtures, hooks and multiple `test()` declarations.
- **Native Python Playwright** for the sync Python API with `page`, `context`, `browser`, `playwright`, `expect` and `project_files`. This mode targets an already running application URL.
- **Guided commands** for the original short command language.

Native repository execution is explicitly trusted local execution, not an isolation sandbox. Check the trust box only for code you want to run with your user permissions. ATF retains imported text files, installs Node dependencies with lifecycle scripts disabled, installs `requirements-playwright.txt` into a project environment if present, installs the selected browser, and uses the root Playwright configuration's `webServer` and `baseURL`. One native run executes at a time. Initial setup can take several minutes; later runs reuse dependencies. The overall deadline is 20 minutes, with a five-minute test deadline.

A root `package.json`, `@playwright/test`, and exactly one root `playwright.config.*` are required for JavaScript/TypeScript and suite execution. The selected browser must match a configured project name (`chromium`, `firefox`, or `webkit`). Repositories needing other build steps, services, credentials or excluded binary assets require additional provisioning; setup failures appear in the logs. Environment files and binary files are not imported. Reimport older reports to retain their source for execution.

The three supplied branches start fixture applications; tests do not place trades, run AI inference or measure medical accuracy. Real test outcomes, file/line references, errors, logs, screenshots, traces and a Playwright HTML report are available under Artifacts. JSON retains the full static plan; Markdown and PDF put measured outcomes first and bound repetitive static detail. Every run is linked to its imported source digest. A new editor run does not imply the repository suite passed.

For **Guided commands**: Put one command on each line, use double quotes around selectors/values with spaces, and use `#` at the start of a line for comments.

| Command | Example | Behavior |
| --- | --- | --- |
| goto | `goto "http://localhost:3000"` | Navigate to an HTTP(S) URL |
| click | `click "text=Sign in"` | Click a Playwright locator |
| fill | `fill "#email" "student@example.com"` | Fill a field |
| press | `press "#email" "Enter"` | Press a keyboard key |
| check | `check "#terms"` | Check a checkbox |
| select | `select "#course" "engineering"` | Select an option by value |
| hover | `hover "nav"` | Hover over a locator |
| expect-text | `expect-text "h1" "Welcome"` | Assert text contains the value |
| expect-visible | `expect-visible "h1"` | Assert visibility |
| expect-title | `expect-title "My app"` | Assert exact page title |
| expect-url | `expect-url "http://localhost:3000/home"` | Assert exact URL |
| screenshot | `screenshot` | Capture the current viewport |

Every completed action also attempts a screenshot. Assertions retry for up to five seconds. Navigation has a 15-second timeout. Runs have at most 40 commands, a 120-second process deadline, two active workers and four total running/queued slots. A failed command stops the remaining steps. Each run starts without prior cookies or login state.

## Evidence and storage

Browser runs are stored in `.atf/browser-runs/<uuid>/`: commands, results, a generated Python script, PNGs, trace ZIP, and a local worker diagnostic log. Source reports continue to use SQLite. `ATF_DATA_DIR` relocates both. Browser artifacts can contain entered values and page content; they remain on your machine until you remove their run folders while the server is stopped. Console/network event lists retain the first 200 events each. Browser history shows the most recent 50 runs; older files remain on disk.

An action-only journey can pass without assertions. Passing is scoped to the commands and assertions in that journey, not whole-project correctness or coverage. Static Playwright discovery uses filenames and source references and may miss custom structures. The Python script reproduces command actions; it is not the imported project's existing test suite.

Keep this single-user service on loopback. The browser runner is a local browser automation tool with network access, not the Docker sandbox used for uploaded unittest code. Run commands only against applications you intend to interact with. Arbitrary uploaded code is never evaluated by the command runner.

## API

- `GET /api/playwright/status`: package availability and setup guidance (browser launch is checked during execution).
- `POST /api/playwright/runs`: JSON `{ "commands": "...", "browser": "chromium", "project_id": null }`.
- `GET /api/playwright/runs?project_id=<id>`: recent runs, optionally scoped to a project.
- `GET /api/playwright/runs/<id>`: progress, command source, steps, and captured evidence.
- `GET /api/playwright/runs/<id>/artifacts/<name>`: allowlisted artifacts only.

## References and design choices

- https://github.com/microsoft/playwright-python — the official Python runtime fits the existing FastAPI stack; it is used directly via the installed Playwright package.
- https://github.com/VinayKumarBM/playwright-sample-project and https://github.com/rajatt95/Playwright_JS — JavaScript/TypeScript examples useful as source-import targets and references for later native suite execution.
- https://github.com/testdino-hq/playwright-skill — best-practice guidance, not a browser execution engine. No skill or third-party source code was copied or installed from these repositories.
- https://playwright.dev/python/docs/trace-viewer — official trace recording and inspection workflow.

Next extensions: isolated native JS/Python suite execution with explicit dependency setup, richer recording/import of Playwright code, scheduled regression runs, and comparison across run histories. These are not implemented by the command runner.
