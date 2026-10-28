import ast
import pytest
from atf.browser_commands import parse_commands, python_script


@pytest.mark.parametrize('source', [
    '', '# only comments', 'eval "1+1"', 'click', 'fill "#x"',
    'goto "file:///etc/passwd"', 'goto "javascript:alert(1)"',
    'goto "https://user:secret@example.com"', 'click "unfinished',
    '\n'.join(['screenshot'] * 41),
])
def test_reject_invalid_commands(source):
    with pytest.raises(ValueError):
        parse_commands(source)


def test_commands_preserve_selectors_and_values_and_export_valid_python():
    steps = parse_commands('# comment\nfill "input[name=title]" "O\'Brien project"\nexpect-text "h1" "Hello world"\nscreenshot')
    assert steps[0]['line'] == 2
    assert steps[0]['args'] == ['input[name=title]', "O'Brien project"]
    script = python_script(steps)
    ast.parse(script)
    assert 'to_contain_text' in script
    assert 'finally:' in script


def test_project_playwright_inventory():
    from atf.playwright_inventory import inspect_playwright
    result = inspect_playwright({
        'playwright.config.ts': 'export default {}',
        'tests/cart.spec.ts': "import {test} from '@playwright/test';\nawait page.waitForTimeout(1000)",
        'package.json': '{"scripts":{"e2e":"playwright test","dev":"vite"}}',
        'test_cart.py': 'def test_cart(page):\n    page.wait_for_timeout(500)',
    })
    assert result['configs'] == ['playwright.config.ts']
    assert len(result['tests']) == 2
    assert len(result['review_candidates']) == 2
    assert result['scripts'][0]['command'] == 'playwright test'
