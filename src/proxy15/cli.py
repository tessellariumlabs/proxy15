"""Command-line tools for local, correctly sized card PDFs."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .render import RenderOptions, create_job, plan_layout

PAPER_SIZES = {
    "Letter": (8.5, 11.0),
    "A4": (210 / 25.4, 297 / 25.4),
    "A5": (148 / 25.4, 210 / 25.4),
    "Legal": (8.5, 14.0),
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
MAX_COPIES = 10_000
MAX_CALIBRATION_SLOTS = 1_000


def collect_images(path: Path) -> list[Path]:
    """Read one image or a directory in deterministic filename order."""
    path = path.expanduser()
    if not path.exists():
        raise ValueError(f"Image path does not exist: {path}")
    if path.is_file():
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported image type: {path.name}. Use PNG, JPEG, TIFF, WebP, or BMP.")
        return [path]
    if not path.is_dir():
        raise ValueError(f"Expected an image file or directory: {path}")
    images = sorted(
        (item for item in path.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda item: item.name,
    )
    if not images:
        raise ValueError(f"No supported images found in: {path}")
    return images


def pair_images(fronts: list[Path], backs: list[Path]) -> list[Path]:
    """Pair separate artwork by unique, case-sensitive filename stems."""
    def by_stem(paths: list[Path], side: str) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for path in paths:
            if path.stem in result:
                raise ValueError(f"Duplicate {side} filename stem: {path.stem}. Each card needs a unique stem.")
            result[path.stem] = path
        return result

    front_map = by_stem(fronts, "front")
    back_map = by_stem(backs, "back")
    if front_map.keys() != back_map.keys():
        details = []
        missing = sorted(front_map.keys() - back_map.keys())
        extra = sorted(back_map.keys() - front_map.keys())
        if missing:
            details.append("missing backs for " + ", ".join(missing))
        if extra:
            details.append("backs without fronts: " + ", ".join(extra))
        raise ValueError("Front/back filename stems must match: " + "; ".join(details))
    return [back_map[path.stem] for path in fronts]


def _finite_number(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Enter a number.") from exc
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("Enter a finite number.")
    return number


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Enter a whole number.") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("Enter a whole number greater than zero.")
    return number


def add_layout_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--paper", choices=[*PAPER_SIZES, "Custom"], default="Letter", help="Paper preset (default: Letter).")
    parser.add_argument("--paper-width", type=_finite_number, help="Custom paper width, in --units.")
    parser.add_argument("--paper-height", type=_finite_number, help="Custom paper height, in --units.")
    parser.add_argument("--units", choices=["in", "mm"], default="in", help="Units for entered dimensions (default: in). Paper presets keep their real size.")
    parser.add_argument("--card-width", type=_finite_number, help="Finished card width (default: 2.5 in / 63.5 mm).")
    parser.add_argument("--card-height", type=_finite_number, help="Finished card height (default: 3.5 in / 88.9 mm).")
    parser.add_argument("--margin", type=_finite_number, help="Minimum printer margin (default: 0.25 in / 6.35 mm).")
    parser.add_argument("--gutter", type=_finite_number, help="Space between trim edges (default: 0.25 in / 6.35 mm).")
    parser.add_argument("--bleed", type=_finite_number, default=0, help="Artwork extension past trim edges (default: 0).")
    parser.add_argument("--dpi", type=_positive_int, default=300, help="Print image resolution (default: 300).")
    parser.add_argument("--flip", choices=["long", "short"], default="long", help="Match the printer's duplex binding edge (default: long).")
    parser.add_argument("--rotate", choices=["auto", "never", "always"], default="auto", help="Rotate cards on paper to improve packing (default: auto).")
    parser.add_argument("--fold", choices=["none", "vertical", "horizontal"], default="none", help="Folded card spread: vertical doubles width; horizontal doubles height.")
    parser.add_argument("--fit", choices=["contain", "cover"], default="contain", help="Contain preserves artwork; cover crops to fill (default: contain).")
    parser.add_argument("--no-marks", action="store_true", help="Omit cut and fold guides.")
    parser.add_argument("--overwrite", action="store_true", help="Replace previously generated output files.")


def options_from_args(args: argparse.Namespace) -> RenderOptions:
    scale = 1 / 25.4 if args.units == "mm" else 1.0
    if args.paper == "Custom":
        if args.paper_width is None or args.paper_height is None:
            raise ValueError("Custom paper requires both --paper-width and --paper-height.")
        paper_width, paper_height = args.paper_width * scale, args.paper_height * scale
    else:
        if args.paper_width is not None or args.paper_height is not None:
            raise ValueError("Use --paper Custom when entering --paper-width or --paper-height.")
        paper_width, paper_height = PAPER_SIZES[args.paper]
    return RenderOptions(
        page_width_in=paper_width,
        page_height_in=paper_height,
        card_width_in=2.5 if args.card_width is None else args.card_width * scale,
        card_height_in=3.5 if args.card_height is None else args.card_height * scale,
        margin_in=0.25 if args.margin is None else args.margin * scale,
        gutter_in=0.25 if args.gutter is None else args.gutter * scale,
        bleed_in=args.bleed * scale,
        dpi=args.dpi,
        duplex_flip=args.flip,
        rotate=args.rotate,
        fold=args.fold,
        fit=args.fit,
        marks=not args.no_marks,
    )


def _print_result(result: object, options: RenderOptions, *, duplex: bool) -> None:
    print(f"PDF: {result.pdf_path}")
    print(f"Layout: {result.columns} columns × {result.rows} rows; {result.sheet_count} sheet(s).")
    if duplex:
        print(f"Print at Actual size / 100%, with duplex enabled and flip on the {options.duplex_flip} edge.")
        print(f"Manual duplex files: {result.fronts_pdf_path} and {result.backs_pdf_path}")
        print("Test one sheet first; manual refeed order depends on your printer.")
    else:
        print("Print at Actual size / 100%, with duplex disabled.")
    print("Use the PDF paper size; disable fit-to-page and printer headers/footers.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proxy15",
        description="Create Christmas and family cards as locally printable PDFs.",
        epilog="Images stay on this computer. Number filenames 01, 02, … for predictable ordering.",
    )
    parser.add_argument("--version", action="version", version=f"Proxy 15 {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="Lay out your artwork for printing.")
    render.add_argument("--fronts", type=Path, required=True, help="One front image or a directory of images.")
    backs = render.add_mutually_exclusive_group()
    backs.add_argument("--backs", type=Path, help="One back image, or a directory with matching unique filename stems.")
    backs.add_argument("--common-back", type=Path, help="One image repeated behind every front.")
    render.add_argument("--copies", type=_positive_int, default=1, help="Copies of a single front image (default: 1).")
    render.add_argument("--output", type=Path, required=True, help="Directory for PDFs, previews, and job details.")
    add_layout_arguments(render)
    demo = commands.add_parser("demo", help="Make an original Christmas card demo.")
    demo.add_argument("--output", type=Path, default=Path("christmas-demo"))
    demo.add_argument("--dpi", type=_positive_int, default=300)
    demo.add_argument("--overwrite", action="store_true")
    calibration = commands.add_parser("calibrate", help="Make a labeled one-sheet duplex test with a ruler.")
    calibration.add_argument("--output", type=Path, default=Path("duplex-calibration"))
    add_layout_arguments(calibration)
    commands.add_parser("gui", help="Open the local desktop card exporter.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "gui":
            from .gui import launch
            launch()
            return 0
        if args.command == "demo":
            from .examples import create_christmas_artwork
            options = RenderOptions(page_width_in=11, page_height_in=8.5, card_width_in=5, card_height_in=7, dpi=args.dpi, rotate="never")
            plan_layout(options)
            fronts, back = create_christmas_artwork(args.output.expanduser() / "artwork", dpi=args.dpi, overwrite=args.overwrite)
            result = create_job(fronts, [back] * len(fronts), args.output.expanduser(), options, overwrite=args.overwrite)
            _print_result(result, options, duplex=True)
            print("Original example artwork is in the artwork subdirectory; edit or replace it with your family's design.")
            return 0
        options = options_from_args(args)
        if args.command == "calibrate":
            from .examples import create_calibration_artwork, write_calibration_instructions
            layout = plan_layout(options)
            if layout.capacity > MAX_CALIBRATION_SLOTS:
                raise ValueError(f"Calibration is limited to {MAX_CALIBRATION_SLOTS:,} slots per sheet. Increase the card size or use smaller paper.")
            fronts, backs = create_calibration_artwork(args.output.expanduser() / "artwork", options, layout, overwrite=args.overwrite)
            result = create_job(fronts, backs, args.output.expanduser(), options, overwrite=args.overwrite)
            write_calibration_instructions(args.output.expanduser(), options, overwrite=args.overwrite)
            _print_result(result, options, duplex=True)
            print("Print one test sheet. Follow calibration-instructions.txt and measure the ruler before printing cards.")
            return 0
        if args.copies > MAX_COPIES:
            raise ValueError(f"Copies is limited to {MAX_COPIES:,} per export. Split a larger batch into separate exports.")
        fronts = collect_images(args.fronts)
        if args.copies != 1 and not args.fronts.expanduser().is_file():
            raise ValueError("--copies is for a single front image. To repeat a directory, duplicate artwork with unique filenames.")
        backs = None
        if args.common_back is not None:
            if not args.common_back.expanduser().is_file():
                raise ValueError("--common-back must name one image file.")
            backs = collect_images(args.common_back)
        elif args.backs is not None:
            back_images = collect_images(args.backs)
            if args.fronts.expanduser().is_file() and args.backs.expanduser().is_file():
                backs = back_images
            else:
                backs = pair_images(fronts, back_images)
        if args.copies != 1:
            fronts = fronts * args.copies
            if backs is not None:
                backs = backs * args.copies
        if args.common_back is not None:
            backs = [backs[0]] * len(fronts)
        result = create_job(fronts, backs, args.output.expanduser(), options, overwrite=args.overwrite)
        _print_result(result, options, duplex=backs is not None)
        return 0
    except SystemExit as exc:
        return int(exc.code or 0)
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print(f"proxy15: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("proxy15: Export cancelled.", file=sys.stderr)
        return 130
