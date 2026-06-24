"""Simple i18n for the Chroma Tool GUI.

Three languages are supported: ``en`` (English, default), ``zh``
(Chinese), and ``ja`` (Japanese).  Widgets register themselves via
:meth:`I18n.attach` and are refreshed automatically when the active
language changes.

Usage::

    i = I18n("en")
    label = ttk.Label(root)
    i.attach(label, "text", "menu.file")
    ...
    i.set_language("ja")  # every attached widget refreshes
"""
from __future__ import annotations

from typing import Callable

TRANSLATIONS: dict[str, dict[str, str]] = {
    # Window / menu
    "app.title": {
        "zh": "Chroma Tool v2.0.1 — 抠图/切割/批处理工具",
        "en": "Chroma Tool v2.0.1 — Background remover, splitter & batch tool",
        "ja": "Chroma Tool v2.0.1 — 背景除去・分割・バッチ処理ツール",
    },
    "menu.file": {"zh": "文件", "en": "File", "ja": "ファイル"},
    "menu.open": {"zh": "添加图像…", "en": "Add Images…", "ja": "画像を追加…"},
    "menu.open_folder": {
        "zh": "添加整个文件夹…",
        "en": "Add Folder…",
        "ja": "フォルダを追加…",
    },
    "menu.export": {
        "zh": "导出当前图像…",
        "en": "Export Current…",
        "ja": "現在の画像を書き出す…",
    },
    "menu.export_all": {
        "zh": "批量导出全部…",
        "en": "Export All (Batch)…",
        "ja": "一括書き出し…",
    },
    "menu.clear_list": {
        "zh": "清空图像列表",
        "en": "Clear Image List",
        "ja": "画像リストをクリア",
    },
    "menu.exit": {"zh": "退出", "en": "Exit", "ja": "終了"},
    "menu.save_settings": {
        "zh": "立即保存设置",
        "en": "Save Settings Now",
        "ja": "設定をいま保存",
    },
    "menu.reset_settings": {
        "zh": "恢复默认设置",
        "en": "Reset to Defaults",
        "ja": "既定値に戻す",
    },
    "menu.export_config": {
        "zh": "导出参数配置…",
        "en": "Export Parameters…",
        "ja": "パラメータ設定を書き出す…",
    },
    "menu.import_config": {
        "zh": "导入参数配置…",
        "en": "Import Parameters…",
        "ja": "パラメータ設定を読み込む…",
    },
    "menu.language": {"zh": "语言", "en": "Language", "ja": "言語"},
    "menu.lang.zh": {
        "zh": "中文",
        "en": "Chinese (中文)",
        "ja": "中国語 (中文)",
    },
    "menu.lang.en": {
        "zh": "英文 (English)",
        "en": "English",
        "ja": "英語 (English)",
    },
    "menu.lang.ja": {
        "zh": "日文 (日本語)",
        "en": "Japanese (日本語)",
        "ja": "日本語",
    },

    # Status bar / prompts
    "status.welcome": {
        "zh": "请添加一张或多张图像开始(支持批量)。",
        "en": "Add one or more images to begin (batch supported).",
        "ja": "1 枚以上の画像を追加してください(バッチ対応)。",
    },
    "status.picked": {
        "zh": "在 ({x},{y}) 取色 → BGR={bgr}",
        "en": "Picked ({x},{y}) → BGR={bgr}",
        "ja": "({x},{y}) で取色 → BGR={bgr}",
    },
    "status.exported": {
        "zh": "已导出 {n} 个切割图 → {dir}",
        "en": "Exported {n} crops → {dir}",
        "ja": "{n} 個の切り出し画像を書き出しました → {dir}",
    },
    "status.batch_done": {
        "zh": "批量完成:{ok}/{total} 张成功,共写出 {n} 个切割图 → {dir}",
        "en": "Batch done: {ok}/{total} images, {n} crops total → {dir}",
        "ja": "一括処理完了:{ok}/{total} 枚成功、合計 {n} 個 → {dir}",
    },
    "status.batch_progress": {
        "zh": "处理中 [{i}/{total}]:{name}",
        "en": "Processing [{i}/{total}]: {name}",
        "ja": "処理中 [{i}/{total}]:{name}",
    },
    "status.settings_saved": {
        "zh": "设置已保存到 {path}",
        "en": "Settings saved to {path}",
        "ja": "設定を {path} に保存しました",
    },
    "status.settings_loaded": {
        "zh": "已恢复上次设置({path})",
        "en": "Loaded settings from {path}",
        "ja": "前回の設定を読み込みました({path})",
    },
    "status.settings_reset": {
        "zh": "已恢复默认设置",
        "en": "Settings reset to defaults",
        "ja": "既定値に戻しました",
    },
    "status.keyer_error": {
        "zh": "抠图错误:{exc}",
        "en": "Error in keyer: {exc}",
        "ja": "クロマキー処理エラー:{exc}",
    },
    "status.strict_error": {
        "zh": "Strict alpha 错误:{exc}",
        "en": "Strict alpha error: {exc}",
        "ja": "Strict alpha エラー:{exc}",
    },
    "status.image_error": {
        "zh": "无法读取 {path}:{exc}",
        "en": "Failed to read {path}: {exc}",
        "ja": "{path} を読み込めません:{exc}",
    },
    "status.profile_loaded": {
        "zh": "已加载 {name} 的专属配置",
        "en": "Loaded saved profile for {name}",
        "ja": "{name} の専用プロファイルを読み込みました",
    },
    "status.profile_saved": {
        "zh": "已保存 {name} 的专属配置",
        "en": "Saved profile for {name}",
        "ja": "{name} のプロファイルを保存しました",
    },
    "status.profile_new": {
        "zh": "{name}:暂无专属配置,沿用当前参数(下次「生成」后会被保存)",
        "en": "{name}: no saved profile yet — inheriting current parameters",
        "ja": "{name}:専用プロファイルなし — 現在のパラメータを引き継ぎます",
    },
    "status.dropped": {
        "zh": "已从拖拽添加 {n} 张图像。",
        "en": "Added {n} images via drag-and-drop.",
        "ja": "ドラッグ＆ドロップで {n} 枚の画像を追加しました。",
    },
    "status.config_saved": {
        "zh": "参数配置已保存到 {path}",
        "en": "Parameter config saved to {path}",
        "ja": "パラメータ設定を {path} に保存しました",
    },
    "status.config_loaded": {
        "zh": "已加载参数配置({path})",
        "en": "Loaded parameter config from {path}",
        "ja": "パラメータ設定を読み込みました({path})",
    },
    "status.config_load_error": {
        "zh": "无法加载配置:{exc}",
        "en": "Could not load config: {exc}",
        "ja": "設定を読み込めません:{exc}",
    },

    # Section headers
    "section.image_list": {
        "zh": "图像列表(批量)",
        "en": "Image list (batch)",
        "ja": "画像リスト(バッチ)",
    },
    "section.naming": {
        "zh": "命名与输出",
        "en": "Naming & output",
        "ja": "命名と出力",
    },
    "section.keying_toggle": {
        "zh": "背景处理",
        "en": "Background removal",
        "ja": "背景処理",
    },
    "section.bg_color": {
        "zh": "背景颜色",
        "en": "Background colour",
        "ja": "背景色",
    },
    "section.mask_mode": {
        "zh": "蒙版模式",
        "en": "Mask mode",
        "ja": "マスクモード",
    },
    "section.shadow": {"zh": "阴影处理", "en": "Shadow handling", "ja": "影の処理"},
    "section.splitter": {"zh": "切割模式", "en": "Splitter", "ja": "分割モード"},
    "section.grid": {"zh": "网格模式", "en": "Grid mode", "ja": "グリッドモード"},
    "section.result": {"zh": "结果", "en": "Result", "ja": "結果"},

    # Image list
    "list.empty": {
        "zh": "(列表为空)",
        "en": "(list is empty)",
        "ja": "(リストは空です)",
    },
    "btn.add_images": {
        "zh": "添加图像…",
        "en": "Add Images…",
        "ja": "画像を追加…",
    },
    "btn.add_folder": {
        "zh": "添加文件夹…",
        "en": "Add Folder…",
        "ja": "フォルダを追加…",
    },
    "btn.remove_selected": {
        "zh": "移除选中",
        "en": "Remove Selected",
        "ja": "選択を削除",
    },
    "btn.clear_list": {"zh": "清空", "en": "Clear", "ja": "クリア"},
    "btn.export_current": {
        "zh": "导出当前",
        "en": "Export Current",
        "ja": "現在のみ書き出す",
    },
    "btn.export_all": {
        "zh": "批量导出全部",
        "en": "Export All (Batch)",
        "ja": "一括書き出し",
    },

    # Naming
    "naming.prefix_label": {
        "zh": "命名前缀(留空则使用图像名)",
        "en": "Prefix (empty = use image name)",
        "ja": "プレフィックス(空欄なら画像名を使用)",
    },
    "naming.start_label": {
        "zh": "起始序号 N",
        "en": "Start index N",
        "ja": "開始番号 N",
    },
    "naming.pad_label": {
        "zh": "序号补零位数(0=不补零)",
        "en": "Zero-pad digits (0=off)",
        "ja": "ゼロ埋め桁数(0=オフ)",
    },
    "naming.preview_label": {
        "zh": "预览:{first}, {second}, …",
        "en": "Preview: {first}, {second}, …",
        "ja": "プレビュー:{first}, {second}, …",
    },
    "naming.out_root_label": {
        "zh": "输出根目录",
        "en": "Output root",
        "ja": "出力ルート",
    },
    "btn.choose_out_root": {"zh": "选择…", "en": "Choose…", "ja": "選択…"},
    "batch.subfolder": {
        "zh": "每张图单独子文件夹(取消勾选 = 全部导出到同一文件夹)",
        "en": "Per-image sub-folder (uncheck = export all into one folder)",
        "ja": "画像ごとにサブフォルダ(チェックを外す = すべて同じフォルダに書き出し)",
    },

    # Keying toggle
    "toggle.remove_bg": {
        "zh": "移除背景(取消勾选 = 只切割)",
        "en": "Remove background (uncheck = only split)",
        "ja": "背景を削除(オフ=分割のみ)",
    },

    # BG colour
    "bg.unpicked": {
        "zh": "bg:(未取色)— 请点击图像取色",
        "en": "bg: (not picked) — click image",
        "ja": "bg:(未選択)— 画像をクリックしてください",
    },
    "bg.auto": {
        "zh": "bg: BGR={bgr}(自动取自 0,0,点击图像可重选)",
        "en": "bg: BGR={bgr}  (auto-sampled from 0,0 — click image to re-pick)",
        "ja": "bg: BGR={bgr}(0,0 から自動取得 — 画像クリックで再取得)",
    },
    "bg.picked": {
        "zh": "bg: BGR={bgr} HSV={hsv}  来自 ({x},{y})",
        "en": "bg: BGR={bgr} HSV={hsv}  from ({x},{y})",
        "ja": "bg: BGR={bgr} HSV={hsv}  位置 ({x},{y})",
    },

    # Sliders
    "slider.exact_d_inner": {
        "zh": "精确模式 d_inner",
        "en": "Exact d_inner",
        "ja": "Exact d_inner",
    },
    "slider.exact_d_outer": {
        "zh": "精确模式 d_outer",
        "en": "Exact d_outer",
        "ja": "Exact d_outer",
    },
    "slider.hsv_hue": {"zh": "HSV 色相", "en": "HSV Hue", "ja": "HSV 色相"},
    "slider.hsv_hue_tol": {
        "zh": "HSV 色相容差",
        "en": "HSV Hue tol",
        "ja": "HSV 色相許容差",
    },
    "slider.hsv_sat_min": {
        "zh": "HSV 饱和度下限",
        "en": "HSV Sat min",
        "ja": "HSV 彩度下限",
    },
    "slider.hsv_val_min": {
        "zh": "HSV 明度下限",
        "en": "HSV Val min",
        "ja": "HSV 明度下限",
    },
    "slider.bg_min_area": {
        "zh": "Area: 背景最小面积",
        "en": "Area: bg min area",
        "ja": "Area: 背景最小面積",
    },
    "slider.feather": {
        "zh": "边缘羽化",
        "en": "Feather",
        "ja": "エッジのぼかし",
    },
    "slider.shadow_intensity": {
        "zh": "阴影强度",
        "en": "Shadow intensity",
        "ja": "影の強さ",
    },
    "slider.shadow_max_alpha": {
        "zh": "阴影最大透明度",
        "en": "Shadow max alpha",
        "ja": "影の最大不透明度",
    },
    "slider.anchor_area": {
        "zh": "主图标面积阈值",
        "en": "Anchor area",
        "ja": "メイン領域の閾値",
    },
    "slider.merge_distance": {
        "zh": "碎片合并距离",
        "en": "Merge distance",
        "ja": "断片マージ距離",
    },
    "slider.min_area": {
        "zh": "最小保留面积",
        "en": "Min area",
        "ja": "最小残存面積",
    },
    "slider.padding": {
        "zh": "裁切边距",
        "en": "Padding",
        "ja": "切り出しマージン",
    },
    "slider.shadow_distance": {
        "zh": "阴影归属距离",
        "en": "Shadow distance",
        "ja": "影の帰属距離",
    },
    "slider.bridge_erode": {
        "zh": "打断像素桥(erode)",
        "en": "Bridge erode",
        "ja": "ピクセル橋の切断(erode)",
    },
    "slider.strict_d_inner": {
        "zh": "Strict d_inner",
        "en": "Strict d_inner",
        "ja": "Strict d_inner",
    },
    "slider.strict_d_outer": {
        "zh": "Strict d_outer",
        "en": "Strict d_outer",
        "ja": "Strict d_outer",
    },
    "slider.cell_w": {"zh": "格子宽度", "en": "Cell W", "ja": "セル幅"},
    "slider.cell_h": {"zh": "格子高度", "en": "Cell H", "ja": "セル高さ"},

    # Mask mode radios
    "mask.exact": {
        "zh": "精确(颜色距离 — 保留阴影/同色细节)",
        "en": "Exact (colour distance — preserves shadows)",
        "ja": "Exact(色距離 — 影と同色ディテールを保持)",
    },
    "mask.area": {
        "zh": "区域(HSV + 大块背景过滤)",
        "en": "Area (HSV + bg-blob filter)",
        "ja": "Area(HSV + 大塊背景フィルタ)",
    },
    "mask.simple": {
        "zh": "简单(仅 HSV 范围)",
        "en": "Simple (HSV range only)",
        "ja": "Simple(HSV 範囲のみ)",
    },

    # Shadow radios
    "shadow.soft": {
        "zh": "柔和(半透明投影)",
        "en": "Soft (semi-transparent drop-shadow)",
        "ja": "ソフト(半透明ドロップシャドウ)",
    },
    "shadow.keep": {
        "zh": "保留原状(不透明绿影)",
        "en": "Keep original (opaque green)",
        "ja": "保持(元の不透明な影)",
    },
    "shadow.remove": {
        "zh": "移除(无阴影)",
        "en": "Remove (no shadow)",
        "ja": "削除(影なし)",
    },

    # Misc
    "check.decon": {
        "zh": "边缘去色污染",
        "en": "Decontaminate edges",
        "ja": "エッジの色被り除去",
    },
    "result.count": {
        "zh": "{n} 个 (be={be})",
        "en": "{n} crops (be={be})",
        "ja": "{n} 個 (be={be})",
    },
    "result.placeholder": {"zh": "—", "en": "—", "ja": "—"},
    "btn.generate": {
        "zh": "生成 / 重新处理",
        "en": "Generate / Re-process",
        "ja": "生成 / 再処理",
    },
    "btn.pick_color": {
        "zh": "调色板取色…",
        "en": "Pick colour…",
        "ja": "カラーピッカー…",
    },
    "hint.generate": {
        "zh": "* 修改参数后点击「生成」才会应用",
        "en": "* Adjust parameters, then click Generate to apply",
        "ja": "* パラメータを変更したら「生成」をクリックして適用してください",
    },
    "hint.batch": {
        "zh": "* 批量导出默认按图像名建子文件夹,可在左侧取消勾选以全部导出到同一文件夹",
        "en": "* Batch export uses per-image sub-folders by default; uncheck on the left to flatten into one folder",
        "ja": "* バッチ書き出しは既定で画像ごとのサブフォルダを使用します。左側のチェックを外すと1つのフォルダにまとめられます",
    },

    # Dialogs
    "dialog.error": {"zh": "错误", "en": "Error", "ja": "エラー"},
    "dialog.cant_read": {
        "zh": "无法读取文件:{path}",
        "en": "Cannot read {path}",
        "ja": "{path} を読み込めません",
    },
    "dialog.export": {"zh": "导出", "en": "Export", "ja": "エクスポート"},
    "dialog.no_icons": {
        "zh": "没有可导出的切割图。",
        "en": "No crops to export.",
        "ja": "書き出す切り出し画像がありません。",
    },
    "dialog.no_images": {
        "zh": "请先添加图像。",
        "en": "Please add at least one image first.",
        "ja": "先に画像を追加してください。",
    },
    "dialog.choose_out": {
        "zh": "选择输出文件夹",
        "en": "Choose output folder",
        "ja": "出力フォルダを選択",
    },
    "dialog.choose_out_root": {
        "zh": "选择批量输出根目录",
        "en": "Choose batch output root",
        "ja": "一括出力のルートフォルダを選択",
    },
    "dialog.export_done": {
        "zh": "已写出 {n} 个切割图到:\n{dir}",
        "en": "Wrote {n} crops to:\n{dir}",
        "ja": "{n} 個の切り出し画像を書き出しました:\n{dir}",
    },
    "dialog.batch_done": {
        "zh": "批量完成:{ok}/{total} 张图像成功,共写出 {n} 个切割图。\n根目录:{dir}",
        "en": "Batch done: {ok}/{total} images, {n} crops total.\nRoot: {dir}",
        "ja": "一括完了:{ok}/{total} 枚成功、合計 {n} 個。\nルート:{dir}",
    },
    "dialog.batch_partial": {
        "zh": "部分失败({fail} 张):\n{details}",
        "en": "Failures ({fail}):\n{details}",
        "ja": "失敗 ({fail} 件):\n{details}",
    },
    "dialog.pick_color_title": {
        "zh": "选择背景颜色",
        "en": "Choose background colour",
        "ja": "背景色を選択",
    },
    "dialog.add_folder": {
        "zh": "添加图像文件夹",
        "en": "Add image folder",
        "ja": "画像フォルダを追加",
    },
    "dialog.export_config": {
        "zh": "导出参数配置",
        "en": "Export parameter config",
        "ja": "パラメータ設定を書き出す",
    },
    "dialog.import_config": {
        "zh": "导入参数配置",
        "en": "Import parameter config",
        "ja": "パラメータ設定を読み込む",
    },
    "dialog.import_scope_prompt": {
        "zh": "如何应用此配置?",
        "en": "How should this config be applied?",
        "ja": "この設定をどのように適用しますか?",
    },
    "dialog.import_scope_current": {
        "zh": "仅当前图像(其他图像保留各自的专属配置)",
        "en": "Current image only (keep other images' profiles)",
        "ja": "現在の画像のみ(他の画像の専用設定はそのまま)",
    },
    "dialog.import_scope_missing": {
        "zh": "仅没有专属配置的图像 + 当前画像(更新回退默认)",
        "en": "Only images without a profile + current image (update fallback)",
        "ja": "専用設定が無い画像 + 現在の画像(フォールバックを更新)",
    },
    "dialog.import_scope_all": {
        "zh": "覆盖全部图像的专属配置",
        "en": "Overwrite every image's profile",
        "ja": "すべての画像の専用設定を上書き",
    },
    "dialog.ok": {"zh": "确定", "en": "OK", "ja": "OK"},
    "dialog.cancel": {"zh": "取消", "en": "Cancel", "ja": "キャンセル"},

    # File chooser
    "file.types_image": {"zh": "图像", "en": "Image", "ja": "画像"},
    "file.types_all": {
        "zh": "所有文件",
        "en": "All",
        "ja": "すべてのファイル",
    },
}

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("zh", "en", "ja")


class I18n:
    """Holds the current language and refreshes attached widgets."""

    def __init__(self, lang: str = DEFAULT_LANG) -> None:
        self.lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
        self._widgets: list[tuple[object, str, str]] = []
        self._listeners: list[Callable[[], None]] = []

    def t(self, key: str, **kwargs) -> str:
        entry = TRANSLATIONS.get(key)
        if entry is None:
            return key
        text = entry.get(self.lang) or entry.get(DEFAULT_LANG) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def attach(self, widget: object, attr: str, key: str) -> None:
        """Register a widget so it auto-updates when language changes."""
        try:
            widget.configure(**{attr: self.t(key)})  # type: ignore[attr-defined]
        except Exception:
            pass
        self._widgets.append((widget, attr, key))

    def add_listener(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def set_language(self, lang: str) -> None:
        if lang not in SUPPORTED_LANGS or lang == self.lang:
            return
        self.lang = lang
        for widget, attr, key in self._widgets:
            try:
                widget.configure(**{attr: self.t(key)})  # type: ignore[attr-defined]
            except Exception:
                pass
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass
