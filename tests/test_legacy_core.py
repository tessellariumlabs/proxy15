from PIL import Image

from proxy15.core import (
    TRIM_H,
    TRIM_W,
    choose_orientation,
    compute_grid,
    mirror_bleed_image,
    parse_grid_str,
    render_pages_pil,
    selftest,
)


def test_compute_grid_letter_defaults_are_stable():
    result = compute_grid(8.5, 11.0, 0.25, 0.25, 0.25, 0.0, 0.0, 0.25, 0.25, TRIM_W, TRIM_H)
    cols, rows, x0, y0, step_x, step_y = result
    assert (cols, rows) == (3, 2)
    assert (x0, y0, step_x, step_y) == (0.25, 1.875, 2.75, 3.75)


def test_compute_grid_does_not_force_card_onto_tiny_page():
    cols, rows, *_ = compute_grid(1.0, 1.0, 0.25, 0.25, 0.25, 0.0, 0.0, 0.25, 0.25, TRIM_W, TRIM_H)
    assert (cols, rows) == (0, 0)


def test_choose_orientation_auto_uses_higher_card_count():
    rotated, card_w, card_h, grid = choose_orientation(
        8.0, 6.0, 0.25, 0.25, 0.25, 0.0, 0.0, 0.25, 0.25, TRIM_W, TRIM_H, "auto"
    )
    assert rotated is True
    assert (card_w, card_h) == (TRIM_H, TRIM_W)
    assert grid == (2, 2)


def test_parse_grid_exact_and_best_aliases():
    assert parse_grid_str("3x3") == (3, 3)
    assert parse_grid_str("best") == (-1, -1)
    assert parse_grid_str("max") == (-1, -1)
    assert parse_grid_str("auto") == (-1, -1)


def test_mirror_bleed_increases_dimensions_by_pad_each_side():
    source = Image.new("RGB", (20, 30), "blue")
    assert mirror_bleed_image(source, 3).size == (26, 36)


def test_extracted_proxy15_selftest(capsys):
    selftest()
    assert "Self-test OK." in capsys.readouterr().out


def test_duplex_pages_are_interleaved_by_sheet(tmp_path):
    fronts_dir = tmp_path / "fronts"
    backs_dir = tmp_path / "backs"
    fronts_dir.mkdir()
    backs_dir.mkdir()
    fronts = []
    backs = []
    for index in range(2):
        front_path = fronts_dir / f"front_{index}.png"
        back_path = backs_dir / f"back_{index}.png"
        Image.new("RGB", (20, 20), "navy").save(front_path)
        Image.new("RGB", (20, 20), "maroon").save(back_path)
        fronts.append(str(front_path))
        backs.append(str(back_path))

    rendered = render_pages_pil(
        fronts,
        backs,
        3.0,
        4.0,
        10,
        0.0,
        0.0,
        0.0,
        0.25,
        0.25,
        0.25,
        0.25,
        0.25,
        False,
        TRIM_W,
        TRIM_H,
        "duplex-test",
        "none",
        0.0,
        0.0,
        0.0,
        False,
        "mirror",
        0.5,
        False,
        0.2,
        0.9,
        4,
        22,
        1.4,
        False,
        2,
        1,
        12,
    )

    assert [(side, page_number) for side, page_number, _, _ in rendered] == [
        ("F", 1),
        ("B", 1),
        ("F", 2),
        ("B", 2),
    ]
