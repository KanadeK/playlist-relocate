# Contributing

Report reproducible failures through [Issues](https://github.com/KanadeK/playlist-relocate/issues).
Use synthetic, minimal inputs. Do not attach private catalogs, media, playlists,
credentials or personal paths. Describe the expected exit status and actual result.

For local development, use Python 3.11+ and a virtual environment:

```sh
python -m venv .venv
# Activate using your shell's standard venv command.
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m coverage run -m unittest discover -s tests
python -m coverage report
python -m build
python scripts/smoke_install.py
```

Changes need a regression case that checks observable behavior. Keep diagnostics
content-free, input files read-only, and the documented scope explicit. Third-party
copyright and license notices must be preserved. CI performs checks only and never
creates commits. No automated dependency-update or merge workflows are configured.
