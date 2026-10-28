"""Evidence-based Playwright discovery; imported code is never executed."""
import json
import re
from pathlib import PurePosixPath


def inspect_playwright(files):
    tests, configs, manifests, patterns = [], [], [], []
    for path, source in sorted(files.items()):
        name = PurePosixPath(path).name
        if name.startswith('playwright.config.'):
            configs.append(path)
        if (re.search(r'\b(?:test|spec)\.[cm]?[jt]sx?$', name) or name.startswith('test_') and name.endswith('.py')) and ('playwright' in source or re.search(r'\bpage\.', source)):
            tests.append(path)
        if name == 'package.json':
            try:
                package = json.loads(source)
                for key, value in package.get('scripts', {}).items():
                    if isinstance(value, str) and 'playwright' in value:
                        manifests.append({'file': path, 'name': key, 'command': value})
            except (ValueError, AttributeError):
                pass
        if path.endswith(('.py', '.js', '.ts', '.mjs', '.tsx')) and ('playwright' in source or path in tests):
            for line, text in enumerate(source.splitlines(), 1):
                if re.search(r'\b(?:waitForTimeout|wait_for_timeout)\s*\(', text):
                    patterns.append({'file': path, 'line': line, 'recommendation': 'Replace fixed sleeps with locator assertions or a specific response/event wait.'})
    return {'tests': tests, 'configs': configs, 'scripts': manifests, 'review_candidates': patterns[:100],
            'note': 'Static discovery by filename and source references. Select Repository test suite in the editor to execute these tests. Discovery alone is not execution evidence.'}
