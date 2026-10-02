"""Exercise the public command line without opening a printer or a GUI."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from proxy15 import cli


def write_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 32), "forestgreen").save(path)
    return path


@pytest.fixture
def captured_jobs(monkeypatch):
    calls = []

    def capture(fronts, backs, output_dir, options, *, overwrite=False):
        calls.append(
            SimpleNamespace(
                fronts=[Path(path) for path in fronts],
                backs=[Path(path) for path in backs] if backs is not None else None,
                output=Path(output_dir),
                options=options,
                overwrite=overwrite,
            )
        )
        output = Path(output_dir)
        return SimpleNamespace(
            pdf_path=output / "cards.pdf",
            fronts_pdf_path=output / "fronts.pdf",
            backs_pdf_path=output / "backs.pdf" if backs else None,
            preview_paths=[],
            columns=3,
            rows=2,
            sheet_count=1,
        )

    monkeypatch.setattr(cli, "create_job", capture)
    return calls


def invoke(arguments):
    """Normalize argparse's documented SystemExit for invalid arguments."""
    try:
        return cli.main(arguments)
    except SystemExit as error:
        return error.code


def render_args(front: Path, output: Path, *extra: str):
    return ["render", "--fronts", str(front), "--output", str(output), *extra]


def test_render_default_dimensions_and_overwrite(tmp_path, captured_jobs):
    front = write_image(tmp_path / "front.png")
    assert invoke(render_args(front, tmp_path / "output", "--overwrite")) == 0
    job, = captured_jobs
    assert job.fronts == [front]
    assert not job.backs
    assert job.output == tmp_path / "output"
    assert job.overwrite is True
    assert job.options.page_width_in == pytest.approx(8.5)
    assert job.options.page_height_in == pytest.approx(11)
    assert job.options.card_width_in == pytest.approx(2.5)
    assert job.options.card_height_in == pytest.approx(3.5)
    assert job.options.margin_in == pytest.approx(0.25)
    assert job.options.gutter_in == pytest.approx(0.25)


def test_millimeter_defaults_preserve_physical_size(tmp_path, captured_jobs):
    front = write_image(tmp_path / "front.png")
    assert invoke(render_args(front, tmp_path / "output", "--units", "mm")) == 0
    job, = captured_jobs
    assert job.options.card_width_in == pytest.approx(2.5)
    assert job.options.card_height_in == pytest.approx(3.5)
    assert job.options.margin_in == pytest.approx(0.25)
    assert job.options.gutter_in == pytest.approx(0.25)


def test_custom_paper_converts_every_measurement_and_preserves_options(tmp_path, captured_jobs):
    front = write_image(tmp_path / "front.png")
    assert invoke(
        render_args(
            front, tmp_path / "output", "--units", "mm", "--paper", "Custom",
            "--paper-width", "254", "--paper-height", "304.8",
            "--card-width", "101.6", "--card-height", "152.4",
            "--margin", "12.7", "--gutter", "6.35", "--bleed", "2.54",
            "--dpi", "150", "--flip", "short", "--rotate", "never",
            "--fold", "vertical", "--fit", "cover", "--no-marks",
        )
    ) == 0
    job, = captured_jobs
    options = job.options
    assert options.page_width_in == pytest.approx(10)
    assert options.page_height_in == pytest.approx(12)
    assert options.card_width_in == pytest.approx(4)
    assert options.card_height_in == pytest.approx(6)
    assert options.margin_in == pytest.approx(0.5)
    assert options.gutter_in == pytest.approx(0.25)
    assert options.bleed_in == pytest.approx(0.1)
    assert options.dpi == 150
    assert options.duplex_flip == "short"
    assert options.rotate == "never"
    assert options.fold == "vertical"
    assert options.fit == "cover"
    assert options.marks is False


@pytest.mark.parametrize(
    ("paper", "width", "height"),
    [("Letter", 8.5, 11), ("Legal", 8.5, 14),
     ("A4", 210 / 25.4, 297 / 25.4), ("A5", 148 / 25.4, 210 / 25.4)],
)
def test_standard_paper_sizes(tmp_path, captured_jobs, paper, width, height):
    front = write_image(tmp_path / "front.png")
    assert invoke(render_args(front, tmp_path / "output", "--paper", paper)) == 0
    options = captured_jobs[0].options
    assert options.page_width_in == pytest.approx(width)
    assert options.page_height_in == pytest.approx(height)


@pytest.mark.parametrize("extra", [[], ["--paper-width", "10"], ["--paper-height", "12"]])
def test_custom_paper_requires_both_dimensions(tmp_path, captured_jobs, capsys, extra):
    front = write_image(tmp_path / "front.png")
    assert invoke(render_args(front, tmp_path / "output", "--paper", "Custom", *extra)) != 0
    assert not captured_jobs
    assert "Traceback" not in capsys.readouterr().err


def test_directory_pairing_uses_stems_and_deterministic_order(tmp_path, captured_jobs):
    fronts = tmp_path / "fronts"
    backs = tmp_path / "backs"
    for stem in ("zebra", "apple", "middle"):
        write_image(fronts / f"{stem}.png")
        write_image(backs / f"{stem}.jpg")
    assert invoke(render_args(fronts, tmp_path / "output", "--backs", str(backs))) == 0
    job, = captured_jobs
    assert [path.stem for path in job.fronts] == ["apple", "middle", "zebra"]
    assert [path.stem for path in job.backs] == ["apple", "middle", "zebra"]


def test_directory_pairing_refuses_mismatching_names(tmp_path, captured_jobs, capsys):
    front = write_image(tmp_path / "fronts" / "family.png")
    back = write_image(tmp_path / "backs" / "other.png")
    assert invoke(render_args(front.parent, tmp_path / "output", "--backs", str(back.parent))) != 0
    assert not captured_jobs
    error = capsys.readouterr().err
    assert error.strip()
    assert "Traceback" not in error


@pytest.mark.parametrize("duplicate_side", ["fronts", "backs"])
def test_directory_pairing_refuses_duplicate_stems(tmp_path, captured_jobs, capsys, duplicate_side):
    fronts = tmp_path / "fronts"
    backs = tmp_path / "backs"
    write_image(fronts / "family.png")
    write_image(backs / "family.png")
    write_image(tmp_path / duplicate_side / "family.jpg")
    assert invoke(render_args(fronts, tmp_path / "output", "--backs", str(backs))) != 0
    assert not captured_jobs
    error = capsys.readouterr().err
    assert "duplicate" in error.lower()
    assert "Traceback" not in error


def test_common_back_is_repeated_for_every_front(tmp_path, captured_jobs):
    fronts = tmp_path / "fronts"
    write_image(fronts / "b.png")
    write_image(fronts / "a.png")
    back = write_image(tmp_path / "message.png")
    assert invoke(render_args(fronts, tmp_path / "output", "--common-back", str(back))) == 0
    job, = captured_jobs
    assert [path.stem for path in job.fronts] == ["a", "b"]
    assert job.backs == [back, back]


def test_single_card_copies_repeat_its_back(tmp_path, captured_jobs):
    front = write_image(tmp_path / "family.png")
    back = write_image(tmp_path / "message.png")
    assert invoke(render_args(front, tmp_path / "output", "--common-back", str(back), "--copies", "3")) == 0
    job, = captured_jobs
    assert job.fronts == [front, front, front]
    assert job.backs == [back, back, back]


def test_single_card_copies_repeat_a_paired_back(tmp_path, captured_jobs):
    front = write_image(tmp_path / "fronts" / "family.png")
    back = write_image(tmp_path / "backs" / "family.jpg")
    assert invoke(render_args(front, tmp_path / "output", "--backs", str(back), "--copies", "3")) == 0
    job, = captured_jobs
    assert job.fronts == [front, front, front]
    assert job.backs == [back, back, back]


def test_single_front_and_back_files_can_have_different_names(tmp_path, captured_jobs):
    front = write_image(tmp_path / "family-photo.png")
    back = write_image(tmp_path / "greeting.png")
    assert invoke(render_args(front, tmp_path / "output", "--backs", str(back))) == 0
    job, = captured_jobs
    assert job.fronts == [front]
    assert job.backs == [back]


def test_copies_rejected_for_a_front_directory(tmp_path, captured_jobs, capsys):
    front = write_image(tmp_path / "fronts" / "family.png")
    assert invoke(render_args(front.parent, tmp_path / "output", "--copies", "2")) != 0
    assert not captured_jobs
    error = capsys.readouterr().err
    assert "cop" in error.lower()
    assert "Traceback" not in error


@pytest.mark.parametrize("copies", ["10001", "1000000000"])
def test_oversized_copy_count_is_rejected_before_allocating_images(
    tmp_path, captured_jobs, monkeypatch, capsys, copies
):
    front = write_image(tmp_path / "family.png")

    class ImagesThatMustNotBeRepeated(list):
        def __mul__(self, count):
            pytest.fail("Oversized --copies must be rejected before multiplying the image list")

    monkeypatch.setattr(cli, "collect_images", lambda path: ImagesThatMustNotBeRepeated([front]))
    assert invoke(render_args(front, tmp_path / "output", "--copies", copies)) != 0
    assert not captured_jobs
    assert not (tmp_path / "output").exists()
    error = capsys.readouterr().err
    assert "10000" in error.replace(",", "")
    assert "Traceback" not in error


def test_copy_count_at_the_export_limit_is_accepted(tmp_path, captured_jobs):
    front = write_image(tmp_path / "family.png")
    assert invoke(render_args(front, tmp_path / "output", "--copies", "10000")) == 0
    job, = captured_jobs
    assert len(job.fronts) == 10000
    assert job.fronts[0] == job.fronts[-1] == front


def test_oversized_calibration_is_rejected_before_creating_artwork(
    tmp_path, captured_jobs, monkeypatch, capsys
):
    from proxy15 import examples

    monkeypatch.setattr(cli, "plan_layout", lambda options: SimpleNamespace(capacity=1001))

    def artwork_must_not_be_created(*args, **kwargs):
        pytest.fail("Oversized calibration must be rejected before generating slot images")

    monkeypatch.setattr(examples, "create_calibration_artwork", artwork_must_not_be_created)
    output = tmp_path / "calibration"
    assert invoke(["calibrate", "--output", str(output)]) != 0
    assert not captured_jobs
    assert not output.exists()
    error = capsys.readouterr().err
    assert "1000" in error.replace(",", "")
    assert "Traceback" not in error


def test_backs_and_common_back_are_mutually_exclusive(tmp_path, captured_jobs, capsys):
    front = write_image(tmp_path / "family.png")
    back = write_image(tmp_path / "message.png")
    assert invoke(render_args(front, tmp_path / "output", "--backs", str(back), "--common-back", str(back))) != 0
    assert not captured_jobs
    assert "Traceback" not in capsys.readouterr().err


def test_missing_front_reports_a_clean_error(tmp_path, captured_jobs, capsys):
    assert invoke(render_args(tmp_path / "missing.png", tmp_path / "output")) != 0
    assert not captured_jobs
    error = capsys.readouterr().err
    assert error.strip()
    assert "Traceback" not in error


@pytest.mark.parametrize("failure", [ValueError("Card does not fit on this paper"), OSError("Output is not writable")])
def test_renderer_failures_are_readable_without_a_traceback(tmp_path, monkeypatch, capsys, failure):
    front = write_image(tmp_path / "front.png")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cli, "create_job", fail)
    assert invoke(render_args(front, tmp_path / "output")) != 0
    error = capsys.readouterr().err
    assert str(failure) in error
    assert "Traceback" not in error
