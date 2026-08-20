"""Render an :class:`~repo_pulse.analyze.Analysis` into a single HTML file."""

from __future__ import annotations

from html import escape
from pathlib import Path

from . import __version__
from .analyze import Analysis
from .charts import (
    churn_chart,
    fmt,
    hbar_chart,
    heatmap_chart,
    stacked_files_chart,
    timeline_chart,
)

TEMPLATE = Path(__file__).with_name("templates") / "report.html"
PROJECT_SLUG = "Giochvanno/repo-pulse"


def _tile(key: str, value: str, note: str = "") -> str:
    note_html = f'<div class="n">{note}</div>' if note else ""
    return (
        f'<div class="tile"><p class="k">{escape(key)}</p>'
        f'<div class="v">{value}</div>{note_html}</div>'
    )


def _table(headers: list[tuple[str, bool]], rows: list[list[str]]) -> str:
    head = "".join(
        f'<th class="num">{escape(h)}</th>' if num else f"<th>{escape(h)}</th>"
        for h, num in headers
    )
    body = []
    for r in rows:
        cells = "".join(
            f'<td class="num">{c}</td>' if num else f"<td>{c}</td>"
            for c, (_, num) in zip(r, headers)
        )
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _delta_html(pct: float | None) -> str:
    if pct is None:
        return '<span class="n">no prior window</span>'
    cls = "up" if pct >= 0 else "down"
    arrow = "▲" if pct >= 0 else "▼"
    return f'<span class="{cls}">{arrow} {abs(pct):.0f}% vs previous 30 days</span>'


def build_tiles(a: Analysis) -> str:
    t, m, r = a.totals, a.momentum, a.risks
    years = t["span_days"] / 365.25
    span = f"{years:.1f} years" if years >= 1 else f"{t['span_days']} days"
    tiles = [
        _tile("Commits", f"{t['commits']:,}".replace(",", " "), f"over {span}"),
        _tile("Contributors", str(t["authors"]), f"{r['active_authors_90d']} active in 90 days"),
        _tile("Commits / week", str(t["commits_per_week"]), _delta_html(m["delta_pct"])),
        _tile(
            "Bus factor",
            str(r["bus_factor"]),
            f"{'people' if r['bus_factor'] != 1 else 'person'} hold 50% of commits",
        ),
        _tile(
            "Net lines",
            ("+" if t["net_lines"] >= 0 else "−") + fmt(abs(t["net_lines"])),
            f"+{fmt(t['insertions'])} / −{fmt(t['deletions'])}",
        ),
        _tile("Files touched", fmt(t["files"]), f"median commit {t['median_commit_size']} lines"),
        _tile("Active days", str(t["active_days"]), f"longest streak {t['longest_streak']} days"),
        _tile("Busiest hour", t["busiest_day"], "author local time"),
    ]
    return "".join(tiles)


def build_risks(a: Analysis) -> str:
    r = a.risks
    bf = r["bus_factor"]
    flag = "warn" if bf <= 2 else "ok"
    names = ", ".join(r["bus_factor_authors"][:4]) or "—"
    notes = [
        f'<li><span class="flag {flag}">bus factor {bf}</span>'
        f"Half of all commits come from <b>{escape(names)}</b>. "
        f"The top contributor alone accounts for <b>{r['top_author_share']}%</b>.</li>",
        (
            f"<li><b>{r['single_owner_files']}</b> frequently-changed files have only ever "
            "been touched by one person — those are the ones to pair on or document.</li>"
            if r["single_owner_files"]
            else '<li><span class="flag ok">spread</span>Every frequently-changed file has '
            "been touched by at least two people.</li>"
        ),
    ]
    if r["single_owner_examples"]:
        items = "".join(
            f'<tr><td class="mono">{escape(x["path"])}</td><td>{escape(x["owner"])}</td></tr>'
            for x in r["single_owner_examples"][:6]
        )
        notes.append(
            "<li>Single-owner hotspots:"
            f'<table style="margin-top:6px"><thead><tr><th>File</th><th>Only author</th>'
            f"</tr></thead><tbody>{items}</tbody></table></li>"
        )
    if r["stale_hot_files"]:
        items = "".join(
            f'<tr><td class="mono">{escape(x["path"])}</td><td class="num">'
            f"{escape(x['last_touched'])}</td></tr>"
            for x in r["stale_hot_files"][:5]
        )
        notes.append(
            "<li>Heavily-changed files nobody has touched in a year:"
            f'<table style="margin-top:6px"><thead><tr><th>File</th>'
            f'<th class="num">Last touched</th></tr></thead><tbody>{items}</tbody></table></li>'
        )
    return f'<ul class="notes">{"".join(notes)}</ul>'


def render(a: Analysis, *, include_noise: bool = False) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    repo = a.repo
    t = a.totals

    remote = repo.get("remote_url")
    link = f' · <a href="{escape(remote)}">{escape(remote.split("//")[-1])}</a>' if remote else ""
    subtitle = (
        f"{escape(repo['branch'])} · {t['first_commit']} → {t['last_commit']} · "
        f"{t['commits']} commits by {t['authors']} contributors{link}"
    )

    author_rows = [
        (
            a_.name if len(a_.name) <= 24 else a_.name[:23] + "…",
            a_.commits,
            f"{a_.name} · {a_.commits} commits ({a_.share}%) · +{fmt(a_.insertions)}/"
            f"-{fmt(a_.deletions)} · {a_.active_days} active days · {a_.first} → {a_.last}",
        )
        for a_ in a.authors
    ]

    replacements = {
        "{{TITLE}}": escape(f"{repo['name']} — repo-pulse report"),
        "{{REPO_NAME}}": escape(repo["name"]),
        "{{SUBTITLE}}": subtitle,
        "{{BRANCH}}": escape(repo["branch"]),
        "{{GRANULARITY}}": a.granularity,
        "{{TILES}}": build_tiles(a),
        "{{TIMELINE}}": timeline_chart(a),
        "{{CHURN}}": churn_chart(a),
        "{{AUTHORS}}": hbar_chart(
            [(n, v, tip) for n, v, tip in author_rows], value_fmt=lambda v: f"{int(v)}"
        ),
        "{{HEATMAP}}": heatmap_chart(a),
        "{{FILES}}": stacked_files_chart(a),
        "{{RISKS}}": build_risks(a),
        "{{NOISE_NOTE}}": "" if not include_noise else " (disabled with --include-noise)",
        "{{TIMELINE_TABLE}}": _table(
            [
                ("Period", False),
                ("Commits", True),
                ("Authors", True),
                ("Added", True),
                ("Removed", True),
            ],
            [
                [
                    escape(b.label),
                    str(b.commits),
                    str(b.authors),
                    fmt(b.insertions),
                    fmt(b.deletions),
                ]
                for b in a.timeline
            ],
        ),
        "{{AUTHORS_TABLE}}": _table(
            [
                ("Contributor", False),
                ("Commits", True),
                ("Share", True),
                ("Added", True),
                ("Removed", True),
                ("Active days", True),
                ("Last seen", True),
            ],
            [
                [
                    escape(x.name),
                    str(x.commits),
                    f"{x.share}%",
                    fmt(x.insertions),
                    fmt(x.deletions),
                    str(x.active_days),
                    x.last,
                ]
                for x in a.authors
            ],
        ),
        "{{FILES_TABLE}}": _table(
            [
                ("File", False),
                ("Commits", True),
                ("Authors", True),
                ("Added", True),
                ("Removed", True),
                ("Last touched", True),
            ],
            [
                [
                    f'<span class="mono">{escape(f.path)}</span>',
                    str(f.commits),
                    str(f.authors),
                    fmt(f.insertions),
                    fmt(f.deletions),
                    f.last_touched,
                ]
                for f in a.files
            ],
        ),
        "{{RECENT}}": _table(
            [("Commit", False), ("Subject", False), ("Author", False), ("Date", True)],
            [
                [
                    f'<span class="mono">{escape(c["sha"])}</span>',
                    escape(c["subject"]),
                    escape(c["author"]),
                    c["date"],
                ]
                for c in a.recent_commits
            ],
        ),
        "{{GENERATED_AT}}": escape(repo["generated_at"]),
        "{{GH_SLUG}}": PROJECT_SLUG,
        "{{FOOTER_NOTE}}": f"v{__version__} · analysed {t['commits']} commits",
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html
