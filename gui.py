"""Tkinter GUI for Chroma Tool.

Layout
------
::

    ┌──────────────────────────────────────────────────────────────┐
    │ Toolbar:  [Generate]  [Export Current]  [Export All Batch]   │
    ├──────────────┬─────────────────────────┬───────────────────── ┤
    │              │                         │                     │
    │ Image list   │   Preview canvas        │   Parameters panel  │
    │ + naming &   │   (current selection)   │   (scrollable)      │
    │ output root  │                         │                     │
    │              │                         │                     │
    └──────────────┴─────────────────────────┴─────────────────────┘
    │ status bar                                                   │

Workflow
--------
1. **Add Images** (or **Add Folder**) on the left.  Click an entry in
   the list to make it the preview.
2. Tweak parameters on the right; click **Generate** to apply.
3. **Export Current** writes the selected image's crops to a chosen
   folder using the naming pattern.
4. **Export All (Batch)** applies the same parameter set to every
   image in the list and writes each image's crops into its own
   sub-folder of the output root.
"""
from __future__ import annotations

import colorsys
import json
import os
import sys
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

# Optional drag-and-drop: tkinterdnd2 isn't always available (e.g. EXE
# builds without the wheel).  When it's missing we fall back to plain Tk
# and skip wiring the drop target — the GUI still works as before.
try:  # pragma: no cover — environment-dependent
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:  # pragma: no cover
    DND_FILES = None  # type: ignore[assignment]
    TkinterDnD = None  # type: ignore[assignment]
    _HAS_DND = False

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from autoparam import auto_params, estimate_bg_bgr
from batch import BatchResult, batch_process
from i18n import DEFAULT_LANG, I18n
from io_utils import (
    IMAGE_SUFFIXES, imread_unicode, imwrite_unicode, iter_image_files,
    to_bgr_and_alpha,
)
from keying import KeyingParams, sample_bgr, sample_hsv
from naming import NamingPattern, image_stem
from pipeline import ProcessParams, ProcessResult, export_crops, process_image
from profiles import (
    PROFILE_VAR_NAMES, load_profiles, normalise_key, save_profiles,
)
from presets import load_presets, save_presets
from settings import (
    GLOBAL_VAR_NAMES, load_settings, save_settings, settings_path,
)
from shadows import ShadowParams
from splitting import ContourParams, GridParams, HybridParams


PREVIEW_MAX = 900
DEFAULT_BG_BGR = (50, 180, 138)
PROFILE_MARK = "● "  # prefix on listbox entries that have a saved profile


# ─── Application ────────────────────────────────────────────────────
class App:
    """The whole Tk application — one window, one config, many images."""

    def __init__(self, root: tk.Tk, lang: str = DEFAULT_LANG) -> None:
        self.root = root
        self._stored = load_settings()
        self._profiles: dict[str, dict] = load_profiles()
        self._presets: dict[str, dict] = load_presets()
        self.i18n = I18n(self._stored.get("lang", lang))

        # ─── data state ─────────────────────────────────────────────
        self.image_paths: list[str] = []
        self.current_index: int | None = None
        self.current_img_bgr: np.ndarray | None = None
        self.current_existing_alpha: np.ndarray | None = None
        self.bg_bgr: tuple[int, int, int] | None = None
        self.active_path: str | None = None  # normalised key into _profiles
        self.last_result: ProcessResult | None = None
        self._preview_imgtk: ImageTk.PhotoImage | None = None
        self._preview_scale: float = 1.0
        self._dynamic_state: list[tuple[tk.StringVar, str, dict]] = []

        # ─── manual merge + canvas interaction state ────────────────
        # Merge rectangles (image coords) for the active image; applied
        # by the pipeline and persisted in the image's profile.
        self.merge_groups: list[tuple[int, int, int, int]] = []
        # "pick" = left-click samples bg colour (original behaviour);
        # "select" = left click/drag selects crops to merge; right click on
        #            a selected crop deselects it, right click on empty space
        #            clears the whole selection, right drag deselects a box.
        self.interact_mode: str = "pick"
        self._selected_crops: set[int] = set()  # indices into last_result.crops
        self._drag_start: tuple[int, int] | None = None  # canvas coords (left)
        self._rubber_band: int | None = None  # canvas rectangle item id (left)
        self._rdrag_start: tuple[int, int] | None = None  # canvas coords (right)
        self._rubber_band_r: int | None = None  # canvas rectangle item id (right)

        # ─── build UI ───────────────────────────────────────────────
        root.geometry("1480x920")
        root.minsize(1100, 720)
        self._refresh_title()
        self.i18n.add_listener(self._refresh_title)
        self.i18n.add_listener(self._refresh_naming_preview)

        self._define_tk_vars()
        self._build_menu()
        self._build_layout()
        self._apply_stored_settings()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_dynamic(self.status_var, "status.welcome")
        self._refresh_naming_preview()

    # ─── i18n state helpers ─────────────────────────────────────────
    def _refresh_title(self) -> None:
        self.root.title(self.i18n.t("app.title"))

    def _refresh_mode_btn(self) -> None:
        """Update the canvas-mode toggle's label for the current mode/lang."""
        if not hasattr(self, "mode_btn"):
            return
        key = "btn.mode_pick" if self.interact_mode == "pick" else "btn.mode_select"
        self.mode_btn.configure(text=self.i18n.t(key))

    def _set_dynamic(self, var: tk.StringVar, key: str, **kwargs) -> None:
        for i, (v, _k, _kw) in enumerate(self._dynamic_state):
            if v is var:
                self._dynamic_state[i] = (var, key, kwargs)
                break
        else:
            self._dynamic_state.append((var, key, kwargs))
        var.set(self.i18n.t(key, **kwargs))

    def _refresh_dynamic(self) -> None:
        for var, key, kwargs in self._dynamic_state:
            try:
                var.set(self.i18n.t(key, **kwargs))
            except Exception:
                pass

    # ─── Tk variable declarations ───────────────────────────────────
    def _define_tk_vars(self) -> None:
        # keying
        self.keying_on = tk.BooleanVar(value=True)
        self.d_inner = tk.IntVar(value=12)
        self.d_outer = tk.IntVar(value=32)
        self.hue = tk.IntVar(value=60)
        self.hue_tol = tk.IntVar(value=25)
        self.sat_min = tk.IntVar(value=60)
        self.val_min = tk.IntVar(value=60)
        self.mode = tk.StringVar(value="exact")
        self.bg_min_area = tk.IntVar(value=50_000)
        self.feather = tk.IntVar(value=2)
        self.decon = tk.BooleanVar(value=True)

        # shadows
        self.shadow_mode = tk.StringVar(value="soft")
        self.shadow_intensity = tk.DoubleVar(value=1.3)
        self.shadow_max_alpha = tk.IntVar(value=180)

        # splitter
        self.split_mode = tk.StringVar(value="hybrid")
        self.anchor_area = tk.IntVar(value=4000)
        self.merge_distance = tk.IntVar(value=80)
        self.min_area = tk.IntVar(value=400)
        self.padding = tk.IntVar(value=4)
        self.shadow_distance = tk.IntVar(value=80)
        self.bridge_erode = tk.IntVar(value=0)
        self.strict_d_inner = tk.IntVar(value=30)
        self.strict_d_outer = tk.IntVar(value=50)
        self.coalesce_distance = tk.IntVar(value=0)
        self.cell_w = tk.IntVar(value=200)
        self.cell_h = tk.IntVar(value=200)

        # naming + batch
        self.naming_prefix = tk.StringVar(value="")
        self.naming_start_index = tk.IntVar(value=1)
        self.naming_zero_pad = tk.IntVar(value=0)
        self.batch_out_root = tk.StringVar(value="")
        # True  → each image gets its own out_root/<stem>/ sub-folder.
        # False → every crop is written straight into out_root.
        self.batch_subfolder = tk.BooleanVar(value=True)

        for var in (self.naming_prefix, self.naming_start_index,
                    self.naming_zero_pad):
            var.trace_add("write", lambda *_: self._refresh_naming_preview())

    # ─── menu ───────────────────────────────────────────────────────
    def _build_menu(self) -> None:
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=False)
        f.add_command(label=self.i18n.t("menu.open"),
                      command=self.cmd_add_images, accelerator="Ctrl+O")
        f.add_command(label=self.i18n.t("menu.open_folder"),
                      command=self.cmd_add_folder)
        f.add_separator()
        f.add_command(label=self.i18n.t("menu.export"),
                      command=self.cmd_export_current, accelerator="Ctrl+E")
        f.add_command(label=self.i18n.t("menu.export_all"),
                      command=self.cmd_export_batch, accelerator="Ctrl+B")
        f.add_separator()
        f.add_command(label=self.i18n.t("menu.clear_list"),
                      command=self.cmd_clear_list)
        f.add_separator()
        f.add_command(label=self.i18n.t("menu.save_settings"),
                      command=self._save_now)
        f.add_command(label=self.i18n.t("menu.reset_settings"),
                      command=self._reset_settings)
        f.add_separator()
        f.add_command(label=self.i18n.t("menu.export_config"),
                      command=self.cmd_export_config)
        f.add_command(label=self.i18n.t("menu.import_config"),
                      command=self.cmd_import_config)
        f.add_separator()
        f.add_command(label=self.i18n.t("menu.exit"),
                      command=self._on_close)
        m.add_cascade(label=self.i18n.t("menu.file"), menu=f)

        lang_menu = tk.Menu(m, tearoff=False)
        self._lang_choice = tk.StringVar(value=self.i18n.lang)
        for code, key in (("zh", "menu.lang.zh"),
                          ("en", "menu.lang.en"),
                          ("ja", "menu.lang.ja")):
            lang_menu.add_radiobutton(
                label=self.i18n.t(key), value=code,
                variable=self._lang_choice,
                command=lambda c=code: self._set_language(c))
        m.add_cascade(label=self.i18n.t("menu.language"), menu=lang_menu)

        self._menu_file = f
        self._menu_lang = lang_menu
        self._menu_root = m
        self.root.config(menu=m)

        self.i18n.add_listener(self._refresh_menu)
        self.root.bind("<Control-o>", lambda _e: self.cmd_add_images())
        self.root.bind("<Control-e>", lambda _e: self.cmd_export_current())
        self.root.bind("<Control-b>", lambda _e: self.cmd_export_batch())

    def _refresh_menu(self) -> None:
        for index, key in [(0, "menu.open"), (1, "menu.open_folder"),
                           (3, "menu.export"), (4, "menu.export_all"),
                           (6, "menu.clear_list"),
                           (8, "menu.save_settings"), (9, "menu.reset_settings"),
                           (11, "menu.export_config"),
                           (12, "menu.import_config"),
                           (14, "menu.exit")]:
            try:
                self._menu_file.entryconfig(index, label=self.i18n.t(key))
            except Exception:
                pass
        self._menu_root.entryconfig(0, label=self.i18n.t("menu.file"))
        self._menu_root.entryconfig(1, label=self.i18n.t("menu.language"))
        self._menu_lang.entryconfig(0, label=self.i18n.t("menu.lang.zh"))
        self._menu_lang.entryconfig(1, label=self.i18n.t("menu.lang.en"))
        self._menu_lang.entryconfig(2, label=self.i18n.t("menu.lang.ja"))

    def _set_language(self, lang: str) -> None:
        self.i18n.set_language(lang)
        self._lang_choice.set(lang)

    # ─── layout ─────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side="top", fill="x", padx=6, pady=(6, 0))
        self._build_toolbar(toolbar)

        main = ttk.Frame(self.root)
        main.pack(side="top", fill="both", expand=True, padx=4, pady=4)

        left = ttk.Frame(main, width=280)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._build_left_panel(left)

        center = ttk.Frame(main)
        center.pack(side="left", fill="both", expand=True, padx=4)
        self._build_preview(center)

        right_holder = ttk.Frame(main, width=360)
        right_holder.pack(side="right", fill="y")
        right_holder.pack_propagate(False)
        self._build_parameters_panel(right_holder)

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var,
                  anchor="w", relief="sunken").pack(side="bottom", fill="x")

    def _build_toolbar(self, parent: ttk.Frame) -> None:
        gen = ttk.Button(parent, command=self.cmd_generate,
                         style="Accent.TButton")
        self.i18n.attach(gen, "text", "btn.generate")
        gen.pack(side="left", padx=2, ipadx=8, ipady=2)

        auto = ttk.Button(parent, command=self.cmd_auto_detect,
                          style="Accent.TButton")
        self.i18n.attach(auto, "text", "btn.auto_detect")
        auto.pack(side="left", padx=2, ipadx=8, ipady=2)

        ttk.Separator(parent, orient="vertical").pack(
            side="left", fill="y", padx=4, pady=2)

        # Canvas-interaction tools: toggle between colour-picking and
        # rubber-band crop selection, plus merge / clear of the selection.
        self.mode_btn = ttk.Button(parent, command=self.cmd_toggle_interact_mode)
        self.mode_btn.pack(side="left", padx=2, ipadx=4)
        self._refresh_mode_btn()
        self.i18n.add_listener(self._refresh_mode_btn)

        merge_btn = ttk.Button(parent, command=self.cmd_merge_selected)
        self.i18n.attach(merge_btn, "text", "btn.merge_selected")
        merge_btn.pack(side="left", padx=2, ipadx=4)

        clear_merge_btn = ttk.Button(parent, command=self.cmd_clear_merges)
        self.i18n.attach(clear_merge_btn, "text", "btn.clear_merges")
        clear_merge_btn.pack(side="left", padx=2, ipadx=4)

        ttk.Separator(parent, orient="vertical").pack(
            side="left", fill="y", padx=4, pady=2)

        exp_one = ttk.Button(parent, command=self.cmd_export_current)
        self.i18n.attach(exp_one, "text", "btn.export_current")
        exp_one.pack(side="left", padx=2, ipadx=4)

        exp_all = ttk.Button(parent, command=self.cmd_export_batch)
        self.i18n.attach(exp_all, "text", "btn.export_all")
        exp_all.pack(side="left", padx=2, ipadx=4)

        self.result_var = tk.StringVar()
        ttk.Label(parent, textvariable=self.result_var,
                  font=("Segoe UI", 10, "bold")).pack(side="right", padx=8)
        self._set_dynamic(self.result_var, "result.placeholder")

        hint = ttk.Label(parent, foreground="#888")
        self.i18n.attach(hint, "text", "hint.batch")
        hint.pack(side="right", padx=8)

    # ─── left panel: image list + naming + output root ──────────────
    def _build_left_panel(self, parent: ttk.Frame) -> None:
        header = ttk.Label(parent, font=("Segoe UI", 10, "bold"))
        self.i18n.attach(header, "text", "section.image_list")
        header.pack(anchor="w", pady=(4, 2))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical")
        self.image_listbox = tk.Listbox(list_frame, yscrollcommand=sb.set,
                                        exportselection=False,
                                        activestyle="dotbox")
        sb.config(command=self.image_listbox.yview)
        sb.pack(side="right", fill="y")
        self.image_listbox.pack(side="left", fill="both", expand=True)
        self.image_listbox.bind("<<ListboxSelect>>", self._on_image_select)
        self._wire_drop_target(self.image_listbox)
        self._wire_drop_target(list_frame)

        btns = ttk.Frame(parent)
        btns.pack(fill="x", pady=2)
        for key, cmd in (("btn.add_images", self.cmd_add_images),
                         ("btn.add_folder", self.cmd_add_folder),
                         ("btn.remove_selected", self.cmd_remove_selected),
                         ("btn.clear_list", self.cmd_clear_list)):
            b = ttk.Button(btns, command=cmd)
            self.i18n.attach(b, "text", key)
            b.pack(side="left", padx=1, pady=1, fill="x", expand=True)

        ttk.Separator(parent).pack(fill="x", pady=(8, 4))

        naming_hdr = ttk.Label(parent, font=("Segoe UI", 10, "bold"))
        self.i18n.attach(naming_hdr, "text", "section.naming")
        naming_hdr.pack(anchor="w")

        body = ttk.Frame(parent)
        body.pack(fill="x", pady=(2, 0))
        body.columnconfigure(1, weight=1)

        lbl1 = ttk.Label(body)
        self.i18n.attach(lbl1, "text", "naming.prefix_label")
        lbl1.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Entry(body, textvariable=self.naming_prefix).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        lbl2 = ttk.Label(body)
        self.i18n.attach(lbl2, "text", "naming.start_label")
        lbl2.grid(row=2, column=0, sticky="w")
        ttk.Spinbox(body, from_=0, to=999_999, textvariable=self.naming_start_index,
                    width=6).grid(row=2, column=1, sticky="e")

        lbl3 = ttk.Label(body)
        self.i18n.attach(lbl3, "text", "naming.pad_label")
        lbl3.grid(row=3, column=0, sticky="w")
        ttk.Spinbox(body, from_=0, to=8, textvariable=self.naming_zero_pad,
                    width=6).grid(row=3, column=1, sticky="e")

        self.naming_preview_var = tk.StringVar()
        ttk.Label(body, textvariable=self.naming_preview_var,
                  foreground="#5588cc",
                  wraplength=260).grid(row=4, column=0, columnspan=2,
                                       sticky="w", pady=(4, 4))

        ttk.Separator(parent).pack(fill="x", pady=(8, 4))

        out_hdr = ttk.Label(parent, font=("Segoe UI", 10, "bold"))
        self.i18n.attach(out_hdr, "text", "naming.out_root_label")
        out_hdr.pack(anchor="w")

        out_frame = ttk.Frame(parent)
        out_frame.pack(fill="x")
        ttk.Entry(out_frame, textvariable=self.batch_out_root).pack(
            side="left", fill="x", expand=True)
        b = ttk.Button(out_frame, command=self.cmd_choose_out_root)
        self.i18n.attach(b, "text", "btn.choose_out_root")
        b.pack(side="right")

        sub_cb = ttk.Checkbutton(parent, variable=self.batch_subfolder)
        self.i18n.attach(sub_cb, "text", "batch.subfolder")
        sub_cb.pack(anchor="w", pady=(4, 0))

    # ─── preview canvas ─────────────────────────────────────────────
    def _build_preview(self, parent: ttk.Frame) -> None:
        self.canvas = tk.Canvas(parent, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        # Right button (select mode): drag to deselect, click on a merged
        # region to undo that one merge.
        self.canvas.bind("<Button-3>", self._on_canvas_press_right)
        self.canvas.bind("<B3-Motion>", self._on_canvas_drag_right)
        self.canvas.bind("<ButtonRelease-3>", self._on_canvas_release_right)
        self.canvas.bind("<Configure>", lambda _e: self._render_preview())

    # ─── parameters panel ───────────────────────────────────────────
    def _build_parameters_panel(self, holder: ttk.Frame) -> None:
        scroll_canvas = tk.Canvas(holder, highlightthickness=0, borderwidth=0)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(holder, orient="vertical",
                               command=scroll_canvas.yview)
        scroll.pack(side="right", fill="y")
        scroll_canvas.configure(yscrollcommand=scroll.set)

        inner = ttk.Frame(scroll_canvas)
        window = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda _e: scroll_canvas.configure(
                       scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>",
                           lambda e: scroll_canvas.itemconfigure(window,
                                                                  width=e.width))

        def _wheel(event: tk.Event) -> str:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
            if getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            scroll_canvas.yview_scroll(delta, "units")
            return "break"

        holder.bind("<Enter>",
                    lambda _e: scroll_canvas.bind_all("<MouseWheel>", _wheel))
        holder.bind("<Leave>",
                    lambda _e: scroll_canvas.unbind_all("<MouseWheel>"))

        self._populate_parameters(inner)

    def _populate_parameters(self, parent: ttk.Frame) -> None:
        row = 0
        parent.columnconfigure(1, weight=1)

        def header(key: str) -> None:
            nonlocal row
            lbl = ttk.Label(parent, font=("Segoe UI", 10, "bold"))
            self.i18n.attach(lbl, "text", key)
            lbl.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 2))
            row += 1

        def slider(key: str, var: tk.Variable, lo: float, hi: float,
                   step: float | None = None) -> None:
            """A label + Scale + Spinbox row, all sharing one Tk variable.

            ``step`` defaults to 1 for IntVar, 0.1 for DoubleVar.  The
            Spinbox lets the user type an exact value; the Scale gives a
            quick visual sweep.  Both stay in sync because they bind to
            the same variable.
            """
            nonlocal row
            is_double = isinstance(var, tk.DoubleVar)
            increment = step if step is not None else (0.1 if is_double else 1)
            lbl = ttk.Label(parent, width=22)
            self.i18n.attach(lbl, "text", key)
            lbl.grid(row=row, column=0, sticky="w")
            ttk.Scale(parent, from_=lo, to=hi, orient="horizontal",
                      variable=var).grid(row=row, column=1, sticky="ew", padx=4)
            sp = ttk.Spinbox(parent, from_=lo, to=hi,
                             increment=increment, width=8,
                             textvariable=var,
                             format="%.2f" if is_double else "%.0f")
            sp.grid(row=row, column=2, sticky="e")
            row += 1

        def check(key: str, var: tk.Variable) -> None:
            nonlocal row
            cb = ttk.Checkbutton(parent, variable=var)
            self.i18n.attach(cb, "text", key)
            cb.grid(row=row, column=0, columnspan=3, sticky="w")
            row += 1

        def radio(key: str, var: tk.Variable, value: str) -> None:
            nonlocal row
            rb = ttk.Radiobutton(parent, variable=var, value=value)
            self.i18n.attach(rb, "text", key)
            rb.grid(row=row, column=0, columnspan=3, sticky="w")
            row += 1

        # ─── named presets ──────────────────────────────────────────
        header("section.presets")
        self.preset_choice = tk.StringVar(value="")
        self.preset_combo = ttk.Combobox(parent, textvariable=self.preset_choice,
                                         state="readonly")
        self.preset_combo.grid(row=row, column=0, columnspan=3,
                               sticky="ew", pady=(0, 2))
        row += 1
        preset_btns = ttk.Frame(parent)
        preset_btns.grid(row=row, column=0, columnspan=3, sticky="ew",
                         pady=(0, 4))
        row += 1
        for key, cmd in (("btn.save_preset", self.cmd_save_preset),
                         ("btn.apply_preset_all", self.cmd_apply_preset_all),
                         ("btn.delete_preset", self.cmd_delete_preset)):
            b = ttk.Button(preset_btns, command=cmd)
            self.i18n.attach(b, "text", key)
            b.pack(side="left", padx=1, fill="x", expand=True)
        self._refresh_preset_combo()

        # ─── keying toggle ──────────────────────────────────────────
        header("section.keying_toggle")
        check("toggle.remove_bg", self.keying_on)

        # ─── background colour ──────────────────────────────────────
        header("section.bg_color")
        self.bg_label = tk.StringVar()
        ttk.Label(parent, textvariable=self.bg_label,
                  foreground="#888", wraplength=320).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
        row += 1
        self._set_dynamic(self.bg_label, "bg.unpicked")
        pick_btn = ttk.Button(parent, command=self._pick_color_dialog)
        self.i18n.attach(pick_btn, "text", "btn.pick_color")
        pick_btn.grid(row=row, column=0, columnspan=3, sticky="ew",
                      pady=(0, 4))
        row += 1
        auto_btn = ttk.Button(parent, command=self.cmd_auto_detect,
                              style="Accent.TButton")
        self.i18n.attach(auto_btn, "text", "btn.auto_detect")
        auto_btn.grid(row=row, column=0, columnspan=3, sticky="ew",
                      pady=(0, 2))
        row += 1
        auto_hint = ttk.Label(parent, foreground="#888", wraplength=320)
        self.i18n.attach(auto_hint, "text", "hint.auto_detect")
        auto_hint.grid(row=row, column=0, columnspan=3, sticky="w",
                       pady=(0, 4))
        row += 1
        # Prominent one-click granularity knob: drives how coarse Auto's
        # output is.  Higher = merge more nearby pieces = fewer, chunkier
        # crops; 0 = finest (current default).  Re-run Auto (or Generate)
        # to apply.  Shares the coalesce_distance variable, so it also
        # works as a live de-fragment slider in manual mode.
        gran_hdr = ttk.Label(parent, font=("Segoe UI", 10, "bold"),
                             foreground="#d08020")
        self.i18n.attach(gran_hdr, "text", "section.granularity")
        gran_hdr.grid(row=row, column=0, columnspan=3, sticky="w",
                      pady=(4, 0))
        row += 1
        slider("slider.coalesce_distance", self.coalesce_distance, 0, 300)
        gran_hint = ttk.Label(parent, foreground="#888", wraplength=320)
        self.i18n.attach(gran_hint, "text", "hint.granularity")
        gran_hint.grid(row=row, column=0, columnspan=3, sticky="w",
                       pady=(0, 4))
        row += 1
        slider("slider.exact_d_inner", self.d_inner, 0, 80)
        slider("slider.exact_d_outer", self.d_outer, 1, 120)
        slider("slider.hsv_hue", self.hue, 0, 179)
        slider("slider.hsv_hue_tol", self.hue_tol, 1, 80)
        slider("slider.hsv_sat_min", self.sat_min, 0, 255)
        slider("slider.hsv_val_min", self.val_min, 0, 255)

        # ─── mask mode ──────────────────────────────────────────────
        header("section.mask_mode")
        radio("mask.exact", self.mode, "exact")
        radio("mask.area", self.mode, "area")
        radio("mask.simple", self.mode, "simple")
        slider("slider.bg_min_area", self.bg_min_area, 1000, 1_000_000)
        slider("slider.feather", self.feather, 0, 8)
        check("check.decon", self.decon)

        # ─── shadow handling ────────────────────────────────────────
        header("section.shadow")
        radio("shadow.soft", self.shadow_mode, "soft")
        radio("shadow.keep", self.shadow_mode, "keep")
        radio("shadow.remove", self.shadow_mode, "remove")
        slider("slider.shadow_intensity", self.shadow_intensity, 0.5, 3.0)
        slider("slider.shadow_max_alpha", self.shadow_max_alpha, 0, 255)

        # ─── splitter ───────────────────────────────────────────────
        header("section.splitter")
        ttk.Combobox(parent, textvariable=self.split_mode,
                     values=["hybrid", "grid", "contour", "none"],
                     state="readonly").grid(row=row, column=0, columnspan=3,
                                            sticky="ew", pady=(0, 4))
        row += 1
        slider("slider.anchor_area", self.anchor_area, 500, 30_000)
        slider("slider.merge_distance", self.merge_distance, 0, 200)
        slider("slider.min_area", self.min_area, 50, 5000)
        slider("slider.padding", self.padding, 0, 32)
        slider("slider.shadow_distance", self.shadow_distance, 0, 200)
        slider("slider.bridge_erode", self.bridge_erode, 0, 8)
        slider("slider.strict_d_inner", self.strict_d_inner, 0, 80)
        slider("slider.strict_d_outer", self.strict_d_outer, 1, 120)

        header("section.grid")
        slider("slider.cell_w", self.cell_w, 16, 600)
        slider("slider.cell_h", self.cell_h, 16, 600)

    # ─── settings persistence ───────────────────────────────────────
    def _collect_settings(self) -> dict:
        data: dict = {
            "lang": self.i18n.lang,
            "image_paths": list(self.image_paths),
        }
        if self.active_path is not None:
            data["active_path"] = self.active_path
        for name in GLOBAL_VAR_NAMES:
            var = getattr(self, name, None)
            if var is None:
                continue
            try:
                data[name] = var.get()
            except Exception:
                pass
        return data

    def _apply_stored_settings(self) -> None:
        data = self._stored
        if not data:
            return
        for name in GLOBAL_VAR_NAMES:
            if name not in data:
                continue
            var = getattr(self, name, None)
            if var is None:
                continue
            try:
                var.set(data[name])
            except Exception:
                pass
        self._set_dynamic(self.status_var, "status.settings_loaded",
                          path=str(settings_path()))
        self._restore_image_list(data)

    def _restore_image_list(self, data: dict) -> None:
        """Re-add previously loaded images and reselect the last active one."""
        paths = data.get("image_paths")
        if not isinstance(paths, list):
            return
        valid = [p for p in paths
                 if isinstance(p, str) and os.path.isfile(p)]
        if not valid:
            return
        self.image_paths.extend(valid)
        self._refresh_listbox()

        target = 0
        last = data.get("active_path")
        if isinstance(last, str):
            for i, p in enumerate(self.image_paths):
                if normalise_key(p) == last:
                    target = i
                    break
        self._select_index(target)

    def _save_now(self) -> None:
        try:
            path = save_settings(self._collect_settings())
        except Exception as exc:
            self._set_dynamic(self.status_var, "status.keyer_error",
                              exc=str(exc))
            return
        self._set_dynamic(self.status_var, "status.settings_saved",
                          path=str(path))

    # ─── parameter config import / export ───────────────────────────
    def cmd_export_config(self) -> None:
        """Write the current parameter widget state to a user-chosen JSON file.

        This dumps a portable snapshot — keying / shadow / split params
        plus the sampled bg colour — so the user can share or version
        their tweaks.  Per-image profiles are not included; this is the
        config of the *currently displayed* image.
        """
        path = filedialog.asksaveasfilename(
            title=self.i18n.t("dialog.export_config"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), (self.i18n.t("file.types_all"), "*.*")],
        )
        if not path:
            return
        snapshot = self._snapshot_profile()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            self._set_dynamic(self.status_var, "status.keyer_error",
                              exc=str(exc))
            return
        self._set_dynamic(self.status_var, "status.config_saved", path=path)

    def cmd_import_config(self) -> None:
        """Load a JSON config file produced by :meth:`cmd_export_config`.

        The user picks how it should interact with the existing per-image
        profile store:

        * **Current only** — only the active image (and the live widgets)
          take the new values.  Other images keep their saved profile.
        * **All images** — every entry in ``_profiles`` is overwritten,
          which is what you want when you've found a config that works
          across the whole batch.
        * **Only images without a profile** — preserves manually tuned
          images, but propagates the imported values to anything still
          using the fallback.

        This keeps the per-image profile system intact while giving the
        user a single source-of-truth file they can ship between
        machines.
        """
        path = filedialog.askopenfilename(
            title=self.i18n.t("dialog.import_config"),
            filetypes=[("JSON", "*.json"), (self.i18n.t("file.types_all"), "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                profile = json.load(fh)
        except Exception as exc:
            self._set_dynamic(self.status_var, "status.config_load_error",
                              exc=str(exc))
            return
        if not isinstance(profile, dict):
            self._set_dynamic(self.status_var, "status.config_load_error",
                              exc="not a dict")
            return

        scope = self._ask_import_scope()
        if scope is None:
            return  # cancelled

        # Always update live widgets so the user sees the new values.
        self._apply_profile(profile)

        if scope == "all":
            for key in list(self._profiles.keys()):
                self._profiles[key] = dict(profile)
        elif scope == "missing":
            # Leave images with explicit profiles alone.  Their fallback
            # changes the next time they're loaded fresh — but the only
            # visible knob right now is the live widget state.
            pass
        # "current": fall through, only the active widget state changed.

        # Save the current image's profile so the change persists for it.
        if self.active_path:
            self._profiles[self.active_path] = self._snapshot_profile()
        try:
            save_profiles(self._profiles)
        except Exception:
            pass

        self._refresh_listbox()
        if self.current_index is not None:
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(self.current_index)
            self.image_listbox.activate(self.current_index)
        self._process_current()
        self._set_dynamic(self.status_var, "status.config_loaded", path=path)

    def _ask_import_scope(self) -> str | None:
        """Modal dialog: return "current" | "all" | "missing" | None (cancel)."""
        dlg = tk.Toplevel(self.root)
        dlg.title(self.i18n.t("dialog.import_config"))
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        choice = tk.StringVar(value="current")
        ttk.Label(dlg, text=self.i18n.t("dialog.import_scope_prompt"),
                  wraplength=360).pack(padx=12, pady=(12, 6), anchor="w")
        for value, key in (("current", "dialog.import_scope_current"),
                           ("missing", "dialog.import_scope_missing"),
                           ("all", "dialog.import_scope_all")):
            ttk.Radiobutton(dlg, variable=choice, value=value,
                            text=self.i18n.t(key)).pack(
                anchor="w", padx=18, pady=2)

        result: dict[str, str | None] = {"value": None}

        def _ok() -> None:
            result["value"] = choice.get()
            dlg.destroy()

        def _cancel() -> None:
            result["value"] = None
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(fill="x", padx=12, pady=12)
        ttk.Button(btns, text=self.i18n.t("dialog.ok"), command=_ok).pack(
            side="right", padx=4)
        ttk.Button(btns, text=self.i18n.t("dialog.cancel"),
                   command=_cancel).pack(side="right")
        dlg.bind("<Return>", lambda _e: _ok())
        dlg.bind("<Escape>", lambda _e: _cancel())
        dlg.wait_window()
        return result["value"]

    def _reset_settings(self) -> None:
        defaults = {
            "keying_on": True,
            "d_inner": 12, "d_outer": 32,
            "hue": 60, "hue_tol": 25, "sat_min": 60, "val_min": 60,
            "mode": "exact",
            "bg_min_area": 50_000, "feather": 2, "decon": True,
            "shadow_mode": "soft", "shadow_intensity": 1.3,
            "shadow_max_alpha": 180,
            "split_mode": "hybrid",
            "anchor_area": 4000, "merge_distance": 80,
            "min_area": 400, "padding": 4,
            "shadow_distance": 80, "bridge_erode": 0,
            "strict_d_inner": 30, "strict_d_outer": 50,
            "coalesce_distance": 0,
            "cell_w": 200, "cell_h": 200,
            "naming_prefix": "", "naming_start_index": 1, "naming_zero_pad": 0,
        }
        for key, val in defaults.items():
            var = getattr(self, key, None)
            if var is not None:
                try:
                    var.set(val)
                except Exception:
                    pass
        self.merge_groups = []
        self._selected_crops.clear()
        self._set_dynamic(self.status_var, "status.settings_reset")

    def _on_close(self) -> None:
        self._save_active_profile()
        try:
            save_settings(self._collect_settings())
        except Exception:
            pass
        try:
            save_profiles(self._profiles)
        except Exception:
            pass
        try:
            save_presets(self._presets)
        except Exception:
            pass
        self.root.destroy()

    # ─── per-image profile machinery ────────────────────────────────
    def _snapshot_profile(self) -> dict:
        """Capture the current widget state as a profile dict."""
        data: dict = {}
        if self.bg_bgr is not None:
            data["bg_bgr"] = list(self.bg_bgr)
        data["merge_groups"] = [list(r) for r in self.merge_groups]
        for name in PROFILE_VAR_NAMES:
            var = getattr(self, name, None)
            if var is None:
                continue
            try:
                data[name] = var.get()
            except Exception:
                pass
        return data

    def _apply_profile(self, profile: dict) -> None:
        """Push a profile dict into the live widgets and bg_bgr."""
        bg = profile.get("bg_bgr")
        if isinstance(bg, list) and len(bg) == 3:
            self.bg_bgr = (int(bg[0]), int(bg[1]), int(bg[2]))
            self._set_dynamic(self.bg_label, "bg.auto",
                              bgr=str(self.bg_bgr))
        self.merge_groups = _coerce_merge_groups(profile.get("merge_groups"))
        self._selected_crops.clear()
        for name in PROFILE_VAR_NAMES:
            if name not in profile:
                continue
            var = getattr(self, name, None)
            if var is None:
                continue
            try:
                var.set(profile[name])
            except Exception:
                pass

    def _save_active_profile(self) -> bool:
        """Write the current widget state into ``_profiles[active_path]``.

        Returns True when a profile was actually written.  No-op when no
        image is currently active.  Persists the whole profile store to
        disk so per-image configs survive restarts.
        """
        if not self.active_path:
            return False
        self._profiles[self.active_path] = self._snapshot_profile()
        try:
            save_profiles(self._profiles)
        except Exception:
            return False
        return True

    # ─── image-list commands ────────────────────────────────────────
    def cmd_add_images(self) -> None:
        types = " ".join(f"*{s}" for s in IMAGE_SUFFIXES)
        paths = filedialog.askopenfilenames(
            title=self.i18n.t("dialog.add_folder"),
            filetypes=[(self.i18n.t("file.types_image"), types),
                       (self.i18n.t("file.types_all"), "*.*")],
        )
        if paths:
            self._append_paths(paths)

    def cmd_add_folder(self) -> None:
        folder = filedialog.askdirectory(title=self.i18n.t("dialog.add_folder"))
        if folder:
            self._append_paths(list(iter_image_files(folder)))

    def cmd_remove_selected(self) -> None:
        selection = list(self.image_listbox.curselection())
        if not selection:
            return
        self._save_active_profile()
        for idx in reversed(selection):
            del self.image_paths[idx]
        self._refresh_listbox()
        if self.image_paths:
            self._select_index(min(selection[0], len(self.image_paths) - 1))
        else:
            self._clear_preview()

    def cmd_clear_list(self) -> None:
        self._save_active_profile()
        self.image_paths.clear()
        self._refresh_listbox()
        self._clear_preview()

    def _append_paths(self, paths) -> None:
        existing = set(self.image_paths)
        added = 0
        for path in paths:
            if path not in existing:
                self.image_paths.append(path)
                existing.add(path)
                added += 1
        self._refresh_listbox()
        if added and self.current_index is None:
            self._select_index(0)
        self._refresh_naming_preview()

    # ─── drag & drop ────────────────────────────────────────────────
    def _wire_drop_target(self, widget) -> None:
        """Register ``widget`` as a drop target for image files / folders."""
        if not _dnd_active(self.root):
            return
        try:
            widget.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            widget.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_drop(self, event) -> str:
        raw = getattr(event, "data", "") or ""
        # tkinterdnd2 returns a Tcl list of paths, paths-with-spaces
        # are wrapped in {…}.  splitlist handles both.
        try:
            tokens = self.root.tk.splitlist(raw)
        except Exception:
            tokens = [raw]
        collected: list[str] = []
        for token in tokens:
            path = token.strip()
            if not path:
                continue
            if os.path.isdir(path):
                collected.extend(iter_image_files(path))
            elif os.path.isfile(path):
                if path.lower().endswith(IMAGE_SUFFIXES):
                    collected.append(path)
        if collected:
            self._append_paths(collected)
            self._set_dynamic(self.status_var, "status.dropped",
                              n=len(collected))
        return "break"

    def _refresh_listbox(self) -> None:
        self.image_listbox.delete(0, tk.END)
        for path in self.image_paths:
            mark = PROFILE_MARK if normalise_key(path) in self._profiles else ""
            self.image_listbox.insert(tk.END, f"{mark}{os.path.basename(path)}")

    def _select_index(self, idx: int) -> None:
        if not (0 <= idx < len(self.image_paths)):
            return
        self.image_listbox.selection_clear(0, tk.END)
        self.image_listbox.selection_set(idx)
        self.image_listbox.activate(idx)
        self.image_listbox.see(idx)
        self._load_image(idx)

    def _on_image_select(self, _event) -> None:
        selection = self.image_listbox.curselection()
        if not selection:
            return
        self._load_image(selection[0])

    def _load_image(self, idx: int) -> None:
        path = self.image_paths[idx]
        key = normalise_key(path)
        raw = imread_unicode(path)
        if raw is None:
            self._set_dynamic(self.status_var, "status.image_error",
                              path=path, exc="decode failed")
            return
        bgr, alpha = to_bgr_and_alpha(raw)

        # Snapshot the outgoing image's widget state before we replace it.
        if self.active_path and self.active_path != key:
            self._profiles[self.active_path] = self._snapshot_profile()
            try:
                save_profiles(self._profiles)
            except Exception:
                pass

        self.active_path = key
        self.current_index = idx
        self.current_img_bgr = bgr
        self.current_existing_alpha = alpha

        display = os.path.basename(path)
        if key in self._profiles:
            self._apply_profile(self._profiles[key])
            self._set_dynamic(self.status_var, "status.profile_loaded",
                              name=display)
        else:
            # New image (no saved profile): always re-derive the
            # background colour from *this* image's border.  Re-using a
            # stale colour from a previously processed image would key
            # the wrong pixels — the bug behind "same params, different
            # result" between sessions.
            self.bg_bgr = estimate_bg_bgr(bgr)
            self.merge_groups = []
            self._selected_crops.clear()
            self._set_dynamic(self.bg_label, "bg.auto",
                              bgr=str(self.bg_bgr))
            self._set_dynamic(self.status_var, "status.profile_new",
                              name=display)

        self._refresh_listbox()
        self.image_listbox.selection_clear(0, tk.END)
        self.image_listbox.selection_set(idx)
        self.image_listbox.activate(idx)
        self._process_current()
        self._refresh_naming_preview()

    def _clear_preview(self) -> None:
        self.active_path = None
        self.current_index = None
        self.current_img_bgr = None
        self.current_existing_alpha = None
        self.last_result = None
        self.merge_groups = []
        self._selected_crops.clear()
        self.canvas.delete("all")

    # ─── parameter extraction ───────────────────────────────────────
    _PARAM_DEFAULTS: dict = {
        "keying_on": True,
        "mode": "exact",
        "d_inner": 12, "d_outer": 32,
        "hue": 60, "hue_tol": 25, "sat_min": 60, "val_min": 60,
        "bg_min_area": 50_000, "feather": 2, "decon": True,
        "shadow_mode": "soft",
        "shadow_intensity": 1.3, "shadow_max_alpha": 180,
        "split_mode": "hybrid",
        "anchor_area": 4000, "merge_distance": 80,
        "min_area": 400, "padding": 4,
        "shadow_distance": 80, "bridge_erode": 0,
        "strict_d_inner": 30, "strict_d_outer": 50,
        "coalesce_distance": 0,
        "cell_w": 200, "cell_h": 200,
    }

    def _params_from_values(self, values: dict,
                            bg_bgr: tuple[int, int, int] | None
                            ) -> ProcessParams:
        """Build a :class:`ProcessParams` from a plain ``{name: value}`` map.

        Both the current widget state and any saved profile end up here
        — that's what keeps batch-mode honest about per-image configs.
        """
        def g(name):
            return values.get(name, self._PARAM_DEFAULTS[name])

        keying_on = bool(g("keying_on"))
        keying = KeyingParams(
            mode=g("mode"),
            bg_bgr=bg_bgr,
            d_inner=g("d_inner"), d_outer=g("d_outer"),
            hue=g("hue"), hue_tol=g("hue_tol"),
            sat_min=g("sat_min"), val_min=g("val_min"),
            bg_min_area=g("bg_min_area"),
            feather=g("feather") if keying_on else 0,
            decontaminate=bool(g("decon")) and keying_on,
        )
        shadows = ShadowParams(
            mode=g("shadow_mode"),
            intensity=float(g("shadow_intensity")),
            max_alpha=int(g("shadow_max_alpha")),
        )
        hybrid = HybridParams(
            anchor_area=g("anchor_area"),
            merge_distance=g("merge_distance"),
            min_keep_area=g("min_area"),
            padding=g("padding"),
            shadow_max_distance=g("shadow_distance"),
            bridge_erode=g("bridge_erode"),
            mask_outside=keying_on,
        )
        grid = GridParams(cell_w=g("cell_w"), cell_h=g("cell_h"))
        contour = ContourParams(min_area=g("min_area"),
                                padding=g("padding"),
                                mask_outside=keying_on)
        merge_groups = _coerce_merge_groups(values.get("merge_groups"))
        return ProcessParams(
            keying_on=keying_on,
            keying=keying, shadows=shadows,
            split_mode=g("split_mode"),
            hybrid=hybrid, grid=grid, contour=contour,
            strict_d_inner=float(g("strict_d_inner")),
            strict_d_outer=float(g("strict_d_outer")),
            coalesce_distance=int(g("coalesce_distance")),
            merge_groups=tuple(tuple(r) for r in merge_groups),
        )

    def _widget_values(self) -> dict:
        """Snapshot every profile-relevant widget value into a plain dict."""
        values: dict = {}
        for name in PROFILE_VAR_NAMES:
            var = getattr(self, name, None)
            if var is None:
                continue
            try:
                values[name] = var.get()
            except Exception:
                pass
        # merge_groups isn't a tk.Variable; carry the live list so the
        # current-widget ProcessParams applies the same manual merges the
        # preview shows.
        values["merge_groups"] = [list(r) for r in self.merge_groups]
        return values

    def _process_params(self) -> ProcessParams:
        """Build a :class:`ProcessParams` from the current widget state."""
        return self._params_from_values(self._widget_values(), self.bg_bgr)

    def _params_from_profile(self, profile: dict) -> ProcessParams:
        """Build a :class:`ProcessParams` from a saved profile dict."""
        bg = profile.get("bg_bgr")
        bg_bgr = None
        if isinstance(bg, list) and len(bg) == 3:
            bg_bgr = (int(bg[0]), int(bg[1]), int(bg[2]))
        return self._params_from_values(profile, bg_bgr)

    def _naming(self) -> NamingPattern:
        prefix = self.naming_prefix.get().strip() or None
        return NamingPattern(prefix=prefix,
                             start_index=int(self.naming_start_index.get()),
                             zero_pad=int(self.naming_zero_pad.get()))

    # ─── bg colour picking ──────────────────────────────────────────
    def _pick_color_dialog(self) -> None:
        initial = self.bg_bgr if self.bg_bgr else DEFAULT_BG_BGR
        b, g, r = initial
        result = colorchooser.askcolor(
            color=f"#{r:02x}{g:02x}{b:02x}",
            title=self.i18n.t("dialog.pick_color_title"),
        )
        if not result or not result[0]:
            return
        rr, gg, bb = result[0]
        self.bg_bgr = (int(bb), int(gg), int(rr))
        h_n, s_n, v_n = colorsys.rgb_to_hsv(rr / 255.0, gg / 255.0, bb / 255.0)
        h_ = int(h_n * 179)
        s_ = int(s_n * 255)
        v_ = int(v_n * 255)
        self.hue.set(h_)
        self.sat_min.set(max(20, s_ - 80))
        self.val_min.set(max(20, v_ - 80))
        self._set_dynamic(self.bg_label, "bg.picked",
                          bgr=str(self.bg_bgr),
                          hsv=f"({h_},{s_},{v_})",
                          x="dialog", y="dialog")

    def cmd_auto_detect(self) -> None:
        """Estimate every parameter from the current image and apply them.

        Detects the background colour off the image border, derives the
        keying distance thresholds from the colour-distance histogram,
        and sizes the splitter from connected-component statistics — then
        pushes all of it into the widgets and re-processes.  Turns the
        ~15-knob manual tune into a single click; the user can still
        fine-tune any slider afterwards.
        """
        if self.current_img_bgr is None:
            self._set_dynamic(self.status_var, "status.auto_no_image")
            return
        try:
            result = auto_params(self.current_img_bgr)
        except Exception as exc:
            self._set_dynamic(self.status_var, "status.keyer_error",
                              exc=str(exc))
            return

        self.bg_bgr = result.bg_bgr
        self._set_dynamic(self.bg_label, "bg.auto", bgr=str(self.bg_bgr))
        for name, value in result.values.items():
            var = getattr(self, name, None)
            if var is None:
                continue
            try:
                var.set(value)
            except Exception:
                pass

        self._process_current()
        self._set_dynamic(self.status_var, "status.auto_done",
                          notes=result.notes)

    def _on_canvas_click(self, event: tk.Event) -> None:
        if self.current_img_bgr is None or self._preview_scale <= 0:
            return
        x_img = int(event.x / self._preview_scale)
        y_img = int(event.y / self._preview_scale)
        h, w = self.current_img_bgr.shape[:2]
        if not (0 <= x_img < w and 0 <= y_img < h):
            return
        self.bg_bgr = sample_bgr(self.current_img_bgr, x_img, y_img)
        h_, s_, v_ = sample_hsv(self.current_img_bgr, x_img, y_img)
        self.hue.set(h_)
        self.sat_min.set(max(20, s_ - 80))
        self.val_min.set(max(20, v_ - 80))
        self._set_dynamic(self.bg_label, "bg.picked",
                          bgr=str(self.bg_bgr),
                          hsv=f"({h_},{s_},{v_})",
                          x=x_img, y=y_img)
        self._set_dynamic(self.status_var, "status.picked",
                          x=x_img, y=y_img, bgr=str(self.bg_bgr))

    # ─── canvas interaction (pick colour vs. select crops) ──────────
    def cmd_toggle_interact_mode(self) -> None:
        """Flip between colour-picking and rubber-band crop selection."""
        self.interact_mode = ("select" if self.interact_mode == "pick"
                              else "pick")
        if self.interact_mode == "pick":
            self._clear_rubber_band()
        self._refresh_mode_btn()
        key = ("status.mode_pick" if self.interact_mode == "pick"
               else "status.mode_select")
        self._set_dynamic(self.status_var, key)

    def _clear_rubber_band(self) -> None:
        if self._rubber_band is not None:
            try:
                self.canvas.delete(self._rubber_band)
            except Exception:
                pass
            self._rubber_band = None
        self._drag_start = None
        if self._rubber_band_r is not None:
            try:
                self.canvas.delete(self._rubber_band_r)
            except Exception:
                pass
            self._rubber_band_r = None
        self._rdrag_start = None

    def _on_canvas_press(self, event: tk.Event) -> None:
        if self.interact_mode == "pick":
            self._on_canvas_click(event)
            return
        # select mode: begin a rubber-band selection
        self._drag_start = (event.x, event.y)
        self._clear_rubber_band_rect_only()
        self._rubber_band = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00ff66", width=2, dash=(4, 2))

    def _clear_rubber_band_rect_only(self) -> None:
        if self._rubber_band is not None:
            try:
                self.canvas.delete(self._rubber_band)
            except Exception:
                pass
            self._rubber_band = None

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self.interact_mode != "select" or self._drag_start is None:
            return
        x0, y0 = self._drag_start
        if self._rubber_band is not None:
            self.canvas.coords(self._rubber_band, x0, y0, event.x, event.y)

    def _on_canvas_release(self, event: tk.Event) -> None:
        if self.interact_mode != "select" or self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        self._clear_rubber_band_rect_only()
        self._drag_start = None
        if self.last_result is None or self._preview_scale <= 0:
            return
        # Canvas → image coords; normalise so drag direction doesn't matter.
        ix0 = min(x0, x1) / self._preview_scale
        iy0 = min(y0, y1) / self._preview_scale
        ix1 = max(x0, x1) / self._preview_scale
        iy1 = max(y0, y1) / self._preview_scale
        rect_w = ix1 - ix0
        rect_h = iy1 - iy0
        if rect_w < 2 and rect_h < 2:
            # Bare click: select the single crop under the cursor.
            for idx, crop in enumerate(self.last_result.crops):
                bx, by, bw, bh = crop.bbox
                if bx <= ix0 <= bx + bw and by <= iy0 <= by + bh:
                    self._selected_crops.add(idx)
                    break
        else:
            # Drag: select every crop the box touches.
            sel_rect = (ix0, iy0, rect_w, rect_h)
            for idx, crop in enumerate(self.last_result.crops):
                if _rect_overlaps_bbox(sel_rect, crop.bbox):
                    self._selected_crops.add(idx)
        self._render_preview()
        self._set_dynamic(self.status_var, "status.selected",
                          n=len(self._selected_crops))

    def _on_canvas_press_right(self, event: tk.Event) -> None:
        if self.interact_mode != "select":
            return
        self._rdrag_start = (event.x, event.y)
        if self._rubber_band_r is not None:
            try:
                self.canvas.delete(self._rubber_band_r)
            except Exception:
                pass
        self._rubber_band_r = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#ff5050", width=2, dash=(4, 2))

    def _on_canvas_drag_right(self, event: tk.Event) -> None:
        if self.interact_mode != "select" or self._rdrag_start is None:
            return
        x0, y0 = self._rdrag_start
        if self._rubber_band_r is not None:
            self.canvas.coords(self._rubber_band_r, x0, y0, event.x, event.y)

    def _on_canvas_release_right(self, event: tk.Event) -> None:
        """Right button in select mode: deselect crops.

        Right-clicking a selected crop deselects just that crop.  Right-
        clicking empty space (or a non-selected crop) clears the whole
        selection.  A right-drag deselects every crop the box touches.
        """
        if self.interact_mode != "select" or self._rdrag_start is None:
            return
        x0, y0 = self._rdrag_start
        x1, y1 = event.x, event.y
        if self._rubber_band_r is not None:
            try:
                self.canvas.delete(self._rubber_band_r)
            except Exception:
                pass
            self._rubber_band_r = None
        self._rdrag_start = None
        if self.last_result is None or self._preview_scale <= 0:
            return

        ix0 = min(x0, x1) / self._preview_scale
        iy0 = min(y0, y1) / self._preview_scale
        ix1 = max(x0, x1) / self._preview_scale
        iy1 = max(y0, y1) / self._preview_scale
        rect_w = ix1 - ix0
        rect_h = iy1 - iy0

        if rect_w < 2 and rect_h < 2:
            # Bare click: deselect the crop under the cursor, else clear all.
            hit = None
            for idx in self._selected_crops:
                if 0 <= idx < len(self.last_result.crops):
                    bx, by, bw, bh = self.last_result.crops[idx].bbox
                    if bx <= ix0 <= bx + bw and by <= iy0 <= by + bh:
                        hit = idx
                        break
            if hit is not None:
                self._selected_crops.discard(hit)
            else:
                self._selected_crops.clear()
        else:
            # Drag: deselect every selected crop the box touches.
            sel_rect = (ix0, iy0, rect_w, rect_h)
            for idx, crop in enumerate(self.last_result.crops):
                if idx in self._selected_crops and _rect_overlaps_bbox(
                        sel_rect, crop.bbox):
                    self._selected_crops.discard(idx)

        self._render_preview()
        self._set_dynamic(self.status_var, "status.selected",
                          n=len(self._selected_crops))

    # ─── processing & rendering ─────────────────────────────────────
    def cmd_generate(self) -> None:
        self._process_current()
        if self._save_active_profile() and self.active_path:
            self._refresh_listbox()
            if self.current_index is not None:
                self.image_listbox.selection_clear(0, tk.END)
                self.image_listbox.selection_set(self.current_index)
                self.image_listbox.activate(self.current_index)
            display = os.path.basename(self.image_paths[self.current_index]) \
                if self.current_index is not None else self.active_path
            self._set_dynamic(self.status_var, "status.profile_saved",
                              name=display)

    # ─── manual merge commands ──────────────────────────────────────
    def cmd_merge_selected(self) -> None:
        """Record a merge rectangle over the selected crops and re-process.

        The union bbox of the selected crops becomes a persistent merge
        group on the active image, so the merge survives re-processing,
        slider tweaks and batch export.
        """
        if self.last_result is None:
            return
        if len(self._selected_crops) < 2:
            self._set_dynamic(self.status_var, "status.merge_need_two")
            return
        crops = self.last_result.crops
        boxes = [crops[i].bbox for i in self._selected_crops
                 if 0 <= i < len(crops)]
        if len(boxes) < 2:
            self._set_dynamic(self.status_var, "status.merge_need_two")
            return
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes)
        y1 = max(b[1] + b[3] for b in boxes)
        self.merge_groups.append((int(x0), int(y0), int(x1 - x0), int(y1 - y0)))
        self._selected_crops.clear()
        self._save_active_profile()
        self._process_current()
        self._set_dynamic(self.status_var, "status.merged",
                          n=len(self.merge_groups))

    def cmd_clear_merges(self) -> None:
        """Drop all manual merge groups on the active image and re-process."""
        if not self.merge_groups:
            self._set_dynamic(self.status_var, "status.merges_cleared")
            return
        self.merge_groups = []
        self._selected_crops.clear()
        self._save_active_profile()
        self._process_current()
        self._set_dynamic(self.status_var, "status.merges_cleared")

    # ─── named-preset commands ──────────────────────────────────────
    def _refresh_preset_combo(self) -> None:
        if not hasattr(self, "preset_combo"):
            return
        names = sorted(self._presets.keys())
        self.preset_combo.configure(values=names)
        if self.preset_choice.get() not in names:
            self.preset_choice.set(names[0] if names else "")

    def cmd_save_preset(self) -> None:
        """Save the current parameter set (incl. bg colour) as a named preset."""
        name = simpledialog.askstring(
            self.i18n.t("section.presets"),
            self.i18n.t("dialog.preset_name_prompt"),
            parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name:
            return
        self._presets[name] = self._snapshot_profile()
        try:
            save_presets(self._presets)
        except Exception as exc:
            self._set_dynamic(self.status_var, "status.keyer_error",
                              exc=str(exc))
            return
        self._refresh_preset_combo()
        self.preset_choice.set(name)
        self._set_dynamic(self.status_var, "status.preset_saved", name=name)

    def cmd_apply_preset_all(self) -> None:
        """Apply the selected preset to the live widgets and every image."""
        name = self.preset_choice.get().strip()
        preset = self._presets.get(name)
        if not preset:
            self._set_dynamic(self.status_var, "status.preset_none")
            return
        # Live widgets + every existing per-image profile take the preset.
        self._apply_profile(preset)
        for key in list(self._profiles.keys()):
            self._profiles[key] = dict(preset)
        if self.active_path:
            self._profiles[self.active_path] = self._snapshot_profile()
        try:
            save_profiles(self._profiles)
        except Exception:
            pass
        self._refresh_listbox()
        if self.current_index is not None:
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(self.current_index)
            self.image_listbox.activate(self.current_index)
        self._process_current()
        self._set_dynamic(self.status_var, "status.preset_applied", name=name)

    def cmd_delete_preset(self) -> None:
        name = self.preset_choice.get().strip()
        if name not in self._presets:
            self._set_dynamic(self.status_var, "status.preset_none")
            return
        del self._presets[name]
        try:
            save_presets(self._presets)
        except Exception:
            pass
        self._refresh_preset_combo()
        self._set_dynamic(self.status_var, "status.preset_deleted", name=name)

    def _process_current(self) -> None:
        if self.current_img_bgr is None:
            return
        try:
            result = process_image(self.current_img_bgr,
                                   self._process_params(),
                                   self.current_existing_alpha)
        except Exception as exc:
            self._set_dynamic(self.status_var, "status.keyer_error",
                              exc=str(exc))
            return
        self.last_result = result
        # The crop list was just regenerated, so any prior selection
        # indices no longer point at the same crops — drop them.
        self._selected_crops.clear()
        self._set_dynamic(self.result_var, "result.count",
                          n=len(result.crops),
                          be=self.bridge_erode.get())
        self._render_preview()

    def _render_preview(self) -> None:
        if self.last_result is None:
            return
        rgba = self.last_result.rgba
        h, w = rgba.shape[:2]
        bg = _checkerboard(h, w)
        alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
        fg = rgba[:, :, :3].astype(np.float32)
        blended = (fg * alpha + bg * (1 - alpha)).astype(np.uint8)

        for idx, crop in enumerate(self.last_result.crops, 1):
            x, y, ww, hh = crop.bbox
            # Selected crops (queued for merge) draw green; the rest red.
            selected = (idx - 1) in self._selected_crops
            colour = (0, 200, 0) if selected else (0, 0, 255)
            cv2.rectangle(blended, (x, y), (x + ww, y + hh), colour, 2)
            cv2.putText(blended, str(idx), (x + 4, y + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)

        cw = self.canvas.winfo_width() or PREVIEW_MAX
        ch = self.canvas.winfo_height() or PREVIEW_MAX
        cw = max(cw, 50)
        ch = max(ch, 50)
        scale = min(cw / w, ch / h, 1.0)
        if scale <= 0:
            scale = 1.0
        if scale < 1.0:
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            blended = cv2.resize(blended, (new_w, new_h),
                                 interpolation=cv2.INTER_AREA)
        self._preview_scale = scale

        rgb = cv2.cvtColor(blended, cv2.COLOR_BGR2RGB)
        self._preview_imgtk = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw",
                                 image=self._preview_imgtk)

    # ─── export commands ────────────────────────────────────────────
    def cmd_export_current(self) -> None:
        if self.last_result is None or not self.last_result.crops:
            messagebox.showinfo(self.i18n.t("dialog.export"),
                                self.i18n.t("dialog.no_icons"))
            return
        out_dir = filedialog.askdirectory(
            title=self.i18n.t("dialog.choose_out"))
        if not out_dir:
            return
        path = self.image_paths[self.current_index]
        naming = self._naming()
        written = export_crops(self.last_result.crops, out_dir, path, naming)
        imwrite_unicode(os.path.join(out_dir, "_transparent.png"),
                        self.last_result.rgba)
        self._set_dynamic(self.status_var, "status.exported",
                          n=len(written), dir=out_dir)
        messagebox.showinfo(
            self.i18n.t("dialog.export"),
            self.i18n.t("dialog.export_done", n=len(written), dir=out_dir),
        )

    def cmd_choose_out_root(self) -> None:
        folder = filedialog.askdirectory(
            title=self.i18n.t("dialog.choose_out_root"))
        if folder:
            self.batch_out_root.set(folder)

    def cmd_export_batch(self) -> None:
        if not self.image_paths:
            messagebox.showinfo(self.i18n.t("dialog.export"),
                                self.i18n.t("dialog.no_images"))
            return
        out_root = self.batch_out_root.get().strip()
        if not out_root:
            out_root = filedialog.askdirectory(
                title=self.i18n.t("dialog.choose_out_root"))
            if not out_root:
                return
            self.batch_out_root.set(out_root)

        # Flush the currently active image's widgets so the latest
        # unsaved tweaks land in its profile before we run the batch.
        self._save_active_profile()

        # Each image uses its own saved profile when it has one; images
        # without a profile fall back to the current widget state.
        fallback = self._process_params()

        def params_for(path: str) -> ProcessParams:
            key = normalise_key(path)
            profile = self._profiles.get(key)
            if profile is None:
                return fallback
            return self._params_from_profile(profile)

        naming = self._naming()

        def progress(idx: int, total: int, name: str) -> None:
            self._set_dynamic(self.status_var, "status.batch_progress",
                              i=idx, total=total, name=name)
            self.root.update_idletasks()

        result: BatchResult = batch_process(
            self.image_paths, out_root, params_for, naming, progress,
            per_image_subfolder=self.batch_subfolder.get())

        self._set_dynamic(self.status_var, "status.batch_done",
                          ok=result.ok_count, total=result.total,
                          n=result.total_crops, dir=out_root)
        summary = self.i18n.t("dialog.batch_done",
                              ok=result.ok_count, total=result.total,
                              n=result.total_crops, dir=out_root)
        failures = result.failures()
        if failures:
            detail = "\n".join(f"• {os.path.basename(f.input_path)}: {f.error}"
                               for f in failures[:8])
            summary += "\n\n" + self.i18n.t("dialog.batch_partial",
                                            fail=result.failure_count,
                                            details=detail)
        messagebox.showinfo(self.i18n.t("dialog.export"), summary)

    # ─── naming preview ─────────────────────────────────────────────
    def _refresh_naming_preview(self) -> None:
        if not hasattr(self, "naming_preview_var"):
            return
        sample_name = ("myimage"
                       if not self.image_paths
                       else image_stem(self.image_paths[
                           self.current_index or 0]))
        try:
            first, second = self._naming().preview(sample_name)
        except Exception:
            first, second = "?", "?"
        self._set_dynamic(self.naming_preview_var, "naming.preview_label",
                          first=first, second=second)


# ─── module-level helpers ───────────────────────────────────────────
def _coerce_merge_groups(raw) -> list[tuple[int, int, int, int]]:
    """Validate a stored ``merge_groups`` value into a list of int 4-tuples.

    Tolerates missing / malformed data (old profiles, hand-edited JSON):
    anything that isn't a clean ``[x, y, w, h]`` is skipped.
    """
    if not isinstance(raw, list):
        return []
    out: list[tuple[int, int, int, int]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 4:
            try:
                out.append((int(item[0]), int(item[1]),
                            int(item[2]), int(item[3])))
            except (TypeError, ValueError):
                continue
    return out


def _rect_overlaps_bbox(rect: tuple[float, float, float, float],
                        bbox: tuple[int, int, int, int]) -> bool:
    """True when selection ``rect`` (x, y, w, h) intersects crop ``bbox``."""
    rx, ry, rw, rh = rect
    bx, by, bw, bh = bbox
    return not (bx >= rx + rw or rx >= bx + bw
                or by >= ry + rh or ry >= by + bh)


def _checkerboard(h: int, w: int, tile: int = 16) -> np.ndarray:
    """Return a light-grey checkerboard image of size ``(h, w, 3)``."""
    bg = np.full((h, w, 3), 200, dtype=np.uint8)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                bg[y:y + tile, x:x + tile] = 240
    return bg.astype(np.float32)


def _make_root() -> tk.Tk:
    """Create the Tk root and enable drag-and-drop when it's safe to.

    We build a plain :class:`tk.Tk` and *then* try to load the native
    ``tkdnd`` package into it, instead of constructing
    ``TkinterDnD.Tk()`` directly.  tkinterdnd2 monkey-patches its
    drop-target methods onto every widget at import time, so a plain root
    gains full drag-and-drop the instant tkdnd loads.

    Doing it this way matters on macOS: ``TkinterDnD.Tk()`` builds the
    window first and only afterwards fails to load an incompatible tkdnd
    (e.g. a Tcl 9 binary against a Tcl 8.6 interpreter — "incompatible
    stubs mechanism").  Tearing that half-built window down can hard-crash
    fragile Tk builds.  Loading the package into a plain root instead
    never leaves a stray window and never needs a risky ``destroy()``: if
    tkdnd can't load we simply keep a normal, drag-and-drop-less window.
    """
    root = tk.Tk()
    if _HAS_DND:
        try:
            root.TkdndVersion = TkinterDnD._require(root)  # type: ignore[attr-defined]
        except Exception:
            pass
    return root


def _dnd_active(root: tk.Tk) -> bool:
    """True when the native tkdnd package loaded into ``root``."""
    return _HAS_DND and getattr(root, "TkdndVersion", None) is not None


def main() -> None:
    root = _make_root()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
