"""Physical print regressions checked through exported jobs and the real CLI."""

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw
from pypdf import PdfReader
import pytest

from proxy15.render import RenderOptions, create_job


FRONT_COLORS = [(220, 50, 60), (40, 180, 70), (50, 70, 210), (230, 190, 40)]
BACK_COLORS = [(40, 190, 200), (220, 100, 30), (150, 50, 190), (80, 120, 50)]


def _artwork(path, color, size=(90, 150), *, marked=False):
    image = Image.new("RGB", size, color)
    if marked:
        draw = ImageDraw.Draw(image)
        width, height = size
        # The two unequal corner marks expose rotations and text-like mirroring.
        draw.rectangle((width * .05, height * .05, width * .30, height * .30), fill="white")
        draw.rectangle((width * .70, height * .70, width * .95, height * .95), fill="black")
    image.save(path)
    return path


def _pixel(image, x_in, y_in, dpi):
    return image.convert("RGB").getpixel((round(x_in * dpi), round(y_in * dpi)))


def _pdf_sheet_image(page):
    # PDFs export a complete raster sheet. Inspect that actual embedded artwork,
    # rather than relying only on metadata or a separately generated preview.
    return max(page.images, key=lambda item: item.image.width * item.image.height).image


def _run_cli(tmp_path, args):
    env = os.environ.copy()
    source = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = source + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "proxy15", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_custom_mm_and_inches_produce_the_same_exact_pdf_paper_size(tmp_path):
    source = _artwork(tmp_path / "family.png", FRONT_COLORS[0], size=(80, 120))
    boxes = []
    # Deliberately choose dimensions that do not produce integer pixels at this
    # DPI: rounded raster dimensions must not change the PDF's physical size.
    for units, divisor in (("mm", 1), ("in", 25.4)):
        output = tmp_path / units
        args = [
            "render", "--fronts", str(source), "--output", str(output),
            "--paper", "Custom", "--units", units,
            "--paper-width", str(149 / divisor),
            "--paper-height", str(223 / divisor),
            "--card-width", str(40 / divisor),
            "--card-height", str(60 / divisor),
            "--margin", str(7 / divisor), "--gutter", str(3 / divisor),
            "--dpi", "47", "--rotate", "never", "--no-marks",
        ]
        completed = _run_cli(tmp_path, args)
        assert completed.returncode == 0, completed.stderr
        page = PdfReader(output / "cards.pdf").pages[0]
        boxes.append((float(page.mediabox.width), float(page.mediabox.height)))
    expected = (149 / 25.4 * 72, 223 / 25.4 * 72)
    assert boxes[0] == pytest.approx(expected, abs=.001)
    assert boxes[1] == pytest.approx(expected, abs=.001)
    assert boxes[0] == pytest.approx(boxes[1], abs=.00001)


@pytest.mark.parametrize(
    "landscape,flip,back_order,upside_down",
    [
        (False, "short", [2, 3, 0, 1], True),
        (True, "short", [1, 0, 3, 2], False),
        (False, "long", [1, 0, 3, 2], False),
        (True, "long", [2, 3, 0, 1], True),
    ],
)
def test_duplex_pairs_and_asymmetric_artwork_match_the_physical_flip(
    tmp_path, landscape, flip, back_order, upside_down
):
    if landscape:
        paper = (6, 4)
        card = (2.5, 1.5)
        size = (150, 90)
        centers = [(1.5, 1), (4.5, 1), (1.5, 3), (4.5, 3)]
    else:
        paper = (4, 6)
        card = (1.5, 2.5)
        size = (90, 150)
        centers = [(1, 1.5), (3, 1.5), (1, 4.5), (3, 4.5)]
    fronts = [_artwork(tmp_path / f"front-{i}.png", color, size) for i, color in enumerate(FRONT_COLORS)]
    backs = [_artwork(tmp_path / f"back-{i}.png", color, size, marked=True) for i, color in enumerate(BACK_COLORS)]
    options = RenderOptions(
        page_width_in=paper[0], page_height_in=paper[1],
        card_width_in=card[0], card_height_in=card[1],
        margin_in=.25, gutter_in=.5, dpi=60,
        duplex_flip=flip, rotate="never", marks=False,
    )
    result = create_job(fronts, backs, tmp_path / "print", options)
    assert (result.columns, result.rows, result.sheet_count) == (2, 2, 1)
    pages = PdfReader(result.pdf_path).pages
    assert len(pages) == 2
    front_image, back_image = map(_pdf_sheet_image, pages)
    for index, (x, y) in enumerate(centers):
        assert _pixel(front_image, x, y, 60) == FRONT_COLORS[index]
        assert _pixel(back_image, x, y, 60) == BACK_COLORS[back_order[index]]
        # Sample inside the top-left and bottom-right corner marks. A mirror
        # would move them to the other diagonal and fails this assertion.
        top_left = (x - card[0] * .35, y - card[1] * .35)
        bottom_right = (x + card[0] * .35, y + card[1] * .35)
        assert _pixel(back_image, *top_left, 60) == ((0, 0, 0) if upside_down else (255, 255, 255))
        assert _pixel(back_image, *bottom_right, 60) == ((255, 255, 255) if upside_down else (0, 0, 0))


def test_two_sheets_interleave_front_and_back_and_supply_manual_duplex_order(tmp_path):
    front_colors = [(210, 30, 40), (30, 60, 210)]
    back_colors = [(40, 180, 80), (220, 150, 30)]
    fronts = [_artwork(tmp_path / f"front-{i}.png", color) for i, color in enumerate(front_colors)]
    backs = [_artwork(tmp_path / f"back-{i}.png", color) for i, color in enumerate(back_colors)]
    options = RenderOptions(
        page_width_in=2, page_height_in=3,
        card_width_in=1.5, card_height_in=2.5,
        margin_in=.25, gutter_in=0, dpi=40, rotate="never", marks=False,
    )
    result = create_job(fronts, backs, tmp_path / "print", options)
    assert result.sheet_count == 2
    expected_by_file = [
        (result.pdf_path, [front_colors[0], back_colors[0], front_colors[1], back_colors[1]]),
        (result.fronts_pdf_path, front_colors),
        (result.backs_pdf_path, back_colors),
        (result.pdf_path.parent / "backs-reversed.pdf", list(reversed(back_colors))),
    ]
    for pdf_path, colors in expected_by_file:
        pages = PdfReader(pdf_path).pages
        assert len(pages) == len(colors)
        assert [_pixel(_pdf_sheet_image(page), 1, 1.5, 40) for page in pages] == colors


def test_unmatched_duplex_input_fails_before_creating_any_output(tmp_path):
    front = _artwork(tmp_path / "front.png", FRONT_COLORS[0])
    back = _artwork(tmp_path / "back.png", BACK_COLORS[0])
    output = tmp_path / "print"
    with pytest.raises(ValueError, match="number of back images"):
        create_job([front, front], [back], output, RenderOptions(dpi=40))
    assert not output.exists()


def test_finished_five_by_seven_folded_card_opens_to_ten_by_seven_on_letter(tmp_path):
    outside = Image.new("RGB", (600, 420), FRONT_COLORS[0])
    ImageDraw.Draw(outside).rectangle((300, 0, 599, 419), fill=FRONT_COLORS[1])
    front = tmp_path / "outside.png"
    outside.save(front)
    inside = _artwork(tmp_path / "inside.png", BACK_COLORS[0], size=(600, 420))
    options = RenderOptions(
        page_width_in=11, page_height_in=8.5,
        card_width_in=5, card_height_in=7, fold="vertical",
        margin_in=.25, dpi=60, rotate="never", duplex_flip="short", marks=False,
    )
    result = create_job([front], [inside], tmp_path / "print", options)
    assert (result.columns, result.rows, result.sheet_count) == (1, 1, 1)
    pages = PdfReader(result.pdf_path).pages
    assert len(pages) == 2
    assert (float(pages[0].mediabox.width), float(pages[0].mediabox.height)) == (792, 612)
    image = _pdf_sheet_image(pages[0])
    # The 10×7-inch spread is centered at x=.5, y=.75, with its fold at x=5.5.
    for point in ((1, 1), (5, 7)):
        assert _pixel(image, *point, 60) == FRONT_COLORS[0]
    for point in ((6, 1), (10, 7)):
        assert _pixel(image, *point, 60) == FRONT_COLORS[1]
    for point in ((.25, 4), (10.75, 4), (5.5, .5), (5.5, 8)):
        assert _pixel(image, *point, 60) == (255, 255, 255)


def test_oversized_folded_card_is_rejected_instead_of_silently_scaled(tmp_path):
    front = _artwork(tmp_path / "outside.png", FRONT_COLORS[0])
    options = RenderOptions(
        page_width_in=11, page_height_in=8.5,
        card_width_in=6, card_height_in=7, fold="vertical",
        margin_in=.25, dpi=40, rotate="auto",
    )
    output = tmp_path / "print"
    with pytest.raises(ValueError, match="No card fits"):
        create_job([front], None, output, options)
    assert not output.exists()
