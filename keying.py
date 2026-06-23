"""Chroma-key background removal.

This module produces an alpha mask separating foreground from a flat
background colour.  It exposes three strategies, two helpers for
sampling colour values from an image, and a small dataclass that
gathers all tunables in one place.

The strategies are:

``exact``
    Pixel becomes background when its BGR Euclidean distance to a
    reference colour drops below ``d_inner``; fully foreground above
    ``d_outer``; soft ramp in between.  Best for cartoon sprites and
    flat-fill artwork — preserves shadows and same-hue inclusions.

``area``
    HSV range mask, then keep only background-shaped large connected
    regions.  Tolerates light gradients in the background.

``simple``
    A plain HSV range mask: anything matching the range is wiped.
    Fastest and most destructive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np

BgrColor = tuple[int, int, int]
KeyingMode = Literal["exact", "area", "simple"]


@dataclass(frozen=True)
class KeyingParams:
    """Tunable parameters for :func:`key_background`."""

    mode: KeyingMode = "exact"
    bg_bgr: BgrColor | None = None

    # exact mode
    d_inner: float = 12.0
    d_outer: float = 32.0

    # HSV (area / simple)
    hue: int = 60
    hue_tol: int = 25
    sat_min: int = 60
    val_min: int = 60
    bg_min_area: int = 50_000

    # post-processing
    feather: int = 2
    decontaminate: bool = True
    decontaminate_strength: float = 0.6
    edge_erode: int = 1


@dataclass(frozen=True)
class KeyingResult:
    """Output of :func:`key_background`: an RGBA frame plus the raw alpha."""

    bgra: np.ndarray
    alpha: np.ndarray = field(repr=False)


# ─── colour sampling ────────────────────────────────────────────────
def _patch(img: np.ndarray, x: int, y: int, radius: int) -> np.ndarray:
    h, w = img.shape[:2]
    x0, y0 = max(0, x - radius), max(0, y - radius)
    x1, y1 = min(w, x + radius + 1), min(h, y + radius + 1)
    return img[y0:y1, x0:x1]


def sample_bgr(img_bgr: np.ndarray, x: int, y: int,
               radius: int = 3) -> BgrColor:
    """Average BGR colour over a small neighbourhood of ``(x, y)``."""
    b, g, r = _patch(img_bgr, x, y, radius).reshape(-1, 3).mean(axis=0)
    return int(b), int(g), int(r)


def sample_hsv(img_bgr: np.ndarray, x: int, y: int,
               radius: int = 3) -> tuple[int, int, int]:
    """Average HSV colour over a small neighbourhood of ``(x, y)``."""
    patch = cv2.cvtColor(_patch(img_bgr, x, y, radius), cv2.COLOR_BGR2HSV)
    h, s, v = patch.reshape(-1, 3).mean(axis=0)
    return int(h), int(s), int(v)


# ─── individual mask builders ───────────────────────────────────────
def _alpha_from_color_distance(img_bgr: np.ndarray, bg: BgrColor,
                               d_inner: float, d_outer: float) -> np.ndarray:
    if d_outer <= d_inner:
        d_outer = d_inner + 1.0
    diff = img_bgr.astype(np.float32) - np.asarray(bg, dtype=np.float32)
    dist = np.sqrt(np.einsum("...c,...c->...", diff, diff))
    ramp = np.clip((dist - d_inner) / (d_outer - d_inner), 0.0, 1.0)
    return (ramp * 255.0).astype(np.uint8)


def _hsv_range_mask(img_bgr: np.ndarray, h_center: int, h_tol: int,
                    s_min: int, v_min: int) -> np.ndarray:
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lower = np.array([max(0, h_center - h_tol), s_min, v_min], dtype=np.uint8)
    upper = np.array([min(179, h_center + h_tol), 255, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lower, upper)


def _largest_blob_mask(binary: np.ndarray, min_area: int,
                       edge_erode: int) -> np.ndarray:
    """Return a binary mask of only those connected regions with area ≥ ``min_area``."""
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    eroded = cv2.erode(binary, k3, iterations=edge_erode) if edge_erode else binary
    num, labels, stats, _ = cv2.connectedComponentsWithStats(eroded, connectivity=8)
    big = np.zeros_like(binary)
    for idx in range(1, num):
        if stats[idx, cv2.CC_STAT_AREA] >= min_area:
            big[labels == idx] = 255
    if edge_erode:
        big = cv2.dilate(big, k3, iterations=edge_erode + 1)
        big = cv2.bitwise_and(big, binary)
    return big


def _decontaminate(bgra: np.ndarray, strength: float,
                   bg: BgrColor | None) -> np.ndarray:
    """Strip residual background tint from semi-transparent edge pixels."""
    b, g, r, a = cv2.split(bgra)
    edge = (a > 0) & (a < 255)
    if not edge.any():
        return bgra
    if bg is not None:
        weight = ((255 - a).astype(np.float32) / 255.0) * strength
        bb, gg, rr = bg

        def _sub(channel: np.ndarray, bg_val: int) -> np.ndarray:
            adj = np.clip(channel.astype(np.float32) - bg_val * weight,
                          0, 255).astype(np.uint8)
            return np.where(edge, adj, channel)

        return cv2.merge([_sub(b, bb), _sub(g, gg), _sub(r, rr), a])

    # Legacy green-suppression fallback (no reference colour).
    rb_max = np.maximum(r, b)
    pull = np.where(g > rb_max, g - rb_max, 0).astype(np.int16)
    new_g = np.clip(g.astype(np.int16) - (pull * strength).astype(np.int16),
                    0, 255).astype(np.uint8)
    return cv2.merge([b, np.where(edge, new_g, g), r, a])


# ─── orchestrator ───────────────────────────────────────────────────
def key_background(img_bgr: np.ndarray, params: KeyingParams) -> KeyingResult:
    """Apply the selected keying mode and return ``(BGRA, alpha)``."""
    bg = params.bg_bgr
    if params.mode == "exact":
        if bg is None:
            bg = tuple(int(c) for c in img_bgr[0, 0])  # type: ignore[assignment]
        alpha = _alpha_from_color_distance(img_bgr, bg,
                                           params.d_inner, params.d_outer)
    elif params.mode == "simple":
        alpha = cv2.bitwise_not(
            _hsv_range_mask(img_bgr, params.hue, params.hue_tol,
                            params.sat_min, params.val_min)
        )
    elif params.mode == "area":
        green = _hsv_range_mask(img_bgr, params.hue, params.hue_tol,
                                params.sat_min, params.val_min)
        alpha = cv2.bitwise_not(_largest_blob_mask(green, params.bg_min_area,
                                                   params.edge_erode))
    else:  # pragma: no cover — guarded by Literal type
        raise ValueError(f"Unknown keying mode: {params.mode!r}")

    if params.feather > 0:
        ksize = params.feather * 2 + 1
        alpha = cv2.GaussianBlur(alpha, (ksize, ksize), 0)

    bgra = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = alpha
    if params.decontaminate:
        bg_for_decon = bg if params.mode == "exact" else None
        bgra = _decontaminate(bgra, params.decontaminate_strength, bg_for_decon)
    return KeyingResult(bgra=bgra, alpha=alpha)


def strict_alpha(img_bgr: np.ndarray, bg: BgrColor,
                 d_inner: float, d_outer: float) -> np.ndarray:
    """Build a tight "icon-body only" alpha for shadow assignment."""
    return _alpha_from_color_distance(img_bgr, bg, d_inner, d_outer)
