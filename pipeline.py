"""Top-level keying + splitting pipeline.

The public surface is intentionally narrow:

* :class:`ProcessParams` — every tunable in one frozen dataclass.
* :func:`process_image` — apply keying → shadow handling → splitting to
  one BGR image and return a :class:`ProcessResult`.
* :func:`export_crops` — write the produced crops to disk under a chosen
  directory using a :class:`naming.NamingPattern`.

The GUI, CLI, and batch runner all share this surface so the underlying
implementation can evolve without touching the front-ends.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from io_utils import imwrite_unicode
from keying import (
    KeyingParams, KeyingResult, key_background, strict_alpha,
)
from naming import NamingPattern
from shadows import ShadowParams, apply as apply_shadows
from splitting import (
    ContourParams, Crop, GridParams, HybridParams, SplitMode,
    coalesce_nearby, merge_crops_in_rects,
    split_contour, split_grid, split_hybrid,
)


@dataclass(frozen=True)
class ProcessParams:
    """Everything required to process a single image end-to-end."""

    keying_on: bool = True
    keying: KeyingParams = field(default_factory=KeyingParams)
    shadows: ShadowParams = field(default_factory=ShadowParams)
    split_mode: SplitMode = "hybrid"
    hybrid: HybridParams = field(default_factory=HybridParams)
    grid: GridParams = field(default_factory=GridParams)
    contour: ContourParams = field(default_factory=ContourParams)
    strict_d_inner: float = 30.0
    strict_d_outer: float = 50.0
    # Post-split de-fragmentation: merge crops whose bboxes sit within
    # this many pixels of each other (0 = off).  A size-agnostic global
    # knob that works even after Auto sizes every blob as its own anchor.
    coalesce_distance: int = 0
    # User-drawn merge rectangles (image coords); any crops whose centre
    # falls inside one are force-merged.  Persisted per image so a manual
    # merge survives re-processing, slider tweaks and batch export.
    merge_groups: tuple[tuple[int, int, int, int], ...] = ()


@dataclass(frozen=True)
class ProcessResult:
    """Outputs of :func:`process_image`."""

    rgba: np.ndarray
    alpha: np.ndarray = field(repr=False)
    crops: list[Crop]


# ─── helpers ────────────────────────────────────────────────────────
def _rgba_passthrough(img_bgr: np.ndarray,
                      existing_alpha: np.ndarray | None) -> np.ndarray:
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = existing_alpha if existing_alpha is not None else 255
    return rgba


def _should_use_strict(params: ProcessParams) -> bool:
    return (params.keying.mode == "exact"
            and params.keying.bg_bgr is not None
            and params.split_mode == "hybrid")


def _build_strict(img_bgr: np.ndarray, params: ProcessParams) -> np.ndarray | None:
    if not _should_use_strict(params):
        return None
    assert params.keying.bg_bgr is not None
    return strict_alpha(img_bgr, params.keying.bg_bgr,
                        params.strict_d_inner, params.strict_d_outer)


def _run_splitter(rgba: np.ndarray, alpha: np.ndarray,
                  strict: np.ndarray | None,
                  params: ProcessParams) -> list[Crop]:
    if params.split_mode == "none":
        return []
    if params.split_mode == "hybrid":
        hybrid = params.hybrid
        if strict is not None and hybrid.dilate_radius != 0:
            hybrid = replace(hybrid, dilate_radius=0)
        return split_hybrid(rgba, alpha, strict, hybrid)
    if params.split_mode == "grid":
        return split_grid(rgba, alpha, params.grid)
    if params.split_mode == "contour":
        return split_contour(rgba, alpha, params.contour)
    raise ValueError(f"Unknown split mode: {params.split_mode!r}")


# ─── main entry ─────────────────────────────────────────────────────
def process_image(img_bgr: np.ndarray, params: ProcessParams,
                  existing_alpha: np.ndarray | None = None) -> ProcessResult:
    """Run the full keying → shadows → splitter pipeline on one image."""
    strict = _build_strict(img_bgr, params)

    if params.keying_on:
        keying_result: KeyingResult = key_background(img_bgr, params.keying)
        rgba = keying_result.bgra
        if strict is not None and params.keying.bg_bgr is not None:
            rgba = apply_shadows(rgba, strict, params.keying.bg_bgr,
                                 params.shadows)
        alpha = rgba[:, :, 3]
    else:
        rgba = _rgba_passthrough(img_bgr, existing_alpha)
        alpha = rgba[:, :, 3]

    hybrid_params = params.hybrid
    if params.split_mode == "hybrid" and not params.keying_on:
        hybrid_params = replace(hybrid_params, mask_outside=False)
    runtime = replace(params, hybrid=hybrid_params)
    crops = _run_splitter(rgba, alpha, strict, runtime)
    if params.coalesce_distance > 0:
        crops = coalesce_nearby(rgba, crops, params.coalesce_distance)
    if params.merge_groups:
        crops = merge_crops_in_rects(rgba, crops, list(params.merge_groups))
    return ProcessResult(rgba=rgba, alpha=alpha, crops=crops)


# ─── exporting ──────────────────────────────────────────────────────
def export_crops(crops: list[Crop], out_dir: str, image_name: str,
                 naming: NamingPattern) -> list[str]:
    """Write ``crops`` into ``out_dir`` using ``naming`` and return their paths.

    The directory is created if missing.  ``_preview.png`` is **not**
    written — preview rendering is a GUI concern only.
    """
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    filenames = naming.render_many(image_name, len(crops))
    for crop, filename in zip(crops, filenames):
        full = os.path.join(out_dir, filename)
        if imwrite_unicode(full, crop.image):
            written.append(full)
    return written
