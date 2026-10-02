"""Home-printer imposition with physical sizing and matched duplex layouts.

The frozen :mod:`proxy15.core` packing helpers are reused here. This public API
adds validated inputs, exact PDF paper sizes, and physically reflected back
positions without mirroring the artwork itself.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .core import choose_orientation, compute_grid

# A 60-megapixel RGB page occupies 180 MB before encoder/source-image buffers.
# Large physical paper remains supported by selecting a lower raster DPI.
MAX_RASTER_PIXELS = 60_000_000
_EPSILON = 1e-9


@dataclass(frozen=True)
class RenderOptions:
    """Sizes are inches; card sizes describe the finished, folded card.

    Folded artwork must contain the complete unfolded spread. ``vertical``
    doubles its width; ``horizontal`` doubles its height. ``contain`` pads an
    image with white, while ``cover`` crops to fill the spread without stretching.
    """

    page_width_in: float = 8.5
    page_height_in: float = 11
    card_width_in: float = 2.5
    card_height_in: float = 3.5
    margin_in: float = 0.25
    gutter_in: float = 0.25
    bleed_in: float = 0
    dpi: int = 300
    duplex_flip: str = "long"
    fit: str = "contain"
    marks: bool = True
    rotate: str = "auto"
    fold: str = "none"


@dataclass(frozen=True)
class Layout:
    """A centered grid in inches, measured from the paper's top-left corner."""

    columns: int
    rows: int
    rotated: bool
    card_width_in: float
    card_height_in: float
    spread_width_in: float
    spread_height_in: float
    x0_in: float
    y0_in: float
    step_x_in: float
    step_y_in: float
    duplex_axis: str

    @property
    def capacity(self) -> int:
        return self.columns * self.rows


@dataclass(frozen=True)
class BuildResult:
    pdf_path: Path
    fronts_pdf_path: Path
    backs_pdf_path: Path | None
    preview_paths: list[Path]
    columns: int
    rows: int
    sheet_count: int


def _number(value: object, name: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        comparison = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be finite and {comparison}")
    return number


def _pixels(width_in: float, height_in: float, dpi: float, label: str) -> tuple[int, int]:
    width = width_in * dpi
    height = height_in * dpi
    if not math.isfinite(width) or not math.isfinite(height):
        raise ValueError(f"{label} exceeds the raster memory limit; reduce size or DPI")
    w, h = round(width), round(height)
    if w < 1 or h < 1:
        raise ValueError(f"{label} is smaller than one pixel at the selected DPI")
    if w * h > MAX_RASTER_PIXELS:
        raise ValueError(f"{label} exceeds {MAX_RASTER_PIXELS:,} pixels; reduce size or DPI")
    return w, h


def _stable_grid(options: RenderOptions, trim_margin: float, w: float, h: float):
    """Use core packing with tolerance for exact metric-to-inch boundaries."""
    result = compute_grid(
        options.page_width_in, options.page_height_in,
        trim_margin, trim_margin, trim_margin, 0, 0,
        options.gutter_in, options.gutter_in, w, h,
    )
    available_w = max(0, options.page_width_in - 2 * trim_margin)
    available_h = max(0, options.page_height_in - 2 * trim_margin)

    def count(available, size):
        ratio = (available + options.gutter_in) / (size + options.gutter_in)
        nearest = round(ratio)
        return max(0, nearest if abs(ratio - nearest) < 1e-10 else math.floor(ratio))

    columns, rows = count(available_w, w), count(available_h, h)
    if (columns, rows) == result[:2]:
        return result
    used_w = columns * w + max(0, columns - 1) * options.gutter_in
    used_h = rows * h + max(0, rows - 1) * options.gutter_in
    return (
        columns, rows,
        trim_margin + max(0, available_w - used_w) / 2,
        trim_margin + max(0, available_h - used_h) / 2,
        w + options.gutter_in, h + options.gutter_in,
    )


def plan_layout(options: RenderOptions) -> Layout:
    """Validate dimensions and select a grid, without reading or writing files."""
    for name in ("page_width_in", "page_height_in", "card_width_in", "card_height_in", "dpi"):
        _number(getattr(options, name), name, positive=True)
    for name in ("margin_in", "gutter_in", "bleed_in"):
        _number(getattr(options, name), name, positive=False)
    if not all(math.isfinite(dimension * 72) for dimension in (options.page_width_in, options.page_height_in)):
        raise ValueError("Paper dimensions exceed the finite PDF page size limit")
    for name, choices in (
        ("duplex_flip", ("long", "short")),
        ("fit", ("contain", "cover")),
        ("rotate", ("auto", "never", "always")),
        ("fold", ("none", "vertical", "horizontal")),
    ):
        if getattr(options, name) not in choices:
            raise ValueError(f"{name} must be one of: {', '.join(choices)}")
    if not isinstance(options.marks, bool):
        raise ValueError("marks must be True or False")
    if options.gutter_in + _EPSILON < 2 * options.bleed_in:
        raise ValueError("gutter_in must be at least twice bleed_in so adjacent bleeds do not overlap")
    _pixels(options.page_width_in, options.page_height_in, options.dpi, "Paper")
    spread_w = options.card_width_in * (2 if options.fold == "vertical" else 1)
    spread_h = options.card_height_in * (2 if options.fold == "horizontal" else 1)
    _pixels(spread_w + 2 * options.bleed_in, spread_h + 2 * options.bleed_in, options.dpi, "Card")
    # Margin measures the distance to printable artwork, including any bleed.
    trim_margin = options.margin_in + options.bleed_in
    mode = {"auto": "auto", "never": "no", "always": "yes"}[options.rotate]
    rotated, _, _, _ = choose_orientation(
        options.page_width_in, options.page_height_in,
        trim_margin, trim_margin, trim_margin, 0, 0,
        options.gutter_in, options.gutter_in, spread_w, spread_h, mode,
    )
    plain = _stable_grid(options, trim_margin, spread_w, spread_h)
    turned = _stable_grid(options, trim_margin, spread_h, spread_w)
    if options.rotate == "auto":
        rotated = (turned[0] * turned[1], turned[0]) > (plain[0] * plain[1], plain[0])
    card_w, card_h = (spread_h, spread_w) if rotated else (spread_w, spread_h)
    columns, rows, x0, y0, step_x, step_y = turned if rotated else plain
    if columns < 1 or rows < 1:
        raise ValueError("No card fits on this paper with the selected margins, bleed, and rotation")
    # Portrait long-edge binding reflects x. In landscape the long edge is
    # horizontal, so the physical flip reflects y instead. A square sheet uses
    # the portrait convention; check its calibration sheet on your printer.
    portrait = options.page_height_in >= options.page_width_in
    reflect_columns = (options.duplex_flip == "long") == portrait
    return Layout(
        columns, rows, rotated, card_w, card_h, spread_w, spread_h,
        x0, y0, step_x, step_y, "columns" if reflect_columns else "rows",
    )


def _input_paths(paths: Sequence[Path], label: str) -> list[Path]:
    if isinstance(paths, (str, bytes, Path)):
        raise ValueError(f"{label} must be a sequence of image paths")
    result = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"{label} image does not exist or is not a file: {path}")
        result.append(path)
    return result


def _load_image(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            if source.width * source.height > MAX_RASTER_PIXELS:
                raise ValueError(f"Image exceeds {MAX_RASTER_PIXELS:,} pixels: {path}")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            if oriented.mode == "RGBA" or "transparency" in oriented.info or oriented.mode == "LA":
                rgba = oriented.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                return background
            return oriented.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError(f"Cannot read image {path}: {error}") from error


def _artwork(path: Path, options: RenderOptions, layout: Layout, *, back: bool) -> Image.Image:
    source = _load_image(path)
    size = _pixels(layout.spread_width_in, layout.spread_height_in, options.dpi, "Card")
    if options.fit == "cover":
        fitted = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    else:
        contained = ImageOps.contain(source, size, method=Image.Resampling.LANCZOS)
        fitted = Image.new("RGB", size, "white")
        fitted.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
    if layout.rotated:
        fitted = fitted.transpose(Image.Transpose.ROTATE_90)
    if back and layout.duplex_axis == "rows":
        fitted = fitted.transpose(Image.Transpose.ROTATE_180)
    # Extend the outermost pixel colors into the bleed. Content inside the trim
    # remains intact, including text; the extension is discarded when cutting.
    pad = round(options.bleed_in * options.dpi)
    if pad:
        w, h = fitted.size
        extended = Image.new("RGB", (w + 2 * pad, h + 2 * pad), "white")
        extended.paste(fitted, (pad, pad))
        for box, dest, target in (
            ((0, 0, 1, h), (0, pad), (pad, h)),
            ((w - 1, 0, w, h), (pad + w, pad), (pad, h)),
            ((0, 0, w, 1), (pad, 0), (w, pad)),
            ((0, h - 1, w, h), (pad, pad + h), (w, pad)),
        ):
            extended.paste(fitted.crop(box).resize(target), dest)
        for x, y, color in (
            (0, 0, fitted.getpixel((0, 0))),
            (pad + w, 0, fitted.getpixel((w - 1, 0))),
            (0, pad + h, fitted.getpixel((0, h - 1))),
            (pad + w, pad + h, fitted.getpixel((w - 1, h - 1))),
        ):
            extended.paste(color, (x, y, x + pad, y + pad))
        fitted = extended
    return fitted


def _position(index: int, layout: Layout, options: RenderOptions, back: bool) -> tuple[float, float]:
    row, column = divmod(index, layout.columns)
    x = layout.x0_in + column * layout.step_x_in
    y = layout.y0_in + row * layout.step_y_in
    if back:
        if layout.duplex_axis == "columns":
            x = options.page_width_in - x - layout.card_width_in
        else:
            y = options.page_height_in - y - layout.card_height_in
    return x, y


def _mark_segments(x: float, y: float, options: RenderOptions, layout: Layout):
    """Yield short cut/fold guides strictly outside artwork and its bleed."""
    w, h, bleed = layout.card_width_in, layout.card_height_in, options.bleed_in
    gap = max(0.015, 1 / options.dpi)
    # At zero margin/gutter there is deliberately no room for marks.
    left_space = x - bleed if abs(x - layout.x0_in) < _EPSILON else options.gutter_in / 2 - bleed
    right_space = options.page_width_in - x - w - bleed if abs(x + w - (layout.x0_in + (layout.columns - 1) * layout.step_x_in + w)) < _EPSILON else options.gutter_in / 2 - bleed
    top_space = y - bleed if abs(y - layout.y0_in) < _EPSILON else options.gutter_in / 2 - bleed
    bottom_space = options.page_height_in - y - h - bleed if abs(y + h - (layout.y0_in + (layout.rows - 1) * layout.step_y_in + h)) < _EPSILON else options.gutter_in / 2 - bleed
    lengths = [min(0.18, space - gap) for space in (left_space, right_space, top_space, bottom_space)]
    left, right, top, bottom = lengths
    if left > 0:
        for yy in (y, y + h):
            yield x - bleed - gap - left, yy, x - bleed - gap, yy
    if right > 0:
        for yy in (y, y + h):
            yield x + w + bleed + gap, yy, x + w + bleed + gap + right, yy
    if top > 0:
        for xx in (x, x + w):
            yield xx, y - bleed - gap - top, xx, y - bleed - gap
    if bottom > 0:
        for xx in (x, x + w):
            yield xx, y + h + bleed + gap, xx, y + h + bleed + gap + bottom
    fold_vertical = options.fold == "vertical"
    if layout.rotated:
        fold_vertical = not fold_vertical
    if options.fold != "none":
        if fold_vertical:
            if top > 0:
                yield x + w / 2, y - bleed - gap - top, x + w / 2, y - bleed - gap
            if bottom > 0:
                yield x + w / 2, y + h + bleed + gap, x + w / 2, y + h + bleed + gap + bottom
        else:
            if left > 0:
                yield x - bleed - gap - left, y + h / 2, x - bleed - gap, y + h / 2
            if right > 0:
                yield x + w + bleed + gap, y + h / 2, x + w + bleed + gap + right, y + h / 2


def _render_sheet(paths: Sequence[Path], options: RenderOptions, layout: Layout, *, back: bool) -> Image.Image:
    page = Image.new("RGB", _pixels(options.page_width_in, options.page_height_in, options.dpi, "Paper"), "white")
    positions = []
    for index, path in enumerate(paths):
        x, y = _position(index, layout, options, back)
        artwork = _artwork(path, options, layout, back=back)
        page.paste(artwork, (round(x * options.dpi) - round(options.bleed_in * options.dpi), round(y * options.dpi) - round(options.bleed_in * options.dpi)))
        positions.append((x, y))
    if options.marks:
        draw = ImageDraw.Draw(page)
        for x, y in positions:
            for segment in _mark_segments(x, y, options, layout):
                draw.line(tuple(round(value * options.dpi) for value in segment), fill="black", width=max(1, round(options.dpi / 144)))
    return page


def _write_pdf(path: Path, pages: Sequence[Path], options: RenderOptions) -> None:
    # Set the MediaBox from inches directly. Pillow's pixel-rounded resolution
    # metadata must never determine the PDF's physical paper dimensions.
    width, height = options.page_width_in * 72, options.page_height_in * 72
    document = canvas.Canvas(str(path), pagesize=(width, height), pageCompression=1)
    document.setTitle("Proxy 15 — printable family cards")
    document.setAuthor("Proxy 15")
    for page in pages:
        with Image.open(page) as image:
            document.drawImage(ImageReader(image), 0, 0, width=width, height=height)
        document.showPage()
    document.save()


def _print_guide(options: RenderOptions, layout: Layout, sheet_count: int, duplex: bool) -> str:
    binding = "long edge" if options.duplex_flip == "long" else "short edge"
    lines = [
        "Proxy 15 — local printer guide", "",
        f"Paper: {options.page_width_in:g} × {options.page_height_in:g} inches.",
        f"Finished card: {options.card_width_in:g} × {options.card_height_in:g} inches.",
        f"Unfolded spread: {layout.spread_width_in:g} × {layout.spread_height_in:g} inches.",
        f"Grid: {layout.columns} columns × {layout.rows} rows; {sheet_count} physical sheet(s).", "",
        "Print at Actual size / 100%. Disable Fit, Shrink, borderless enlargement,",
        "multiple-pages-per-sheet and booklet modes. Match the paper size above.",
        "Use paper and cardstock supported by your printer; check its printable margins.",
        "Print one test sheet on plain paper first, then hold it to the light to check",
        "front/back registration and the size with a ruler before using cardstock.", "",
    ]
    if duplex:
        lines.extend([
            f"Automatic duplex: print cards.pdf with two-sided printing, flip on {binding}.",
            "The PDF pairs front 1/back 1, front 2/back 2, and so on.",
            "Manual duplex: print fronts.pdf first, then reload the stack following",
            "your printer's instructions and print backs.pdf. If reloading reverses",
            "the sheet order, use backs-reversed.pdf instead. Do not reverse the",
            "order again in the print dialog. Test one sheet to determine which",
            "face and edge enter your printer first; feed paths vary by printer.",
            f"Back positions reflect across {layout.duplex_axis}; artwork is never mirrored.",
        ])
        if layout.duplex_axis == "rows":
            lines.append("Back artwork is rotated 180° to match the selected physical flip.")
    else:
        lines.append("Single-sided: print cards.pdf or fronts.pdf with duplex disabled.")
    if options.fold != "none":
        lines.extend(["", f"Cut each spread, then fold on its {options.fold} center line.",
                      "The fold indicators are outside the card; do not cut through the center."])
    lines.extend(["", "Crop/fold marks are outside artwork and bleed and appear only where space permits.",
                  "Printer registration tolerances can require adjusting its duplex alignment.",
                  "Preview PNGs show the printed pages; use the PDFs for physical sizing.", ""])
    return "\n".join(lines)


def create_job(
    fronts: Sequence[Path],
    backs: Sequence[Path] | None,
    output_dir: Path,
    options: RenderOptions,
    *,
    overwrite: bool = False,
) -> BuildResult:
    """Render complete, ordered image pairs into a printable job directory.

    All inputs and collisions are checked before exporting. Existing generated
    files require ``overwrite=True``; input images are never overwritten.
    """
    layout = plan_layout(options)
    front_paths = _input_paths(fronts, "Front")
    back_paths = _input_paths(backs, "Back") if backs is not None else None
    if not front_paths:
        raise ValueError("At least one front image is required")
    if back_paths is not None and len(back_paths) != len(front_paths):
        raise ValueError("The number of back images must equal the number of front images")
    target = Path(output_dir).expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise ValueError(f"Output path is not a directory: {target}")
    sheet_count = math.ceil(len(front_paths) / layout.capacity)
    front_names = [f"preview-front-{number:03d}.png" for number in range(1, sheet_count + 1)]
    back_names = [f"preview-back-{number:03d}.png" for number in range(1, sheet_count + 1)] if back_paths is not None else []
    names = ["cards.pdf", "fronts.pdf", "layout.json", "print-guide.txt", *front_names, *back_names]
    if back_paths is not None:
        names.extend(["backs.pdf", "backs-reversed.pdf"])
    reserved = {target / name for name in (*names, "backs.pdf", "backs-reversed.pdf")}
    old_previews = set(target.glob("preview-front-*.png")) | set(target.glob("preview-back-*.png"))
    managed = reserved | old_previews
    sources = set(front_paths + (back_paths or []))
    # Resolving output symlinks also catches a generated filename pointing to
    # an input elsewhere. Atomic replacement itself never follows such links.
    if sources.intersection(path.resolve() for path in managed):
        raise ValueError("An input image collides with a generated output; choose another output directory")
    collisions = [path for path in managed if path.exists() or path.is_symlink()]
    if collisions and not overwrite:
        raise FileExistsError(f"Output already exists: {min(collisions)}; use overwrite=True to replace generated files")
    if any(path.is_dir() and not path.is_symlink() for path in collisions):
        raise ValueError("A generated output path is an existing directory")
    # Force image decoding now; a corrupt image cannot produce a partial job.
    for path in front_paths + (back_paths or []):
        image = _load_image(path)
        image.close()
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".proxy15-", dir=target) as scratch:
        staging = Path(scratch)
        front_pages, back_pages, interleaved = [], [], []
        for sheet in range(sheet_count):
            start, stop = sheet * layout.capacity, (sheet + 1) * layout.capacity
            front_page = staging / front_names[sheet]
            with _render_sheet(front_paths[start:stop], options, layout, back=False) as image:
                image.save(front_page, "PNG", dpi=(options.dpi, options.dpi))
            front_pages.append(front_page)
            interleaved.append(front_page)
            if back_paths is not None:
                back_page = staging / back_names[sheet]
                with _render_sheet(back_paths[start:stop], options, layout, back=True) as image:
                    image.save(back_page, "PNG", dpi=(options.dpi, options.dpi))
                back_pages.append(back_page)
                interleaved.append(back_page)
        _write_pdf(staging / "cards.pdf", interleaved, options)
        _write_pdf(staging / "fronts.pdf", front_pages, options)
        if back_pages:
            _write_pdf(staging / "backs.pdf", back_pages, options)
            _write_pdf(staging / "backs-reversed.pdf", list(reversed(back_pages)), options)
        metadata = {
            "format_version": 1,
            "options": asdict(options),
            "layout": asdict(layout),
            "card_count": len(front_paths),
            "sheet_count": sheet_count,
            "duplex": back_paths is not None,
            "pdf_page_size_points": [options.page_width_in * 72, options.page_height_in * 72],
            "files": names,
        }
        (staging / "layout.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        (staging / "print-guide.txt").write_text(_print_guide(options, layout, sheet_count, back_paths is not None), encoding="utf-8")
        for name in names:
            os.replace(staging / name, target / name)
        # On an explicitly overwritten job, remove stale managed back pages or
        # previews so a previous run cannot be mistaken for the new job.
        for obsolete in managed - {target / name for name in names}:
            if obsolete.exists() or obsolete.is_symlink():
                obsolete.unlink()
    preview_names = [name for pair in zip(front_names, back_names) for name in pair] if back_names else front_names
    return BuildResult(
        target / "cards.pdf", target / "fronts.pdf",
        target / "backs.pdf" if back_paths is not None else None,
        [target / name for name in preview_names], layout.columns, layout.rows, sheet_count,
    )
