# Proxy 15

**Free, local Christmas and photo card layouts for duplex home printing.**

Proxy 15 turns your family's artwork, photographs, and greetings into PDF
print sheets. Choose a finished card size, choose the paper your local printer
uses, and export aligned fronts and backs with optional cut and fold guides.
Use it for an afternoon making Christmas cards together, or adapt it for other
occasions.

The initial public release is under review. The installation instructions
below use the release branch.

The software runs locally. Your images are not uploaded, and rendering needs
no account, API key, cloud service, or model download. Once its Python
dependencies are installed, it works offline. The code and generated sample
artwork are available under the [ISC license](LICENSE).

## What you can make

- Flat, two-sided cards or folded greeting cards.
- Custom finished dimensions in inches or millimetres, within your chosen
  paper's printable area.
- Letter, Legal, A4, A5, or custom paper sizes, with adjustable margins,
  gutters, bleed, and output resolution.
- A different back for each front, or one common back for a whole set.
- PDFs for automatic duplex printing, plus separate front and back PDFs for
  printers that need manual refeeding.
- Christmas sample cards and a labelled duplex calibration sheet to try first.

Proxy 15 provides print files and instructions. Paper handling, duplex mode,
and scaling are selected in your printer's print dialog.

## Install from source

You need Python 3.10 or newer and Git. The rendering and command-line tools
work without a graphical desktop. The optional desktop interface needs
Tkinter, which is included in many Windows and macOS Python distributions.
On Ubuntu or Debian, install the system package `python3-tk` if needed.

```sh
git clone --branch codex/public-release https://github.com/tessellariumlabs/proxy15.git
cd proxy15
python -m venv .venv
```

Activate the environment on macOS or Linux:

```sh
source .venv/bin/activate
```

Or in Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then install and create a sample print job:

```sh
python -m pip install .
proxy15 demo --output christmas-demo
```

Open `christmas-demo/cards.pdf` to see the ready-to-print sample. The demo also
creates original artwork you can use as a starting point. To open the desktop
interface:

```sh
proxy15 gui
```

`python -m proxy15` is an alternative to `proxy15` in all commands below.

## Make your own cards

Put front images in one folder and back images in another. Pair corresponding
images by filename stem: for example, `fronts/avery.png` pairs with
`backs/avery.jpg`. For a shared reverse side, use `--common-back` instead.
PNG, JPEG, TIFF, WebP, and BMP images are supported.
When both inputs are single files, their names may differ, for example
`--fronts front.png --backs back.png`.

```sh
proxy15 render --fronts family/fronts --backs family/backs \
  --output family/print --paper Letter \
  --card-width 5 --card-height 7 --units in
```

For repeated copies of a single design, pass one front image and add
`--copies`, for example `--fronts family/front.png --copies 12`. Omit both
back options for a single-sided job. Each export accepts up to 10,000 copies;
split larger batches into separate exports.

For metric dimensions and a common back:

```sh
proxy15 render --fronts family/fronts --common-back family/greeting.png \
  --output family/print-a4 --paper A4 --units mm \
  --card-width 105 --card-height 148 --margin 8 --gutter 8
```

The line continuations above are for macOS and Linux shells. In PowerShell or
Command Prompt, put the command on one line.

Custom paper is supported too:

```sh
proxy15 render --fronts family/fronts --common-back family/greeting.png \
  --output family/custom --paper Custom --units mm \
  --paper-width 210 --paper-height 297 --card-width 90 --card-height 130 \
  --margin 8 --gutter 8
```

For folded cards, dimensions mean the **closed, finished card**. Supply
two-panel artwork for the outside and inside. For example, a 5 × 7 inch card
with `--fold vertical` uses an open 10 × 7 inch image:

```sh
proxy15 render --fronts family/outside --backs family/inside \
  --output family/folded --paper Letter --units in \
  --card-width 5 --card-height 7 --fold vertical
```

See the [printing guide](docs/PRINTING.md) for artwork preparation, folding,
bleed, and duplex setup. Run `proxy15 render --help` for every option.

## Print at the intended size

1. Generate and print a one-sheet trial with
   `proxy15 calibrate --output duplex-test`.
2. Select the PDF's paper size and orientation. Print at **Actual size / 100%**,
   with page fitting and extra margins disabled where your viewer allows it.
3. Select double-sided printing and the same flip edge used when generating
   the layout (`--flip long` or `--flip short`). Inspect the calibration sheet
   before printing the full set.
4. For manual duplex, print `fronts.pdf`, refeed the sheets according to your
   printer's feed path, then print `backs.pdf` or `backs-reversed.pdf` as the
   calibration result requires.

Printer margins, feed direction, cardstock support, and alignment vary by
model. Use settings and paper your printer supports; software tests do not
replace a physical test sheet.
Calibration jobs are limited to 1,000 slots per sheet; increase the card size
or use smaller paper if a test layout exceeds that limit.

Each duplex print job includes:

| File | Purpose |
| --- | --- |
| `cards.pdf` | Interleaved front and back pages for automatic duplex printing |
| `fronts.pdf` | Front pages for manual duplex printing |
| `backs.pdf` | Back pages in matching sheet order |
| `backs-reversed.pdf` | Back pages in reverse sheet order for manual feeding |
| `preview-front-001.png`, `preview-back-001.png`, … | Rendered sheet previews |
| `print-guide.txt` | Instructions for this layout |
| `layout.json` | Dimensions and layout metadata |

Defaults are Letter paper, a 2.5 × 3.5 inch finished card, 0.25 inch margins
and gutters, no bleed, 300 DPI, long-edge duplex, automatic layout rotation,
and cut guides. Images keep their proportions: `--fit contain` includes the
whole image; `--fit cover` fills the card by cropping. Use `--no-marks` to
omit guides and `--overwrite` to replace an existing job deliberately.

## Contribute

Bug reports, documentation improvements, and contributions are welcome.
Read [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and useful
details to include when reporting a printing issue. The
[release notes](docs/RELEASE_NOTES.md) describe the initial public scope.

The original Proxy 15 rendering core is preserved, with its provenance in
[UPSTREAM.json](UPSTREAM.json). See [NOTICE.md](NOTICE.md) for attribution.
