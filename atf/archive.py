"""Bounded archive ingestion. Uploaded files are never imported on the host."""
import io
import stat
import zipfile
from pathlib import PurePosixPath

from atf.limits import MAX_UPLOAD, MAX_EXPANDED, MAX_SOURCE, MAX_FILE, MAX_ENTRIES, MIB
SKIP = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', '.next'}
EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.json', '.toml', '.yml', '.yaml', '.md', '.txt', '.html', '.css', '.sql', '.sh'}

def read_archive(data):
    stream = io.BytesIO(data) if isinstance(data, bytes) else data
    stream.seek(0, 2)
    if stream.tell() > MAX_UPLOAD:
        raise ValueError(f'ZIP exceeds the {MAX_UPLOAD // MIB} MB upload limit.')
    stream.seek(0)
    files, skipped, total, source_size = {}, [], 0, 0
    seen = set()
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError(f'Archive contains more than {MAX_ENTRIES:,} entries.')
            for item in entries:
                name = item.filename.replace('\\', '/')
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:
                    raise ValueError('Archive contains an unsafe path.')
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('Symbolic links are not accepted.')
                total += item.file_size
                if total > MAX_EXPANDED:
                    raise ValueError(f'Expanded archive exceeds the {MAX_EXPANDED // MIB} MB size limit.')
                if item.is_dir():
                    continue
                normalized = str(path)
                if normalized in seen:
                    raise ValueError('Duplicate archive paths are not accepted.')
                seen.add(normalized)
                if any(p in SKIP for p in path.parts) or path.name.startswith('.env') or path.suffix.lower() not in EXTENSIONS:
                    skipped.append(name)
                    continue
                if item.file_size > MAX_FILE:
                    skipped.append(name)
                    continue
                source_size += item.file_size
                if source_size > MAX_SOURCE:
                    raise ValueError(f'Supported source exceeds the {MAX_SOURCE // MIB} MB analysis limit. Exclude generated files or increase ATF_MAX_SOURCE_MB.')
                raw = archive.read(item)
                try:
                    source = raw.decode('utf-8-sig')
                except UnicodeDecodeError:
                    skipped.append(name)
                    continue
                if '\x00' in source:
                    skipped.append(name)
                    continue
                files[normalized] = source
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError('Upload must be a readable, unencrypted ZIP archive.') from exc
    if not files:
        raise ValueError('No supported UTF-8 project files found.')
    # Normalize the single enclosing folder produced by GitHub ZIP downloads.
    roots = {name.split('/')[0] for name in files}
    if len(roots) == 1 and all('/' in name for name in files):
        files = {name.split('/', 1)[1]: source for name, source in files.items()}
    return files, skipped
