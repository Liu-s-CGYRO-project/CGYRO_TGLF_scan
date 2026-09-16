"""Release ordering shared by GitHub, local libraries, and manager updates."""
from builtins import any, float, int, len, sorted, str, tuple
from datetime import datetime, timezone
import re

MANAGER_VERSION = '1.9.1'
SORT_OPTIONS = {'发布时间：新 → 旧': 'published', '版本号：新 → 旧': 'version', '版本号：旧 → 新': 'version_asc'}
_SEMVER = re.compile(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
                     r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z')


def semantic_version(value):
    match = _SEMVER.fullmatch(str(value))
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    identifiers = tuple(pre.split('.')) if pre else ()
    if any(part.isdigit() and len(part) > 1 and part.startswith('0') for part in identifiers):
        return None
    return (int(major), int(minor), int(patch), 0 if pre else 1,
            tuple((0, int(part)) if part.isdigit() else (1, part) for part in identifiers))


def version_key(value):
    text = str(value)
    natural = tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                    for part in re.findall(r'\d+|\D+', text))
    # The project migrated from calendar versions to SemVer. Keep the old
    # calendar series below the current series instead of interpreting 2026
    # as a newer major version than 1. Timestamps remain the default ordering.
    calendar = re.match(r'^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\.|$)', text)
    if calendar:
        try:
            datetime(*(int(part) for part in calendar.groups()))
            return (1, natural)
        except ValueError:
            pass
    semantic = semantic_version(text)
    return (2, semantic) if semantic is not None else (0, natural)


def published_time(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    except (ValueError, OverflowError, OSError):
        return float('-inf')


def sort_releases(releases, mode='published'):
    def key(release):
        version = version_key(release.get('version', ''))
        date = published_time(release.get('created', ''))
        identity = tuple(str(release.get(k, '')) for k in ('author', 'id', 'path', 'asset_id'))
        return ((date, version) if mode == 'published' else (version, date)) + (identity,)
    return sorted(releases, key=key, reverse=mode != 'version_asc')
