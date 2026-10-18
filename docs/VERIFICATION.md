# Verification record — 18 October 2026

## Automated checks completed locally

- 23 tests passed with `ATF_INTEGRATION=1` on Windows / Python 3.14.2 / Docker Desktop Linux engine 29.8.2.
- The default suite reports 21 passed and 2 skipped (Docker integration tests are opt-in).
- Real Docker checks verified successful unittest execution, non-root UID, read-only root filesystem, blocked outbound network, zero-test reporting and forced timeout of an infinite loop.
- Regression checks cover ZIP traversal, symlinks, size/entry limits, ignored secrets/dependencies, invalid ZIPs, exact static finding locations, syntax failure, credential-value exclusion, queue saturation, report exports, architecture inventory, generated scaffold syntax, UI asset serving, and unavailable integrations.
- Python compile checks passed for the new application and edited legacy modules.
- One dependency deprecation warning is emitted by FastAPI/Starlette's httpx TestClient integration; it does not fail the suite.

## Real demo checks

- The bundled cart suite ran inside Docker: 3 tests, 1 passing, 1 failure (shared mutable cart), 1 error (empty average).
- A real local Ollama `qwen2.5:3b` request returned a project review; output is model-generated and requires verification.
- Browser flow exercised the sample submission, automatic polling, findings and result navigation.
- The dashboard is served on loopback at port 8000.

## Not claimed as verified

- The optional legacy PostgreSQL/Redis/Celery deployment was not started or tested end to end.
- CI configuration is added but has not run on GitHub.
- No external penetration test, public multi-tenant security assessment, load benchmark, coverage percentage, or dependency-CVE scan is claimed.
- No universal correctness or complete all-language test generation is claimed.

## Larger uploads and repository import update

- Default local suite: 43 passed, 2 Docker tests skipped (unchanged runner isolation tests remain opt-in).
- Added tests for uploads exceeding the old 10 MB limit, configured limits, oversized-file filtering, source budgets, public GitHub URL/ref validation, streamed downloads, download errors/redirect rejection, size caps, report provenance, and queue-slot release after failures.
- Limits are exposed by `/api/limits` and displayed by the dashboard.
- Live checks: a 103,809,313-byte ZIP was accepted and analyzed; a public GitHub import of this repository completed with 33 accepted files from its then-current default branch. Browser verification confirmed the import form, limits, and completed report.
