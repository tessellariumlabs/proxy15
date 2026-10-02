"""Original example artwork and printable duplex diagnostics."""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from .render import Layout, RenderOptions


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=max(8, size))


def _prepare(paths: list[Path], *, overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Example output already exists: {existing[0]}. Choose another output directory or use --overwrite.")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def _center_text(draw: ImageDraw.ImageDraw, y: float, text: str, width: int, *, size: int, fill: str) -> None:
    draw.text((width / 2, y), text, anchor="mt", font=_font(size), fill=fill)


def create_christmas_artwork(directory: Path, *, dpi: int = 300, overwrite: bool = False) -> tuple[list[Path], Path]:
    """Draw two original 5 × 7 inch designs and a shared greeting back."""
    dpi = min(300, max(72, dpi))
    width, height = 5 * dpi, 7 * dpi
    fronts = [directory / "fronts" / "01-christmas-tree.png", directory / "fronts" / "02-christmas-stars.png"]
    back = directory / "christmas-back.png"
    _prepare([*fronts, back], overwrite=overwrite)
    for index, path in enumerate(fronts):
        image = Image.new("RGB", (width, height), "#153c32" if index == 0 else "#8b2a35")
        draw = ImageDraw.Draw(image)
        border = int(dpi * 0.24)
        draw.rectangle((border, border, width - border, height - border), outline="#e4d4a5", width=max(1, dpi // 75))
        for x, y in [(0.8, 1.3), (4.2, 1.1), (0.7, 4.8), (4.1, 4.6), (1.4, 2.1), (3.7, 2.7)]:
            x, y = x * dpi, y * dpi
            radius = dpi * 0.06
            draw.line((x - radius, y, x + radius, y), fill="#e4d4a5", width=max(1, dpi // 80))
            draw.line((x, y - radius, x, y + radius), fill="#e4d4a5", width=max(1, dpi // 80))
        center = width / 2
        draw.rectangle((center - dpi * 0.14, dpi * 4.3, center + dpi * 0.14, dpi * 4.75), fill="#e4d4a5")
        for top, base, span in [(1.9, 3.2, 0.8), (2.55, 3.9, 1.1), (3.2, 4.5, 1.4)]:
            draw.polygon(((center, dpi * top), (center - dpi * span, dpi * base), (center + dpi * span, dpi * base)), fill="#e8f0df")
        star_points = []
        for point in range(10):
            angle = -math.pi / 2 + point * math.pi / 5
            radius = dpi * (0.23 if point % 2 == 0 else 0.1)
            star_points.append((center + math.cos(angle) * radius, dpi * 1.73 + math.sin(angle) * radius))
        draw.polygon(star_points, fill="#e4d4a5")
        if index:
            for x, y in [(2.2, 2.8), (2.65, 3.35), (1.95, 3.9), (3.1, 4.1)]:
                radius = dpi * 0.08
                draw.ellipse((x * dpi - radius, y * dpi - radius, x * dpi + radius, y * dpi + radius), fill="#8b2a35")
        _center_text(draw, dpi * 5.1, "Merry Christmas", width, size=int(dpi * 0.37), fill="#fff9e8")
        _center_text(draw, dpi * 5.78, "Made with love, together", width, size=int(dpi * 0.16), fill="#e4d4a5")
        image.save(path, dpi=(dpi, dpi))
        image.close()
    image = Image.new("RGB", (width, height), "#fffaf0")
    draw = ImageDraw.Draw(image)
    _center_text(draw, dpi * 1.25, "Wishing you a season", width, size=int(dpi * 0.25), fill="#153c32")
    _center_text(draw, dpi * 1.78, "of peace, joy, and togetherness.", width, size=int(dpi * 0.21), fill="#153c32")
    _center_text(draw, dpi * 3.6, "With love from", width, size=int(dpi * 0.24), fill="#153c32")
    draw.line((dpi * 1.1, dpi * 4.48, dpi * 3.9, dpi * 4.48), fill="#8b2a35", width=max(1, dpi // 100))
    _center_text(draw, dpi * 5.6, "Add your family's name or a handwritten message.", width, size=int(dpi * 0.13), fill="#153c32")
    image.save(back, dpi=(dpi, dpi))
    image.close()
    return fronts, back


def create_calibration_artwork(directory: Path, options: RenderOptions, layout: Layout, *, overwrite: bool = False) -> tuple[list[Path], list[Path]]:
    """Create one full sheet of distinct front/back slot labels at true scale."""
    dpi = min(300, max(72, options.dpi))
    width = max(1, round(layout.spread_width_in * dpi))
    height = max(1, round(layout.spread_height_in * dpi))
    fronts = [directory / "fronts" / f"{slot:03d}.png" for slot in range(1, layout.capacity + 1)]
    backs = [directory / "backs" / f"{slot:03d}.png" for slot in range(1, layout.capacity + 1)]
    _prepare([*fronts, *backs], overwrite=overwrite)
    font_scale = min(width / 5, height / 6, dpi * 0.23)
    for side, paths in [("FRONT", fronts), ("BACK", backs)]:
        for slot, path in enumerate(paths, start=1):
            image = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(image)
            inset = max(2, round(min(width, height) * 0.025))
            draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), outline="black", width=max(1, dpi // 100))
            _center_text(draw, height * 0.08, "TOP ^", width, size=round(font_scale), fill="black")
            _center_text(draw, height * 0.28, f"{side} {slot:03d}", width, size=round(font_scale), fill="black")
            _center_text(draw, height * 0.44, "Match this number on both sides", width, size=round(font_scale * 0.48), fill="black")
            # One-inch ruler, or a smaller explicitly labeled interval if the card is tiny.
            length_in = min(1.0, max(0.01, layout.spread_width_in * 0.7))
            length = length_in * dpi
            x0, y0 = (width - length) / 2, height * 0.7
            draw.line((x0, y0, x0 + length, y0), fill="black", width=max(1, dpi // 100))
            for tick in range(9):
                x = x0 + tick * length / 8
                draw.line((x, y0, x, y0 - min(height * 0.05, dpi * (0.1 if tick % 4 == 0 else 0.06))), fill="black", width=max(1, dpi // 150))
            _center_text(draw, y0 + height * 0.05, f"{length_in:g} in = {length_in * 25.4:g} mm", width, size=round(font_scale * 0.56), fill="black")
            image.save(path, dpi=(dpi, dpi))
            image.close()
    return fronts, backs


def write_calibration_instructions(directory: Path, options: RenderOptions, *, overwrite: bool = False) -> Path:
    path = directory / "calibration-instructions.txt"
    _prepare([path], overwrite=overwrite)
    path.write_text(
        "Proxy 15 duplex calibration\n\n"
        "1. Use ordinary paper for this one-sheet test. Select the PDF's exact paper size.\n"
        "2. Print the combined PDF at Actual size / 100%. Disable fit-to-page,\n"
        "   scaling, and printer headers/footers. Enable duplex and select\n"
        f"   flip on the {options.duplex_flip} edge in the printer driver.\n"
        "3. If you refeed manually, print fronts.pdf first, then backs.pdf on the\n"
        "   reverse. Feed orientation and page order depend on the printer.\n"
        "4. Measure the ruler against its printed label (1 inch is 25.4 mm).\n"
        "   A wrong length means the print dialog changed the scale.\n"
        "5. Hold the sheet to a light: each numbered front should align with the\n"
        "   same numbered back. Use TOP arrows to check each card's orientation.\n"
        "   If backs are upside down, choose the other binding edge and generate\n"
        "   a matching calibration job. If offset, adjust your printer's alignment.\n"
        "6. Confirm the driver, paper size, orientation, and margin settings before\n"
        "   printing a larger batch. Small registration offsets are common.\n\n"
        "No print job is sent by this application. You choose when and where to print.\n",
        encoding="utf-8",
    )
    return path
