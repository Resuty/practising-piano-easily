# Verification

## Automated tests

Run the current source tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Coverage includes music theory, MIDI state, practice completion, timelines, passage boundaries, hand filters, persistence, English and Japanese course/quiz coverage, language switching, legacy data locations and source-export boundaries.

## Windows build checks

After building the EXE:

```powershell
.\.venv\Scripts\python.exe -X utf8 packaging/verify_portfolio.py
```

The script uses fresh profiles below `exports/packaging-checks`. It checks:

- the actual frozen MIDI-discovery helper with a minimal Windows PATH and without PYTHONPATH/PYTHONHOME
- frozen application startup in a separate working directory, new database creation, initial Japanese selection and absence of error logs
- source UI rendering with an in-memory database and simulated device discovery
- Japanese and English pages for home, beginner lessons, chord tutorials, falling notes and score practice

The test terminates only its own temporary application process. It does not use or replace the regular user's database.

ZIP creation checks CRC, allowed contents and SHA-256. The source-only export omits Git history and performs additional publication checks.

## Validation limits

These are local software checks, not clean-machine or physical-hardware certification. They do not establish compatibility with every MIDI/audio driver, device disconnection case, screen resolution, company network or online score source.

Translated explanations and music terminology have not undergone comprehensive specialist or native-speaker review. Timing, fingering and expression are not assessed by the application. The Windows build is unsigned.
