# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-08-20

First release.

### Added

- The path argument also accepts a clone URL (`https://`, `git@…`, `ssh://`): the
  repository is cloned to a temporary directory, analysed, and cleaned up. The clone
  skips the working-tree checkout but keeps the full history.
- `repo-pulse <path>` writes a single self-contained HTML report: activity timeline,
  code churn, contributor ranking, weekday × hour heatmap, hot files, and a risk section
  (bus factor, top-author concentration, single-owner files, abandoned hotspots).
- `-f json` for machine-readable metrics and `-f text` for a terminal summary with a
  sparkline.
- Range and scope flags: `--days`, `--since`, `--until`, `--branch`, `--max-commits`,
  `--include-merges`, `--include-noise`, `--top`.
- Light and dark themes, hover tooltips, and a table view of every chart for
  accessibility. The categorical palette is validated for colour-vision deficiency.
- Zero runtime dependencies — standard library and `git` only.
- `scripts/make_demo_repo.py` generates a synthetic repository for trying the tool out.
