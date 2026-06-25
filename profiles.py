"""Per-image configuration profiles.

Each image, keyed by its normalised absolute path, gets its own copy of
the keying / shadow / split parameters plus the sampled background
colour.  Switching images in the GUI loads that image's profile;
switching away first saves the current widget state under the previous
image's key.  Profiles persist between sessions in:

* Windows:  ``%APPDATA%\\ChromaTool\\profiles.json``
* Other:    ``~/.config/chromatool/profiles.json``

The same image file under a different path counts as a different
profile — the absolute path is the only identity used.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


# Tk variable names that belong to a per-image profile.  ``bg_bgr`` is
# stored separately because it isn't a tk.Variable on the GUI side.
PROFILE_VAR_NAMES: tuple[str, ...] = (
    # keying
    "keying_on",
    "d_inner", "d_outer",
    "hue", "hue_tol", "sat_min", "val_min",
    "mode", "bg_min_area", "feather", "decon",
    # shadow
    "shadow_mode", "shadow_intensity", "shadow_max_alpha",
    # splitter
    "split_mode",
    "anchor_area", "merge_distance", "min_area", "padding",
    "shadow_distance", "bridge_erode",
    "strict_d_inner", "strict_d_outer",
    "coalesce_distance",
    "cell_w", "cell_h",
)


def profiles_path() -> Path:
    """Resolve the per-user profiles file path, creating its folder."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
        folder = base / "ChromaTool"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME")
                    or Path.home() / ".config")
        folder = base / "chromatool"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "profiles.json"


def normalise_key(path: str) -> str:
    """Canonicalise an image path so trivial spelling variants collide.

    Uses :func:`os.path.abspath` and :func:`os.path.normcase` so that
    ``D:/foo/bar.png`` and ``d:\\foo\\bar.png`` map to the same key on
    Windows; on POSIX, case is preserved.
    """
    try:
        return os.path.normcase(os.path.abspath(path))
    except OSError:
        return path


def load_profiles() -> dict[str, dict[str, Any]]:
    """Read the persisted profile store; ``{}`` on first run / corruption."""
    path = profiles_path()
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


def save_profiles(data: dict[str, dict[str, Any]]) -> Path:
    """Atomically write the profile store to disk."""
    path = profiles_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    tmp.replace(path)
    return path


__all__ = [
    "PROFILE_VAR_NAMES",
    "load_profiles",
    "normalise_key",
    "profiles_path",
    "save_profiles",
]
