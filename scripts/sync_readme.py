"""Inject the canonical feature list into every README.

Reads ``docs/readme_features.py`` (the single source of truth) and
rewrites the block between ``<!-- FEATURES:START -->`` and
``<!-- FEATURES:END -->`` in each language's README with a freshly
rendered, numbered list.

Run it any time after editing the feature list::

    python scripts/sync_readme.py

It is **idempotent** — running twice produces no further changes — and
uses only the standard library, so it works in CI with no extra installs.
Exit code is non-zero if a README is missing its marker pair, so a
misconfigured file fails the build loudly instead of silently skipping.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# README filename → language key in FEATURES entries.
README_LANG: dict[str, str] = {
    "README.md": "en",
    "README.zh.md": "zh",
    "README.ja.md": "ja",
}

START = "<!-- FEATURES:START -->"
END = "<!-- FEATURES:END -->"

# Note left in the rendered block so a human editing the README directly
# is pointed back at the source of truth.
EDIT_NOTE = {
    "en": "<!-- AUTO-GENERATED from docs/readme_features.py — edit there, "
          "not here. -->",
    "zh": "<!-- 本段由 docs/readme_features.py 自动生成,请在那里修改,勿直接"
          "编辑此处。 -->",
    "ja": "<!-- このリストは docs/readme_features.py から自動生成されます。"
          "編集はそちらで行ってください。 -->",
}


def _load_features() -> list[dict[str, str]]:
    """Import ``docs/readme_features.py`` by path and return its FEATURES."""
    module_path = ROOT / "docs" / "readme_features.py"
    spec = importlib.util.spec_from_file_location("readme_features", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.FEATURES)


def _render(features: list[dict[str, str]], lang: str) -> str:
    """Render the numbered Markdown list for one language."""
    lines = [EDIT_NOTE[lang], ""]
    for index, feature in enumerate(features, start=1):
        text = feature[lang]
        lines.append(f"{index}. {text}")
    return "\n".join(lines)


def _inject(readme_text: str, rendered: str, filename: str) -> str:
    """Replace the content between the markers; keep the markers."""
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END),
        re.DOTALL,
    )
    if not pattern.search(readme_text):
        raise SystemExit(
            f"ERROR: {filename} is missing the "
            f"{START} … {END} marker pair.\n"
            "Add the two markers around the feature list first."
        )
    replacement = f"{START}\n{rendered}\n{END}"
    return pattern.sub(lambda _m: replacement, readme_text)


def main() -> int:
    features = _load_features()
    changed: list[str] = []
    for filename, lang in README_LANG.items():
        path = ROOT / filename
        if not path.exists():
            print(f"skip {filename} (not found)")
            continue
        original = path.read_text(encoding="utf-8")
        rendered = _render(features, lang)
        updated = _inject(original, rendered, filename)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(filename)
            print(f"updated {filename}")
        else:
            print(f"unchanged {filename}")
    print(f"\n{len(changed)} file(s) changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
