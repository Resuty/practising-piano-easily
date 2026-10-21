# practising piano easily

A Windows desktop app for learning piano notes, chords and score reading at your own pace with a MIDI keyboard, interactive notation and falling-note guidance.

[日本語](README.md) · [简体中文](README.zh-CN.md)

## Features

- 24 beginner lessons, 12 practice pieces, and a 10-chapter chord course with examples and self-tests
- Target-first chord practice: add missing notes and correct mistakes without restarting
- Synchronized grand staff and falling notes, four-bar passages, optional demonstrations and passage loops
- Both-hand, right-hand and left-hand practice; note labels, score zoom and bars-per-line settings
- Local MIDI import with an optional PDF, plus permission-aware discovery of online scores
- Ear training, harmony analysis, voice-leading comparisons and chord-progression MIDI export
- Local SQLite practice records and persistent settings
- English, Japanese and Simplified Chinese interfaces, lesson explanations and chord tutorials

Without a MIDI keyboard, you can click the on-screen keys to try the basic workflow. Normal playing uses your keyboard's own sound; built-in previews and demonstrations use a simple synthesizer.

## Run from source

Windows 10/11 x64 and Python 3.11+ are required. The checked runtime uses Python 3.13 and PySide6 6.8.3. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m practising_piano_easily.app
```

After setup, `start.bat` also launches the app. Select **English** in the top-right language menu. The source version defaults to Simplified Chinese for a new profile; the Windows distribution defaults to Japanese. Saved language choices take priority.

Connect a MIDI keyboard using a data-capable USB cable, then select its input in **MIDI Monitor**. No online account is required for local practice.

## Build the Windows distribution

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -X utf8 packaging/build_portfolio.py
```

The output is `exports/portfolio/practising-piano-easily-windows.zip`. Extract the entire archive and run `practising-piano-easily.exe`. Python is not required on the receiving machine. Keep `_internal` beside the executable. The app is unsigned; follow your computer's security policy.

See the [English user guide](packaging/README_en.md) and [build notes](packaging/BUILD.md).

## Tests and design

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover music theory, MIDI state, practice checking, timelines, storage and language switching. See [verification scope](packaging/VERIFICATION.md), [architecture](docs/ARCHITECTURE.md), [theory model](docs/MUSIC_THEORY.md) and [practice contracts](docs/TRAINING_MODEL.md).

## Data and limitations

Source-mode data stays in `data/`. New Windows profiles use `%LOCALAPPDATA%/practising-piano-easily/`; existing installations may reuse their legacy location. Public source exports and distribution archives exclude personal databases, imported music, audio, credentials and old Git history.

Practice primarily checks pitch and octave, not rhythm, holding time, fingering or expression. MIDI notation and register-based hand assignment do not reproduce an original engraved score perfectly. PDFs are not optically recognized. Chord and key analysis provides candidates, not probabilities or a unique musical answer.

Use external scores only under their individual licenses and access requirements. Third-party scores and audio are not distributed with the project. Dependency notices are in [THIRD_PARTY.md](packaging/THIRD_PARTY.md).
