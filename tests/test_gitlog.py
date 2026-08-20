from datetime import datetime

import pytest

from repo_pulse.gitlog import (
    FIELD_SEP,
    RECORD_SEP,
    GitError,
    _normalise_remote,
    _normalise_rename,
    looks_like_url,
    parse_log,
    repo_name_from_url,
    resolve_repo,
)


def _record(sha, author, email, iso, parents, subject, numstat=""):
    head = FIELD_SEP.join([sha, author, email, iso, parents, subject])
    return RECORD_SEP + head + ("\n" + numstat if numstat else "")


def test_parse_single_commit_with_numstat():
    text = _record(
        "abc123",
        "Ada Chen",
        "Ada@Example.com",
        "2024-05-01T10:30:00+02:00",
        "",
        "Fix retry logic",
        "12\t4\tsrc/core.py\n0\t9\ttests/test_core.py",
    )
    commits = parse_log(text)
    assert len(commits) == 1
    c = commits[0]
    assert c.sha == "abc123"
    assert c.author == "Ada Chen"
    assert c.email == "ada@example.com"  # normalised for identity matching
    assert c.date == datetime.fromisoformat("2024-05-01T10:30:00+02:00")
    assert c.insertions == 12 and c.deletions == 13
    assert [f.path for f in c.files] == ["src/core.py", "tests/test_core.py"]
    assert not c.is_merge


def test_binary_files_do_not_count_as_lines():
    text = _record("s", "A", "a@b.c", "2024-01-01T00:00:00+00:00", "", "Add logo", "-\t-\tlogo.png")
    (c,) = parse_log(text)
    assert c.insertions == 0 and c.deletions == 0
    assert c.files[0].binary is True


def test_merge_commits_are_detected():
    text = _record("s", "A", "a@b.c", "2024-01-01T00:00:00+00:00", "p1 p2", "Merge branch")
    (c,) = parse_log(text)
    assert c.is_merge


def test_multiple_commits_and_blank_input():
    text = "".join(
        _record(
            f"s{i}", "A", "a@b.c", f"2024-01-0{i + 1}T00:00:00+00:00", "", f"c{i}", "1\t0\ta.py"
        )
        for i in range(3)
    )
    assert len(parse_log(text)) == 3
    assert parse_log("") == []


def test_paths_with_tabs_survive():
    text = _record(
        "s", "A", "a@b.c", "2024-01-01T00:00:00+00:00", "", "odd", "1\t1\tweird\tname.py"
    )
    (c,) = parse_log(text)
    assert c.files[0].path == "weird\tname.py"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("src/{old => new}/file.py", "src/new/file.py"),
        ("old.py => new.py", "new.py"),
        ("plain/path.py", "plain/path.py"),
        ("{ => src}/a.py", "src/a.py"),
    ],
)
def test_rename_notation_collapses_to_destination(raw, expected):
    assert _normalise_rename(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("git@github.com:me/repo.git", "https://github.com/me/repo"),
        ("https://github.com/me/repo.git", "https://github.com/me/repo"),
        ("https://gitlab.com/me/repo", "https://gitlab.com/me/repo"),
    ],
)
def test_remote_urls_become_browsable(raw, expected):
    assert _normalise_remote(raw) == expected


@pytest.mark.parametrize(
    "value,is_url",
    [
        ("https://github.com/me/repo", True),
        ("http://git.example.com/repo.git", True),
        ("git@github.com:me/repo.git", True),
        ("ssh://git@host/repo.git", True),
        ("file:///tmp/repo", True),
        (".", False),
        ("~/code/app", False),
        ("/abs/path/repo", False),
        ("C:\\code\\repo", False),
    ],
)
def test_url_detection(value, is_url):
    assert looks_like_url(value) is is_url


@pytest.mark.parametrize(
    "url,name",
    [
        ("https://github.com/me/repo", "repo"),
        ("https://github.com/me/repo.git", "repo"),
        ("git@github.com:me/repo.git", "repo"),
        ("https://github.com/me/repo/", "repo"),
    ],
)
def test_repo_name_from_url(url, name):
    assert repo_name_from_url(url) == name


def test_resolve_repo_rejects_non_repository(tmp_path):
    with pytest.raises(GitError):
        resolve_repo(tmp_path)
