"""Import public GitHub snapshots without invoking Git or accepting arbitrary hosts."""
import re
import tempfile
import time
from contextlib import contextmanager
from urllib.parse import quote, urlsplit

import httpx
from atf.limits import MAX_UPLOAD, MIB


def parse_repository(url, ref=''):
    parsed = urlsplit(url.strip())
    if (parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com'
            or parsed.query or parsed.fragment):
        raise ValueError('Use a public repository URL: https://github.com/owner/repository (no credentials, query or fragment).')
    parts = parsed.path.strip('/').split('/')
    if len(parts) != 2 or not all(re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in parts):
        raise ValueError('Paste the repository root URL; enter a branch, tag or commit in the separate ref field.')
    owner, repo = parts
    if repo.endswith('.git'): repo = repo[:-4]
    if not repo or owner in {'.','..'} or repo in {'.','..'}:
        raise ValueError('Invalid GitHub repository name.')
    ref = ref.strip() or 'HEAD'
    if len(ref) > 200 or not re.fullmatch(r'[A-Za-z0-9_./-]+', ref) or '..' in ref or ref.startswith(('/', '-')):
        raise ValueError('Invalid branch, tag or commit reference.')
    return owner, repo, ref


@contextmanager
def repository_archive(url, ref=''):
    owner, repo, ref = parse_repository(url, ref)
    # Construct a fixed-host download URL, never fetch the user URL itself.
    download = f'https://codeload.github.com/{owner}/{repo}/zip/{quote(ref, safe="")}'
    started = time.monotonic()
    with tempfile.TemporaryFile() as archive:
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False, trust_env=False) as client:
                with client.stream('GET', download, headers={'User-Agent':'ATF-project-review', 'Accept-Encoding':'identity'}) as response:
                    if response.status_code == 404:
                        raise ValueError('Repository or ref not found. Only public GitHub repositories are supported; upload a ZIP for private projects.')
                    if response.status_code in (403, 429):
                        raise ValueError('GitHub declined or rate-limited the download. Try again later or upload a ZIP.')
                    if response.is_redirect:
                        raise ValueError('Repository download redirected. Use the current canonical GitHub repository URL.')
                    response.raise_for_status()
                    length = response.headers.get('content-length', '')
                    if length.isdigit() and int(length) > MAX_UPLOAD:
                        raise ValueError(f'Repository archive exceeds {MAX_UPLOAD // MIB} MB.')
                    total = 0
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > MAX_UPLOAD:
                            raise ValueError(f'Repository archive exceeds {MAX_UPLOAD // MIB} MB.')
                        if time.monotonic() - started > 120:
                            raise ValueError('Repository download exceeded two minutes. Try a ZIP upload.')
                        archive.write(chunk)
        except httpx.HTTPError as exc:
            raise ValueError('Could not download the GitHub repository. Check connectivity or upload a ZIP.') from exc
        archive.seek(0)
        yield archive, {'kind':'github', 'url':f'https://github.com/{owner}/{repo}', 'ref':ref}
