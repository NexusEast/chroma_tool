"""Unicode-safe image I/O helpers.

OpenCV's ``imread`` / ``imwrite`` choke on non-ASCII paths on Windows.
We round-trip through ``numpy.fromfile`` and ``cv2.imencode`` to avoid
that.
"""
from __future__ import annotations

import os
from typing import Iterable

import cv2
import numpy as np


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")


def imread_unicode(path: str, flags: int = cv2.IMREAD_UNCHANGED) -> np.ndarray | None:
    """Read an image even when ``path`` contains non-ASCII characters."""
    try:
        buffer = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if buffer.size == 0:
        return None
    return cv2.imdecode(buffer, flags)


def imwrite_unicode(path: str, image: np.ndarray) -> bool:
    """Write ``image`` to ``path``; safe for non-ASCII paths."""
    ext = os.path.splitext(path)[1] or ".png"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        return False
    encoded.tofile(path)
    return True


def to_bgr_and_alpha(raw: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    """Normalise an arbitrary input image to BGR + optional alpha plane."""
    if raw.ndim == 2:
        return cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR), None
    if raw.shape[2] == 4:
        return raw[:, :, :3].copy(), raw[:, :, 3].copy()
    return raw, None


def iter_image_files(root: str) -> Iterable[str]:
    """Yield absolute paths to every image file directly under ``root``."""
    if not os.path.isdir(root):
        return
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if not os.path.isfile(full):
            continue
        if entry.lower().endswith(IMAGE_SUFFIXES):
            yield full
