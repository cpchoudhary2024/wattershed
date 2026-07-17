"""Paths, environment, and shared constants.

Data layout (relative to the repo root, overridable via WATTERSHED_DATA_DIR):
  data/cache/      downloaded raw source files (gitignored, reproducible)
  data/interim/    large intermediate build artifacts (gitignored)
  data/processed/  compact committed artifacts consumed at screening time
  data/reference/  small hand-maintained lookup tables (committed, cited)
  data/curated/    hand-curated site registry (committed, cited)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _find_repo_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "wattershed").exists():
            return parent
    return None


def data_dir() -> Path:
    env = os.environ.get("WATTERSHED_DATA_DIR")
    if env:
        return Path(env).expanduser()
    root = _find_repo_root()
    if root is not None:
        return root / "data"
    return Path.home() / ".wattershed" / "data"


DATA_DIR = data_dir()
CACHE_DIR = DATA_DIR / "cache"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
CURATED_DIR = DATA_DIR / "curated"

for _d in (CACHE_DIR, INTERIM_DIR, PROCESSED_DIR, REFERENCE_DIR, CURATED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Polite client identification for public APIs.
USER_AGENT = "wattershed/0.1 (open-source siting screening tool)"

# Optional keys — everything required runs keyless.
EIA_API_KEY = os.environ.get("EIA_API_KEY") or None
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY") or None

# Facility-proximity search radius for the community-burden pillar.
# 5 km follows EPA EJScreen's proximity-indicator convention of neighborhood-
# scale buffers; see docs/METHODOLOGY.md §4.
PROXIMITY_RADIUS_KM = 5.0

# Buffer used for the population-weighted neighborhood summary around a site.
NEIGHBORHOOD_RADIUS_KM = 5.0
