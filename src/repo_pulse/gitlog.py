"""Read a repository's history out of ``git`` and into plain Python objects.

Only the standard library is used: we shell out to ``git log`` once, with a
machine-friendly format, and parse the stream.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"

_PRETTY = RECORD_SEP + FIELD_SEP.join(["%H", "%aN", "%aE", "%aI", "%P", "%s"])

# "src/{old => new}/file.py" and "old.py => new.py"
_RENAME_BRACED = re.compile(r"\{(?P<old>[^{}]*) => (?P<new>[^{}]*)\}")


class GitError(RuntimeError):
    """Raised when git is missing, or the path is not a usable repository."""


@dataclass(frozen=True)
class FileChange:
    path: str
    insertions: int
    deletions: int
    binary: bool = False

    @property
    def churn(self) -> int:
        return self.insertions + self.deletions


@dataclass
class Commit:
    sha: str
    author: str
    email: str
    date: datetime
    subject: str
    parents: tuple[str, ...] = ()
    files: list[FileChange] = field(default_factory=list)

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def insertions(self) -> int:
        return sum(f.insertions for f in self.files)

    @property
    def deletions(self) -> int:
        return sum(f.deletions for f in self.files)


@dataclass
class RepoInfo:
    path: Path
    name: str
    branch: str
    remote_url: str | None
    head: str | None


def _run(args: list[str], cwd: Path, check: bool = True) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            # git speaks UTF-8 regardless of the console codepage (matters on Windows).
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on host
        raise GitError("git is not installed or not on PATH") from exc
    if check and proc.returncode != 0:
        raise GitError(f"`git {' '.join(args)}` failed: {proc.stderr.strip() or proc.returncode}")
    return proc.stdout


def looks_like_url(value: str) -> bool:
    """True for things you'd clone rather than open: URLs and scp-style git addresses."""
    value = value.strip()
    if value.startswith(("http://", "https://", "ssh://", "git://", "file://")):
        return True
    # git@github.com:user/repo.git
    return value.startswith("git@") and ":" in value


def repo_name_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return name[:-4] if name.endswith(".git") else name or "repository"


def clone(url: str, into: Path) -> Path:
    """Clone ``url`` into ``into`` — full history, but no working tree.

    ``git log --numstat`` reads objects, not files, so skipping the checkout makes
    this noticeably faster and smaller. A shallow clone is *not* used: repo-pulse
    needs the whole history to say anything useful.
    """
    target = into / repo_name_from_url(url)
    _run(["clone", "--quiet", "--no-checkout", url, str(target)], into)
    return target


def resolve_repo(path: str | Path) -> RepoInfo:
    """Validate ``path`` is inside a git work tree and describe the repository."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise GitError(f"path does not exist: {p}")
    if not p.is_dir():
        p = p.parent

    top = _run(["rev-parse", "--show-toplevel"], p).strip()
    if not top:
        raise GitError(f"not a git repository: {p}")
    root = Path(top)

    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"], root, check=False).strip()
    head = _run(["rev-parse", "--short", "HEAD"], root, check=False).strip() or None
    remote = _run(["config", "--get", "remote.origin.url"], root, check=False).strip()

    return RepoInfo(
        path=root,
        name=root.name,
        branch=branch or "HEAD",
        remote_url=_normalise_remote(remote) if remote else None,
        head=head,
    )


def _normalise_remote(url: str) -> str:
    """Turn ``git@github.com:user/repo.git`` into a browsable https URL."""
    url = url.strip()
    if url.startswith("git@") and ":" in url:
        host, _, tail = url.partition(":")
        url = f"https://{host[4:]}/{tail}"
    if url.endswith(".git"):
        url = url[:-4]
    return url


def _normalise_rename(path: str) -> str:
    """Collapse git's rename notation down to the destination path."""
    if " => " not in path:
        return path
    if "{" in path:
        return _RENAME_BRACED.sub(lambda m: m.group("new"), path).replace("//", "/")
    return path.split(" => ", 1)[1]


def parse_log(text: str) -> list[Commit]:
    """Parse the output of ``git log`` in this module's format."""
    commits: list[Commit] = []
    for chunk in text.split(RECORD_SEP):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        head, _, body = chunk.partition("\n")
        parts = head.split(FIELD_SEP)
        if len(parts) < 6:
            continue
        sha, author, email, iso, parents, subject = parts[:6]
        try:
            date = datetime.fromisoformat(iso)
        except ValueError:
            continue
        commit = Commit(
            sha=sha,
            author=author.strip() or "(unknown)",
            email=email.strip().lower(),
            date=date,
            subject=subject.strip(),
            parents=tuple(p for p in parents.split() if p),
        )
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            added, removed, path = cols[0], cols[1], "\t".join(cols[2:])
            binary = added == "-" or removed == "-"
            commit.files.append(
                FileChange(
                    path=_normalise_rename(path),
                    insertions=0 if binary else int(added or 0),
                    deletions=0 if binary else int(removed or 0),
                    binary=binary,
                )
            )
        commits.append(commit)
    return commits


def read_commits(
    repo: RepoInfo,
    *,
    since: str | None = None,
    until: str | None = None,
    days: int | None = None,
    branch: str | None = None,
    max_commits: int | None = None,
    include_merges: bool = False,
) -> list[Commit]:
    """Run ``git log`` and return commits, newest first."""
    args = [
        # Without this git escapes non-ASCII paths as "\320\272..." octal soup.
        "-c",
        "core.quotepath=false",
        "log",
        f"--pretty=format:{_PRETTY}",
        "--numstat",
        "--no-color",
        "-M",  # detect renames
    ]
    if not include_merges:
        args.append("--no-merges")
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        args.append(f"--since={cutoff.date().isoformat()}")
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if max_commits:
        args.append(f"--max-count={max_commits}")
    if branch:
        args.append(branch)

    out = _run(args, repo.path)
    commits = parse_log(out)
    if not commits:
        raise GitError("no commits matched — try a wider --since window or a different --branch")
    return commits
