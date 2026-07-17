"""Wattershed CLI.

  wattershed screen --lat 35.06 --lon -90.07 --mw 300 --cooling evaporative
  wattershed screen --address "3231 Paul R Lowry Rd, Memphis, TN" --mw 300
  wattershed screen --site xai-colossus-memphis --report out/memphis.html
  wattershed sites
  wattershed screen-all --out-dir out/
  wattershed build-reference
  wattershed build-dashboard
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import config
from .models import CoolingTech, Screening, SiteInput

app = typer.Typer(add_completion=False, rich_markup_mode="rich", no_args_is_help=True)
console = Console()

TIER_COLORS = {"Low": "green", "Moderate": "yellow", "Elevated": "dark_orange", "High": "red"}


def _load_curated() -> dict[str, dict]:
    import yaml

    p = config.CURATED_DIR / "sites.yaml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text())
    return {s["slug"]: s for s in data.get("sites", [])}


def _site_from_curated(entry: dict) -> SiteInput:
    return SiteInput(
        slug=entry["slug"],
        name=entry["name"],
        lat=entry["lat"],
        lon=entry["lon"],
        address=entry.get("address", ""),
        operator=entry.get("operator", ""),
        status=entry.get("status", ""),
        it_mw=entry.get("announced_mw"),
        cooling=CoolingTech(entry.get("cooling", "unknown")),
        coord_precision=entry.get("coord_precision", "locality"),
        provenance=entry.get("citations", []),
        notes=entry.get("notes", ""),
    )


def _print_screening(s: Screening) -> None:
    color = TIER_COLORS.get(s.tier.value, "white")
    header = f"[bold]{s.site.name}[/bold]\n{s.geo.county_name} County, {s.geo.state_abbr} · tract {s.geo.tract_geoid}"
    console.print(Panel(header, title="Wattershed screening", subtitle=s.generated_at))
    t = Table(show_header=True, header_style="bold")
    t.add_column("Pillar")
    t.add_column("Score", justify="right")
    t.add_column("Band")
    t.add_column("Top driver")
    for p in (s.water, s.grid, s.burden):
        t.add_row(
            p.pillar,
            "—" if p.score is None else f"{p.score:.0f}",
            p.band,
            p.drivers[0] if p.drivers else "",
        )
    console.print(t)
    console.print(f"Overall screening tier: [bold {color}]{s.tier.value.upper()}[/bold {color}]")
    for r in s.tier_reasons:
        console.print(f"  • {r}")
    if s.demand:
        console.print(
            f"\nModeled demand @ {s.demand.it_mw:.0f} MW IT (util {s.demand.utilization:.0%}): "
            f"{s.demand.it_energy_mwh_yr/1e6:.2f} TWh IT/yr"
        )
        for sc in s.demand.scenarios:
            pct = f" ({sc.pct_county_public_supply:.1f}% county PS)" if sc.pct_county_public_supply else ""
            console.print(
                f"  {sc.cooling:<12} PUE {sc.pue:.2f} · {sc.water_mgd:.2f} MGD{pct} · "
                f"{(sc.co2e_tonnes_yr or 0):,.0f} t CO₂e/yr"
            )
    console.print("\n[dim]Every value above carries a source and vintage — use --json or --report "
                  "for the full provenance ledger.[/dim]")


@app.command()
def screen(
    lat: Optional[float] = typer.Option(None),
    lon: Optional[float] = typer.Option(None),
    address: Optional[str] = typer.Option(None, help="One-line address (Census geocoder)"),
    site: Optional[str] = typer.Option(None, help="Slug from the curated registry (see `sites`)"),
    name: str = typer.Option("Unnamed site"),
    mw: Optional[float] = typer.Option(None, help="Announced IT capacity, MW"),
    cooling: str = typer.Option("unknown", help="evaporative | hybrid | air | unknown"),
    json_out: Optional[Path] = typer.Option(None, "--json", help="Write full result JSON here"),
    report: Optional[Path] = typer.Option(None, help="Write HTML report here"),
):
    """Screen one location (coordinates, address, or curated site)."""
    from .pipelines.screen import screen_point, screen_site

    rto = None
    if site:
        entry = _load_curated().get(site)
        if not entry:
            console.print(f"[red]Unknown site slug:[/red] {site} — run `wattershed sites`")
            raise typer.Exit(1)
        s_in = _site_from_curated(entry)
        rto = entry.get("rto")
        result = screen_site(s_in, rto_override=rto)
    elif address:
        from .geocode import geocode_address

        glat, glon, matched = geocode_address(address)
        result = screen_point(glat, glon, name=name, it_mw=mw, cooling=cooling, address=matched)
    elif lat is not None and lon is not None:
        result = screen_point(lat, lon, name=name, it_mw=mw, cooling=cooling)
    else:
        console.print("[red]Provide --site, --address, or --lat/--lon.[/red]")
        raise typer.Exit(1)

    _print_screening(result)
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(result.to_json())
        console.print(f"JSON → {json_out}")
    if report:
        from .report.render import render_report

        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(result))
        console.print(f"Report → {report}")


@app.command()
def sites():
    """List the hand-curated site registry (with provenance counts)."""
    entries = _load_curated()
    t = Table(show_header=True, header_style="bold")
    for col in ("slug", "name", "state", "status", "MW", "citations"):
        t.add_column(col)
    for slug, e in entries.items():
        t.add_row(
            slug, e["name"], e.get("state", ""), e.get("status", ""),
            str(e.get("announced_mw", "—")), str(len(e.get("citations", []))),
        )
    console.print(t)
    console.print("[dim]Manually compiled from cited public reporting — not exhaustive, "
                  "not authoritative. See data/curated/sites.yaml.[/dim]")


@app.command("screen-all")
def screen_all(out_dir: Path = typer.Option(Path("out"), help="Directory for per-site JSON")):
    """Screen every curated site; write per-site JSON (feeds the dashboard)."""
    from .pipelines.screen import screen_site

    out_dir.mkdir(parents=True, exist_ok=True)
    for slug, entry in _load_curated().items():
        console.print(f"[bold]{slug}[/bold] …", end=" ")
        try:
            res = screen_site(_site_from_curated(entry), rto_override=entry.get("rto"))
            (out_dir / f"{slug}.json").write_text(res.to_json())
            console.print(f"{res.tier.value} (water {res.water.score}, grid {res.grid.score}, "
                          f"burden {res.burden.score})")
        except Exception as e:  # keep batch going; a broken site is a finding, not a crash
            console.print(f"[red]failed: {e}[/red]")


@app.command()
def batch(
    input_csv: Path = typer.Argument(..., help="CSV with columns: name,lat,lon[,mw,cooling]"),
    out_dir: Path = typer.Option(Path("out/batch"), help="Per-row JSON + memos + summary.csv"),
):
    """Portfolio mode: screen every row of a CSV, write a scored summary table."""
    import csv as csv_mod

    from .pipelines.screen import screen_point
    from .report.render import render_report

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = list(csv_mod.DictReader(open(input_csv)))
    summary = []
    for i, r in enumerate(rows):
        name = r.get("name") or f"row-{i+1}"
        try:
            res = screen_point(
                float(r["lat"]), float(r["lon"]), name=name,
                it_mw=float(r["mw"]) if r.get("mw") else None,
                cooling=(r.get("cooling") or "unknown").strip().lower(),
            )
            slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
            (out_dir / f"{slug}.json").write_text(res.to_json())
            (out_dir / f"{slug}.html").write_text(render_report(res))
            summary.append(
                {
                    "name": name, "lat": r["lat"], "lon": r["lon"],
                    "county": f"{res.geo.county_name}, {res.geo.state_abbr}",
                    "tier": res.tier.value,
                    "water": res.water.score, "grid": res.grid.score, "burden": res.burden.score,
                }
            )
            console.print(f"{name}: {res.tier.value}")
        except Exception as e:
            summary.append({"name": name, "lat": r.get("lat"), "lon": r.get("lon"),
                            "county": "", "tier": f"ERROR: {e}", "water": None, "grid": None, "burden": None})
            console.print(f"[red]{name}: {e}[/red]")
    with open(out_dir / "summary.csv", "w", newline="") as f:
        w = csv_mod.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    console.print(f"Summary → {out_dir/'summary.csv'}")


@app.command("build-atlas")
def build_atlas_cmd():
    """Rebuild the national county siting-pressure atlas from committed artifacts."""
    from .pipelines.atlas import ATLAS_PATH, build_atlas

    df = build_atlas()
    console.print(f"{len(df)} counties → {ATLAS_PATH}")


@app.command("build-reference")
def build_reference(skip_aqueduct: bool = typer.Option(False, help="Skip the 261 MB Aqueduct step")):
    """Rebuild the national tract reference table from primary sources."""
    from .pipelines.build_reference import build

    build(skip_aqueduct=skip_aqueduct)


@app.command("build-dashboard")
def build_dashboard(
    results_dir: Path = typer.Option(Path("out")),
    out_file: Path = typer.Option(Path("site/index.html")),
):
    """Assemble the static dashboard from screened results."""
    from .dashboard.build import build as build_dash

    build_dash(results_dir, out_file)
    console.print(f"Dashboard → {out_file}")


@app.command()
def doctor():
    """Data-freshness health check: what's current, what's aging, what to do."""
    import json
    from datetime import date, datetime

    from . import provenance

    today = date.today()

    def age_days(iso: str | None) -> int | None:
        if not iso:
            return None
        return (today - datetime.fromisoformat(iso.replace("Z", "")).date()).days

    rows: list[tuple[str, str, str, str]] = []  # layer, vintage/state, status, action

    usdm_age = age_days(provenance.retrieved_at(config.CACHE_DIR / "usdm_current.zip"))
    if usdm_age is None:
        rows.append(("Drought (USDM weekly)", "not yet fetched", "—", "fetches automatically on first screen"))
    elif usdm_age <= 7:
        rows.append(("Drought (USDM weekly)", f"cache {usdm_age}d old", "FRESH", "auto-refreshes (≤3-day cache)"))
    else:
        rows.append(("Drought (USDM weekly)", f"cache {usdm_age}d old", "AGING", "will refresh on next screen"))

    manifest = config.PROCESSED_DIR / "reference_manifest.json"
    if manifest.exists():
        built = json.loads(manifest.read_text()).get("build_date", "")
        b_age = age_days(built + "T00:00:00") or 0
        status = "FRESH" if b_age < 200 else "AGING"
        action = "OK" if b_age < 200 else "consider `wattershed build-reference` (ACS/PLACES update annually)"
        rows.append(("Tract reference table", f"built {built}", status, action))
    else:
        rows.append(("Tract reference table", "MISSING", "ACTION", "run `wattershed build-reference` or restore committed artifact"))

    rows.append(
        ("Grid rates (eGRID2023 rev.2)", "calendar 2023, pub. 2025-06", "CURRENT EDITION",
         "check epa.gov/egrid ~early 2027 for eGRID2024; update URL in sources/egrid.py")
    )
    rows.append(
        ("Grid strain (NERC 2025 LTRA)", "pub. 2026-01, window 2026–2030", "CURRENT EDITION",
         "next LTRA ~Dec 2026; refresh data/reference/nerc_ltra.csv from its Table 1")
    )
    rows.append(
        ("EJScreen 2.32 pollution fields", "frozen (EPA withdrew tool 2025-02)", "FROZEN",
         "no successor exists; vintage is flagged on every output")
    )
    rows.append(
        ("County water denominators", "USGS 2015 (latest county census)", "FROZEN",
         "no newer county compilation; flagged MEDIUM confidence in output")
    )
    rows.append(
        ("Curated site registry", "facts cited as of 2026-07-16", "AGES FAST",
         "re-verify citations before public use; this industry changes monthly")
    )

    t = Table(show_header=True, header_style="bold")
    for col in ("Data layer", "Vintage / state", "Status", "What to do"):
        t.add_column(col, overflow="fold")
    for r in rows:
        t.add_row(*r)
    console.print(t)
    console.print(
        "[dim]Design intent: live layers refresh themselves; annual layers are one-line updates; "
        "frozen layers are disclosed on every output rather than silently served.[/dim]"
    )


@app.command("provenance")
def provenance_cmd():
    """Print the full registered source ledger."""
    from .provenance import SOURCES

    t = Table(show_header=True, header_style="bold")
    for col in ("id", "provider", "vintage"):
        t.add_column(col)
    for s in SOURCES.values():
        t.add_row(s.id, s.provider, s.vintage)
    console.print(t)


if __name__ == "__main__":
    app()
