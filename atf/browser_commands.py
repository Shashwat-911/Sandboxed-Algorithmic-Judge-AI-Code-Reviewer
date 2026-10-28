"""Small, explicit command language. Never evaluates submitted Python or shell code."""
import shlex
from urllib.parse import urlparse

ARITY = {'goto': 1, 'click': 1, 'fill': 2, 'press': 2, 'check': 1,
         'select': 2, 'hover': 1, 'expect-text': 2, 'expect-visible': 1,
         'expect-title': 1, 'expect-url': 1, 'screenshot': 0}


def validate_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an HTTP(S) URL without embedded credentials.')
    return value


def parse_commands(source):
    steps = []
    for line, raw in enumerate(source.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            raise ValueError(f'Line {line}: {exc}') from exc
        name, *args = parts
        if name not in ARITY:
            raise ValueError(f'Line {line}: unknown command {name!r}. Choose: {", ".join(ARITY)}.')
        if len(args) != ARITY[name]:
            raise ValueError(f'Line {line}: {name} needs {ARITY[name]} argument(s). Quote values containing spaces.')
        if name == 'goto':
            validate_url(args[0])
        steps.append({'line': line, 'command': name, 'args': args})
    if not 1 <= len(steps) <= 40:
        raise ValueError('Write between 1 and 40 commands.')
    return steps


def python_script(steps, browser='chromium'):
    lines = ['from playwright.sync_api import sync_playwright, expect', '',
             'with sync_playwright() as p:', f'    browser = p.{browser}.launch()',
             '    context = browser.new_context(viewport={"width": 1280, "height": 800})',
             '    context.tracing.start(screenshots=True, snapshots=True, sources=True)',
             '    page = context.new_page()', '    page.set_default_timeout(5000)', '    try:']
    for index, step in enumerate(steps):
        name, args = step['command'], step['args']
        a = [repr(arg) for arg in args]
        if name == 'goto': code = f'page.goto({a[0]}, wait_until="domcontentloaded")'
        elif name == 'screenshot': code = f'page.screenshot(path="step-{index + 1}.png")'
        elif name == 'expect-text': code = f'expect(page.locator({a[0]})).to_contain_text({a[1]})'
        elif name == 'expect-visible': code = f'expect(page.locator({a[0]})).to_be_visible()'
        elif name == 'expect-title': code = f'expect(page).to_have_title({a[0]})'
        elif name == 'expect-url': code = f'expect(page).to_have_url({a[0]})'
        else:
            method = 'select_option' if name == 'select' else name
            code = f'page.locator({a[0]}).{method}({", ".join(a[1:])})'
        lines.append('        ' + code)
    lines += ['    finally:', '        context.tracing.stop(path="trace.zip")', '        browser.close()', '']
    return '\n'.join(lines)
