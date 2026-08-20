from datetime import date, datetime, timedelta, timezone

import pytest

from repo_pulse.analyze import (
    analyse,
    bus_factor,
    is_noise,
    longest_streak,
    pick_granularity,
)
from repo_pulse.charts import fmt
from repo_pulse.cli import sparkline
from repo_pulse.gitlog import Commit, FileChange, RepoInfo


def make_commit(day, author="Ada", email="ada@x.dev", files=(("src/a.py", 10, 2),), hour=12):
    return Commit(
        sha=f"{author}{day}",
        author=author,
        email=email,
        date=datetime(2024, 1, 1, hour, tzinfo=timezone.utc) + timedelta(days=day),
        subject="work",
        files=[FileChange(p, i, d) for p, i, d in files],
    )


@pytest.fixture
def repo(tmp_path):
    return RepoInfo(path=tmp_path, name="demo", branch="main", remote_url=None, head="abc1234")


@pytest.mark.parametrize(
    "counts,expected",
    [
        ([10], 1),
        ([5, 5], 1),
        ([1, 1, 1, 1], 2),
        ([90, 5, 5], 1),
        ([], 0),
    ],
)
def test_bus_factor(counts, expected):
    assert bus_factor(counts) == expected


def test_longest_streak_counts_consecutive_days():
    days = {date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 9)}
    assert longest_streak(days) == 3
    assert longest_streak(set()) == 0


@pytest.mark.parametrize("span,expected", [(10, "day"), (70, "day"), (200, "week"), (900, "month")])
def test_granularity_follows_lifespan(span, expected):
    assert pick_granularity(span) == expected


@pytest.mark.parametrize(
    "path,noise",
    [
        ("package-lock.json", True),
        ("vendor/lib/x.go", True),
        ("assets/app.min.js", True),
        ("poetry.lock", True),
        ("src/core.py", False),
        ("docs/guide.md", False),
    ],
)
def test_noise_filter(path, noise):
    assert is_noise(path) is noise


def test_analysis_totals_and_rankings(repo):
    commits = [
        make_commit(0, "Ada", "ada@x.dev", (("src/a.py", 10, 0),)),
        make_commit(1, "Ada", "ada@x.dev", (("src/a.py", 5, 3), ("src/b.py", 1, 1))),
        make_commit(2, "Bo", "bo@x.dev", (("src/b.py", 2, 2),)),
        make_commit(3, "Bo", "bo@x.dev", (("package-lock.json", 900, 900),)),
    ]
    a = analyse(repo, commits)

    assert a.totals["commits"] == 4
    assert a.totals["authors"] == 2
    assert a.totals["insertions"] == 918  # totals keep every line...
    assert [f.path for f in a.files] == ["src/a.py", "src/b.py"]  # ...rankings drop noise
    assert a.authors[0].name == "Ada"
    assert a.authors[0].share == 50.0
    assert a.risks["bus_factor"] == 1
    assert a.granularity == "day"


def test_noise_can_be_kept(repo):
    commits = [make_commit(0, files=(("package-lock.json", 5, 5),))]
    a = analyse(repo, commits, include_noise=True)
    assert [f.path for f in a.files] == ["package-lock.json"]


def test_timeline_keeps_quiet_periods_as_gaps(repo):
    a = analyse(repo, [make_commit(0), make_commit(5)])
    assert len(a.timeline) == 6
    assert [b.commits for b in a.timeline] == [1, 0, 0, 0, 0, 1]


def test_single_owner_files_are_flagged(repo):
    commits = [make_commit(d, "Ada", "ada@x.dev", (("src/solo.py", 3, 1),)) for d in range(4)]
    a = analyse(repo, commits)
    assert a.risks["single_owner_files"] == 1
    assert a.risks["single_owner_examples"][0]["owner"] == "Ada"


def test_heatmap_places_commits_by_weekday_and_hour(repo):
    a = analyse(repo, [make_commit(0, hour=9)])  # 2024-01-01 was a Monday
    assert a.heatmap[0][9] == 1
    assert sum(sum(row) for row in a.heatmap) == 1


@pytest.mark.parametrize(
    "value,expected", [(4, "4"), (1200, "1.2k"), (1_000_000, "1M"), (0, "0"), (-2500, "-2.5k")]
)
def test_number_formatting(value, expected):
    assert fmt(value) == expected


def test_sparkline_shape():
    assert sparkline([]) == ""
    assert len(sparkline([1, 2, 3])) == 3
    assert len(sparkline(list(range(500)), width=40)) == 40
    assert sparkline([0, 10])[0] == "▁"
