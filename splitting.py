"""Split a keyed image into individual sprites.

Three strategies are exposed:

``hybrid``
    Connected-component segmentation with anchor/fragment absorption and
    optional dual-mask shadow assignment.  The "strict" alpha drives icon
    identity; a "loose" alpha contributes shadows/foliage that get
    re-assigned to the nearest icon body via a distance transform.

``grid``
    Plain fixed-size cell slicing.

``contour``
    External-contour detection — useful when icons overlap lightly.

Every strategy returns a list of :class:`Crop` objects: image patch,
bounding box, and the area in pixels of the owned region.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

SplitMode = Literal["hybrid", "grid", "contour", "none"]


@dataclass(frozen=True)
class Crop:
    """One cropped sprite produced by a splitter."""

    image: np.ndarray
    bbox: tuple[int, int, int, int]  # (x, y, w, h)
    area: int


@dataclass(frozen=True)
class HybridParams:
    """Parameters for :func:`split_hybrid`."""

    anchor_area: int = 4000
    merge_distance: int = 80
    min_keep_area: int = 400
    padding: int = 4
    dilate_radius: int = 3
    shadow_max_distance: int = 60
    mask_outside: bool = True
    bridge_erode: int = 0


@dataclass(frozen=True)
class GridParams:
    """Parameters for :func:`split_grid`."""

    cell_w: int = 200
    cell_h: int = 200
    offset_x: int = 0
    offset_y: int = 0
    skip_empty: bool = True
    min_alpha_ratio: float = 0.03


@dataclass(frozen=True)
class ContourParams:
    """Parameters for :func:`split_contour`."""

    min_area: int = 1000
    padding: int = 4
    mask_outside: bool = True


# ─── shared helpers ─────────────────────────────────────────────────
def _binary_from_alpha(alpha: np.ndarray, dilate_radius: int
                       ) -> tuple[np.ndarray, np.ndarray]:
    binary = (alpha > 32).astype(np.uint8) * 255
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k3, iterations=1)
    if dilate_radius > 0:
        ksize = dilate_radius * 2 + 1
        kk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        return binary, cv2.dilate(binary, kk, iterations=1)
    return binary, binary


def _bbox_gap(a: tuple[int, int, int, int],
              b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(0, max(bx - (ax + aw), ax - (bx + bw)))
    dy = max(0, max(by - (ay + ah), ay - (by + bh)))
    return float(np.hypot(dx, dy))


def _crop_with_box(rgba: np.ndarray, mask: np.ndarray, padding: int,
                   mask_outside: bool) -> Crop | None:
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    h_img, w_img = rgba.shape[:2]
    x0 = max(0, int(xs.min()) - padding)
    y0 = max(0, int(ys.min()) - padding)
    x1 = min(w_img, int(xs.max()) + 1 + padding)
    y1 = min(h_img, int(ys.max()) + 1 + padding)
    patch = rgba[y0:y1, x0:x1].copy()
    if mask_outside:
        local = mask[y0:y1, x0:x1]
        patch[~local, 3] = 0
    return Crop(image=patch, bbox=(x0, y0, x1 - x0, y1 - y0),
                area=int(mask.sum()))


def _sort_crops_reading_order(crops: list[Crop],
                              row_height: int = 80) -> list[Crop]:
    return sorted(crops, key=lambda c: (c.bbox[1] // row_height, c.bbox[0]))


# ─── hybrid split ───────────────────────────────────────────────────
@dataclass
class _Component:
    label: int
    area: int
    bbox: tuple[int, int, int, int]
    is_anchor: bool
    absorbed_into: int | None = None


def _build_components(labels: np.ndarray, stats: np.ndarray,
                      min_keep_area: int, anchor_area: int
                      ) -> list[_Component]:
    out: list[_Component] = []
    for idx in range(1, stats.shape[0]):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < min_keep_area:
            continue
        bbox = (int(stats[idx, cv2.CC_STAT_LEFT]),
                int(stats[idx, cv2.CC_STAT_TOP]),
                int(stats[idx, cv2.CC_STAT_WIDTH]),
                int(stats[idx, cv2.CC_STAT_HEIGHT]))
        out.append(_Component(label=idx, area=area, bbox=bbox,
                              is_anchor=area >= anchor_area))
    return out


def _absorb_fragments(components: list[_Component], merge_distance: int) -> None:
    anchors = [c for c in components if c.is_anchor]
    if not anchors:
        return
    for fragment in (c for c in components if not c.is_anchor):
        nearest = min(anchors, key=lambda a: _bbox_gap(fragment.bbox, a.bbox))
        if _bbox_gap(fragment.bbox, nearest.bbox) <= merge_distance:
            fragment.absorbed_into = nearest.label


def _expand_into_shadow(loose_alpha: np.ndarray, icon_mask: np.ndarray,
                        icon_label: np.ndarray, max_distance: int) -> np.ndarray:
    if max_distance <= 0:
        return icon_label
    inverse_icons = (icon_mask == 0).astype(np.uint8) * 255
    distance, voronoi = cv2.distanceTransformWithLabels(
        inverse_icons, cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL
    )
    ys, xs = np.where(icon_mask > 0)
    seed_voronoi = voronoi[ys, xs]
    seed_label = icon_label[ys, xs]
    v_to_label: dict[int, int] = {}
    for v, l in zip(seed_voronoi.tolist(), seed_label.tolist()):
        v_to_label.setdefault(int(v), int(l))

    shadow_zone = ((loose_alpha > 32) & (icon_mask == 0)
                   & (distance <= max_distance))
    if shadow_zone.any():
        flat = voronoi[shadow_zone].astype(np.int64).ravel()
        # Vectorised lookup beats np.vectorize.
        lookup = np.zeros(int(flat.max()) + 1, dtype=np.int32)
        for v, l in v_to_label.items():
            if v < lookup.shape[0]:
                lookup[v] = l
        icon_label[shadow_zone] = lookup[flat]
    return icon_label


def split_hybrid(rgba: np.ndarray, loose_alpha: np.ndarray,
                 strict_alpha: np.ndarray | None,
                 params: HybridParams) -> list[Crop]:
    """Anchor + fragment connected-component splitter with shadow handoff."""
    base = loose_alpha if strict_alpha is None else strict_alpha
    _, dilated = _binary_from_alpha(base, params.dilate_radius)
    if params.bridge_erode > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        for_cc = cv2.erode(dilated, kernel, iterations=params.bridge_erode)
    else:
        for_cc = dilated
    num, labels, stats, _ = cv2.connectedComponentsWithStats(for_cc,
                                                              connectivity=8)
    if num <= 1:
        return []

    components = _build_components(labels, stats, params.min_keep_area,
                                   params.anchor_area)
    if not components:
        return []
    _absorb_fragments(components, params.merge_distance)

    group_for_label: dict[int, int] = {}
    group_ids: set[int] = set()
    for c in components:
        gid = c.absorbed_into if c.absorbed_into is not None else c.label
        group_for_label[c.label] = gid
        group_ids.add(gid)

    icon_mask = np.zeros_like(loose_alpha, dtype=np.uint8)
    icon_label = np.zeros_like(labels, dtype=np.int32)
    for c in components:
        gid = group_for_label[c.label]
        sel = labels == c.label
        icon_mask[sel] = 1
        icon_label[sel] = gid

    icon_label = _expand_into_shadow(loose_alpha, icon_mask, icon_label,
                                     params.shadow_max_distance)

    crops: list[Crop] = []
    for gid in group_ids:
        owned = icon_label == gid
        crop = _crop_with_box(rgba, owned, params.padding, params.mask_outside)
        if crop is not None:
            crops.append(crop)
    return _sort_crops_reading_order(crops)


# ─── grid split ─────────────────────────────────────────────────────
def split_grid(rgba: np.ndarray, alpha: np.ndarray,
               params: GridParams) -> list[Crop]:
    h_img, w_img = rgba.shape[:2]
    crops: list[Crop] = []
    y = params.offset_y
    while y + params.cell_h <= h_img:
        x = params.offset_x
        while x + params.cell_w <= w_img:
            cell = rgba[y:y + params.cell_h, x:x + params.cell_w]
            cell_alpha = cell[:, :, 3]
            visible = (cell_alpha > 16).sum()
            if not params.skip_empty or visible / cell_alpha.size >= params.min_alpha_ratio:
                crops.append(Crop(image=cell.copy(),
                                  bbox=(x, y, params.cell_w, params.cell_h),
                                  area=int(visible)))
            x += params.cell_w
        y += params.cell_h
    return crops


# ─── contour split ──────────────────────────────────────────────────
def split_contour(rgba: np.ndarray, alpha: np.ndarray,
                  params: ContourParams) -> list[Crop]:
    binary, _ = _binary_from_alpha(alpha, dilate_radius=2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    h_img, w_img = rgba.shape[:2]
    crops: list[Crop] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < params.min_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        x0 = max(0, x - params.padding)
        y0 = max(0, y - params.padding)
        x1 = min(w_img, x + w + params.padding)
        y1 = min(h_img, y + h + params.padding)
        patch = rgba[y0:y1, x0:x1].copy()
        if params.mask_outside:
            full_mask = np.zeros((h_img, w_img), dtype=np.uint8)
            cv2.drawContours(full_mask, [contour], -1, 255,
                             thickness=cv2.FILLED)
            local_mask = full_mask[y0:y1, x0:x1]
            patch[local_mask == 0, 3] = 0
        crops.append(Crop(image=patch, bbox=(x0, y0, x1 - x0, y1 - y0),
                          area=int(area)))
    return _sort_crops_reading_order(crops)
