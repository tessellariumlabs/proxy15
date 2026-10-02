# Contributing to Proxy 15

Thank you for helping make local card printing more useful and dependable.
Small fixes, clearer instructions, accessible interface improvements, and
tests for real layout problems are welcome.

## Development setup

Clone the repository and create a Python 3.10+ virtual environment as shown
in the [README](README.md). Activate it, then install the development tools:

```sh
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build
```

Before submitting a change, run the tests and generate the sample and duplex
calibration jobs:

```sh
proxy15 demo --output christmas-demo
proxy15 calibrate --output duplex-test
```

Inspect the PDFs for changes involving page size, card placement, pairing,
folding, or duplex behaviour. Add a regression test when correcting a layout
or rendering bug. Do not commit generated jobs or personal artwork.

The GitHub workflow tests Python 3.10 and 3.13 on Linux, Windows, and macOS,
builds the distribution, and exercises the installed command-line tools.
Physical printer testing is separate from these software checks.

## Report a problem

For a reproducible report, include:

- Your operating system, Python version, and Proxy 15 version.
- The command or desktop settings used, and the full error text if any.
- A minimal sample image you have permission to share.
- `layout.json` and the relevant PDF page, after checking them for personal
  information.
- For a printing issue: printer model, PDF viewer, paper size, scale, flip
  edge, and whether you used automatic or manual duplex.
- The result you expected and the result you observed.

Use generated example artwork when possible. Public issues and pull requests
are visible to everyone; family photographs are usually unnecessary for a
useful report.

## Submit a pull request

Keep changes focused and describe the problem, the resulting behaviour, and
how you checked it. Explain any change to image fitting, file pairing, physical
dimensions, or printer instructions. Update the documentation if a command
or user-visible behaviour changes.

`src/proxy15/core.py` preserves the original rendering core identified in
[UPSTREAM.json](UPSTREAM.json). Changes to that file must include a clear
reason and updated provenance rather than silently replacing the retained
source. Prefer extending the standalone interface where appropriate.

By submitting a contribution, you agree that it can be distributed under
the project's [ISC license](LICENSE).
