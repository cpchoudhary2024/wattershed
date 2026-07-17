"""Static dashboard builder.

Emits ONE self-contained HTML file: state outlines are projected to SVG paths
in Python (composite Albers USA — lower 48 + AK/HI insets, d3-compatible
parameters), site results are embedded as JSON, and interactivity is ~100
lines of vanilla JS. No CDN, no tiles, no build system — it works from a
file:// URL, on GitHub Pages, and inside a strict CSP.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .. import config
from ..sources.base import cached_download, extract_zip

_STATES_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"

W, H = 975, 610


class _Albers:
    def __init__(self, phi1, phi2, phi0, lam0, scale, tx, ty):
        n = (math.sin(math.radians(phi1)) + math.sin(math.radians(phi2))) / 2
        self.n = n
        self.C = math.cos(math.radians(phi1)) ** 2 + 2 * n * math.sin(math.radians(phi1))
        self.rho0 = math.sqrt(self.C - 2 * n * math.sin(math.radians(phi0))) / n
        self.lam0 = math.radians(lam0)
        self.scale, self.tx, self.ty = scale, tx, ty

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        lam, phi = math.radians(lon), math.radians(lat)
        under = self.C - 2 * self.n * math.sin(phi)
        rho = math.sqrt(max(under, 0.0)) / self.n
        theta = self.n * (lam - self.lam0)
        x = rho * math.sin(theta)
        y = self.rho0 - rho * math.cos(theta)
        # SVG y grows downward; negate the math-northward axis
        return self.tx + self.scale * x, self.ty - self.scale * y


# d3.geoAlbersUsa-equivalent composite for a 975×610 viewport
_LOWER48 = _Albers(29.5, 45.5, 38.7 - 0.0, -96 - 0.6, 1070, W / 2, H / 2)
_ALASKA = _Albers(55, 65, 58.5 - 2.0, -154 - 2.0, 1070 * 0.35, W / 2 - 0.307 * W, H / 2 + 0.201 * H)
_HAWAII = _Albers(8, 18, 19.9 - 3.0, -157 - 3.0, 1070, W / 2 - 0.205 * W, H / 2 + 0.212 * H)


def project(lon: float, lat: float, statefp: str = "") -> tuple[float, float]:
    if statefp == "02" or (lat > 50 and lon < -128):
        return _ALASKA(lon, lat)
    if statefp == "15" or (lat < 24 and lon < -152):
        return _HAWAII(lon, lat)
    return _LOWER48(lon, lat)


def _ring_to_path(coords, statefp: str) -> str:
    pts = [project(x, y, statefp) for x, y in coords[:: max(1, len(coords) // 400)]]
    if len(pts) < 3:
        return ""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    d += "".join(f"L{x:.1f},{y:.1f}" for x, y in pts[1:])
    return d + "Z"


def build_state_paths() -> str:
    import geopandas as gpd

    zp = cached_download(_STATES_URL, "cb_2024_us_state_20m.zip", "census_gazetteer_2024")
    d = extract_zip(zp, "cb_states")
    shp = sorted(d.rglob("*.shp"))[0]
    gdf = gpd.read_file(shp)
    paths = []
    for _, row in gdf.iterrows():
        fp = row["STATEFP"]
        # CONUS map: territories always excluded; AK/HI omitted (no LTRA
        # assessment areas, no screened sites) with a legend footnote
        if fp in ("72", "60", "66", "69", "78", "02", "15"):
            continue
        geom = row.geometry
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        d_attr = "".join(_ring_to_path(list(p.exterior.coords), fp) for p in polys)
        if d_attr:
            paths.append(f'<path class="state" d="{d_attr}"/>')
    return "\n".join(paths)


def _site_payload(results_dir: Path) -> list[dict]:
    sites = []
    for f in sorted(results_dir.glob("*.json")):
        s = json.loads(f.read_text())
        x, y = project(s["site"]["lon"], s["site"]["lat"])
        drivers = (s["water"]["drivers"] + s["grid"]["drivers"] + s["burden"]["drivers"])[:4]
        demand = s.get("demand") or {}
        lead = None
        if demand:
            lead = next((sc for sc in demand["scenarios"] if sc["cooling"] == s["site"]["cooling"]),
                        demand["scenarios"][0])
        sites.append(
            {
                "slug": f.stem,
                "name": s["site"]["name"],
                "operator": s["site"]["operator"],
                "state": s["geo"]["state_abbr"],
                "county": s["geo"]["county_name"],
                "status": s["site"]["status"],
                "tier": s["tier"],
                "reasons": s["tier_reasons"],
                "scores": {
                    "water": s["water"]["score"],
                    "grid": s["grid"]["score"],
                    "burden": s["burden"]["score"],
                },
                "drivers": drivers,
                "mw": s["site"]["it_mw"],
                "demand": {
                    "cooling": lead["cooling"],
                    "mgd": lead["water_mgd"],
                    "co2e": lead["co2e_tonnes_yr"],
                    "twh": round(lead["facility_energy_mwh_yr"] / 1e6, 2),
                } if lead else None,
                "mitigations": [m["title"] for m in s["mitigations"][:3]],
                "citations": [
                    {"title": c["title"], "url": c["url"], "source": c["source"], "date": str(c["date"])}
                    for c in s["site"]["provenance"]
                ],
                "notes": s["site"]["notes"],
                "usdm_date": next(
                    (i["vintage"] for i in s["water"]["indicators"] if i["id"] == "usdm_current"), ""
                ),
                "x": round(x, 1),
                "y": round(y, 1),
                "generated": s["generated_at"][:10],
            }
        )
    return sites


def _county_payload() -> list[dict]:
    """Atlas layer: per-county SVG path + pillar scores, from the committed
    county_atlas.csv and cartographic county boundaries."""
    import pandas as pd

    from ..pipelines import atlas as atlas_mod

    if not atlas_mod.ATLAS_PATH.exists():
        return []
    scores = pd.read_csv(atlas_mod.ATLAS_PATH, dtype={"county": str})
    scores["county"] = scores["county"].str.zfill(5)
    lookup = scores.set_index("county")
    gdf = atlas_mod.county_shapes()
    out = []
    for _, row in gdf.iterrows():
        fips = row["GEOID"]
        if fips not in lookup.index:
            continue
        geom = row.geometry
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        d_attr = "".join(_ring_to_path(list(p.exterior.coords), row["STATEFP"]) for p in polys)
        if not d_attr:
            continue
        s = lookup.loc[fips]

        def num(v):
            return None if pd.isna(v) else round(float(v), 1)

        out.append(
            {
                "f": fips,
                "n": f"{row['NAME']}, {row['STUSPS']}",
                "d": d_attr,
                "w": num(s["water"]),
                "g": num(s["grid"]),
                "b": num(s["burden"]),
                "p": int(s["population"]),
            }
        )
    return out


def build(results_dir: Path, out_file: Path) -> None:
    template = (Path(__file__).parent / "template.html").read_text()
    sites = _site_payload(results_dir)
    manifest_path = config.PROCESSED_DIR / "reference_manifest.json"
    build_date = ""
    if manifest_path.exists():
        build_date = json.loads(manifest_path.read_text()).get("build_date", "")
    counties = _county_payload()
    html = (
        template.replace("<!--__MAP_PATHS__-->", build_state_paths())
        .replace("/*__SITE_DATA__*/", "const SITES = " + json.dumps(sites) + ";")
        .replace("/*__COUNTY_DATA__*/", "const COUNTIES = " + json.dumps(counties, separators=(",", ":")) + ";")
        .replace("__BUILD_DATE__", build_date or "n/a")
        .replace("__GEN_DATE__", sites[0]["generated"] if sites else "")
    )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(html)
