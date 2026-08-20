"""End-to-end: build a tiny real repository, then run the CLI against it."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from repo_pulse.cli import main


def git(cwd, *args, **env):
    """Run git in an isolated config sandbox, on any OS."""
    environ = {
        # Keep the host's PATH (and SystemRoot on Windows) so `git` is findable.
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(cwd / ".gitconfig"),
        "GIT_CONFIG_SYSTEM": str(cwd / ".gitconfig-system"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(cwd),
        **env,
    }
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, env=environ)


@pytest.fixture(scope="module")
def sample_repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("sample")
    git(root, "init", "-q", "-b", "main")
    people = [("Ada Chen", "ada@example.com"), ("Bo Ali", "bo@example.com")]
    for i in range(6):
        name, email = people[i % 2]
        (root / "app.py").write_text("\n".join(f"line {j}" for j in range(i * 3 + 2)) + "\n")
        if i % 2 == 0:
            (root / "README.md").write_text(f"# sample {i}\n")
        git(root, "add", "-A")
        git(
            root,
            "commit",
            "-q",
            "--no-gpg-sign",
            "-m",
            f"commit {i}",
            GIT_AUTHOR_NAME=name,
            GIT_AUTHOR_EMAIL=email,
            GIT_AUTHOR_DATE=f"2024-03-0{i + 1}T1{i}:00:00+00:00",
            GIT_COMMITTER_NAME=name,
            GIT_COMMITTER_EMAIL=email,
            GIT_COMMITTER_DATE=f"2024-03-0{i + 1}T1{i}:00:00+00:00",
        )
    return root


def test_html_report_is_written_and_self_contained(sample_repo, tmp_path, capsys):
    out = tmp_path / "report.html"
    assert main([str(sample_repo), "-o", str(out)]) == 0
    html = out.read_text(encoding="utf-8")

    assert html.startswith("<!DOCTYPE html>")
    assert "{{" not in html  # every placeholder was filled
    assert "<svg" in html and "Ada Chen" in html
    assert "http://" not in html.replace("http://www.w3.org", "")  # no external requests
    assert "repo-pulse:" in capsys.readouterr().out


def test_json_output_is_machine_readable(sample_repo, capsys):
    assert main([str(sample_repo), "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["totals"]["commits"] == 6
    assert data["totals"]["authors"] == 2
    assert data["risks"]["bus_factor"] == 1
    assert data["repo"]["branch"] == "main"


def test_text_output_has_a_sparkline(sample_repo, capsys):
    assert main([str(sample_repo), "-f", "text"]) == 0
    out = capsys.readouterr().out
    assert "commits" in out and "bus factor" in out
    assert any(ch in out for ch in "▁▂▃▄▅▆▇█")


def test_date_window_filters_commits(sample_repo, capsys):
    assert main([str(sample_repo), "-f", "json", "--until", "2024-03-03"]) == 0
    assert json.loads(capsys.readouterr().out)["totals"]["commits"] == 3


def test_non_ascii_paths_are_not_octal_escaped(tmp_path, capsys):
    """git escapes non-ASCII paths by default; we turn that off."""
    root = tmp_path / "unicode-repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    folder = root / "документы"
    folder.mkdir()
    (folder / "отчёт.md").write_text("привет\n", encoding="utf-8")
    git(root, "add", "-A")
    git(
        root,
        "commit",
        "-q",
        "--no-gpg-sign",
        "-m",
        "добавил отчёт",
        GIT_AUTHOR_NAME="Иван Петров",
        GIT_AUTHOR_EMAIL="ivan@example.com",
        GIT_AUTHOR_DATE="2024-05-05T10:00:00+00:00",
        GIT_COMMITTER_NAME="Иван Петров",
        GIT_COMMITTER_EMAIL="ivan@example.com",
        GIT_COMMITTER_DATE="2024-05-05T10:00:00+00:00",
    )

    assert main([str(root), "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["files"][0]["path"] == "документы/отчёт.md"
    assert data["authors"][0]["name"] == "Иван Петров"
    assert data["recent_commits"][0]["subject"] == "добавил отчёт"


def test_clone_url_is_fetched_before_analysis(sample_repo, capsys):
    """A URL argument is cloned into a temp dir — tested offline via file://."""
    url = sample_repo.as_uri()
    assert main([url, "-f", "json"]) == 0
    out = capsys.readouterr()
    assert "cloning" in out.err
    data = json.loads(out.out)
    assert data["totals"]["commits"] == 6
    assert data["repo"]["name"] == sample_repo.name


def test_missing_repository_exits_with_error(tmp_path, capsys):
    assert main([str(tmp_path / "nope"), "-f", "text"]) == 2
    assert "repo-pulse:" in capsys.readouterr().err


def test_empty_window_is_reported_not_crashed(sample_repo, capsys):
    assert main([str(sample_repo), "-f", "text", "--since", "2030-01-01"]) == 2
    assert "no commits matched" in capsys.readouterr().err
