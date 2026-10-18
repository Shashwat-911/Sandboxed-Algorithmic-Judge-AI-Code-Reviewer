# Five-minute demo and viva guide

1. Run `start.ps1`, open the dashboard, and explain the goal: turn an uploaded source project into an evidence-based review and a testing plan.
2. Select Docker tests and local AI if both integrations are ready. Click **Try sample project**.
3. Show **Findings**: `cart.py:6` has a mutable default argument. Explain why a list is reused between calls.
4. Show **Execution**: the real Docker suite finds shared cart state and division by zero. One test passes, one fails and one errors. Explain the difference between an assertion failure and an unexpected exception.
5. Show **Test plan**: normal, empty/invalid, boundary and repeated-call scenarios. These are proposed, not executed. Download **Tests** to demonstrate an honest skipped scaffold ready for domain-specific assertions.
6. Show **AI review**: real local-model suggestions, with context limits and availability explicitly reported.
7. Show **Architecture**, **Files**, and **Roadmap**, then download Markdown/JSON as the review handoff.
8. Upload your own ZIP (up to 100 MB), or choose **GitHub repository** and paste a public repository URL. Leave ref blank for its default branch, or specify a branch, tag or commit. Exclude dependencies and secrets before creating local archives.

## Explain the engineering choices

- Why Docker? Uploaded tests must not run directly on the API host. Network and resource restrictions contain normal accidental failures; containers are not an absolute security guarantee.
- Why AST? Python structure yields exact function and issue locations without executing code.
- Why SQLite? A reliable local resume demo has fewer prerequisites. The original PostgreSQL/Celery design remains available for discussing distributed evolution.
- What if AI is down? Deterministic analysis and reporting still work; AI is visibly unavailable.
- Does it test every language? No. Inventory/text rules support multiple languages; real suite execution currently supports Python standard-library unittest.
- Are generated tests complete? No. Scenarios and scaffolds require requirement-specific assertions. The tool never reports proposed tests as passed.
- How do you scale it? Replace the local executor with a durable queue, isolate execution workers on separate hosts, add authentication, quotas, metrics, and framework-specific runners.

## Next practical extensions

1. Dependency-prebuilt runner images for pytest and JavaScript.
2. Coverage and mutation testing on supported suites.
3. Requirement-aware test generation with human-reviewed assertions.
4. PR integrations, baseline comparisons, authenticated team workspaces.
