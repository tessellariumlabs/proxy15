import json
from dataclasses import replace

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from proxy15.render import RenderOptions, create_job, plan_layout


def image_file(tmp_path, name="front.png", color="red", size=(40, 40)):
    path = tmp_path / name
    Image.new("RGB", size, color).save(path)
    return path


def small_options(**changes):
    options = RenderOptions(
        page_width_in=3, page_height_in=4,
        card_width_in=2, card_height_in=3,
        margin_in=0.25, gutter_in=0.25,
        dpi=40, marks=False, rotate="never",
    )
    return replace(options, **changes)


@pytest.mark.parametrize("field", [
    "page_width_in", "page_height_in", "card_width_in", "card_height_in", "dpi",
])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), "3", True])
def test_dimensions_reject_invalid_values(field, value):
    with pytest.raises(ValueError, match=field):
        plan_layout(replace(RenderOptions(), **{field: value}))


@pytest.mark.parametrize("field", ["margin_in", "gutter_in", "bleed_in"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_spacing_rejects_invalid_values(field, value):
    with pytest.raises(ValueError, match=field):
        plan_layout(replace(RenderOptions(), **{field: value}))


def test_tiny_raster_and_huge_memory_requests_are_rejected():
    with pytest.raises(ValueError, match="one pixel"):
        plan_layout(replace(RenderOptions(), dpi=0.00001))
    with pytest.raises(ValueError, match="pixels"):
        plan_layout(replace(RenderOptions(), dpi=100000))


def test_bleed_needs_sufficient_space_and_paper_fit():
    with pytest.raises(ValueError, match="twice"):
        plan_layout(small_options(bleed_in=0.2, gutter_in=0.25))
    with pytest.raises(ValueError, match="No card fits"):
        plan_layout(small_options(page_width_in=2, page_height_in=3, margin_in=0, bleed_in=0.1))


def test_fold_finished_size_and_exact_metric_fit():
    options = RenderOptions(
        page_width_in=210 / 25.4, page_height_in=148 / 25.4,
        card_width_in=105 / 25.4, card_height_in=148 / 25.4,
        fold="vertical", margin_in=0, gutter_in=0, rotate="never",
    )
    layout = plan_layout(options)
    assert (layout.columns, layout.rows) == (1, 1)
    assert layout.spread_width_in == options.page_width_in
    assert layout.spread_height_in == options.page_height_in


def test_exact_grid_boundary_with_decimal_gutter():
    layout = plan_layout(small_options(
        page_width_in=6.2, page_height_in=2,
        card_width_in=2, card_height_in=2,
        margin_in=0, gutter_in=0.1,
    ))
    assert (layout.columns, layout.rows) == (3, 1)


def test_pdf_physical_size_ignores_pixel_rounding(tmp_path):
    path = image_file(tmp_path)
    options = small_options(page_width_in=3.013, page_height_in=4.017, dpi=37)
    result = create_job([path], None, tmp_path / "job", options)
    reader = PdfReader(result.pdf_path)
    assert len(reader.pages) == 1
    assert float(reader.pages[0].mediabox.width) == pytest.approx(3.013 * 72, abs=1e-5)
    assert float(reader.pages[0].mediabox.height) == pytest.approx(4.017 * 72, abs=1e-5)
    assert result.backs_pdf_path is None


@pytest.mark.parametrize("fit", ["contain", "cover"])
def test_aspect_ratio_fit_never_stretches(tmp_path, fit):
    path = image_file(tmp_path, size=(80, 40))
    options = small_options(card_width_in=2, card_height_in=2, fit=fit)
    result = create_job([path], None, tmp_path / "job", options)
    layout = plan_layout(options)
    with Image.open(result.preview_paths[0]) as page:
        x, y = round(layout.x0_in * options.dpi), round(layout.y0_in * options.dpi)
        assert page.getpixel((x + 40, y + 40)) == (255, 0, 0)
        expected = (255, 255, 255) if fit == "contain" else (255, 0, 0)
        assert page.getpixel((x + 40, y + 5)) == expected


def test_transparency_is_flattened_on_white(tmp_path):
    path = tmp_path / "transparent.png"
    Image.new("RGBA", (20, 30), (255, 0, 0, 128)).save(path)
    options = small_options()
    result = create_job([path], None, tmp_path / "job", options)
    with Image.open(result.preview_paths[0]) as page:
        assert page.getpixel((60, 80)) == (255, 127, 127)
    with Image.open(path) as source:
        assert source.mode == "RGBA"
        assert source.getpixel((0, 0)) == (255, 0, 0, 128)


def test_exif_orientation_is_applied_before_fitting(tmp_path):
    path = tmp_path / "phone.jpg"
    source = Image.new("RGB", (80, 40), "blue")
    ImageDraw.Draw(source).rectangle((0, 0, 39, 39), fill="red")
    exif = Image.Exif()
    exif[274] = 6  # 90° clockwise: the red left half becomes the top half.
    source.save(path, exif=exif, quality=100, subsampling=0)
    options = small_options(card_width_in=1, card_height_in=2)
    result = create_job([path], None, tmp_path / "job", options)
    layout = plan_layout(options)
    with Image.open(result.preview_paths[0]) as page:
        x = round((layout.x0_in + 0.5) * options.dpi)
        top = page.getpixel((x, round((layout.y0_in + 0.25) * options.dpi)))
        bottom = page.getpixel((x, round((layout.y0_in + 1.75) * options.dpi)))
    assert top[0] > 240 and top[2] < 10
    assert bottom[2] > 240 and bottom[0] < 10


def test_corrupt_image_fails_before_output_directory_exists(tmp_path):
    good = image_file(tmp_path)
    broken = tmp_path / "broken.png"
    broken.write_text("this is not a picture")
    target = tmp_path / "job"
    with pytest.raises(ValueError, match="Cannot read image"):
        create_job([good, broken], None, target, small_options())
    assert not target.exists()


def test_unequal_back_counts_fail_before_export(tmp_path):
    path = image_file(tmp_path)
    with pytest.raises(ValueError, match="number of back"):
        create_job([path], [], tmp_path / "job", small_options())
    assert not (tmp_path / "job").exists()


def test_overwrite_is_explicit_and_cleans_stale_generated_backs(tmp_path):
    path = image_file(tmp_path)
    target = tmp_path / "job"
    create_job([path, path], [path, path], target, small_options())
    unrelated = target / "family-note.txt"
    unrelated.write_text("keep this")
    with pytest.raises(FileExistsError):
        create_job([path], None, target, small_options())
    result = create_job([path], None, target, small_options(), overwrite=True)
    assert result.backs_pdf_path is None
    assert not (target / "backs.pdf").exists()
    assert not (target / "preview-front-002.png").exists()
    assert not (target / "preview-back-001.png").exists()
    assert unrelated.read_text() == "keep this"
    assert path.exists()


def test_input_in_managed_output_name_cannot_be_overwritten(tmp_path):
    path = image_file(tmp_path, name="preview-front-001.png")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="collides"):
        create_job([path], None, tmp_path, small_options(), overwrite=True)
    assert path.read_bytes() == before


@pytest.mark.parametrize("landscape,flip,axis", [
    (False, "long", "columns"), (False, "short", "rows"),
    (True, "long", "rows"), (True, "short", "columns"),
])
def test_duplex_reflects_absolute_positions_and_preserves_art(tmp_path, landscape, flip, axis):
    options = small_options(
        page_width_in=6 if landscape else 5,
        page_height_in=5 if landscape else 6,
        card_width_in=2, card_height_in=2, duplex_flip=flip,
    )
    front = image_file(tmp_path, color="green")
    back = tmp_path / "back.png"
    art = Image.new("RGB", (80, 80), "blue")
    ImageDraw.Draw(art).rectangle((0, 0, 39, 79), fill="red")
    art.save(back)
    # A partial sheet catches cases where implementations fill empty slots on
    # the left instead of reflecting the actual occupied front positions.
    result = create_job([front], [back], tmp_path / "job", options)
    layout = plan_layout(options)
    assert layout.duplex_axis == axis
    x, y = layout.x0_in, layout.y0_in
    if axis == "columns":
        x = options.page_width_in - x - layout.card_width_in
    else:
        y = options.page_height_in - y - layout.card_height_in
    with Image.open(result.preview_paths[1]) as page:
        left = page.getpixel((round((x + 0.25) * options.dpi), round((y + 1) * options.dpi)))
        right = page.getpixel((round((x + 1.75) * options.dpi), round((y + 1) * options.dpi)))
    assert (left, right) == (((255, 0, 0), (0, 0, 255)) if axis == "columns" else ((0, 0, 255), (255, 0, 0)))


def test_bleed_does_not_modify_trim_art_and_marks_stay_outside(tmp_path):
    path = image_file(tmp_path, size=(40, 60))
    options = small_options(bleed_in=0.1, gutter_in=0.25, marks=True)
    result = create_job([path], None, tmp_path / "job", options)
    layout = plan_layout(options)
    with Image.open(result.preview_paths[0]) as page:
        trim = page.crop((
            round(layout.x0_in * options.dpi), round(layout.y0_in * options.dpi),
            round((layout.x0_in + layout.card_width_in) * options.dpi),
            round((layout.y0_in + layout.card_height_in) * options.dpi),
        ))
        assert trim.getextrema() == ((255, 255), (0, 0), (0, 0))
        assert page.getpixel((round((layout.x0_in - 0.05) * options.dpi), round((layout.y0_in + 1) * options.dpi))) == (255, 0, 0)
    metadata = json.loads((tmp_path / "job" / "layout.json").read_text())
    assert metadata["options"]["bleed_in"] == 0.1
    assert metadata["sheet_count"] == 1
