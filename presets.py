"""Named parameter presets, shared across all images.

A *preset* is a named snapshot of a full parameter set — the same shape
as a per-image profile (see :mod:`profiles`): the sampled background
colour, every keying / shadow / split tunable, and any manual merge
groups.  Unlike profiles, which are keyed by image path and loaded
automatically, presets are picked by name from a dropdown and can be
applied to *every* image at once.

The intended workflow: tune one image of a given art style, save the
result as a named preset, then apply that preset to the whole batch of
same-style images in one click.

Presets persist between sessions in:

* Windows:  ``%APPDATA%\\ChromaTool\\presets.json``
* Other:    ``~/.config/chromatool/presets.json``
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def presets_path() -> Path:
    """Resolve the per-user presets file path, creating its folder."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
        folder = base / "ChromaTool"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME")
                    or Path.home() / ".config")
        folder = base / "chromatool"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "presets.json"


def load_presets() -> dict[str, dict[str, Any]]:
    """Read the persisted preset store; ``{}`` on first run / corruption."""
    path = presets_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = value
    return out


def save_presets(data: dict[str, dict[str, Any]]) -> Path:
    """Atomically write the preset store to disk."""
    path = presets_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    tmp.replace(path)
    return path


__all__ = ["load_presets", "presets_path", "save_presets"]
