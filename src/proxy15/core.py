"""Pure Pillow extraction of the frozen proxy15 imposition engine.

The functions in this module intentionally retain proxy15's packing and rendering
behavior. Interactive prompting, command parsing, and approval are lease-layer
responsibilities and do not live here.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

TRIM_W = 2.5
TRIM_H = 3.5
DEFAULT_BLEED = 0.125
CROP_LEN = 0.20

_TRI_MASK_CACHE: Dict[Tuple[str, int, int, int], Image.Image] = {}
_DIAMOND_MASK_CACHE: Dict[Tuple[int, int, int], Image.Image] = {}


def mm_to_in(mm: float) -> float:
    return mm / 25.4


PRESETS = {
    "A4": {"label": "A4 (210x297 mm)", "pw": mm_to_in(210), "ph": mm_to_in(297), "gutter": 0.25, "margin": 0.25, "gripper": 0.00},
    "Letter": {"label": "US Letter (8.5x11)", "pw": 8.5, "ph": 11.0, "gutter": 0.25, "margin": 0.25, "gripper": 0.00},
    "12x18": {"label": "12×18 digital", "pw": 12.0, "ph": 18.0, "gutter": 0.25, "margin": 0.25, "gripper": 0.25},
    "13x19": {"label": "13×19 (A3+)", "pw": 13.0, "ph": 19.0, "gutter": 0.25, "margin": 0.25, "gripper": 0.25},
    "B2": {"label": "B2 (500×707 mm)", "pw": mm_to_in(500), "ph": mm_to_in(707), "gutter": 0.25, "margin": 0.50, "gripper": 0.50},
    "19x26": {"label": "Offset half (19×26)", "pw": 19.0, "ph": 26.0, "gutter": 0.25, "margin": 0.50, "gripper": 0.50},
    "23x35": {"label": "Offset (23×35)", "pw": 23.0, "ph": 35.0, "gutter": 0.25, "margin": 0.50, "gripper": 0.50},
    "26x40": {"label": "Offset (26×40)", "pw": 26.0, "ph": 40.0, "gutter": 0.25, "margin": 0.50, "gripper": 0.50},
    "Custom": {"label": "Custom", "pw": 13.0, "ph": 19.0, "gutter": 0.25, "margin": 0.25, "gripper": 0.50},
}
ORDERED_KEYS = ["A4", "Letter", "12x18", "13x19", "B2", "19x26", "23x35", "26x40", "Custom"]


def draw_crop_ticks_perimeter(draw, xL, xR, yT, yB, gap_px, cpx, c, r, cols, rows):
    g = max(gap_px, 1)
    if c == 0:
        draw.line([xL - cpx, yT, xL - g, yT], fill="black", width=2)
        draw.line([xL - cpx, yB, xL - g, yB], fill="black", width=2)
    if c == cols - 1:
        draw.line([xR + g, yT, xR + cpx, yT], fill="black", width=2)
        draw.line([xR + g, yB, xR + cpx, yB], fill="black", width=2)
    if r == 0:
        draw.line([xL, yT - cpx, xL, yT - g], fill="black", width=2)
        draw.line([xR, yT - cpx, xR, yT - g], fill="black", width=2)
    if r == rows - 1:
        draw.line([xL, yB + g, xL, yB + cpx], fill="black", width=2)
        draw.line([xR, yB + g, xR, yB + cpx], fill="black", width=2)


def _soften_edge_band(im: Image.Image, band: int = 1, diff_threshold: float = 10.0) -> Image.Image:
    im = im.copy().convert("RGBA")
    w, h = im.size
    band = max(1, band)
    if w <= 2 * band + 2 or h <= 2 * band + 2:
        return im
    g = im.convert("L")

    def mean_abs_row(y0: int, y1: int) -> float:
        row0 = list(g.crop((0, y0, w, y0 + 1)).getdata())
        row1 = list(g.crop((0, y1, w, y1 + 1)).getdata())
        return sum(abs(a - b) for a, b in zip(row0, row1)) / max(1, len(row0))

    def mean_abs_col(x0: int, x1: int) -> float:
        col0 = list(g.crop((x0, 0, x0 + 1, h)).getdata())
        col1 = list(g.crop((x1, 0, x1 + 1, h)).getdata())
        return sum(abs(a - b) for a, b in zip(col0, col1)) / max(1, len(col0))

    if max(mean_abs_row(0, band), mean_abs_row(h - 1, h - band - 1), mean_abs_col(0, band), mean_abs_col(w - 1, w - band - 1)) < diff_threshold:
        return im
    strip_top = im.crop((0, band, w, band + 1))
    for y in range(band):
        im.paste(strip_top, (0, y))
    strip_bottom = im.crop((0, h - band - 1, w, h - band))
    for y in range(h - band, h):
        im.paste(strip_bottom, (0, y))
    strip_left = im.crop((band, 0, band + 1, h))
    for x in range(band):
        im.paste(strip_left, (x, 0))
    strip_right = im.crop((w - band - 1, 0, w - band, h))
    for x in range(w - band, w):
        im.paste(strip_right, (x, 0))
    return im


def mirror_bleed_image(im: Image.Image, pad_px: int) -> Image.Image:
    if pad_px <= 0:
        return im.convert("RGB")
    im = _soften_edge_band(im, band=1, diff_threshold=10.0).convert("RGBA")
    w, h = im.size
    pad = max(1, min(pad_px, w // 2, h // 2))
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    canvas.paste(im, (pad, pad))
    left, right = im.crop((0, 0, pad, h)), im.crop((w - pad, 0, w, h))
    top, bottom = im.crop((0, 0, w, pad)), im.crop((0, h - pad, w, h))
    canvas.paste(ImageOps.mirror(left), (0, pad))
    canvas.paste(ImageOps.mirror(right), (pad + w, pad))
    canvas.paste(ImageOps.flip(top), (pad, 0))
    canvas.paste(ImageOps.flip(bottom), (pad, pad + h))
    tl, tr = im.crop((0, 0, pad, pad)), im.crop((w - pad, 0, w, pad))
    bl, br = im.crop((0, h - pad, pad, h)), im.crop((w - pad, h - pad, w, h))
    canvas.paste(ImageOps.flip(ImageOps.mirror(tl)), (0, 0))
    canvas.paste(ImageOps.flip(ImageOps.mirror(tr)), (pad + w, 0))
    canvas.paste(ImageOps.flip(ImageOps.mirror(bl)), (0, pad + h))
    canvas.paste(ImageOps.flip(ImageOps.mirror(br)), (pad + w, pad + h))
    return canvas.convert("RGB")


def _corner_masks(W: int, H: int, pad_px: int, corner_px: int):
    inner = (pad_px, pad_px, W - pad_px, H - pad_px)
    msq = Image.new("L", (W, H), 0)
    ImageDraw.Draw(msq).rectangle(inner, fill=255)
    mrd = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mrd).rounded_rectangle(inner, radius=corner_px, fill=255)
    return ImageChops.subtract(msq, mrd), mrd, inner


def _clip_box(W: int, H: int, box):
    x1, y1, x2, y2 = box
    return max(0, x1), max(0, y1), min(W, x2), min(H, y2)


def _per_corner_boxes(W: int, H: int, pad: int, r: int):
    return {
        "tl": {"ring": (pad, pad, pad + 2 * r, pad + 2 * r), "outer": (0, 0, pad, pad)},
        "tr": {"ring": (W - pad - 2 * r, pad, W - pad, pad + 2 * r), "outer": (W - pad, 0, W, pad)},
        "bl": {"ring": (pad, H - pad - 2 * r, pad + 2 * r, H - pad), "outer": (0, H - pad, pad, H)},
        "br": {"ring": (W - pad - 2 * r, H - pad - 2 * r, W - pad, H - pad), "outer": (W - pad, H - pad, W, H)},
    }


def _noise_std_gray(img: Image.Image, mask: Optional[Image.Image]) -> float:
    stat = ImageStat.Stat(img.convert("L"), mask)
    var = stat.var[0] if isinstance(stat.var, (list, tuple)) else stat.var
    return float(math.sqrt(max(0.0, var)))


def _blur_mask(msk: Image.Image, feather_px: int) -> Image.Image:
    return msk if feather_px <= 0 else msk.filter(ImageFilter.GaussianBlur(float(feather_px)))


def _get_triangle_mask(corner: str, w: int, h: int, feather_px: int) -> Image.Image:
    key = (corner, w, h, feather_px)
    if key in _TRI_MASK_CACHE:
        return _TRI_MASK_CACHE[key]
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    points = {"tl": [(0, 0), (w, 0), (0, h)], "tr": [(w, 0), (0, 0), (w, h)], "bl": [(0, h), (w, h), (0, 0)], "br": [(w, h), (0, h), (w, 0)]}
    d.polygon(points[corner], fill=255)
    m = _blur_mask(m, feather_px)
    _TRI_MASK_CACHE[key] = m
    return m


def _get_diamond_mask(w: int, h: int, feather_px: int) -> Image.Image:
    key = (w, h, feather_px)
    if key in _DIAMOND_MASK_CACHE:
        return _DIAMOND_MASK_CACHE[key]
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon([(w // 2, 0), (w - 1, h // 2), (w // 2, h - 1), (0, h // 2)], fill=255)
    m = _blur_mask(m, feather_px)
    _DIAMOND_MASK_CACHE[key] = m
    return m


def fill_corner_wedges_black(imb: Image.Image, pad_px: int, corner_px: int) -> Image.Image:
    W, H = imb.size
    wedge_mask_inner, _, _ = _corner_masks(W, H, pad_px, corner_px)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    if wedge_mask_inner.getbbox():
        imb = Image.composite(black, imb, wedge_mask_inner)
    tri_mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(tri_mask)
    d.polygon([(0, 0), (pad_px, 0), (0, pad_px)], fill=255)
    d.polygon([(W, 0), (W - pad_px, 0), (W, pad_px)], fill=255)
    d.polygon([(0, H), (pad_px, H), (0, H - pad_px)], fill=255)
    d.polygon([(W, H), (W - pad_px, H), (W, H - pad_px)], fill=255)
    return Image.composite(black, imb, tri_mask)


def fill_corner_wedges_avg(imb: Image.Image, pad_px: int, corner_px: int, ring_scale: float = 0.12, auto_ring: bool = False, ring_scale_min: float = 0.25, ring_scale_max: float = 0.75, noise_low: float = 6.0, noise_high: float = 20.0, cross_scale: float = 0.15, auto_feather: bool = True, feather_base_px: int = 2, feather_min_px: int = 0, feather_max_px: int = 6) -> Image.Image:
    W, H = imb.size
    if pad_px <= 0 or corner_px <= 0:
        return imb
    wedge_mask_inner, mrd_outer, inner = _corner_masks(W, H, pad_px, corner_px)

    def ring_px_for(box_ring, base_scale):
        scale = base_scale
        if auto_ring:
            inset = max(1, int(corner_px * 0.25))
            inner2 = (inner[0] + inset, inner[1] + inset, inner[2] - inset, inner[3] - inset)
            probe = Image.new("L", (W, H), 0)
            ImageDraw.Draw(probe).rounded_rectangle(inner2, radius=max(0, corner_px - inset), fill=255)
            ring_probe = ImageChops.subtract(mrd_outer, probe).crop(box_ring)
            sigma = _noise_std_gray(imb.crop(box_ring), ring_probe if ring_probe.getbbox() else None)
            t = 0.0 if noise_high <= noise_low else (max(noise_low, min(noise_high, sigma)) - noise_low) / (noise_high - noise_low)
            scale = ring_scale_min + t * (ring_scale_max - ring_scale_min)
        return max(1, int(round(corner_px * max(0.05, min(1.0, scale)))))

    per_corner = {}
    for key, bb in _per_corner_boxes(W, H, pad_px, corner_px).items():
        ring_px = ring_px_for(bb["ring"], ring_scale)
        ring_box = _clip_box(W, H, _per_corner_boxes(W, H, pad_px, ring_px)[key]["ring"])
        inner2 = (inner[0] + ring_px, inner[1] + ring_px, inner[2] - ring_px, inner[3] - ring_px)
        inner_mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(inner_mask).rounded_rectangle(inner2, radius=max(0, corner_px - ring_px), fill=255)
        ring_mask = ImageChops.subtract(mrd_outer, inner_mask).crop(ring_box)
        region = imb.crop(ring_box)
        sigma = _noise_std_gray(region, ring_mask if ring_mask.getbbox() else None)
        if auto_feather:
            t = 0.0 if noise_high <= noise_low else (max(noise_low, min(noise_high, sigma)) - noise_low) / (noise_high - noise_low)
            feather_px = int(round(feather_min_px + t * (feather_max_px - feather_min_px)))
        else:
            feather_px = int(feather_base_px)
        mean = tuple(int(round(v)) for v in ImageStat.Stat(region, ring_mask if ring_mask.getbbox() else None).mean[:3])
        per_corner[key] = {"mean": mean, "ring_box": ring_box, "outer_box": _clip_box(W, H, bb["outer"]), "feather_px": max(0, feather_px)}

    for data in per_corner.values():
        rb = data["ring_box"]
        piece = wedge_mask_inner.crop(rb)
        if piece.getbbox():
            piece = _blur_mask(piece, data["feather_px"])
            region = imb.crop(rb)
            imb.paste(Image.composite(Image.new("RGB", region.size, data["mean"]), region, piece), rb[:2])
    for key, data in per_corner.items():
        ob = data["outer_box"]
        w, h = ob[2] - ob[0], ob[3] - ob[1]
        if w > 0 and h > 0:
            region = imb.crop(ob)
            imb.paste(Image.composite(Image.new("RGB", region.size, data["mean"]), region, _get_triangle_mask(key, w, h, data["feather_px"])), ob[:2])
    dpx = max(1, int(round(pad_px * max(0.1, min(1.0, cross_scale)))))
    centers = {"tl": (pad_px, pad_px), "tr": (W - pad_px, pad_px), "bl": (pad_px, H - pad_px), "br": (W - pad_px, H - pad_px)}
    for key, (cx, cy) in centers.items():
        box = _clip_box(W, H, (cx - dpx, cy - dpx, cx + dpx, cy + dpx))
        w, h = box[2] - box[0], box[3] - box[1]
        if w > 0 and h > 0:
            region = imb.crop(box)
            imb.paste(Image.composite(Image.new("RGB", region.size, per_corner[key]["mean"]), region, _get_diamond_mask(w, h, per_corner[key]["feather_px"])), box[:2])
    return imb


def _apply_corner_mode(img_rgb: Image.Image, bleed_px: int, corner_px: int, mode: str, ring_scale: float, auto_ring: bool, ring_scale_min: float, ring_scale_max: float, noise_low: float, noise_high: float, cross_scale: float, auto_feather: bool, feather_base_px: int, feather_min_px: int, feather_max_px: int) -> Image.Image:
    if bleed_px <= 0 or corner_px <= 0 or mode in ("none", "mirror"):
        return img_rgb
    if mode == "black":
        return fill_corner_wedges_black(img_rgb, bleed_px, corner_px)
    if mode == "avg":
        return fill_corner_wedges_avg(img_rgb, bleed_px, corner_px, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px)
    return img_rgb


def list_images(d: Path) -> List[str]:
    pats = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    return [str(p) for p in sorted(d.glob("*")) if p.suffix.lower() in pats]


def _fit_count(avail, gutter, card):
    if card <= 0:
        raise ValueError("card dimensions must be positive")
    if avail < card:
        return 0
    return int((avail + gutter) // (card + gutter))


def compute_grid(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gutter_x, gutter_y, card_w, card_h):
    avail_w = max(0.0, max(0.0, pw - 2 * margin_lr) - 2 * max(0.0, outer_gx))
    avail_h = max(0.0, max(0.0, ph - (margin_top + margin_bottom)) - 2 * max(0.0, outer_gy))
    gx, gy = max(0.0, gutter_x), max(0.0, gutter_y)
    cols = _fit_count(avail_w, gx, card_w)
    rows = _fit_count(avail_h, gy, card_h)
    used_w = cols * card_w + (cols - 1) * gx
    used_h = rows * card_h + (rows - 1) * gy
    x0 = margin_lr + max(0.0, outer_gx) + max(0.0, avail_w - used_w) / 2.0
    y0 = margin_top + max(0.0, outer_gy) + max(0.0, avail_h - used_h) / 2.0
    return cols, rows, x0, y0, card_w + gx, card_h + gy


def choose_orientation(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gx, gy, cw, ch, rotate_mode):
    if rotate_mode == "yes":
        cols, rows, *_ = compute_grid(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gx, gy, ch, cw)
        return True, ch, cw, (cols, rows)
    if rotate_mode == "no":
        cols, rows, *_ = compute_grid(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gx, gy, cw, ch)
        return False, cw, ch, (cols, rows)
    c1, r1, *_ = compute_grid(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gx, gy, cw, ch)
    c2, r2, *_ = compute_grid(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gx, gy, ch, cw)
    return (True, ch, cw, (c2, r2)) if c2 * r2 > c1 * r1 or (c2 * r2 == c1 * r1 and c2 > c1) else (False, cw, ch, (c1, r1))


def optimize_for_target_grid(pw, ph, gripper, grip_side, target_cols, target_rows, min_margin, min_gx, min_gy, outer_gx, outer_gy, cw, ch, rotate_mode):
    def try_rot(rot):
        cw_, ch_ = (ch, cw) if rot else (cw, ch)
        base = max(0.0, min_margin)
        mt, mb = base + (gripper if grip_side == "top" else 0.0), base + (gripper if grip_side == "bottom" else 0.0)
        avail_w, avail_h = pw - 2 * base - 2 * max(0.0, outer_gx), ph - mt - mb - 2 * max(0.0, outer_gy)
        gaps_x, gaps_y = max(0, target_cols - 1), max(0, target_rows - 1)
        if avail_w <= 0 or avail_h <= 0 or target_cols * cw_ + gaps_x * max(0.0, min_gx) > avail_w or target_rows * ch_ + gaps_y * max(0.0, min_gy) > avail_h:
            return None
        gx = max(min_gx, (avail_w - target_cols * cw_) / gaps_x if gaps_x else 0.0)
        gy = max(min_gy, (avail_h - target_rows * ch_) / gaps_y if gaps_y else 0.0)
        return rot, base, mt, mb, gx, gy, cw_, ch_
    opts = [x for rot in ((rotate_mode == "yes",) if rotate_mode in ("no", "yes") else (False, True)) if (x := try_rot(rot))]
    if not opts:
        return False, False, 0, 0, 0, 0, 0, 0, 0, 0
    rot, mlr, mt, mb, gx, gy, cw_, ch_ = max(opts, key=lambda x: (x[4] * x[5], x[0]))
    return True, rot, mlr, mt, mb, gx, gy, cw_, ch_, target_cols, target_rows


def maximize_grid_best(pw, ph, gripper, grip_side, min_margin, min_gx, min_gy, outer_gx, outer_gy, cw, ch, rotate_mode):
    def try_rot(rot):
        cw_, ch_ = (ch, cw) if rot else (cw, ch)
        base = max(0.0, min_margin)
        mt, mb = base + (gripper if grip_side == "top" else 0.0), base + (gripper if grip_side == "bottom" else 0.0)
        avail_w = max(0.0, pw - 2 * base - 2 * max(0.0, outer_gx))
        avail_h = max(0.0, ph - mt - mb - 2 * max(0.0, outer_gy))
        gx_min, gy_min = max(0.0, min_gx), max(0.0, min_gy)
        C, R = _fit_count(avail_w, gx_min, cw_), _fit_count(avail_h, gy_min, ch_)
        if C < 1 or R < 1:
            return None
        gx = max(gx_min, (avail_w - C * cw_) / max(1, C - 1) if C > 1 else 0.0)
        gy = max(gy_min, (avail_h - R * ch_) / max(1, R - 1) if R > 1 else 0.0)
        return rot, base, mt, mb, gx, gy, cw_, ch_, C, R
    opts = [x for rot in ((rotate_mode == "yes",) if rotate_mode in ("no", "yes") else (False, True)) if (x := try_rot(rot))]
    if not opts:
        return False, min_margin, min_margin, min_margin, min_gx, min_gy, cw, ch, 0, 0
    return max(opts, key=lambda x: (x[8] * x[9], x[4] * x[5]))


def draw_page_pil(img_paths: List[str], pw_in: float, ph_in: float, dpi: int, bleed_in: float, cols: int, rows: int, x0_in: float, y0_top_in: float, step_x_in: float, step_y_in: float, rotate_cards: bool, card_w_in: float, card_h_in: float, hud_text: str = "", marks: str = "crop", mark_gap: float = 0.0, corner: float = 0.125, safety: float = 0.0, use_bleed_paste: bool = False, corner_mode: str = "mirror", ring_scale: float = 0.33, auto_ring: bool = False, ring_scale_min: float = 0.25, ring_scale_max: float = 0.75, noise_low: float = 6.0, noise_high: float = 20.0, cross_scale: float = 0.6, auto_feather: bool = True, feather_base_px: int = 6, feather_min_px: int = 0, feather_max_px: int = 18) -> Image.Image:
    W, H = int(round(pw_in * dpi)), int(round(ph_in * dpi))
    page = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(page)
    bleed_px, card_w_px, card_h_px = int(round(bleed_in * dpi)), int(round(card_w_in * dpi)), int(round(card_h_in * dpi))
    step_x_px, step_y_px, x0_px, y0_px = int(round(step_x_in * dpi)), int(round(step_y_in * dpi)), int(round(x0_in * dpi)), int(round(y0_top_in * dpi))
    cpx, gap_px, idx = int(round(CROP_LEN * dpi)), int(round(mark_gap * dpi)), 0
    for r in range(rows):
        yT, yB = y0_px + r * step_y_px, y0_px + r * step_y_px + card_h_px
        for c in range(cols):
            if idx >= len(img_paths):
                break
            xL, xR = x0_px + c * step_x_px, x0_px + c * step_x_px + card_w_px
            if marks == "all":
                draw.rectangle([xL - bleed_px, yT - bleed_px, xR + bleed_px, yB + bleed_px], outline="black", width=2)
                draw.rectangle([xL, yT, xR, yB], outline="black", width=2)
            elif marks == "crop":
                draw_crop_ticks_perimeter(draw, xL, xR, yT, yB, gap_px, cpx, c, r, cols, rows)
            try:
                im = Image.open(img_paths[idx]).convert("RGB")
            except Exception:
                im = Image.new("RGB", (card_w_px, card_h_px), "gray")
            if rotate_cards:
                im = im.rotate(90, expand=True)
            if use_bleed_paste and bleed_px > 0:
                im = im.resize((card_w_px + 2 * bleed_px, card_h_px + 2 * bleed_px), Image.Resampling.LANCZOS)
                im = _apply_corner_mode(im, bleed_px, int(round(max(0.0, corner) * dpi)), corner_mode, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px)
                page.paste(im, (xL - bleed_px, yT - bleed_px))
            else:
                page.paste(im.resize((card_w_px, card_h_px), Image.Resampling.LANCZOS), (xL, yT))
            idx += 1
    if hud_text:
        try:
            draw.text((20, 20), hud_text, fill="black")
        except Exception:
            pass
    return page


def save_layout_report(pw, ph, dpi, margin_lr, margin_top, margin_bottom, cols, rows, x0, y0, step_x, step_y, cw, ch, bleed, out_png: Path, title: str, outer_gx, outer_gy):
    W, H = int(round(pw * dpi)), int(round(ph * dpi))
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, H - 1], outline="black", width=2)
    ml, mt, mb = int(round(margin_lr * dpi)), int(round(margin_top * dpi)), int(round(margin_bottom * dpi))
    d.rectangle([ml, mt, W - ml - 1, H - mb - 1], outline="black", width=1)
    ogx, ogy = int(round(outer_gx * dpi)), int(round(outer_gy * dpi))
    d.rectangle([ml + ogx, mt + ogy, W - ml - 1 - ogx, H - mb - 1 - ogy], outline="black", width=1)
    bx, x0p, y0p = int(round(bleed * dpi)), int(round(x0 * dpi)), int(round(y0 * dpi))
    cwp, chp, sxp, syp = int(round(cw * dpi)), int(round(ch * dpi)), int(round(step_x * dpi)), int(round(step_y * dpi))
    for r in range(rows):
        for c in range(cols):
            x, y = x0p + c * sxp, y0p + r * syp
            d.rectangle([x - bx, y - bx, x + cwp + bx, y + chp + bx], outline="black", width=1)
            d.rectangle([x, y, x + cwp, y + chp], outline="black", width=2)
    d.text((20, 20), f"{title} | {cols}×{rows} | card {cw:.3f}×{ch:.3f}in | bleed {bleed:.3f}in | step {step_x:.3f},{step_y:.3f}in | outer {outer_gx:.3f},{outer_gy:.3f}in", fill="black")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, "PNG")


def render_pages_pil(fronts, backs, pw, ph, dpi, bleed, outer_gx, outer_gy, gx, gy, margin_lr, margin_top, margin_bottom, rotate_cards, cw, ch, name, marks, mark_gap, corner, safety, use_bleed_paste, corner_mode, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px):
    """Render every front and back sheet with the same inputs used by PDF output."""
    cols, rows, x0, y0, step_x, step_y = compute_grid(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gx, gy, cw, ch)
    per_page = cols * rows

    def render_side(label, paths):
        rendered = []
        total_pages = (len(paths) + per_page - 1) // per_page
        for page_index in range(total_pages):
            page = draw_page_pil(paths[page_index * per_page:(page_index + 1) * per_page], pw, ph, dpi, bleed, cols, rows, x0, y0, step_x, step_y, rotate_cards, cw, ch, f"{name}  {label} p{page_index + 1}/{total_pages}", marks, mark_gap, corner, safety, use_bleed_paste, corner_mode, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px)
            rendered.append((label, page_index + 1, total_pages, page))
        return rendered

    front_pages = render_side("F", fronts)
    back_pages = render_side("B", backs or [])
    pages = []
    for page_index in range(max(len(front_pages), len(back_pages))):
        if page_index < len(front_pages):
            pages.append(front_pages[page_index])
        if page_index < len(back_pages):
            pages.append(back_pages[page_index])
    if not pages:
        raise ValueError("No pages generated")
    return pages


def paginate_pil(fronts, backs, out_path: Path, pw, ph, dpi, bleed, outer_gx, outer_gy, gx, gy, margin_lr, margin_top, margin_bottom, rotate_cards, cw, ch, name, marks, mark_gap, corner, safety, use_bleed_paste, corner_mode, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px):
    rendered = render_pages_pil(fronts, backs, pw, ph, dpi, bleed, outer_gx, outer_gy, gx, gy, margin_lr, margin_top, margin_bottom, rotate_cards, cw, ch, name, marks, mark_gap, corner, safety, use_bleed_paste, corner_mode, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px)
    pages = [page for _, _, _, page in rendered]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(out_path, "PDF", resolution=dpi, save_all=True, append_images=pages[1:])


def save_preview(fronts, pw, ph, dpi, bleed, outer_gx, outer_gy, gx, gy, margin_lr, margin_top, margin_bottom, rotate_cards, cw, ch, name, out_png: Path, corner, marks, mark_gap, use_bleed_paste, corner_mode, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px):
    cols, rows, x0, y0, step_x, step_y = compute_grid(pw, ph, margin_lr, margin_top, margin_bottom, outer_gx, outer_gy, gx, gy, cw, ch)
    page = draw_page_pil(fronts[:cols * rows] if fronts else [], pw, ph, dpi, bleed, cols, rows, x0, y0, step_x, step_y, rotate_cards, cw, ch, f"{name} PREVIEW", marks, mark_gap, corner, 0.0, use_bleed_paste, corner_mode, ring_scale, auto_ring, ring_scale_min, ring_scale_max, noise_low, noise_high, cross_scale, auto_feather, feather_base_px, feather_min_px, feather_max_px)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    page.save(out_png, "PNG")


def parse_grid_str(s: str) -> Tuple[int, int]:
    s = s.strip().lower()
    if s in ("best", "max", "auto"):
        return -1, -1
    parts = s.replace("x", "×").split("×")
    if len(parts) != 2:
        raise ValueError("Format CxR, e.g. 3x3 or 'best'")
    c, r = int(parts[0]), int(parts[1])
    if c < 1 or r < 1:
        raise ValueError("CxR must be >=1")
    return c, r


def selftest() -> None:
    cols, rows, *_ = compute_grid(mm_to_in(210), mm_to_in(297), 0.25, 0.25, 0.25, 0.10, 0.10, 0.25, 0.25, TRIM_W, TRIM_H)
    assert cols >= 2 and rows >= 2
    print("Self-test OK.")
