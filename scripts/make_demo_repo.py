#!/usr/bin/env python3
"""Build a synthetic git repository so you can try repo-pulse without a real one.

    python scripts/make_demo_repo.py /tmp/demo
    repo-pulse /tmp/demo --open

The generated history has several contributors with different working rhythms,
a couple of people who leave partway through, hot files, and one abandoned
module — enough for every panel in the report to have something to say.
"""

from __future__ import annotations

import random
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

AUTHORS = [
    # name, email, weight, start_month, end_month, tz, night_owl
    ("Ada Chen", "ada@example.com", 34, 0, 42, "+0800", False),
    ("Ivan Petrov", "ivan@example.com", 24, 0, 30, "+0300", True),
    ("Mei Tanaka", "mei@example.com", 18, 6, 42, "+0900", False),
    ("Luis Ortega", "luis@example.com", 12, 14, 42, "-0500", False),
    ("Sam Okoro", "sam@example.com", 8, 22, 42, "+0100", True),
    ("dependabot[bot]", "bot@example.com", 4, 18, 42, "+0000", False),
]

FILES = [
    ("src/core/engine.py", 30),
    ("src/core/scheduler.py", 18),
    ("src/api/routes.py", 22),
    ("src/api/auth.py", 9),
    ("src/legacy/importer.py", 6),
    ("src/utils/text.py", 7),
    ("tests/test_engine.py", 20),
    ("tests/test_api.py", 14),
    ("README.md", 8),
    ("docs/guide.md", 5),
    ("package-lock.json", 6),
]

VERBS = ["Fix", "Refactor", "Add", "Speed up", "Simplify", "Document", "Test", "Drop"]
NOUNS = [
    "retry logic",
    "the scheduler",
    "auth middleware",
    "the CSV importer",
    "error messages",
    "the config loader",
    "rate limiting",
    "the cache layer",
    "pagination",
    "the CLI flags",
]


def run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    proc = subprocess.run(args, cwd=str(cwd), capture_output=True, env=env, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"git failed: {' '.join(args)}\n{proc.stdout.strip()}\n{proc.stderr.strip()}"
        )


def main(target: str = "/tmp/demo-repo", months: int = 42, seed: int = 7) -> int:
    rng = random.Random(seed)
    root = Path(target).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        print(f"refusing to write into non-empty {root}", file=sys.stderr)
        return 1
    root.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q", "-b", "main"], root)

    import os

    base = datetime.now() - timedelta(days=months * 30)
    day = 0
    total = 0
    for month in range(months):
        # A release cadence: busy months, then a quiet one.
        intensity = 1.6 if month % 7 in (0, 1) else (0.35 if month % 11 == 5 else 1.0)
        active = [a for a in AUTHORS if a[3] <= month < a[4]]
        if not active:
            continue
        commits = int(rng.uniform(12, 34) * intensity)
        for _ in range(commits):
            name, email, _w, _s, _e, tz, owl = rng.choices(active, weights=[a[2] for a in active])[
                0
            ]
            offset_day = day + rng.randint(0, 29)
            hour = rng.choice([21, 22, 23, 0, 1] if owl else [9, 10, 11, 13, 14, 15, 16, 17])
            when = base + timedelta(days=offset_day, hours=hour, minutes=rng.randint(0, 59))
            if when.weekday() >= 5 and rng.random() > 0.25:
                when -= timedelta(days=2)
            stamp = when.strftime(f"%Y-%m-%dT%H:%M:%S{tz}")

            touched = rng.choices(
                [f[0] for f in FILES], weights=[f[1] for f in FILES], k=rng.randint(1, 3)
            )
            for path in set(touched):
                if path == "src/legacy/importer.py" and month > months - 14:
                    continue  # abandoned module
                p = root / path
                p.parent.mkdir(parents=True, exist_ok=True)
                lines = [f"line {rng.randint(0, 10**6)}" for _ in range(rng.randint(3, 60))]
                if p.exists() and rng.random() < 0.7:
                    old = p.read_text().splitlines()
                    keep = old[: max(0, len(old) - rng.randint(0, 25))]
                    lines = keep + lines
                p.write_text("\n".join(lines) + "\n")

            env = dict(os.environ)
            env.update(
                GIT_AUTHOR_NAME=name,
                GIT_AUTHOR_EMAIL=email,
                GIT_AUTHOR_DATE=stamp,
                GIT_COMMITTER_NAME=name,
                GIT_COMMITTER_EMAIL=email,
                GIT_COMMITTER_DATE=stamp,
            )
            run(["git", "add", "-A"], root, env)
            staged = subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(root), capture_output=True, text=True
            ).stdout.strip()
            if not staged:  # the only candidate file was the abandoned module
                continue
            subject = f"{rng.choice(VERBS)} {rng.choice(NOUNS)}"
            run(["git", "commit", "-q", "--no-gpg-sign", "-m", subject], root, env)
            total += 1
        day += 30

    print(f"created {total} commits across {months} months in {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
