# Chroma Tool

> **English:** README.md  ·  **中文:** [README.zh.md](README.zh.md)  ·  **日本語:** [README.ja.md](README.ja.md)

![Chroma Tool — keying an icon sprite sheet, batch list on the left, parameters on the right](preview.png)

> **Chroma-key background removal + sprite-sheet splitter + batch processor.**
> Python tool with both a Tkinter GUI and a CLI.  Takes a flat-coloured
> background image (e.g. a green-screen sprite sheet or an icon grid),
> removes the background while preserving shadows and same-hue details,
> and slices each foreground object into its own transparent PNG.

**Topics / keywords:** chroma key · green screen background removal ·
sprite sheet splitter · sprite cutter · icon grid extractor · alpha
matting · soft drop shadow preservation · batch image processing ·
transparent PNG · RGBA output · foreground extraction · cartoon
sprites · game asset pipeline · Python · OpenCV · Tkinter GUI · CLI ·
no-LLM offline tool.

## Table of contents

1. [What it does](#what-it-does)
2. [Headline features](#headline-features)
3. [When to reach for this tool](#when-to-reach-for-this-tool)
4. [Install](#install)
5. [GUI quick start](#gui-quick-start)
6. [CLI quick start](#cli-quick-start)
7. [Output layout](#output-layout)
8. [Naming pattern](#naming-pattern)
9. [Keying modes](#keying-modes)
10. [Split strategies](#split-strategies)
11. [Shadow handling](#shadow-handling)
12. [Tuning cheat sheet](#tuning-cheat-sheet)
13. [Architecture](#architecture)
14. [FAQ](#faq)
15. [Known limitations](#known-limitations)

## What it does

Chroma Tool takes one image (or many) with a **flat-coloured background**
— for example a game sprite sheet on green, an icon grid on a pastel
fill, or a product render on a colour key — and produces:

* a per-pixel **alpha mask** that separates foreground from background
  while preserving shadows and same-hue inclusions (foliage, accents,
  drop-shadows);
* a set of **cropped transparent PNGs**, one per detected sprite.

In **batch mode** the same parameter set is applied to many input
images at once, and each image's crops are written to its own
sub-folder named after the image.

It is a pure computer-vision tool — no LLM, no cloud, no telemetry.
Everything runs locally with OpenCV and NumPy.

## Headline features

<!-- FEATURES:START -->
<!-- AUTO-GENERATED from docs/readme_features.py — edit there, not here. -->

1. **One-click Auto.** Detects the background colour from the image border, derives every keying/splitting parameter from the colour-distance histogram and connected-component statistics, and fills in all the sliders — turning a ~15-knob manual tune into a single click.  You can still fine-tune afterwards (GUI button, or `--auto` on the CLI).
2. **One-click granularity + manual merge.** A single prominent *Fine ↔ Coarse* slider sets how chunky one-click Auto's output is — drag it up to merge nearby pieces into fewer, bigger crops. For anything Auto still gets wrong, a *Select* canvas mode lets you click or box-select stray crops (right-click to deselect) and merge them into one.  Manual merges are remembered per image, so they survive re-processing, slider tweaks and batch export.
3. **Named parameter presets.** Save a whole tuned parameter set (including the background colour) under a name, then apply it to every image in the list with one click — ideal when a batch shares one art style.  Presets persist between sessions.
4. **Batch processing.** Add dozens of images to the GUI (or pass a folder to the CLI), tune the parameters on one preview image, then export them all with the same config in one click.
5. **Per-image profiles.** Switching images in the list loads that image's own saved parameters.  The key is the absolute path, so the same image in a different location is a separate profile.  Profiles persist between sessions.
6. **Custom naming.** Pick a prefix, a starting index, and the number of zero-pad digits.  A blank prefix uses the input image's stem with a running `_N` suffix: `myimage_1.png`, `myimage_2.png`, ….
7. **Per-image output folders.** Each input image's crops land in a sub-folder named after the input image — no name collisions when batching.
8. **Shadow-preserving keying.** A dual-alpha pipeline reassigns shadow pixels to the nearest icon body via OpenCV's distance transform, so drop-shadows stay attached to their parent sprite instead of being eaten by the chroma mask.
9. **Soft drop-shadow re-projection.** Shadow pixels can be converted from opaque background-colour to semi-transparent black so they look natural on any new composite.
10. **Three split strategies.** Hybrid (connected components + anchor/fragment merging), fixed grid, or external contour.
11. **Three keying modes.** Exact (BGR distance), area (HSV + large connected blob), simple (pure HSV range).
12. **No `_preview.png` clutter.** Preview rendering is GUI-only; the export folder contains only your crops (plus an optional `_transparent.png` in single-image mode).
13. **Trilingual GUI** — English (default), Chinese and Japanese, switchable at runtime.
14. **Persistent settings.** Every slider and choice survives between launches, stored as JSON in `%APPDATA%\ChromaTool\settings.json` (or `~/.config/chromatool/settings.json` on Linux/macOS).
<!-- FEATURES:END -->

## When to reach for this tool

* You have a **sprite sheet** on a flat-colour background and want each
  sprite as its own transparent PNG.
* You have a folder of **product photos shot on green/blue screen** and
  need to batch-strip the background.
* You're building a **game asset pipeline** and want a scriptable
  background-remover in CI.
* You have an **icon grid** from a design comp and want every icon as a
  separate file.
* You want a **GUI tool** to iterate on chroma-key parameters
  interactively, then apply the result to a whole folder.

This tool is **not** for:

* Soft-edge subjects like hair, fur, or motion-blur — use alpha matting
  (e.g. [PyMatting](https://github.com/pymatting/pymatting)) afterwards.
* Multi-colour or photographic backgrounds — only one background colour
  is keyed at a time.
* Touching/overlapping sprites that share foreground pixels — the
  splitter relies on connected components.

## Install

```bash
pip install -r requirements.txt
```

Dependencies: `opencv-python`, `numpy`, `Pillow`.  Python 3.10+.

## GUI quick start

```bash
python gui.py
```

1. **File → Add Images** (or **Add Folder**) to populate the image list
   on the left.
2. Click an entry to make it the live preview.
3. Tweak parameters on the right; click **Generate** to re-process the
   selected image.
4. In the *Naming & output* panel set a **prefix**, **start index** and
   **zero-pad** — a live preview shows the next two filenames that
   will be written.
5. Choose an **Output root** folder.
6. **Export All (Batch)** applies the current parameters to every image
   in the list and writes each image's crops into its own sub-folder
   of the output root.

Keyboard shortcuts: `Ctrl+O` add images, `Ctrl+E` export current image,
`Ctrl+B` export the whole batch.

## CLI quick start

Single image:

```bash
# Pick background from pixel (0,0) and use the default hybrid splitter.
python cli.py process input.png out_dir

# Sample background from a specific pixel.
python cli.py process input.png out_dir --pick 5 5

# Force an explicit BGR background colour.
python cli.py process input.png out_dir --bg 50 180 138

# Custom output naming.
python cli.py process input.png out_dir \
    --name-prefix hero --name-start 0 --name-pad 3
# → hero_000.png, hero_001.png, …

# Fixed-grid splitter for uniform sprite sheets.
python cli.py process sheet.png out --split grid --cell-w 200 --cell-h 200
```

Batch (each input → its own sub-folder under `--out-root`):

```bash
python cli.py batch --out-root output/ a.png b.png c.png
python cli.py batch --out-root output/ ./sprites_folder/
python cli.py batch --out-root output/ ./sprites/ \
    --name-prefix icon --name-pad 3
```

Run `python cli.py process --help` or `python cli.py batch --help` for
every flag.  The short form `python cli.py IN OUT …` (no sub-command)
is also accepted and routes to `process`.

## Output layout

Single-image export writes everything into the chosen output folder:

```
out_dir/
├── _transparent.png       full keyed image (RGBA, optional)
├── myimage_1.png
├── myimage_2.png
└── …
```

Batch export creates one folder per input image:

```
out_root/
├── myimage/
│   ├── myimage_1.png
│   ├── myimage_2.png
│   └── …
├── another/
│   ├── another_1.png
│   └── …
└── …
```

**No `_preview.png` is ever written.**  The bounding-box preview is a
GUI-only debugging aid.

## Naming pattern

A blank prefix is replaced by the input image's stem.  Sequence
numbers start at the configured start index and can be zero-padded.

| prefix  | start | pad | first three filenames                              |
|---------|------:|----:|----------------------------------------------------|
| *blank* |     1 |   0 | `myimage_1.png`, `myimage_2.png`, `myimage_3.png`  |
| *blank* |     0 |   3 | `myimage_000.png`, `myimage_001.png`, `myimage_002.png` |
| `hero`  |     1 |   2 | `hero_01.png`, `hero_02.png`, `hero_03.png`        |

## Keying modes

| Mode | When to use | What it does |
|---|---|---|
| `exact` *(default)* | Flat-colour backgrounds (cartoon art, UI, game sprites) | BGR Euclidean distance from a sampled background colour with a soft alpha ramp between `d_inner` and `d_outer`.  Preserves shadows and same-hue inclusions. |
| `area` | Slightly noisy background, want to keep small same-coloured pockets inside objects | HSV range mask → connected components → only large blobs count as background. |
| `simple` | Solid green-screen, no shadows to keep | Pure HSV range — fastest, most destructive. |

## Split strategies

| Strategy | Best for |
|---|---|
| `hybrid` *(default)* | Icons separated by background gaps.  Anchors absorb fragments; dual-alpha distance transform reassigns shadow pixels to their parent icon. |
| `grid` | Uniform sprite sheet with known cell size. |
| `contour` | Lightly overlapping icons; uses external contour polygons. |
| `none` | Only do background removal, skip splitting. |

## Shadow handling

| Mode | Effect on composited result |
|---|---|
| `soft` *(default)* | Subtle semi-transparent drop shadow under each sprite — looks natural on any new background. |
| `keep` | Original opaque background-tinted shadow blob. |
| `remove` | Sprite floats with no shadow. |

Tunables: `--shadow-intensity` (0.5 – 3.0, higher = darker),
`--shadow-max-alpha` (0 – 255 cap), `--shadow-color` (BGR tint).

## Tuning cheat sheet

| Problem | Tweak |
|---|---|
| Background still showing through | Raise `--d-outer` (or `--hue-tol` for HSV modes) |
| Shadows / foliage being eaten | Lower `--d-outer`, raise `--d-inner` |
| Shadows too dark / too light | Adjust `--shadow-intensity` and `--shadow-max-alpha` |
| Adjacent icons merging into one crop | Raise `--bridge-erode`; lower `--shadow-distance`; raise `--strict-d-inner` |
| Tiny stray crops | Raise `--min-area` |
| Decorations split off from their parent | Raise `--merge-distance` or `--shadow-distance` |
| Coloured halo around objects | Raise `--feather`; keep decontamination on |

## Architecture

```
chroma_tool/
├── io_utils.py     unicode-safe image read/write + folder iteration
├── keying.py       background detection (exact / area / simple)
├── shadows.py      shadow soften / keep / remove
├── splitting.py    hybrid / grid / contour split strategies
├── pipeline.py     ProcessParams + process_image + export_crops
├── batch.py        many-image batch runner with per-item results
├── naming.py       NamingPattern and filename rendering
├── settings.py     persistent GUI settings (JSON in %APPDATA% / XDG)
├── i18n.py         zh / en translations for the GUI
├── cli.py          command-line front-end
├── gui.py          Tkinter front-end
├── requirements.txt
└── README.md
```

Each layer exposes its own frozen dataclass of parameters; the
top-level `pipeline.ProcessParams` composes them.  Both `cli.py` and
`gui.py` build a `ProcessParams` and pass it to `pipeline.process_image`
(single image) or `batch.batch_process` (many images) — no business
logic lives in either front-end, so the underlying implementation can
evolve without touching them.

## FAQ

**Q: Does this need an internet connection or an LLM?**
A: No.  Pure offline computer vision (OpenCV + NumPy).

**Q: Can I script it from Python?**
A: Yes.  Import `pipeline.process_image` for single images or
`batch.batch_process` for many.  Both take a single `ProcessParams`
dataclass.

**Q: Can I run it headless on a server / in CI?**
A: Use `cli.py`.  The GUI is optional.

**Q: Does it preserve the shadow under each sprite?**
A: Yes — that's the dual-alpha "exact" pipeline's whole point.  Pick
`shadow_mode=soft` for a natural drop shadow on any new background, or
`keep` to leave the original opaque shadow untouched.

**Q: How does it handle non-ASCII filenames on Windows?**
A: All image I/O goes through `numpy.fromfile` / `cv2.imencode`, which
correctly handles Unicode paths where `cv2.imread` / `cv2.imwrite`
would fail.

**Q: What if my sprites touch / share foreground pixels?**
A: Connected components won't separate them.  Try `--bridge-erode 2`
to break thin pixel bridges, raise `--strict-d-inner` to tighten the
icon body mask, or fall back to `--split grid` for uniform sheets.

**Q: Does it write a `_preview.png`?**
A: No.  Preview rendering is a GUI-only concern; exports contain only
your crops (plus an optional `_transparent.png` from single-image
export).

**Q: Where are my settings stored?**
A: Windows: `%APPDATA%\ChromaTool\settings.json`.
   Linux/macOS: `~/.config/chromatool/settings.json`.
The file is written atomically on every GUI close and via *File →
Save Settings Now*.

**Q: 中文界面 / 日本語インターフェース?**
A: GUI defaults to English — switch via *Language → 中文* or
*Language → 日本語* in the menu.  See [README.zh.md](README.zh.md)
for the Chinese docs and [README.ja.md](README.ja.md) for the
Japanese docs.

## Known limitations

* **Touching sprites can't be split by connected components.**  Two
  sprites that share a single pixel of foreground will be cropped as
  one.  Mitigate with `--bridge-erode`, or use `--split grid` on
  uniform sheets.
* **Single background colour per image.**  Multi-colour backgrounds
  need multiple keying passes (not provided).
* **No alpha matting on hair/fur.**  For very soft edges, post-process
  with [PyMatting](https://github.com/pymatting/pymatting) after the
  tool's alpha is produced.

## License

Pure computer-vision code — see the repository for the license file.
