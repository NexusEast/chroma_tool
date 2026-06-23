"""Shadow handling for keyed images.

Once a tight "body" alpha is known, every pixel that's *visible* in the
loose alpha but absent from the body mask is treated as shadow.  Three
strategies handle those pixels:

``soft``     — convert to semi-transparent tint (default; natural drop-shadow).
``keep``     — leave the original opaque colour unchanged.
``remove``   — erase shadow pixels entirely.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from keying import BgrColor

ShadowMode = Literal["soft", "keep", "remove"]

BODY_ALPHA_THRESHOLD = 32
VISIBLE_ALPHA_THRESHOLD = 32


@dataclass(frozen=True)
class ShadowParams:
    """Tunables for shadow softening."""

    mode: ShadowMode = "soft"
    intensity: float = 1.3
    max_alpha: int = 180
    color: BgrColor = (0, 0, 0)


def _shadow_mask(loose_alpha: np.ndarray,
                 body_alpha: np.ndarray) -> np.ndarray:
    visible = loose_alpha > VISIBLE_ALPHA_THRESHOLD
    body = body_alpha > BODY_ALPHA_THRESHOLD
    return visible & ~body


def soften(rgba: np.ndarray, body_alpha: np.ndarray, bg: BgrColor,
           params: ShadowParams) -> np.ndarray:
    """Replace shadow pixels with semi-transparent ``params.color``."""
    out = rgba.copy()
    rgb = out[:, :, :3]
    alpha = out[:, :, 3]

    shadow = _shadow_mask(alpha, body_alpha)
    if not shadow.any():
        return out

    bg_luma = float(sum(bg)) / 3.0
    if bg_luma < 1.0:
        return out
    pixel_luma = rgb.astype(np.float32).mean(axis=2)
    darkness = np.clip((bg_luma - pixel_luma) / bg_luma * params.intensity,
                       0.0, 1.0)
    shadow_alpha = np.minimum((darkness * 255.0).astype(np.int32),
                              int(params.max_alpha)).astype(np.uint8)

    alpha[shadow] = shadow_alpha[shadow]
    rgb[shadow] = params.color
    out[:, :, :3] = rgb
    out[:, :, 3] = alpha
    return out


def remove(rgba: np.ndarray, body_alpha: np.ndarray) -> np.ndarray:
    """Zero out the alpha of anything not in the body."""
    out = rgba.copy()
    keep = body_alpha > BODY_ALPHA_THRESHOLD
    a = out[:, :, 3].copy()
    a[~keep] = 0
    out[:, :, 3] = a
    return out


def apply(rgba: np.ndarray, body_alpha: np.ndarray | None,
          bg: BgrColor | None, params: ShadowParams) -> np.ndarray:
    """Top-level dispatch by mode.  No-ops when the body alpha is missing."""
    if params.mode == "keep" or body_alpha is None:
        return rgba
    if params.mode == "remove":
        return remove(rgba, body_alpha)
    if params.mode == "soft":
        if bg is None:
            return rgba
        return soften(rgba, body_alpha, bg, params)
    raise ValueError(f"Unknown shadow mode: {params.mode!r}")
