"""Bounded archive ingestion. Uploaded files are never imported on the host."""
import io
import stat
import zipfile
from pathlib import PurePosixPath

MAX_UPLOAD = 10 * 1024 * 1024
MAX_EXPANDED = 20 * 1024 * 1024
SKIP = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', '.next'}
EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.json', '.toml', '.yml', '.yaml', '.md', '.txt', '.html', '.css', '.sql', '.sh'}

def read_archive(data: bytes):
    if len(data) > MAX_UPLOAD:
        raise ValueError('ZIP exceeds the 10 MB upload limit.')
    files, skipped, total = {}, [], 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000:
                raise ValueError('Archive contains more than 1,000 entries.')
            for item in entries:
                name = item.filename.replace('\\', '/')
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:
                    raise ValueError('Archive contains an unsafe path.')
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('Symbolic links are not accepted.')
                total += item.file_size
                if total > MAX_EXPANDED or item.file_size > 1024 * 1024:
                    raise ValueError('Expanded archive exceeds file or total size limits.')
                if item.is_dir():
                    continue
                if any(p in SKIP for p in path.parts) or path.name.startswith('.env') or path.suffix.lower() not in EXTENSIONS:
                    skipped.append(name)
                    continue
                if name in files:
                    raise ValueError('Duplicate archive paths are not accepted.')
                raw = archive.read(item)
                try:
                    source = raw.decode('utf-8-sig')
                except UnicodeDecodeError:
                    skipped.append(name)
                    continue
                if '\x00' in source:
                    skipped.append(name)
                    continue
                files[name] = source
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError('Upload must be a readable, unencrypted ZIP archive.') from exc
    if not files:
        raise ValueError('No supported UTF-8 project files found.')
    # Normalize the single enclosing folder produced by GitHub ZIP downloads.
    roots = {name.split('/')[0] for name in files}
    if len(roots) == 1 and all('/' in name for name in files):
        files = {name.split('/', 1)[1]: source for name, source in files.items()}
    return files, skipped
