"""Single source of truth for the README "headline features" list.

Why this file exists
--------------------
The three READMEs (English / Chinese / Japanese) each carry a "headline
features" list that used to be maintained by hand — and had already
drifted out of sync between languages.  This module is the *one* place
that list lives now.  ``scripts/sync_readme.py`` renders it into every
README between the ``<!-- FEATURES:START -->`` / ``<!-- FEATURES:END -->``
markers, so adding a feature is a one-line edit here in three languages
and never touches the README prose by hand again.

Conventions
-----------
* **No version numbers.**  This list describes what the tool does *now*,
  not a changelog.  When a capability is removed, delete its entry.
* Each entry is ``{"en": ..., "zh": ..., "ja": ...}``; all three keys are
  required.  The leading ``**bold lead-in.**`` is part of the text so the
  renderer stays trivial (it just numbers the lines).
* Keep the three languages saying the *same thing* — when you add a
  feature, write all three at once.

stdlib-only on purpose: the sync script must run in CI without any
third-party imports.
"""
from __future__ import annotations

FEATURES: list[dict[str, str]] = [
    {
        "en": "**One-click Auto.** Detects the background colour from the "
              "image border, derives every keying/splitting parameter from "
              "the colour-distance histogram and connected-component "
              "statistics, and fills in all the sliders — turning a ~15-knob "
              "manual tune into a single click.  You can still fine-tune "
              "afterwards (GUI button, or `--auto` on the CLI).",
        "zh": "**一键自动。** 从图像边框检测背景色,再用颜色距离直方图和连通域"
              "统计推导出全部抠图/切割参数并填好所有滑块——把十几个旋钮的手动"
              "调参收成一次点击,之后仍可手动微调(GUI 按钮,或 CLI 的 "
              "`--auto`)。",
        "ja": "**ワンクリック自動。** 画像の枠から背景色を検出し、色距離"
              "ヒストグラムと連結成分統計から全キーイング/分割パラメータを"
              "導出して全スライダーを埋めます。約 15 個の手動調整をワン"
              "クリックに集約し、後から微調整も可能です(GUI ボタン、または"
              " CLI の `--auto`)。",
    },
    {
        "en": "**Batch processing.** Add dozens of images to the GUI (or "
              "pass a folder to the CLI), tune the parameters on one preview "
              "image, then export them all with the same config in one click.",
        "zh": "**批量处理。** 在 GUI 里加入几十张图,在一张预览图上调好参数,"
              "然后一键用同一套参数导出所有图(CLI 可直接传文件夹)。",
        "ja": "**バッチ処理。** GUI に画像を何十枚もまとめて投入(または CLI "
              "でフォルダを渡す)し、プレビュー画像 1 枚でパラメータを"
              "追い込み、ワンクリックで全画像を同じ設定で書き出せます。",
    },
    {
        "en": "**Per-image profiles.** Switching images in the list loads "
              "that image's own saved parameters.  The key is the absolute "
              "path, so the same image in a different location is a separate "
              "profile.  Profiles persist between sessions.",
        "zh": "**每张图独立配置档案。** 在列表里切换图片会自动载入该图保存过的"
              "参数。键是**绝对路径**,所以同一张图放在不同位置算不同档案。"
              "档案在多次启动间保留。",
        "ja": "**画像ごとの専用プロファイル。** リストで画像を切り替えると、"
              "その画像専用に保存されたパラメータが自動で読み込まれます。"
              "キーは**絶対パス**なので、同じ画像でも別の場所に置けば別の"
              "プロファイルになります。終了後も保存されます。",
    },
    {
        "en": "**Custom naming.** Pick a prefix, a starting index, and the "
              "number of zero-pad digits.  A blank prefix uses the input "
              "image's stem with a running `_N` suffix: `myimage_1.png`, "
              "`myimage_2.png`, ….",
        "zh": "**自定义命名。** 可设置前缀、起始序号、补零位数。前缀留空时默认"
              "使用输入文件名,序号格式如 `myimage_1.png`、`myimage_2.png` "
              "……",
        "ja": "**自由な命名規則。** プレフィックス、開始番号、ゼロ埋め桁数を"
              "指定可能。プレフィックスが空ならファイル名の語幹を使用し、"
              "`myimage_1.png`, `myimage_2.png` … のような連番を生成します。",
    },
    {
        "en": "**Per-image output folders.** Each input image's crops land "
              "in a sub-folder named after the input image — no name "
              "collisions when batching.",
        "zh": "**每张图独立子文件夹。** 批量导出时,每张输入图的切割结果会被"
              "放进以该图文件名命名的子目录,杜绝同名文件互相覆盖。",
        "ja": "**画像ごとの出力サブフォルダ。** 各入力画像の切り出し結果は"
              "その画像名のサブフォルダに分けられ、ファイル名の衝突を"
              "回避します。",
    },
    {
        "en": "**Shadow-preserving keying.** A dual-alpha pipeline reassigns "
              "shadow pixels to the nearest icon body via OpenCV's distance "
              "transform, so drop-shadows stay attached to their parent "
              "sprite instead of being eaten by the chroma mask.",
        "zh": "**阴影保留的抠图算法。** 内部维护“严格”和“宽松”两套 alpha,"
              "通过 OpenCV 的距离变换把阴影像素归属给最近的图标主体,"
              "避免阴影被一刀切掉或飘到隔壁图标头上。",
        "ja": "**影を保持するキーイング。** 二重アルファパイプラインと OpenCV "
              "の距離変換により、影ピクセルを最も近いスプライト本体に"
              "自動で割り当てます。隣のスプライトに影が漏れたり、影が"
              "刈り取られたりしません。",
    },
    {
        "en": "**Soft drop-shadow re-projection.** Shadow pixels can be "
              "converted from opaque background-colour to semi-transparent "
              "black so they look natural on any new composite.",
        "zh": "**软投影重投。** 阴影像素可以从“不透明背景色”转换为“半透明"
              "黑色”,在合成到任何新背景上时都能形成自然的投影。",
        "ja": "**ソフトドロップシャドウへの再投影。** 背景色の不透明な影を"
              "半透明の黒(または任意の色)に変換し、どんな新しい背景に"
              "合成しても自然に馴染むようにできます。",
    },
    {
        "en": "**Three split strategies.** Hybrid (connected components + "
              "anchor/fragment merging), fixed grid, or external contour.",
        "zh": "**三种切割策略:** hybrid(连通域 + 主图标吸收碎片)、"
              "grid(固定网格)、contour(外轮廓)。",
        "ja": "**3 つの分割戦略。** hybrid(連結成分 + アンカー/断片マージ)、"
              "grid(固定セル)、contour(外輪郭)。",
    },
    {
        "en": "**Three keying modes.** Exact (BGR distance), area (HSV + "
              "large connected blob), simple (pure HSV range).",
        "zh": "**三种抠图模式:** exact(BGR 距离)、area(HSV + 大块连通域)、"
              "simple(纯 HSV 范围)。",
        "ja": "**3 つのキーイングモード。** exact(BGR 距離)、area(HSV + "
              "大塊連結成分)、simple(純粋 HSV 範囲)。",
    },
    {
        "en": "**No `_preview.png` clutter.** Preview rendering is GUI-only; "
              "the export folder contains only your crops (plus an optional "
              "`_transparent.png` in single-image mode).",
        "zh": "**不再生成 `_preview.png`。** 预览只在 GUI 画布中显示,输出目录"
              "只包含真正的切割图(单图导出时可选额外生成 `_transparent.png`)。",
        "ja": "**`_preview.png` は出力しません。** プレビュー描画は GUI 内のみ"
              "で行われ、出力フォルダには切り出し画像のみが保存されます"
              "(シングル画像書き出し時にオプションで `_transparent.png` を"
              "含む)。",
    },
    {
        "en": "**Trilingual GUI** — English (default), Chinese and Japanese, "
              "switchable at runtime.",
        "zh": "**中英日三语界面**,运行时可切换,默认英文。",
        "ja": "**3 言語 GUI** — 英語(デフォルト)、中国語、日本語。実行時に"
              "切り替え可能。",
    },
    {
        "en": "**Persistent settings.** Every slider and choice survives "
              "between launches, stored as JSON in "
              "`%APPDATA%\\ChromaTool\\settings.json` (or "
              "`~/.config/chromatool/settings.json` on Linux/macOS).",
        "zh": "**设置自动持久化**,以 JSON 形式保存到 "
              "`%APPDATA%\\ChromaTool\\settings.json` (Windows) 或 "
              "`~/.config/chromatool/settings.json` (Linux/macOS)。",
        "ja": "**設定の永続化。** すべてのスライダーと選択肢が起動間で"
              "復元され、`%APPDATA%\\ChromaTool\\settings.json`(Linux/macOS "
              "は `~/.config/chromatool/settings.json`)に JSON で保存されます。",
    },
]

LANGS: tuple[str, ...] = ("en", "zh", "ja")

__all__ = ["FEATURES", "LANGS"]
