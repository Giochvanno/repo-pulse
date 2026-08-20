"""Hand-rolled SVG charts — no plotting library, no runtime dependencies.

Every chart is plain SVG that references CSS custom properties for colour, so
the same markup works in light and dark mode. Hover targets carry ``data-tip``
attributes; the tooltip layer lives in the HTML template.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from .analyze import WEEKDAYS, Analysis

# Chart geometry (user units; the SVG scales to its container).
W = 920
H = 280
PAD_L, PAD_R, PAD_T, PAD_B = 46, 14, 18, 30


def fmt(n: float) -> str:
    """Compact human numbers: 1234 -> 1.2k."""
    n = float(n)
    for unit, div in (("M", 1e6), ("k", 1e3)):
        if abs(n) >= div:
            v = n / div
            return f"{v:.1f}".rstrip("0").rstrip(".") + unit
    return f"{n:.0f}"


def _nice_max(value: float, steps: int = 4) -> float:
    """Round an axis maximum up to something a human would have chosen."""
    if value <= 0:
        return 1.0
    raw = value / steps
    mag = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 0.1
    for mult in (1, 2, 2.5, 5, 10):
        if mag * mult >= raw:
            return mag * mult * steps
    return value


def _ticks(vmax: float, steps: int = 4) -> list[float]:
    return [vmax * i / steps for i in range(steps + 1)]


def _bar_path(x: float, y: float, w: float, h: float, r: float = 4.0, up: bool = True) -> str:
    """A bar with rounded ends away from the baseline, square at the baseline."""
    r = max(0.0, min(r, w / 2, h))
    if h <= 0:
        return ""
    if up:
        return (
            f"M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
            f"L{x + w:.1f},{y + h:.1f} Z"
        )
    return (
        f"M{x:.1f},{y:.1f} L{x:.1f},{y + h - r:.1f} Q{x:.1f},{y + h:.1f} {x + r:.1f},{y + h:.1f} "
        f"L{x + w - r:.1f},{y + h:.1f} Q{x + w:.1f},{y + h:.1f} {x + w:.1f},{y + h - r:.1f} "
        f"L{x + w:.1f},{y:.1f} Z"
    )


def _hbar_path(x: float, y: float, w: float, h: float, r: float = 4.0) -> str:
    """Horizontal bar: rounded right end, square against the left baseline."""
    r = max(0.0, min(r, h / 2, w))
    if w <= 0:
        return ""
    return (
        f"M{x:.1f},{y:.1f} L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
        f"L{x + w:.1f},{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} "
        f"L{x:.1f},{y + h:.1f} Z"
    )


def _svg(body: str, height: int = H, width: int = W, label: str = "") -> str:
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="{escape(label)}">'
        f"{body}</svg>"
    )


def _x_labels(points: Sequence[tuple[float, str]], y: float, min_gap: float = 78.0) -> str:
    """Draw as many x labels as fit without ever letting two collide."""
    if not points:
        return ""
    keep: list[tuple[float, str]] = []
    last = -1e9
    for x, label in points:
        if x - last >= min_gap:
            keep.append((x, label))
            last = x
    # The final bucket is the interesting one — make room for it.
    if keep and points[-1][0] - keep[-1][0] < min_gap and keep[-1] != points[-1]:
        keep.pop()
    if not keep or keep[-1] != points[-1]:
        keep.append(points[-1])
    out = []
    for x, label in keep:
        # Keep the outermost labels inside the drawing area.
        anchor = "middle"
        if x > W - 70:
            anchor, x = "end", W - PAD_R
        elif x < PAD_L + 24:
            anchor, x = "start", PAD_L - 20
        out.append(
            f'<text class="tick" x="{x:.1f}" y="{y:.0f}" text-anchor="{anchor}">'
            f"{escape(label)}</text>"
        )
    return "".join(out)


def _grid(vmax: float, top: float, bottom: float, steps: int = 4) -> str:
    out = []
    for t in _ticks(vmax, steps):
        y = bottom - (t / vmax) * (bottom - top) if vmax else bottom
        out.append(
            f'<line class="grid" x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end">{fmt(t)}</text>'
        )
    return "".join(out)


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #


def timeline_chart(a: Analysis) -> str:
    """Commits over time — area + line, with a hover crosshair."""
    pts = a.timeline
    if not pts:
        return ""
    vmax = _nice_max(max(p.commits for p in pts))
    top, bottom = PAD_T, H - PAD_B
    n = len(pts)
    step = (W - PAD_L - PAD_R) / max(n - 1, 1)

    def xy(i: int, v: float) -> tuple[float, float]:
        return PAD_L + i * step, bottom - (v / vmax) * (bottom - top)

    coords = [xy(i, p.commits) for i, p in enumerate(pts)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
    area = (
        f"M{coords[0][0]:.1f},{bottom:.1f} "
        + " ".join(f"L{x:.1f},{y:.1f}" for x, y in coords)
        + f" L{coords[-1][0]:.1f},{bottom:.1f} Z"
    )

    xlabels = _x_labels([(coords[i][0], p.label) for i, p in enumerate(pts)], y=H - 8)

    hits = "".join(
        f'<rect class="hit" x="{coords[i][0] - step / 2:.1f}" y="{top}" '
        f'width="{step:.1f}" height="{bottom - top:.1f}" '
        f'data-x="{coords[i][0]:.1f}" data-y="{coords[i][1]:.1f}" '
        f'data-tip="{escape(p.label)} · {p.commits} commits · {p.authors} authors · '
        f'+{fmt(p.insertions)}/-{fmt(p.deletions)}"/>'
        for i, p in enumerate(pts)
    )

    peak = max(range(n), key=lambda i: pts[i].commits)
    px, py = coords[peak]
    peak_label = (
        f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="4.5"/>'
        f'<text class="point-label" x="{min(px, W - PAD_R - 40):.1f}" y="{py - 12:.1f}" '
        f'text-anchor="middle">{pts[peak].commits}</text>'
    )

    body = (
        f'<g class="crosshair" style="display:none">'
        f'<line class="cross-line" y1="{top}" y2="{bottom}"/>'
        f'<circle class="cross-dot" r="5"/></g>'
    )
    return _svg(
        _grid(vmax, top, bottom)
        + f'<path class="area" d="{area}"/><path class="line" d="{line}"/>'
        + peak_label
        + xlabels
        + body
        + hits,
        label=f"Commits per {a.granularity} over the life of the repository",
    )


def churn_chart(a: Analysis) -> str:
    """Lines added above the baseline, lines removed below it (diverging)."""
    pts = a.timeline
    if not pts:
        return ""
    height = 260
    top, bottom = 16, height - 28
    mid = (top + bottom) / 2
    vmax = _nice_max(max([max(p.insertions, p.deletions) for p in pts] or [1]), steps=2)
    n = len(pts)
    slot = (W - PAD_L - PAD_R) / n
    bw = max(2.0, slot - 2.0)  # 2px surface gap between adjacent bars

    bars = []
    for i, p in enumerate(pts):
        x = PAD_L + i * slot + (slot - bw) / 2
        h_up = (p.insertions / vmax) * (mid - top)
        h_dn = (p.deletions / vmax) * (bottom - mid)
        if h_up > 0:
            bars.append(f'<path class="s1" d="{_bar_path(x, mid - h_up, bw, h_up, up=True)}"/>')
        if h_dn > 0:
            bars.append(f'<path class="s8" d="{_bar_path(x, mid + 1, bw, h_dn, up=False)}"/>')
        bars.append(
            f'<rect class="hit" x="{PAD_L + i * slot:.1f}" y="{top}" width="{slot:.1f}" '
            f'height="{bottom - top:.1f}" data-tip="{escape(p.label)} · '
            f'+{fmt(p.insertions)} added · -{fmt(p.deletions)} removed"/>'
        )

    xlabels = _x_labels(
        [(PAD_L + i * slot + slot / 2, p.label) for i, p in enumerate(pts)], y=height - 8
    )
    axis = (
        f'<line class="baseline" x1="{PAD_L}" y1="{mid:.1f}" x2="{W - PAD_R}" y2="{mid:.1f}"/>'
        f'<text class="tick" x="{PAD_L - 8}" y="{top + 10}" text-anchor="end">+{fmt(vmax)}</text>'
        f'<text class="tick" x="{PAD_L - 8}" y="{bottom}" text-anchor="end">−{fmt(vmax)}</text>'
    )
    return _svg(
        axis + "".join(bars) + xlabels, height=height, label="Lines added and removed over time"
    )


def hbar_chart(
    rows: Sequence[tuple[str, float, str]],
    *,
    row_h: int = 34,
    label_w: int = 190,
    value_fmt=fmt,
) -> str:
    """Horizontal bars: (label, value, tooltip). One series, so no legend."""
    if not rows:
        return ""
    height = row_h * len(rows) + 12
    vmax = max(v for _, v, _ in rows) or 1
    track = W - label_w - 90
    out = []
    for i, (label, value, tip) in enumerate(rows):
        y = 6 + i * row_h
        w = (value / vmax) * track
        out.append(
            f'<text class="row-label" x="0" y="{y + row_h / 2 + 4:.0f}">{escape(label)}</text>'
            f'<path class="s1" d="{_hbar_path(label_w, y + 6, max(w, 2), row_h - 14)}"/>'
            f'<text class="row-value" x="{label_w + max(w, 2) + 10:.0f}" '
            f'y="{y + row_h / 2 + 4:.0f}">{escape(value_fmt(value))}</text>'
            f'<rect class="hit" x="0" y="{y}" width="{W}" height="{row_h}" '
            f'data-tip="{escape(tip)}"/>'
        )
    return _svg("".join(out), height=height, width=W, label="Ranked bar chart")


def stacked_files_chart(a: Analysis) -> str:
    """Top files by churn, split into lines added / removed."""
    files = a.files
    if not files:
        return ""
    row_h, label_w = 34, 300
    height = row_h * len(files) + 12
    vmax = max(f.churn for f in files) or 1
    track = W - label_w - 90
    out = []
    for i, f in enumerate(files):
        y = 6 + i * row_h
        w_add = (f.insertions / vmax) * track
        w_del = (f.deletions / vmax) * track
        short = f.path if len(f.path) <= 40 else "…" + f.path[-39:]
        added = _hbar_path(label_w, y + 6, max(w_add, 1), row_h - 14, r=0)
        # 2px surface gap between the two segments
        removed = _hbar_path(label_w + w_add + 2, y + 6, max(w_del, 1), row_h - 14)
        out.append(
            f'<text class="row-label mono" x="0" y="{y + row_h / 2 + 4:.0f}">{escape(short)}</text>'
            f'<path class="s1" d="{added}"/>'
            f'<path class="s8" d="{removed}"/>'
            f'<text class="row-value" x="{label_w + w_add + w_del + 12:.0f}" '
            f'y="{y + row_h / 2 + 4:.0f}">{fmt(f.churn)}</text>'
            f'<rect class="hit" x="0" y="{y}" width="{W}" height="{row_h}" '
            f'data-tip="{escape(f.path)} · {f.commits} commits · {f.authors} authors · '
            f'+{fmt(f.insertions)}/-{fmt(f.deletions)}"/>'
        )
    return _svg("".join(out), height=height, label="Most-changed files")


def heatmap_chart(a: Analysis) -> str:
    """Weekday x hour commit density — one hue, light to dark."""
    heat = a.heatmap
    vmax = max((max(row) for row in heat), default=0) or 1
    cell, gap = 33, 2
    left, topy = 42, 22
    height = topy + 7 * (cell + gap) + 20
    width = left + 24 * (cell + gap) + 8
    out = []
    for h in range(0, 24, 3):
        out.append(
            f'<text class="tick" x="{left + h * (cell + gap) + cell / 2:.0f}" y="14" '
            f'text-anchor="middle">{h:02d}</text>'
        )
    for d, row in enumerate(heat):
        y = topy + d * (cell + gap)
        out.append(
            f'<text class="tick" x="{left - 8}" y="{y + cell / 2 + 4:.0f}" '
            f'text-anchor="end">{WEEKDAYS[d]}</text>'
        )
        for h, v in enumerate(row):
            x = left + h * (cell + gap)
            level = 0 if v == 0 else min(6, 1 + int(5 * (v / vmax)))
            out.append(
                f'<rect class="cell l{level}" x="{x}" y="{y}" width="{cell}" height="{cell}" '
                f'rx="4" data-tip="{WEEKDAYS[d]} {h:02d}:00 · {v} commits"/>'
            )
    return _svg(
        "".join(out),
        height=height,
        width=width,
        label="Commits by weekday and hour of day",
    )
