"""Automatic parameter estimation for one-click splitting.

The manual workflow exposes ~15 knobs (distance thresholds, anchor /
min areas, merge distance, …).  In practice, for the ``exact`` keying
mode that's the default, almost all of them are *derivable* from two
measurements taken off the image itself:

1. **The background colour** — sprite sheets are framed by a flat chroma
   fill, so the dominant colour of the 1-pixel border is the background
   with very high confidence (see :func:`estimate_bg_bgr`).

2. **The background/foreground distance threshold** — once the colour is
   known, every pixel has a BGR Euclidean distance to it.  Background
   pixels form a tall spike near zero; foreground pixels spread out far
   above.  The *valley* between the spike and the foreground mass is the
   natural cut point (see :func:`_distance_valley`).  Plain Otsu over the
   whole range over-shoots because the foreground spans a huge spread;
   we instead search for the histogram minimum in a low window, which
   lands on the same value a human would tune to.

From those two numbers we derive the inner/outer ramp, the strict-alpha
thresholds used for icon identity, and — by running connected-component
statistics on the strict mask — the anchor area, minimum keep area, and
merge distance for the hybrid splitter.

The public surface is intentionally tiny:

* :func:`estimate_bg_bgr` — dominant border colour.
* :func:`auto_params` — full ``AutoResult`` (bg colour + a flat
  ``{widget_name: value}`` map ready to drop into the GUI widgets or the
  CLI argument defaults).

Everything is grounded in measurements off the supplied image; no
network, no learned model, no new dependencies beyond OpenCV/NumPy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from keying import BgrColor


@dataclass(frozen=True)
class AutoResult:
    """Outcome of :func:`auto_params`.

    ``bg_bgr``
        The detected background colour (BGR).

    ``values``
        A flat ``{widget_name: value}`` map keyed by the same names the
        GUI uses for its Tk variables (``d_inner``, ``anchor_area``, …).
        Callers apply only the keys they care about; unknown keys are
        simply ignored by the widget/profile layer.

    ``notes``
        Short human-readable diagnostics (e.g. detected icon count),
        surfaced in the status bar so the user knows what happened.
    """

    bg_bgr: BgrColor
    values: dict[str, float | int | str | bool]
    notes: str = ""
    extras: dict[str, float] = field(default_factory=dict)


# ─── background colour ──────────────────────────────────────────────
def estimate_bg_bgr(img_bgr: np.ndarray, border: int = 2) -> BgrColor:
    """Return the dominant colour of the image's outer frame.

    Samples a ``border``-pixel-thick ring around the edge and returns the
    most common colour after light quantisation (8-level buckets), which
    is robust to JPEG noise and anti-aliasing.  Falls back to the corner
    pixel for degenerate (tiny) images.
    """
    h, w = img_bgr.shape[:2]
    if h < 4 or w < 4:
        return tuple(int(c) for c in img_bgr[0, 0])  # type: ignore[return-value]

    b = max(1, border)
    ring = np.concatenate([
        img_bgr[:b, :].reshape(-1, 3),
        img_bgr[-b:, :].reshape(-1, 3),
        img_bgr[:, :b].reshape(-1, 3),
        img_bgr[:, -b:].reshape(-1, 3),
    ], axis=0)

    quantised = (ring // 8) * 8
    uniq, counts = np.unique(quantised, axis=0, return_counts=True)
    dominant = uniq[int(counts.argmax())]
    # Nudge to the bucket centre so we don't sit on the low edge.
    centre = np.clip(dominant.astype(np.int32) + 4, 0, 255)
    return int(centre[0]), int(centre[1]), int(centre[2])


# ─── distance threshold (the key measurement) ───────────────────────
def _distance_map(img_bgr: np.ndarray, bg: BgrColor) -> np.ndarray:
    diff = img_bgr.astype(np.float32) - np.asarray(bg, dtype=np.float32)
    return np.sqrt(np.einsum("...c,...c->...", diff, diff))


def _distance_valley(dist: np.ndarray, lo: int = 8, hi: int = 80,
                     smooth: int = 9) -> int:
    """Find the histogram valley between the background spike and fg mass.

    The background colour produces a sharp peak at distance ≈ 0; real
    content sits well above.  We smooth the 0–255 distance histogram and
    take its minimum inside ``[lo, hi]`` — the trough that separates the
    two populations.  ``lo`` keeps us off the spike itself; ``hi`` keeps
    us out of the broad foreground hump.
    """
    cap = np.clip(dist, 0, 255).astype(np.uint8)
    hist = cv2.calcHist([cap], [0], None, [256], [0, 256]).ravel()
    if smooth > 1:
        ksize = smooth if smooth % 2 == 1 else smooth + 1
        hist = cv2.GaussianBlur(hist.reshape(-1, 1), (1, ksize), 0).ravel()
    hi = min(hi, 255)
    if hi <= lo:
        return lo
    segment = hist[lo:hi + 1]
    return lo + int(segment.argmin())


# ─── splitter geometry from connected components ─────────────────────
def _strict_mask(dist: np.ndarray, d_inner: float, d_outer: float) -> np.ndarray:
    if d_outer <= d_inner:
        d_outer = d_inner + 1.0
    ramp = np.clip((dist - d_inner) / (d_outer - d_inner), 0.0, 1.0)
    mask = (ramp > 0.125).astype(np.uint8) * 255  # mirrors alpha>32 in splitting
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, k3, iterations=1)


def _split_geometry(mask: np.ndarray, floor_area: int = 400
                    ) -> dict[str, int]:
    """Estimate anchor/min areas and merge distance from blob stats.

    Runs connected components on the strict mask, looks at the size of
    the icon-sized blobs, and derives:

    * ``anchor_area``    — half the median large-blob area (anything that
      big is certainly a full icon, not a fragment).
    * ``min_area``       — a small fraction of the anchor, floored, to
      drop specks but keep genuine small icons.
    * ``merge_distance`` — ~⅓ of the median icon width, so a detached
      decoration glues back to its parent but separate icons don't.
    """
    num, _labels, stats, _ = cv2.connectedComponentsWithStats(
        mask, connectivity=8)
    if num <= 1:
        return {"anchor_area": 4000, "min_area": floor_area,
                "merge_distance": 80, "_icon_count": 0}

    areas = stats[1:, cv2.CC_STAT_AREA]
    widths = stats[1:, cv2.CC_STAT_WIDTH]
    heights = stats[1:, cv2.CC_STAT_HEIGHT]

    big = areas >= floor_area
    big_areas = areas[big]
    if big_areas.size == 0:
        return {"anchor_area": 4000, "min_area": floor_area,
                "merge_distance": 80, "_icon_count": 0}

    median_area = float(np.median(big_areas))
    # The anchor threshold must sit *below* the typical icon so every
    # real icon is classified as an anchor (not a fragment that gets
    # absorbed into a neighbour).  A fraction of the median — floored at
    # ~10th percentile — keeps small-but-genuine icons as their own
    # anchors while still excluding stray specks.
    p10 = float(np.percentile(big_areas, 10))
    anchor_area = int(max(floor_area * 2, min(median_area * 0.2, p10)))
    min_area = int(max(floor_area // 8 or 50, anchor_area * 0.05))

    anchor_sel = big & (areas >= median_area)
    if anchor_sel.any():
        median_w = float(np.median(widths[anchor_sel]))
        median_h = float(np.median(heights[anchor_sel]))
    else:
        median_w = float(np.median(widths[big]))
        median_h = float(np.median(heights[big]))
    merge_distance = int(np.clip(min(median_w, median_h) * 0.3, 8, 200))

    return {
        "anchor_area": anchor_area,
        "min_area": min_area,
        "merge_distance": merge_distance,
        "_icon_count": int(big_areas.size),
    }


# ─── top-level estimator ─────────────────────────────────────────────
def auto_params(img_bgr: np.ndarray) -> AutoResult:
    """Estimate a full parameter set for ``img_bgr`` (exact/hybrid path).

    The returned ``values`` map is safe to apply wholesale to the GUI
    widgets: it sets the keying mode to ``exact`` and the split mode to
    ``hybrid`` (the combination these estimates are tuned for) and fills
    in every derived threshold.  HSV-mode and grid knobs are left at
    their existing values since this estimator targets the exact-colour
    path, which is what the tool defaults to.
    """
    bg = estimate_bg_bgr(img_bgr)
    dist = _distance_map(img_bgr, bg)

    d_outer = _distance_valley(dist)
    d_outer = int(np.clip(d_outer, 12, 80))
    d_inner = int(max(4, round(d_outer * 0.4)))

    strict_d_inner = d_outer
    strict_d_outer = int(min(120, round(d_outer * 1.6)))

    geom = _split_geometry(_strict_mask(dist, strict_d_inner, strict_d_outer))
    icon_count = geom.pop("_icon_count", 0)

    values: dict[str, float | int | str | bool] = {
        "keying_on": True,
        "mode": "exact",
        "d_inner": d_inner,
        "d_outer": d_outer,
        "strict_d_inner": strict_d_inner,
        "strict_d_outer": strict_d_outer,
        "split_mode": "hybrid",
        "anchor_area": geom["anchor_area"],
        "min_area": geom["min_area"],
        "merge_distance": geom["merge_distance"],
        # sensible companions for the hybrid path
        "shadow_distance": int(np.clip(geom["merge_distance"], 40, 120)),
        "feather": 2,
        "padding": 4,
        # NOTE: coalesce_distance is deliberately NOT set here.  It is the
        # user-facing "granularity" knob (see the GUI slider below the Auto
        # button): Auto preserves whatever the user dialled in rather than
        # resetting it, so "drag slider → click Auto" yields the chosen
        # coarseness.  Its default is 0 (current, most-fragmented behaviour).
    }

    notes = (f"bg={bg}  d_inner/outer={d_inner}/{d_outer}  "
             f"strict={strict_d_inner}/{strict_d_outer}  "
             f"~{icon_count} icons")

    return AutoResult(bg_bgr=bg, values=values, notes=notes,
                      extras={"icon_count": float(icon_count)})


__all__ = ["AutoResult", "auto_params", "estimate_bg_bgr"]
