"""Turn a list of commits into the numbers the report shows."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .gitlog import Commit, RepoInfo

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Paths that say more about tooling than about the work.
NOISE_PREFIXES = ("vendor/", "node_modules/", "third_party/", "dist/", "build/")
NOISE_SUFFIXES = (".lock", ".min.js", ".min.css", ".map", ".svg", ".po", ".mo")
NOISE_NAMES = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
)


def is_noise(path: str) -> bool:
    """Generated or vendored files that would otherwise dominate every chart."""
    lowered = path.lower()
    name = lowered.rsplit("/", 1)[-1]
    return (
        lowered.startswith(NOISE_PREFIXES)
        or lowered.endswith(NOISE_SUFFIXES)
        or name in NOISE_NAMES
    )


@dataclass
class AuthorStat:
    name: str
    email: str
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    files: int = 0
    active_days: int = 0
    first: str = ""
    last: str = ""
    share: float = 0.0


@dataclass
class FileStat:
    path: str
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    authors: int = 0
    last_touched: str = ""

    @property
    def churn(self) -> int:
        return self.insertions + self.deletions


@dataclass
class Bucket:
    label: str
    start: str
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    authors: int = 0


@dataclass
class Analysis:
    repo: dict[str, Any]
    totals: dict[str, Any]
    timeline: list[Bucket]
    granularity: str
    authors: list[AuthorStat]
    files: list[FileStat]
    heatmap: list[list[int]]
    extensions: list[dict[str, Any]]
    risks: dict[str, Any]
    momentum: dict[str, Any]
    recent_commits: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "totals": self.totals,
            "granularity": self.granularity,
            "timeline": [asdict(b) for b in self.timeline],
            "authors": [asdict(a) for a in self.authors],
            "files": [{**asdict(f), "churn": f.churn} for f in self.files],
            "heatmap": self.heatmap,
            "extensions": self.extensions,
            "risks": self.risks,
            "momentum": self.momentum,
            "recent_commits": self.recent_commits,
        }


def _bucket_key(d: date, granularity: str) -> tuple[str, str]:
    """Return (sort key / iso start, human label) for a date at a granularity."""
    if granularity == "day":
        return d.isoformat(), d.strftime("%d %b")
    if granularity == "week":
        monday = d - timedelta(days=d.weekday())
        return monday.isoformat(), monday.strftime("%d %b")
    start = d.replace(day=1)
    return start.isoformat(), start.strftime("%b %Y")


def pick_granularity(span_days: int) -> str:
    if span_days <= 70:
        return "day"
    if span_days <= 730:
        return "week"
    return "month"


def _iter_buckets(first: date, last: date, granularity: str) -> Iterable[date]:
    """Yield one date per bucket so quiet periods still show up as gaps."""
    if granularity == "day":
        cur = first
        while cur <= last:
            yield cur
            cur += timedelta(days=1)
    elif granularity == "week":
        cur = first - timedelta(days=first.weekday())
        while cur <= last:
            yield cur
            cur += timedelta(days=7)
    else:
        cur = first.replace(day=1)
        while cur <= last:
            yield cur
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)


def bus_factor(counts: list[int], threshold: float = 0.5) -> int:
    """How many people it takes to cover ``threshold`` of the work."""
    total = sum(counts)
    if total <= 0:
        return 0
    running = 0
    for i, c in enumerate(sorted(counts, reverse=True), start=1):
        running += c
        if running / total >= threshold:
            return i
    return len(counts)


def longest_streak(days: set[date]) -> int:
    if not days:
        return 0
    best = run = 1
    ordered = sorted(days)
    for prev, cur in zip(ordered, ordered[1:]):
        run = run + 1 if cur - prev == timedelta(days=1) else 1
        best = max(best, run)
    return best


def analyse(
    repo: RepoInfo,
    commits: list[Commit],
    *,
    top: int = 10,
    include_noise: bool = False,
) -> Analysis:
    commits = sorted(commits, key=lambda c: c.date)
    first_dt, last_dt = commits[0].date, commits[-1].date
    span_days = max((last_dt.date() - first_dt.date()).days, 1)
    granularity = pick_granularity(span_days)

    authors: dict[str, AuthorStat] = {}
    author_days: dict[str, set[date]] = defaultdict(set)
    author_files: dict[str, set[str]] = defaultdict(set)
    files: dict[str, FileStat] = {}
    file_authors: dict[str, set[str]] = defaultdict(set)
    heat = [[0] * 24 for _ in range(7)]
    ext_commits: Counter[str] = Counter()
    ext_churn: Counter[str] = Counter()
    active_days: set[date] = set()
    sizes: list[int] = []
    bucket_data: dict[str, Bucket] = {}
    bucket_authors: dict[str, set[str]] = defaultdict(set)

    for c in commits:
        key = c.email or c.author.lower()
        stat = authors.setdefault(key, AuthorStat(name=c.author, email=c.email))
        stat.commits += 1
        stat.insertions += c.insertions
        stat.deletions += c.deletions
        day = c.date.date()
        stat.first = stat.first or day.isoformat()
        stat.last = day.isoformat()
        author_days[key].add(day)
        active_days.add(day)
        heat[c.date.weekday()][c.date.hour] += 1
        sizes.append(c.insertions + c.deletions)

        bkey, blabel = _bucket_key(day, granularity)
        bucket = bucket_data.setdefault(bkey, Bucket(label=blabel, start=bkey))
        bucket.commits += 1
        bucket.insertions += c.insertions
        bucket.deletions += c.deletions
        bucket_authors[bkey].add(key)

        for f in c.files:
            if not include_noise and is_noise(f.path):
                continue
            fs = files.setdefault(f.path, FileStat(path=f.path))
            fs.commits += 1
            fs.insertions += f.insertions
            fs.deletions += f.deletions
            fs.last_touched = day.isoformat()
            file_authors[f.path].add(key)
            author_files[key].add(f.path)
            ext = _extension(f.path)
            ext_commits[ext] += 1
            ext_churn[ext] += f.churn

    total_commits = len(commits)
    for key, stat in authors.items():
        stat.active_days = len(author_days[key])
        stat.files = len(author_files[key])
        stat.share = round(100 * stat.commits / total_commits, 1)
    for path, fs in files.items():
        fs.authors = len(file_authors[path])

    # Fill in empty buckets so the timeline shows real gaps.
    timeline: list[Bucket] = []
    for d in _iter_buckets(first_dt.date(), last_dt.date(), granularity):
        bkey, blabel = _bucket_key(d, granularity)
        b = bucket_data.get(bkey) or Bucket(label=blabel, start=bkey)
        b.authors = len(bucket_authors.get(bkey, ()))
        timeline.append(b)

    ranked_authors = sorted(authors.values(), key=lambda a: -a.commits)
    ranked_files = sorted(files.values(), key=lambda f: (-f.churn, -f.commits))

    single_owner = [f for f in ranked_files if f.authors == 1 and f.commits >= 3]
    stale_cut = (last_dt.date() - timedelta(days=365)).isoformat()
    stale = [f for f in ranked_files[: top * 5] if f.last_touched < stale_cut]

    now = last_dt.date()
    recent_30 = sum(1 for c in commits if (now - c.date.date()).days < 30)
    prior_30 = sum(1 for c in commits if 30 <= (now - c.date.date()).days < 60)
    recent_authors = {
        (c.email or c.author.lower()) for c in commits if (now - c.date.date()).days < 90
    }

    totals = {
        "commits": total_commits,
        "authors": len(authors),
        "files": len(files),
        "insertions": sum(a.insertions for a in authors.values()),
        "deletions": sum(a.deletions for a in authors.values()),
        "active_days": len(active_days),
        "span_days": span_days,
        "first_commit": first_dt.date().isoformat(),
        "last_commit": last_dt.date().isoformat(),
        "commits_per_week": round(total_commits / max(span_days / 7, 1), 1),
        "median_commit_size": int(statistics.median(sizes)) if sizes else 0,
        "longest_streak": longest_streak(active_days),
        "busiest_day": _busiest(heat),
    }
    totals["net_lines"] = totals["insertions"] - totals["deletions"]

    risks = {
        "bus_factor": bus_factor([a.commits for a in ranked_authors]),
        "bus_factor_authors": [
            a.name for a in ranked_authors[: bus_factor([a.commits for a in ranked_authors])]
        ],
        "top_author_share": ranked_authors[0].share if ranked_authors else 0.0,
        "single_owner_files": len(single_owner),
        "single_owner_examples": [
            {"path": f.path, "owner": _owner_name(authors, file_authors[f.path])}
            for f in single_owner[:top]
        ],
        "stale_hot_files": [
            {"path": f.path, "last_touched": f.last_touched, "churn": f.churn} for f in stale[:top]
        ],
        "active_authors_90d": len(recent_authors),
    }

    momentum = {
        "commits_30d": recent_30,
        "commits_prev_30d": prior_30,
        "delta_pct": _pct_change(prior_30, recent_30),
        "authors_90d": len(recent_authors),
    }

    extensions = [
        {"ext": ext, "commits": n, "churn": ext_churn[ext]} for ext, n in ext_commits.most_common(8)
    ]

    recent = [
        {
            "sha": c.sha[:8],
            "author": c.author,
            "date": c.date.date().isoformat(),
            "subject": c.subject[:120],
        }
        for c in reversed(commits[-min(len(commits), 12) :])
    ]

    return Analysis(
        repo={
            "name": repo.name,
            "branch": repo.branch,
            "remote_url": repo.remote_url,
            "head": repo.head,
            "path": str(repo.path),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        totals=totals,
        timeline=timeline,
        granularity=granularity,
        authors=ranked_authors[:top],
        files=ranked_files[:top],
        heatmap=heat,
        extensions=extensions,
        risks=risks,
        momentum=momentum,
        recent_commits=recent,
    )


def _extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "." not in name or name.startswith("."):
        return name if name.startswith(".") else "(no ext)"
    return "." + name.rsplit(".", 1)[1].lower()


def _owner_name(authors: dict[str, AuthorStat], keys: set[str]) -> str:
    for k in keys:
        if k in authors:
            return authors[k].name
    return "(unknown)"


def _busiest(heat: list[list[int]]) -> str:
    best = (0, 0, -1)
    for d, row in enumerate(heat):
        for h, v in enumerate(row):
            if v > best[2]:
                best = (d, h, v)
    return f"{WEEKDAYS[best[0]]} {best[1]:02d}:00"


def _pct_change(prev: int, cur: int) -> float | None:
    if prev == 0:
        return None
    return round(100 * (cur - prev) / prev, 1)
