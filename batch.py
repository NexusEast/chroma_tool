"""Batch processing: apply parameters to many images.

The result of every input image is written into its own sub-folder of
the chosen output root, named after the input image's stem:

    out_root/
    ├── inputA/
    │   ├── inputA_1.png
    │   ├── inputA_2.png
    │   └── …
    └── inputB/
        ├── inputB_1.png
        └── …

The ``params`` argument of :func:`batch_process` accepts either a
single :class:`ProcessParams` (apply that one config to every image)
**or** a callable ``path -> ProcessParams`` (different config per
image — used by the GUI to look up each image's saved profile).

No ``_preview.png`` is written.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Union

from io_utils import imread_unicode, to_bgr_and_alpha
from naming import NamingPattern, image_stem
from pipeline import ProcessParams, export_crops, process_image


ProgressCallback = Callable[[int, int, str], None]
ParamsResolver = Callable[[str], ProcessParams]
ParamsArg = Union[ProcessParams, ParamsResolver]


@dataclass
class ItemResult:
    """Outcome of processing one image in a batch run."""

    input_path: str
    output_dir: str
    crop_count: int = 0
    written_files: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class BatchResult:
    """Aggregate outcome of a batch run."""

    items: list[ItemResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def ok_count(self) -> int:
        return sum(1 for it in self.items if it.ok)

    @property
    def failure_count(self) -> int:
        return self.total - self.ok_count

    @property
    def total_crops(self) -> int:
        return sum(it.crop_count for it in self.items)

    def failures(self) -> list[ItemResult]:
        return [it for it in self.items if not it.ok]


def _output_dir_for(input_path: str, out_root: str) -> str:
    return os.path.join(out_root, image_stem(input_path))


def _resolve_params(params: ParamsArg, path: str) -> ProcessParams:
    """Pick the right :class:`ProcessParams` for ``path``.

    A plain ``ProcessParams`` is returned as-is; a callable is invoked
    with the image path so callers can deliver a per-image config.
    """
    if isinstance(params, ProcessParams):
        return params
    return params(path)


def _process_one(input_path: str, out_root: str,
                 params: ProcessParams, naming: NamingPattern) -> ItemResult:
    out_dir = _output_dir_for(input_path, out_root)
    item = ItemResult(input_path=input_path, output_dir=out_dir)
    try:
        raw = imread_unicode(input_path)
        if raw is None:
            item.error = "failed to read"
            return item
        bgr, existing_alpha = to_bgr_and_alpha(raw)
        result = process_image(bgr, params, existing_alpha)
        item.written_files = export_crops(result.crops, out_dir,
                                          input_path, naming)
        item.crop_count = len(result.crops)
    except Exception as exc:  # pragma: no cover — surfaces in UI
        item.error = f"{type(exc).__name__}: {exc}"
    return item


def batch_process(input_paths: list[str], out_root: str,
                  params: ParamsArg, naming: NamingPattern,
                  progress: ProgressCallback | None = None) -> BatchResult:
    """Run :func:`pipeline.process_image` over each input path.

    ``params`` may be a single :class:`ProcessParams` (legacy single
    config) or a callable ``path -> ProcessParams`` so each image can
    use its own per-image profile.
    """
    os.makedirs(out_root, exist_ok=True)
    aggregate = BatchResult()
    total = len(input_paths)
    for index, path in enumerate(input_paths, start=1):
        if progress is not None:
            progress(index, total, os.path.basename(path))
        this_params = _resolve_params(params, path)
        aggregate.items.append(
            _process_one(path, out_root, this_params, naming))
    return aggregate

