"""Global app settings (one set for the whole GUI session).

Per-image keying / shadow / split parameters live in :mod:`profiles`;
what stays here is genuinely global to the app:

* the active language (``lang``)
* naming pattern fields (``naming_prefix``, ``naming_start_index``,
  ``naming_zero_pad``)
* the batch output root (``batch_out_root``) and whether batch export
  uses per-image sub-folders (``batch_subfolder``)
* the image list (``image_paths``) and the last-active image
  (``active_path``) so the GUI can restore the session on reopen

Settings file lives at:

* Windows:  ``%APPDATA%\\ChromaTool\\settings.json``
* Other:    ``~/.config/chromatool/settings.json``
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


GLOBAL_VAR_NAMES: tuple[str, ...] = (
    "naming_prefix",
    "naming_start_index",
    "naming_zero_pad",
    "batch_out_root",
    "batch_subfolder",
)


def settings_path() -> Path:
    """Resolve the per-user settings file path, creating its folder."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
        folder = base / "ChromaTool"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME")
                    or Path.home() / ".config")
        folder = base / "chromatool"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"


def load_settings() -> dict[str, Any]:
    """Read the persisted settings; return ``{}`` if missing or invalid."""
    path = settings_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: dict[str, Any]) -> Path:
    """Atomically write ``data`` to the persistent settings file."""
    path = settings_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    tmp.replace(path)
    return path
