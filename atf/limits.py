"""Configurable resource limits for the local ATF workspace (MiB units)."""
import os


def positive(name, default):
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer.')
    return value


MIB = 1024 * 1024
MAX_UPLOAD = positive('ATF_MAX_UPLOAD_MB', 100) * MIB
MAX_EXPANDED = positive('ATF_MAX_EXPANDED_MB', 500) * MIB
MAX_SOURCE = positive('ATF_MAX_SOURCE_MB', 50) * MIB
MAX_FILE = positive('ATF_MAX_FILE_MB', 5) * MIB
MAX_ENTRIES = positive('ATF_MAX_ARCHIVE_ENTRIES', 20000)
