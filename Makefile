PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: install test lint screen-all reports dashboard reference all clean

install:
	python3 -m venv .venv
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check src tests

## Screen every curated site -> out/*.json
screen-all:
	.venv/bin/wattershed screen-all --out-dir out

## Render per-site HTML memos -> out/reports/
reports:
	$(PY) -c "import json; from pathlib import Path; \
	from wattershed.models import Screening; from wattershed.report.render import render_report; \
	outdir = Path('out/reports'); outdir.mkdir(parents=True, exist_ok=True); \
	[ (outdir/(f.stem + '.html')).write_text(render_report(Screening.model_validate_json(f.read_text()))) \
	  for f in sorted(Path('out').glob('*.json')) ]"

## Assemble the static dashboard -> site/index.html
dashboard:
	.venv/bin/wattershed build-dashboard --results-dir out --out-file site/index.html

## Full reproduction of the committed national reference artifacts (~600 MB of
## downloads, 15-40 min). Everything else works without running this.
reference:
	.venv/bin/wattershed build-reference

all: screen-all reports dashboard

clean:
	rm -rf out site .pytest_cache .ruff_cache
