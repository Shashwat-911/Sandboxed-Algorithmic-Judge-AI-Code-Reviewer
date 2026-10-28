import time
import httpx
from playwright.sync_api import expect


def wait_run(base, run_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = httpx.get(f'{base}/api/playwright/runs/{run_id}').json()
        if result['status'] not in ('queued', 'running'):
            return result
        time.sleep(.3)
    raise AssertionError('Browser run did not finish')


def test_workshop_journey_and_artifacts(page, live_server):
    page.goto(live_server)
    page.locator('#pw-run').click()
    expect(page.locator('#pw-notice')).to_contain_text('Journey passed', timeout=45000)
    expect(page.locator('#pw-progress')).to_contain_text('8/8 steps passed')
    expect(page.locator('#pw-preview img')).to_be_visible()
    page.get_by_role('tab', name='Console', exact=True).click()
    expect(page.locator('#pw-evidence')).to_contain_text('Task added')
    page.get_by_role('tab', name='Network', exact=True).click()
    expect(page.locator('#pw-evidence')).to_contain_text('workshop.html')
    page.get_by_role('tab', name='Artifacts', exact=True).click()
    for name in ['Python script', 'Run JSON', 'Playwright trace']:
        link = page.locator('#pw-evidence').get_by_role('link', name='↓ ' + name, exact=True)
        assert page.request.get(live_server + link.get_attribute('href')).status == 200
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path='docs/playwright-studio-preview.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path='docs/playwright-studio-mobile.png', full_page=True)


def test_failure_stops_run_and_preserves_evidence(live_server):
    response = httpx.post(live_server+'/api/playwright/runs', json={'commands':f'goto "{live_server}/static/workshop.html"\nexpect-text "h1" "This text does not exist"\nclick "#add"'})
    assert response.status_code == 202
    result = wait_run(live_server, response.json()['id'])
    assert result['status'] == 'failed'
    assert [s['status'] for s in result['steps']] == ['passed', 'failed', 'skipped']
    assert result['steps'][1]['screenshot']
    assert 'trace.zip' in result['artifacts']


def test_invalid_commands_and_artifact_access(live_server):
    assert httpx.post(live_server+'/api/playwright/runs', json={'commands':'goto "file:///C:/Windows/win.ini"'}).status_code == 400
    assert httpx.post(live_server+'/api/playwright/runs', json={'commands':'screenshot', 'project_id':'does-not-exist'}).status_code == 404
    assert httpx.get(live_server+'/api/playwright/runs/not-a-uuid').status_code == 404
