"""Shared download/caching layer.

Every raw file lands in data/cache with a .meta.json stamp (source id, URL,
retrieval timestamp) so results can always answer "where did this number come
from, and when was it fetched?"
"""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import requests

from .. import config, provenance

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT})


class SourceUnavailable(RuntimeError):
    """Raised when an upstream source cannot be fetched; callers degrade to an
    explicit data-gap indicator rather than fabricating a value."""


def cached_download(
    url: str,
    filename: str,
    source_id: str,
    max_age_days: float | None = None,
    timeout: int = 300,
) -> Path:
    dest = config.CACHE_DIR / filename
    if dest.exists():
        age_days = (time.time() - dest.stat().st_mtime) / 86400
        if max_age_days is None or age_days <= max_age_days:
            return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with _session.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        tmp.replace(dest)
    except requests.RequestException as e:
        tmp.unlink(missing_ok=True)
        if dest.exists():  # stale copy beats no copy; caller sees stamp age
            return dest
        raise SourceUnavailable(f"{source_id}: {e}") from e
    provenance.stamp_file(dest, source_id)
    return dest


def fetch_json(url: str, params: dict | None = None, timeout: int = 60):
    try:
        r = _session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        raise SourceUnavailable(f"{url}: {e}") from e


def fetch_text(url: str, params: dict | None = None, timeout: int = 120) -> str:
    try:
        r = _session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        raise SourceUnavailable(f"{url}: {e}") from e


def extract_zip(zip_path: Path, subdir_name: str | None = None) -> Path:
    """Extract into cache and return the extraction directory (idempotent)."""
    out = config.CACHE_DIR / (subdir_name or (zip_path.stem + "_extracted"))
    marker = out / ".extracted_ok"
    if marker.exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    marker.touch()
    return out
