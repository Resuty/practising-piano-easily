# Architecture

## Dependency boundaries

`practising_piano_easily.core` contains spelling-aware notes, intervals, chords, keys and voice-leading calculations. It does not import Qt, MIDI drivers or audio playback.

The trainers and analysis modules use the core model. The UI presents their state and forwards user actions; it does not define a second set of theory or scoring rules.

## Input and practice

`midi/state.py` distinguishes physically pressed keys from notes sustained by a pedal. Practice normally checks fresh physical key events. Device discovery runs in a subprocess with an eight-second timeout; opening a MIDI port runs in a worker thread.

The source entry point is `python -m practising_piano_easily.app`. The frozen EXE handles `--midi-scan OUTPUT.json` before importing the GUI. The helper returns UTF-8 JSON through a temporary file because a windowed EXE has no stdout.

The beginner course, score follower and falling-note session preserve separate completion records. Interrupted or demonstration-only sessions do not count as completed practice. Detailed rules are in [TRAINING_MODEL.md](TRAINING_MODEL.md).

## Shared musical time

MIDI tempo and time-signature changes form a shared beat/second/measure timeline. Notation, falling blocks, selected passages and chord references use this timeline.

Long scores render only visible staff systems. Display zoom and bars-per-line change layout, not the note timestamps or scoring state. A PDF is an independent reference view; it does not provide exact note coordinates.

Imported MIDI hand assignments use an adjustable register split or a manually selected track. Built-in exercises have explicit left/right parts. These are practice assignments, not automatic fingering recognition.

## Audio and analysis

NumPy generates the demonstration waveform; sounddevice handles playback. Rendering and question generation can be tested without an audio device.

Chord and key analysis exposes heuristic candidates, separately from user-confirmed harmonic interpretation. Composition uses the same chord/voicing data for analysis and MIDI export.

## Persistence and display languages

SQLite stores attempts, derived mastery and settings. Related writes use transactions. CSV/JSON are exports, not a second editable store.

Display translations use stable source strings and canonical combo-box values. Musical symbols, answer indices, question IDs, filenames and device names remain independent of the display language. Japanese tutorial prose is a separate authored resource; the score notes and quiz answer indices are shared.

`paths.data_directory()` and `paths.database_path()` keep writable records outside bundled resources. Source runs use `data/`; new frozen runs use the application's local user-data directory. Legacy database locations are reused without moving or replacing their contents.

## Distribution boundary

The PyInstaller specification bundles application code and authored content, not the user's data directory. `packaging/build_portfolio.py` uses an explicit source allowlist for source snapshots and GitHub exports. It rejects databases, personal media, environment files, caches and Git history in release contents.

The source-only export has no dependency on an existing Git repository. Release manifests identify the accompanying source by a content digest rather than a private commit history. Third-party notices are preserved.
