import pytest
from playwright.sync_api import Page, expect


def test_dashboard_loads_and_toggles_modes(page: Page, live_server: str):
    """Test dashboard initial load, title, and toggling between Upload ZIP and GitHub modes."""
    page.goto(live_server)

    # 1. Assert title & brand
    expect(page).to_have_title("ATF · Playwright Studio")
    expect(page.locator(".brand")).to_contain_text("atf")

    # 2. Assert default mode is ZIP upload
    zip_mode_btn = page.locator("#zip-mode")
    repo_mode_btn = page.locator("#repo-mode")
    upload_form = page.locator("#upload-form")
    repo_form = page.locator("#repo-form")

    expect(zip_mode_btn).to_have_attribute("aria-pressed", "true")
    expect(upload_form).to_be_visible()
    expect(repo_form).to_be_hidden()

    # 3. Switch to GitHub repository mode
    repo_mode_btn.click()
    expect(repo_mode_btn).to_have_attribute("aria-pressed", "true")
    expect(zip_mode_btn).to_have_attribute("aria-pressed", "false")
    expect(repo_form).to_be_visible()
    expect(upload_form).to_be_hidden()

    # 4. Switch back to ZIP mode
    zip_mode_btn.click()
    expect(upload_form).to_be_visible()
    expect(repo_form).to_be_hidden()


def test_sample_project_analysis_flow(page: Page, live_server: str):
    """Test full interactive user journey: triggering sample project analysis, polling, and inspecting tabs."""
    page.goto(live_server)

    # Click the "Try sample project" button
    page.locator("#demo").click()

    # Wait for the analysis to complete
    expect(page.locator("#notice")).to_contain_text("Analysis complete", timeout=20000)

    # Wait for the report title to update to sample project
    expect(page.locator("#report-title")).to_contain_text("sample", ignore_case=True, timeout=20000)

    # Verify metrics appear
    expect(page.locator(".metrics")).to_be_visible()
    expect(page.locator(".metric").first).to_be_visible()

    # Verify export buttons are revealed
    expect(page.locator("#exports")).to_be_visible()
    expect(page.locator("#pdf")).to_be_visible()
    expect(page.locator("#markdown")).to_be_visible()

    # Click each tab and verify content panels load
    # Tab 1: Findings
    page.locator('button[data-tab="findings"]').click()
    expect(page.locator(".panel")).to_contain_text("static checks", ignore_case=True)

    # Tab 2: Test plan
    page.locator('button[data-tab="tests"]').click()
    expect(page.locator(".panel")).to_contain_text("Proposed scenarios", ignore_case=True)

    # Tab 3: Architecture
    page.locator('button[data-tab="architecture"]').click()
    expect(page.locator(".panel")).to_contain_text("Entry points", ignore_case=True)

    # Verify project is listed in recent history sidebar
    expect(page.locator("#history")).to_contain_text("sample", ignore_case=True)


def test_network_interception_resilience(page: Page, live_server: str):
    """Demonstrate Playwright network mocking: intercept API calls to simulate backend error."""
    page.goto(live_server)

    # Intercept the demo trigger endpoint and mock a 500 error
    page.route("**/api/demo*", lambda route: route.fulfill(
        status=500,
        content_type="application/json",
        body='{"detail": "Simulated backend failure"}'
    ))

    # Click demo button
    page.locator("#demo").click()

    # UI should catch the error and display notice without crashing
    expect(page.locator("#notice")).to_contain_text("Simulated backend failure", timeout=5000)
