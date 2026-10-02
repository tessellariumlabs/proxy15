# Printing family cards with Proxy 15

Proxy 15 creates PDFs with explicit physical page sizes and matching front
and back layouts. Your PDF viewer and printer driver control the actual
printing. Start with a plain-paper test before using cardstock or a large
batch.

## Prepare artwork

Create your front images in any drawing, photo, or layout tool. Add your
greeting to the artwork before importing it. Proxy 15 arranges images on
print sheets; it does not provide a photo editor or shared live canvas.

Put corresponding images in separate front and back folders. Files pair by
filename stem, regardless of extension: `sam.png` can pair with `sam.jpg`.
Use unique stems within each folder. For the same reverse side on every
card, supply `--common-back path/to/greeting.png` instead of `--backs`.
Pairing is case-sensitive. Supported inputs are PNG, JPEG, TIFF, WebP, and
BMP images; export other artwork formats to one of these first.
When both inputs are single files, the front and back filenames do not need
to match. For example, `--fronts front.png --backs inside.png` pairs those
two images directly.

To repeat a single design, pass its file as `--fronts` and use `--copies N`.
The copies option applies to a single front file, rather than a folder.
Omit `--backs` and `--common-back` for single-sided printing.
An export accepts up to 10,000 copies. Split larger batches into separate
exports to keep each job manageable.

Prepare images at the card's intended aspect ratio. At 300 DPI, a 5 × 7 inch
card is 1500 × 2100 pixels. Enlarging a small image does not create detail.
Photographs and drawings should be your own or used with permission.

The fit choices preserve image proportions:

- `--fit contain` shows the whole image and leaves padding when the shapes
  differ. This is the default.
- `--fit cover` fills the card and crops any excess. Keep names, faces,
  borders, and greetings away from the edges if you choose this option.

## Choose card and paper sizes

`--card-width` and `--card-height` describe the finished size of a flat card
or the closed size of a folded card. `--units in` or `--units mm` applies to
card size, margin, gutter, bleed, and custom paper dimensions. Preset paper
names always retain their standard physical dimensions.

| Paper | Standard dimensions |
| --- | --- |
| Letter | 8.5 × 11 inches |
| Legal | 8.5 × 14 inches |
| A4 | 210 × 297 millimetres |
| A5 | 148 × 210 millimetres |
| Custom | Your `--paper-width` × `--paper-height` |

Choose custom dimensions that your printer supports. A card must fit inside
the usable paper area after margins and bleed are reserved. Proxy 15 reports
layouts that cannot fit rather than shrinking the cards silently.

`--rotate auto` compares card orientations to fit cards efficiently.
`--rotate never` keeps the artwork upright on the paper, and `--rotate always`
turns the artwork 90 degrees. This rotates the cards, not the paper dimensions.
Check the generated PDF's page orientation when choosing printer settings.

Margins are the minimum clear space between the paper's edge and the
printed artwork. Use a margin at least as large as your printer's unprintable
border. The gutter is the space between neighbouring trim edges. To use
bleed, set `--bleed` to the amount of artwork extending beyond each trim
edge. Bleed is reserved in addition to the margin, and the gutter must be at
least twice the bleed so neighbouring artwork cannot overlap. Cut at the
trim guides, not the outer bleed edge.

Prepare the input image for the trim size. Proxy 15 extends its outermost
pixel colours into the bleed area, leaving the content inside the trim
unchanged. Leave space beyond twice the bleed in the gutter when you need
room for cut guides between cards.

For example, this uses an eighth-inch bleed with a quarter-inch gutter:

```sh
proxy15 render --fronts family/fronts --common-back family/greeting.png \
  --output family/bleed --paper Letter --units in \
  --card-width 2.5 --card-height 3.5 --margin 0.25 --gutter 0.25 --bleed 0.125
```

The `--dpi` option controls raster rendering resolution, not physical card
size. The default is 300. Higher values increase memory use and file size.
Very large paper sizes may require a lower DPI to stay within the renderer's
60-megapixel page limit.
Artwork and placement round to raster pixels, about 0.085 millimetres per
pixel at 300 DPI. The PDF retains the exact physical paper dimensions.

## Make folded greeting cards

Prepare one outside image and one inside image for each card. Each image
contains **both panels** of the opened card.

- With `--fold vertical`, the fold runs down the middle. The open artwork
  is twice the finished width and the same height. Looking at the outside
  artwork upright, put the back cover on the left and the front cover on
  the right. Put the inside-left and inside-right content in the corresponding
  halves of the inside image.
- With `--fold horizontal`, the fold runs across the middle. The open
  artwork is the finished width and twice the finished height. Prepare the
  upper and lower panels for your intended top-fold design, then check their
  orientation on a folded test sheet before printing a batch.

Use the outside images as `--fronts` and the inside images as `--backs`.
Cut around the open card outline, then fold on the centre guide. A 5 × 7 inch
vertical-fold card therefore needs a 10 × 7 inch open layout, plus room for
the paper margins and any bleed.

## Automatic duplex printing

`cards.pdf` interleaves pages in this order:

```text
sheet 1 front, sheet 1 back, sheet 2 front, sheet 2 back, …
```

Open it in a PDF viewer that offers control over print scaling. Select:

1. The PDF's paper size and orientation.
2. **Actual size / 100%**. Turn off fit-to-page, shrink-to-fit, booklet mode,
   multiple pages per sheet, and extra viewer margins.
3. Double-sided printing with the flip edge matching `--flip long` or
   `--flip short` from your render command.
4. A paper type and tray that support the sheet you are using.

The flip edge refers to the long or short physical edge of the printed
sheet. Which edge feels natural can change between portrait and landscape
paper. Proxy 15 positions backs for the selected edge, but the PDF cannot
force a printer driver to use it. Test before assuming a driver setting is
correct. Some printers cannot duplex heavy cardstock automatically.

Generate a labelled alignment sheet:

```sh
proxy15 calibrate --output duplex-test --paper Letter --flip long
```

Use the same paper and flip choice as your actual job. Print one sheet,
turn it over, and check the labels, orientation, and registration. Measure a
known card dimension to confirm the printer used 100% scaling. Minor
physical registration differences can remain even with correct settings.
Calibration fills one sheet with numbered pairs, top markers, and a labeled
ruler. Follow the generated `calibration-instructions.txt`; a one-inch ruler
should measure 25.4 millimetres. Test layouts are limited to 1,000 slots per
sheet. Increase the card size or use smaller paper if that limit is exceeded.

## Manual duplex printing

Manual printing is useful when your printer has no duplex unit or requires
single-sided feeding for cardstock.

1. Print a one-sheet calibration job's `fronts.pdf` at 100%.
2. Mark a corner of the sheet lightly in pencil and note how it exits the
   printer.
3. Refeed it according to your printer's instructions and print the matching
   `backs.pdf`.
4. Inspect the result. Adjust which face enters the tray and which edge leads
   until the back is upright and matches the front.
5. For a batch, print `fronts.pdf`, refeed the stack using the tested method,
   then print `backs.pdf`. If your feed path reverses the stack's order, use
   `backs-reversed.pdf` instead.

`backs-reversed.pdf` reverses the order of **sheets**, not the positions of
individual cards. Do not also enable reverse page order in the print dialog
unless your tested workflow calls for it. Feed paths differ between printer
models, so there is no universal face-up or face-down instruction.

## Inspect the output

Each job includes PDFs, numbered PNG previews, `layout.json`, and
`print-guide.txt`. The previews show the raster sheet layout. The PDFs retain
the requested physical paper size. The JSON records the layout settings for
reference when reproducing a job.

An output directory already containing a job is protected against accidental
replacement. Use a new directory for each design or pass `--overwrite` when
you intend to replace its files.

## Troubleshoot a test sheet

| Symptom | Check |
| --- | --- |
| Cards print smaller than requested | Set Actual size / 100%; disable fit-to-page and extra margins. |
| Back prints upside down | Match the driver flip edge to `--flip`; repeat the one-sheet test. |
| Wrong backs appear in a manual batch | Try `backs-reversed.pdf` and verify the stack's feed order. |
| Artwork clips near the paper edge | Increase the margin to suit your printer's printable area. |
| Faces or text are cropped | Use `--fit contain`, or revise artwork to match the card ratio. |
| Fronts and backs differ slightly in position | Check paper guides and feed settings; allow room for the printer's registration tolerance. |
| Cardstock jams or will not duplex | Use a supported weight, the specified tray, and manual duplex if required. |

Software validation covers dimensions, pairing, and rendered alignment.
Printer mechanics, paper stock, and driver behaviour require your physical
test sheet. If you report a printing problem, include the details requested
in [CONTRIBUTING.md](../CONTRIBUTING.md), using sample artwork without private
family photographs.
