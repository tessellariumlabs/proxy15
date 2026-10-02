# 1.0.0 release candidate

This initial public release proposal packages Proxy 15 as a local tool for
families creating Christmas, photo, and greeting cards. It retains the
original rendering core and adds a standalone Python interface and print
exports.

## Included

- Installable `proxy15` command and an optional Tkinter desktop interface.
- Finished card dimensions in inches or millimetres and preset or custom
  paper dimensions.
- Flat and folded cards, aspect-preserving image fitting, margins, gutters,
  bleed, optional guides, and configurable rendering resolution.
- Filename-based front/back pairing and a shared-back option.
- Aligned duplex PDF output, separate front and back PDFs, and a reverse
  sheet-order back PDF for manual printing.
- Original Christmas sample artwork, a labelled calibration job, PNG
  previews, layout metadata, and job-specific printing instructions.
- ISC licensing, source provenance, contributor documentation, and a
  cross-platform software test and build workflow.

## Scope and validation

Rendering runs locally without accounts, API keys, cloud services, or model
weights. The desktop interface edits layout settings and selects existing
artwork.

The software creates print files but does not select printer-driver settings.
Physical duplex alignment, cardstock handling, and feed direction depend on
the printer. Run the supplied calibration job before printing a batch. The
test suite checks software behaviour; it does not certify physical printer
compatibility.

This proposal does not publish a package to PyPI. Installation instructions
use the source repository, and the public pull request is the review point
for the initial release.
