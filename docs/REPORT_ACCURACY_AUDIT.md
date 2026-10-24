# Finance report accuracy audit

Audit date: 24 October 2026.

## Verdict

The supplied report is a partial static review, not a completed correctness assessment. It explicitly recorded unavailable Docker execution and unavailable AI review. Its 200 proposed scenarios were not executed tests.

The original report used a moving HEAD reference. This audit inspected finance commit `88792ffd297889b20a8823685a1519902101ba2d` read-only. All 46 original file/line/rule references could be reproduced using the former analyzer on this snapshot, but the inventory has changed: the original listed 140 accepted files / 31,437 lines; the audited snapshot contains 144 / 33,447. This does not prove the original source snapshot was identical.

## Findings that need context

- Five high-severity dynamic-execution findings occur in test harnesses that compile extracted local AST nodes: `tests/test_broker_safety.py:25`, `tests/test_publication_safety.py:16`, `tests/test_reporting.py:72`, and `tests/test_session_timing.py:30,48`. They warrant source-trust review, but are not automatically demonstrated production vulnerabilities. The revised analyzer marks this pattern medium and explains the uncertainty. Other input-driven evaluation remains high.
- Seven broad silent exception handlers are real observations with different consequences. In `main.py:588`, a daily-data fetch failure can retain a bullish default: this deserves targeted behavior tests and explicit fallback policy. Other handlers include display/equity updates, a Windows popup, clock handling and response-body fallback. They should not be assigned the same operational meaning without tracing their callers.
- Long functions indicate maintenance cost, not proven incorrect behavior. Test functions are now excluded from that rule.

The revised snapshot yields 12 medium and 33 low findings, with no high findings. A lower severity count does not certify safety or trading correctness.

## Method improvements

Python rules now inspect syntax instead of matching executable-looking text in comments and strings. Findings include context, confidence and evidence; credential values are omitted. Keyword-only mutable defaults are covered. Non-Python files receive inventory only.

Planning balances production modules and prioritizes findings within each file. For this snapshot, 80 of 185 eligible functions were selected, with 105 explicitly omitted; all 33 production files were represented. Risk-manager methods are included. Scenarios cite their structural basis and remain proposals requiring assertions and execution. Future-scope suggestions describe the reviewed project instead of ATF features.

AI excerpts prioritize production source across modules, with included/omitted files reported. This remains bounded context, not whole-repository model comprehension. Every report now has an explicit verification status, analyzer version and accepted-source digest. PDF, Markdown and the dashboard expose the same verification limits.

The runner discovers unittest directories without package markers and distinguishes missing dependencies, zero tests and all-skipped suites from success.

## Verification and limits

ATF regression suite: 53 passed, 2 Docker integration tests skipped. Synthetic authored fixtures validated discovery, dependency-blocked, empty and all-skipped outcomes. The three-page PDF sample was rendered and visually checked. No live Docker integration or Ollama review is claimed for this update.

No finance code was executed, imported, modified or committed. No broker operations occurred. The corrected local report is a static audit with execution and AI marked not requested. Financial/business correctness, strategy profitability, dependency vulnerabilities and complete code coverage remain unverified. The bullish-default behavior remains a review item in finance; this change fixes ATF reporting, not the trading application.
