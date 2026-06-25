"""Headless GUI screenshot driver for the README.

Launches the real Tkinter GUI, programmatically loads the synthetic
sample sheet, runs one-click Auto so the canvas shows detected crops and
the sliders are populated, then grabs the window and writes it to
``preview.png`` at the repo root (overwriting the old screenshot that all
three READMEs reference).

Designed to run under ``xvfb-run`` in CI, but also works on a normal
Windows/macOS desktop so a developer can refresh the screenshot locally::

    python scripts/gen_sample.py
    python scripts/screenshot_gui.py

Screen-grab strategy, in order of preference:
1. ``PIL.ImageGrab.grab()`` — native on Windows/macOS, X11 on Linux.
2. ``import -window root`` (ImageMagick) — Linux fallback.
3. ``scrot`` — Linux fallback.

The window is placed at the top-left and the virtual screen in CI is
sized to match it, so a full-screen grab is effectively a clean window
shot with no WM chrome.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PREVIEW = ROOT / "preview.png"
SAMPLE = ROOT / "_sample_sheet.png"
WIN_W, WIN_H = 1480, 920


def _isolate_settings() -> None:
    """Point settings/profiles at a throwaway dir before ``gui`` loads.

    The GUI restores the previous session (image list, per-image
    profiles) from ``%APPDATA%\\ChromaTool`` / ``~/.config/chromatool``.
    For a reproducible screenshot we must NOT inherit a developer's real
    session — otherwise we'd shoot whatever sprite sheet they last opened
    (and ship it publicly).  Redirecting the config roots to an empty
    temp dir guarantees a clean start with only our synthetic sample.

    ``settings.py`` / ``profiles.py`` read these env vars at call time,
    so setting them before ``import gui`` is sufficient.
    """
    import os

    tmp = tempfile.mkdtemp(prefix="chromatool-shot-")
    os.environ["APPDATA"] = tmp          # Windows
    os.environ["XDG_CONFIG_HOME"] = tmp  # Linux/macOS


def _ensure_sample() -> Path:
    if not SAMPLE.exists():
        import gen_sample  # type: ignore[import-not-found]

        gen_sample.generate(SAMPLE)
    return SAMPLE


def _is_headless_ci() -> bool:
    """True when running under CI on a virtual (Xvfb) X display.

    There the virtual screen is sized to the window, so a full-screen
    grab is the clean shot; a per-window bbox grab can clip if the WM
    offsets the window.  On a real desktop we want the tight bbox.
    """
    import os

    return bool(os.environ.get("CI")) and sys.platform.startswith("linux")


def _pump(root, seconds: float) -> None:
    """Drive the Tk event loop for ``seconds`` so the canvas renders."""
    end = time.time() + seconds
    while time.time() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.03)


def _grab_pil(path: Path, bbox: tuple[int, int, int, int] | None) -> bool:
    try:
        from PIL import ImageGrab

        # Grab only the window's rectangle when we know it, so a local
        # run on a real desktop captures just the GUI — not your whole
        # screen.  In CI the Xvfb screen matches the window, so a full
        # grab (bbox=None fallback) is equivalent anyway.
        img = ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab()
        img.save(path)
        return True
    except Exception as exc:  # noqa: BLE001 — fall through to CLI tools
        print(f"ImageGrab failed: {exc}", file=sys.stderr)
        return False


def _grab_cli(path: Path) -> bool:
    for cmd in (["import", "-window", "root", str(path)],
                ["scrot", "-o", str(path)]):
        try:
            subprocess.run(cmd, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if path.exists() and path.stat().st_size > 0:
                return True
        except Exception:  # noqa: BLE001 — try the next tool
            continue
    return False


def main() -> int:
    _isolate_settings()
    sample = _ensure_sample()

    import gui  # imported after sys.path tweak + settings isolation

    root = gui._make_root()
    # Best-effort: keep the window borderless-ish and pinned top-left so a
    # full-screen grab is effectively a clean window shot.
    try:
        root.geometry(f"{WIN_W}x{WIN_H}+0+0")
    except Exception:
        pass

    app = gui.App(root)
    _pump(root, 0.6)

    # Programmatic load → select → auto, no dialogs.
    try:
        app._append_paths([str(sample)])
        app._select_index(0)
        _pump(root, 0.4)
        app.cmd_auto_detect()
    except Exception as exc:  # noqa: BLE001 — still try to grab whatever rendered
        print(f"driving the GUI failed: {exc}", file=sys.stderr)

    _pump(root, 1.2)  # let auto re-process + canvas redraw settle

    # On a real desktop, grab just the window rectangle so we don't
    # capture the whole screen.  Under Xvfb in CI the virtual screen is
    # sized to the window and WM placement can offset winfo_root* in ways
    # that clip a bbox grab — so there we deliberately grab the full
    # screen (bbox=None), which equals the window anyway.
    bbox: tuple[int, int, int, int] | None = None
    if not _is_headless_ci():
        try:
            root.update_idletasks()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            w, h = root.winfo_width(), root.winfo_height()
            if w > 1 and h > 1:
                bbox = (x, y, x + w, y + h)
        except Exception:
            bbox = None

    ok = _grab_pil(PREVIEW, bbox)
    if not ok and sys.platform.startswith("linux"):
        ok = _grab_cli(PREVIEW)

    try:
        root.destroy()
    except Exception:
        pass

    if not ok:
        print("ERROR: could not capture a screenshot.", file=sys.stderr)
        return 1
    size = PREVIEW.stat().st_size
    print(f"wrote {PREVIEW} ({size} bytes)")
    return 0 if size > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
