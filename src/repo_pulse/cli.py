"""Command line interface for repo-pulse."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import webbrowser
from pathlib import Path

from . import __version__
from .analyze import analyse
from .charts import fmt
from .gitlog import GitError, clone, looks_like_url, read_commits, resolve_repo
from .report import render

SPARKS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[int], width: int = 48) -> str:
    """A single-line commit-activity chart for the terminal."""
    if not values:
        return ""
    if len(values) > width:  # average down into `width` buckets
        size = len(values) / width
        values = [
            int(sum(values[int(i * size) : max(int((i + 1) * size), int(i * size) + 1)]))
            for i in range(width)
        ]
    hi = max(values) or 1
    return "".join(SPARKS[min(len(SPARKS) - 1, int(v / hi * (len(SPARKS) - 1)))] for v in values)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="repo-pulse",
        description="Turn any git repository into a beautiful, self-contained HTML report.",
        epilog="Examples:\n"
        "  repo-pulse .                      report for the current repo\n"
        "  repo-pulse ~/code/app --days 90   only the last quarter\n"
        "  repo-pulse https://github.com/psf/requests   clone it first, then report\n"
        "  repo-pulse . -f text              quick summary in the terminal\n"
        "  repo-pulse . -f json -o pulse.json  machine-readable metrics\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="local path to a git repository, or a clone URL (default: .)",
    )
    p.add_argument("-o", "--output", help="output file (default: <repo>-pulse.html)")
    p.add_argument(
        "-f",
        "--format",
        choices=("html", "json", "text"),
        default="html",
        help="output format (default: html)",
    )
    p.add_argument("-n", "--top", type=int, default=10, help="rows per ranking (default: 10)")
    p.add_argument("--days", type=int, help="only analyse the last N days")
    p.add_argument("--since", help="git date, e.g. 2024-01-01 or '6 months ago'")
    p.add_argument("--until", help="git date upper bound")
    p.add_argument("-b", "--branch", help="branch or revision range (default: current HEAD)")
    p.add_argument("--max-commits", type=int, help="stop after N commits (useful on huge repos)")
    p.add_argument("--include-merges", action="store_true", help="count merge commits too")
    p.add_argument(
        "--include-noise",
        action="store_true",
        help="keep lockfiles, vendor/ and other generated paths in file rankings",
    )
    p.add_argument("--open", action="store_true", help="open the report in your browser")
    p.add_argument("-q", "--quiet", action="store_true", help="print nothing but errors")
    p.add_argument("-V", "--version", action="version", version=f"repo-pulse {__version__}")
    return p


def text_summary(a) -> str:
    t, r, m = a.totals, a.risks, a.momentum
    spark = sparkline([b.commits for b in a.timeline])
    lines = [
        f"\n  {a.repo['name']}  ({a.repo['branch']})",
        f"  {t['first_commit']} → {t['last_commit']}  ·  {t['span_days']} days\n",
        f"  commits        {t['commits']:>8}   ({t['commits_per_week']}/week)",
        f"  contributors   {t['authors']:>8}   ({r['active_authors_90d']} active in 90d)",
        f"  files touched  {t['files']:>8}",
        f"  lines          {'+' + fmt(t['insertions']):>8} / -{fmt(t['deletions'])}",
        f"  bus factor     {r['bus_factor']:>8}   ({', '.join(r['bus_factor_authors'][:3])})",
        f"  busiest        {t['busiest_day']:>8}",
        f"\n  activity per {a.granularity}",
        f"  {spark}",
        "",
        "  top contributors",
    ]
    for author in a.authors[:5]:
        bar = "█" * max(1, round(author.share / 4))
        lines.append(f"    {author.name[:22]:<22} {author.commits:>5}  {bar} {author.share}%")
    lines.append("\n  hot files")
    for f in a.files[:5]:
        path = f.path if len(f.path) <= 46 else "…" + f.path[-45:]
        lines.append(f"    {path:<46} {f.commits:>4} commits  {fmt(f.churn):>6} lines")
    if m["delta_pct"] is not None:
        arrow = "▲" if m["delta_pct"] >= 0 else "▼"
        lines.append(
            f"\n  last 30 days: {m['commits_30d']} commits "
            f"{arrow} {abs(m['delta_pct']):.0f}% vs the 30 before"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="repo-pulse-") as scratch:
        try:
            target = args.path
            if looks_like_url(target):
                if not args.quiet:
                    print(f"repo-pulse: cloning {target} …", file=sys.stderr)
                target = clone(target, Path(scratch))
            repo = resolve_repo(target)
            commits = read_commits(
                repo,
                since=args.since,
                until=args.until,
                days=args.days,
                branch=args.branch,
                max_commits=args.max_commits,
                include_merges=args.include_merges,
            )
        except GitError as exc:
            print(f"repo-pulse: {exc}", file=sys.stderr)
            return 2

        analysis = analyse(repo, commits, top=args.top, include_noise=args.include_noise)

        if args.format == "text":
            sys.stdout.write(text_summary(analysis))
            return 0

        if args.format == "json":
            payload = json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(payload, encoding="utf-8")
                if not args.quiet:
                    print(f"repo-pulse: wrote {args.output}")
            else:
                sys.stdout.write(payload + "\n")
            return 0

        out = Path(args.output or f"{repo.name}-pulse.html")
        out.write_text(render(analysis, include_noise=args.include_noise), encoding="utf-8")
        if not args.quiet:
            size = out.stat().st_size / 1024
            print(
                f"repo-pulse: {analysis.totals['commits']} commits, "
                f"{analysis.totals['authors']} contributors → {out} ({size:.0f} KB)"
            )
        if args.open:
            webbrowser.open(out.resolve().as_uri())
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
