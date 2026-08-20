# Contributing

Thanks for wanting to make this better. The project is small on purpose — please keep it
that way.

## The two rules

1. **No runtime dependencies.** `repo-pulse` must keep working with nothing but Python's
   standard library and `git`. Dev-only tools (`pytest`, `ruff`) are fine.
2. **Every metric answers a question.** If you can't write the one-sentence question a
   number answers ("how exposed are we if one person leaves?"), it doesn't go on the page.

## Setup

```bash
pip install -e ".[dev]"
pytest              # 45+ tests, no network, no fixtures to download
ruff check . && ruff format --check .
```

To look at real output while you work:

```bash
python scripts/make_demo_repo.py /tmp/demo   # synthetic repo, ~1000 commits
repo-pulse /tmp/demo -o /tmp/demo.html --open
```

## Where things live

| File | Responsibility |
|---|---|
| `gitlog.py` | Everything that shells out to `git`. Nothing else may call `subprocess`. |
| `analyze.py` | Pure functions: commits in, numbers out. Easiest place to add a metric. |
| `charts.py` | Numbers to SVG strings. No data decisions here. |
| `report.py` | Numbers + SVG into the HTML template. |
| `templates/report.html` | All CSS and JS. Inline only — the report must open offline. |

## Adding a metric

1. Compute it in `analyse()` and put it in `totals`, `risks`, or a new field on `Analysis`.
2. Add it to `to_dict()` so JSON consumers get it too.
3. Surface it — a stat tile in `build_tiles()`, a bullet in `build_risks()`, or a chart.
4. Add a test in `tests/test_analyze.py` using the `make_commit` helper.

## Charts

Colours come from CSS custom properties, never hard-coded hex, so light and dark mode both
work. The palette is checked for colour-vision deficiency: if you add a series colour,
don't invent one — reuse a defined `--series-*` slot, and make sure the chart is still
readable with colours removed (direct labels or the table view).
