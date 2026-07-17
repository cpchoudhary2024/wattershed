"""Per-site HTML report renderer — a print-ready screening memo.

Design: light, print-first document (consulting deliverable). All CSS inline;
no external assets; charts are pure HTML/CSS (percentile bars, score meters,
mix bar) so the file works offline and in print. Colors follow the validated
reference palette (docs in the dataviz method): status colors carry tier/band
STATE and always ship with a text label; sequential blue carries magnitude.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Screening

_TEMPLATES = Path(__file__).parent / "templates"

TIER_STYLE = {
    "Low": ("#0ca30c", "#eaf6ea"),
    "Moderate": ("#8a6d00", "#fdf3d7"),
    "Elevated": ("#a34f13", "#fde8dc"),
    "High": ("#d03b3b", "#fbe4e4"),
}

BAND_COLOR = {
    "low": "#0ca30c",
    "moderate": "#8a6d00",
    "high": "#a34f13",
    "severe": "#d03b3b",
    "insufficient data": "#898781",
}

# Fuel mix folded to five fixed groups (categorical slots 1–5, fixed order).
MIX_GROUPS = [
    ("Fossil", ["coal", "oil", "gas", "other_fossil"], "#2a78d6"),
    ("Nuclear", ["nuclear"], "#008300"),
    ("Hydro", ["hydro"], "#e87ba4"),
    ("Wind + Solar", ["wind", "solar"], "#eda100"),
    ("Other", ["biomass", "geothermal", "other"], "#1baf7a"),
]


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["fmt_num"] = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else v
    env.filters["fmt0"] = lambda v: f"{v:.0f}" if isinstance(v, (int, float)) else "—"
    env.filters["fmt1"] = lambda v: f"{v:.1f}" if isinstance(v, (int, float)) else "—"
    return env


def _mix_groups(screening: Screening) -> list[dict]:
    mix_ind = next((i for i in screening.grid.indicators if i.id == "egrid_mix"), None)
    if mix_ind is None:
        return []
    # recover mix from the demand/grid stats attached at screen time
    stats_mix = screening.neighborhood.get("_grid_mix") or {}
    if not stats_mix:
        return []
    out = []
    for label, fuels, color in MIX_GROUPS:
        share = 100 * sum(stats_mix.get(f, 0.0) for f in fuels)
        if share > 0.05:
            out.append({"label": label, "pct": round(share, 1), "color": color})
    return out


def render_report(screening: Screening) -> str:
    env = _env()
    tpl = env.get_template("report.html.j2")
    tier_fg, tier_bg = TIER_STYLE[screening.tier.value]
    return tpl.render(
        s=screening,
        tier_fg=tier_fg,
        tier_bg=tier_bg,
        band_color=BAND_COLOR,
        mix_groups=_mix_groups(screening),
    )
