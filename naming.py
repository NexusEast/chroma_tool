"""Filename rendering for exported crops.

The naming pattern lets the user pick a custom prefix, the starting
sequence number, and whether to zero-pad the number.  A blank prefix
falls back to the input image's stem.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NamingPattern:
    """Configuration controlling how crops are named.

    With ``prefix=None`` (or empty) the input image's stem is used,
    matching the user-facing description ``myimage_1.png``,
    ``myimage_2.png``, ….
    """

    prefix: str | None = None
    start_index: int = 1
    zero_pad: int = 0
    extension: str = ".png"

    def resolve_prefix(self, image_name: str) -> str:
        if self.prefix:
            return self.prefix
        return os.path.splitext(os.path.basename(image_name))[0] or "image"

    def render(self, image_name: str, index: int) -> str:
        prefix = self.resolve_prefix(image_name)
        number = self._format_number(index)
        return f"{prefix}_{number}{self.extension}"

    def render_many(self, image_name: str, count: int) -> list[str]:
        return [self.render(image_name, self.start_index + i)
                for i in range(count)]

    def preview(self, image_name: str = "myimage") -> tuple[str, str]:
        first = self.render(image_name, self.start_index)
        second = self.render(image_name, self.start_index + 1)
        return first, second

    def _format_number(self, index: int) -> str:
        if self.zero_pad <= 0:
            return str(index)
        return str(index).zfill(self.zero_pad)


DEFAULT_NAMING = NamingPattern()


def image_stem(path: str) -> str:
    """Return the bare filename (no extension) for ``path``."""
    return os.path.splitext(os.path.basename(path))[0]
