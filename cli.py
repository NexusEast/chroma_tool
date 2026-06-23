"""Command-line front-end for Chroma Tool.

Two top-level commands:

``chroma_tool process``
    Process a single image (or a single image with ``--input``).

``chroma_tool batch``
    Apply the same parameter set to many images.  Each input image's
    crops land in their own sub-folder of ``--out-root``.

Either command can be run via::

    python cli.py process IN OUT [options]
    python cli.py batch    --out-root OUT IN1 IN2 …  [options]

A short positional form ``python cli.py IN OUT`` is also accepted and
routed to ``process`` automatically as a convenience.
"""
from __future__ import annotations

import argparse
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from batch import batch_process
from io_utils import imread_unicode, imwrite_unicode, iter_image_files, to_bgr_and_alpha
from keying import KeyingParams, sample_bgr, sample_hsv
from naming import NamingPattern
from pipeline import ProcessParams, export_crops, process_image
from shadows import ShadowParams
from splitting import ContourParams, GridParams, HybridParams


# ─── argparse builders ──────────────────────────────────────────────
def _add_keying_args(group: argparse._ArgumentGroup) -> None:
    group.add_argument("--no-keying", action="store_true",
                       help="Skip background removal; use any existing alpha.")
    group.add_argument("--mode", choices=["exact", "area", "simple"],
                       default="exact",
                       help="Background detection mode (default: exact).")
    group.add_argument("--pick", nargs=2, type=int, metavar=("X", "Y"),
                       default=[0, 0],
                       help="Sample bg colour at this pixel (default: 0 0).")
    group.add_argument("--bg", nargs=3, type=int, metavar=("B", "G", "R"),
                       help="Explicit bg colour (overrides --pick).")
    group.add_argument("--d-inner", type=float, default=12.0)
    group.add_argument("--d-outer", type=float, default=32.0)
    group.add_argument("--hue", type=int, default=60)
    group.add_argument("--hue-tol", type=int, default=25)
    group.add_argument("--sat-min", type=int, default=60)
    group.add_argument("--val-min", type=int, default=60)
    group.add_argument("--bg-min-area", type=int, default=50_000)
    group.add_argument("--feather", type=int, default=2)
    group.add_argument("--no-decon", action="store_true")
    group.add_argument("--shadow-mode", choices=["soft", "keep", "remove"],
                       default="soft")
    group.add_argument("--shadow-intensity", type=float, default=1.3)
    group.add_argument("--shadow-max-alpha", type=int, default=180)
    group.add_argument("--shadow-color", nargs=3, type=int,
                       default=[0, 0, 0], metavar=("B", "G", "R"))


def _add_split_args(group: argparse._ArgumentGroup) -> None:
    group.add_argument("--split", choices=["hybrid", "grid", "contour", "none"],
                       default="hybrid")
    group.add_argument("--anchor-area", type=int, default=4000)
    group.add_argument("--merge-distance", type=int, default=80)
    group.add_argument("--min-area", type=int, default=400)
    group.add_argument("--padding", type=int, default=4)
    group.add_argument("--shadow-distance", type=int, default=80)
    group.add_argument("--bridge-erode", type=int, default=0)
    group.add_argument("--strict-d-inner", type=float, default=30.0)
    group.add_argument("--strict-d-outer", type=float, default=50.0)
    group.add_argument("--cell-w", type=int, default=200)
    group.add_argument("--cell-h", type=int, default=200)
    group.add_argument("--offset-x", type=int, default=0)
    group.add_argument("--offset-y", type=int, default=0)


def _add_naming_args(group: argparse._ArgumentGroup) -> None:
    group.add_argument("--name-prefix", default=None,
                       help="Output file prefix; blank = input filename stem.")
    group.add_argument("--name-start", type=int, default=1,
                       help="Starting sequence number (default 1).")
    group.add_argument("--name-pad", type=int, default=0,
                       help="Zero-pad digits, 0 = no padding (default 0).")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chroma_tool",
        description="Chroma-key background removal + sprite splitting "
                    "with batch support.",
    )
    sub = parser.add_subparsers(dest="command")

    p_proc = sub.add_parser("process",
                            help="Process one image.")
    p_proc.add_argument("input")
    p_proc.add_argument("output")
    _add_keying_args(p_proc.add_argument_group("chroma key"))
    _add_split_args(p_proc.add_argument_group("split"))
    _add_naming_args(p_proc.add_argument_group("naming"))

    p_batch = sub.add_parser("batch", help="Process many images.")
    p_batch.add_argument("inputs", nargs="+",
                         help="Input files and/or folders.")
    p_batch.add_argument("--out-root", required=True,
                         help="Directory under which each image gets a "
                              "named sub-folder.")
    _add_keying_args(p_batch.add_argument_group("chroma key"))
    _add_split_args(p_batch.add_argument_group("split"))
    _add_naming_args(p_batch.add_argument_group("naming"))
    return parser


# ─── argparse → dataclass ───────────────────────────────────────────
def _bg_from_args(args: argparse.Namespace,
                  fallback_img) -> tuple[tuple[int, int, int] | None, int]:
    """Return (bg_bgr, hue) — sampling from the first input image if needed."""
    if args.bg is not None:
        return tuple(int(c) for c in args.bg), args.hue
    if fallback_img is not None and args.pick is not None:
        x, y = args.pick
        bg = sample_bgr(fallback_img, x, y)
        hue, _, _ = sample_hsv(fallback_img, x, y)
        return bg, hue
    return None, args.hue


def _process_params_from_args(args: argparse.Namespace,
                              bg_bgr: tuple[int, int, int] | None,
                              hue: int) -> ProcessParams:
    keying = KeyingParams(
        mode=args.mode, bg_bgr=bg_bgr,
        d_inner=args.d_inner, d_outer=args.d_outer,
        hue=hue, hue_tol=args.hue_tol,
        sat_min=args.sat_min, val_min=args.val_min,
        bg_min_area=args.bg_min_area,
        feather=0 if args.no_keying else args.feather,
        decontaminate=not args.no_decon and not args.no_keying,
    )
    shadows = ShadowParams(
        mode=args.shadow_mode,
        intensity=args.shadow_intensity,
        max_alpha=args.shadow_max_alpha,
        color=tuple(int(c) for c in args.shadow_color),
    )
    hybrid = HybridParams(
        anchor_area=args.anchor_area,
        merge_distance=args.merge_distance,
        min_keep_area=args.min_area,
        padding=args.padding,
        shadow_max_distance=args.shadow_distance,
        bridge_erode=args.bridge_erode,
        mask_outside=not args.no_keying,
    )
    grid = GridParams(cell_w=args.cell_w, cell_h=args.cell_h,
                      offset_x=args.offset_x, offset_y=args.offset_y)
    contour = ContourParams(min_area=args.min_area, padding=args.padding,
                            mask_outside=not args.no_keying)
    return ProcessParams(
        keying_on=not args.no_keying,
        keying=keying,
        shadows=shadows,
        split_mode=args.split,
        hybrid=hybrid,
        grid=grid,
        contour=contour,
        strict_d_inner=args.strict_d_inner,
        strict_d_outer=args.strict_d_outer,
    )


def _naming_from_args(args: argparse.Namespace) -> NamingPattern:
    return NamingPattern(prefix=args.name_prefix,
                         start_index=args.name_start,
                         zero_pad=args.name_pad)


# ─── input expansion ────────────────────────────────────────────────
def _expand_inputs(paths: list[str]) -> list[str]:
    out: list[str] = []
    for path in paths:
        if os.path.isdir(path):
            out.extend(iter_image_files(path))
        else:
            out.append(path)
    return out


# ─── commands ───────────────────────────────────────────────────────
def _cmd_process(args: argparse.Namespace) -> int:
    raw = imread_unicode(args.input)
    if raw is None:
        print(f"Failed to read {args.input}", file=sys.stderr)
        return 2
    img_bgr, existing_alpha = to_bgr_and_alpha(raw)
    print(f"Input: {img_bgr.shape[1]}x{img_bgr.shape[0]}"
          f"{' (with alpha)' if existing_alpha is not None else ''}")

    bg, hue = _bg_from_args(args, img_bgr)
    if bg is not None:
        print(f"Background BGR={bg}")
    params = _process_params_from_args(args, bg, hue)
    naming = _naming_from_args(args)

    os.makedirs(args.output, exist_ok=True)
    result = process_image(img_bgr, params, existing_alpha)
    imwrite_unicode(os.path.join(args.output, "_transparent.png"), result.rgba)

    files = export_crops(result.crops, args.output, args.input, naming)
    print(f"Wrote {len(files)} crops to {args.output}")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    inputs = _expand_inputs(args.inputs)
    if not inputs:
        print("No input images resolved.", file=sys.stderr)
        return 2

    first = imread_unicode(inputs[0])
    first_bgr, _ = to_bgr_and_alpha(first) if first is not None else (None, None)
    bg, hue = _bg_from_args(args, first_bgr)
    params = _process_params_from_args(args, bg, hue)
    naming = _naming_from_args(args)

    def progress(index: int, total: int, name: str) -> None:
        print(f"[{index}/{total}] {name}")

    result = batch_process(inputs, args.out_root, params, naming, progress)
    print(f"\nBatch done: {result.ok_count}/{result.total} images, "
          f"{result.total_crops} crops total → {args.out_root}")
    for failure in result.failures():
        print(f"  ! {failure.input_path}: {failure.error}", file=sys.stderr)
    return 0 if result.failure_count == 0 else 1


# ─── legacy compat ──────────────────────────────────────────────────
def _maybe_inject_legacy_command(argv: list[str]) -> list[str]:
    """Allow the short ``python cli.py IN OUT …`` positional form."""
    if not argv:
        return argv
    known = {"process", "batch", "-h", "--help"}
    if argv[0] in known or argv[0].startswith("-"):
        return argv
    if len(argv) >= 2 and not argv[0].startswith("-"):
        return ["process", *argv]
    return argv


def main(argv: list[str] | None = None) -> int:
    argv = _maybe_inject_legacy_command(list(sys.argv[1:] if argv is None else argv))
    parser = _build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if args.command == "process":
        return _cmd_process(args)
    if args.command == "batch":
        return _cmd_batch(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
