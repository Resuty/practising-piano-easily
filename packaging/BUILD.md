# Build and source export

Use Windows x64 and a local Python virtual environment. The verified runtime uses Python 3.13 and PySide6 6.8.3; the Qt requirement remains on the 6.8 line.

## Windows application

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -X utf8 packaging/build_portfolio.py
```

The output is `exports/portfolio/practising-piano-easily-windows.zip`, containing the EXE, dynamic libraries, usage notes, clean source and third-party licenses. Existing executable output directories are not overwritten automatically.

`--archive-only` refreshes the source, documents and ZIP without recompiling the EXE. It replaces only the generated `Source` and `THIRD_PARTY` staging subdirectories. Make source edits in the project, not these staging copies.

## Clean repository source

```powershell
.\.venv\Scripts\python.exe -X utf8 packaging/build_portfolio.py --source-only
```

This creates:

- `exports/github/practising-piano-easily/`: files ready for a new repository
- `exports/github/practising-piano-easily-source.zip`: the same source as a ZIP

The export is allowlisted, has no `.git` history, and excludes personal data, downloaded scores, audio, credentials, developer settings and caches. It also checks authored text for Windows user-profile paths and recognizable credential formats. This is a publication safeguard, not a guarantee that arbitrary future content is safe.

Existing source exports are preserved. Use a fresh output destination for a later export after someone has started editing or initializing a repository there.

## Runtime details

The module entry is `practising_piano_easily.app`. Authored tutorial Markdown is bundled as a read-only resource. Writable files use the source `data/` directory or the frozen application's local user-data directory. Legacy locations are reused when needed, without copying or moving databases.

The MIDI helper is `practising-piano-easily.exe --midi-scan OUTPUT.json`. It returns UTF-8 JSON without a GUI. The parent enforces an eight-second timeout.

Release manifests contain a digest of the accompanying source, not private Git commit metadata. License texts in `packaging/licenses` are copied unchanged; runtime wheel metadata and available notices are collected separately. Qt DLLs remain dynamically loaded. Applicable notices and exact corresponding-source links are retained in `THIRD_PARTY`.

Building or exporting does not upload to GitHub, create a repository, change account identity or set sharing permissions.
