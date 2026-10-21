# practising piano easily

A Windows piano-learning app with MIDI input, interactive sheet music and falling-note practice.

## Start

Extract the complete ZIP to a local folder and run `practising-piano-easily.exe`. The build targets Windows 10/11 x64 and does not require Python. Keep the `_internal` folder beside the executable.

A new distribution profile starts in Japanese. Choose **English** in the top-right language menu; your choice is saved. English includes interface text, the 24 beginner lessons, 12 practice-piece explanations, and the chord tutorial and self-tests. Japanese and Simplified Chinese remain available. The executable is unsigned; follow your computer's security policy.

## Try a short session

1. Open **Beginner lessons / scores**, select the first lesson, and listen. Without a MIDI keyboard, click the on-screen keys.
2. In **Chord Trainer**, read the target first. Add notes slowly, keeping correct keys held while correcting extras.
3. In **Falling piano practice**, choose a built-in piece and play its demonstration. Practice normally works in four-bar passages, with optional pre-practice demonstrations and loops.
4. In **Chord Tutorial**, read the explanation, check the keyboard example and try the self-test. Clicking a chord in the playing screen opens its chapter; Esc returns to the paused position, followed by the resume countdown.

The score and falling-note pages support both-hand and separate-hand practice. You can adjust score zoom and the number of bars per line. Normal playing uses your keyboard's own sound; previews and demonstrations use the app's simple synthesizer.

## Local data

New profiles save practice records, settings and imported music in `%LOCALAPPDATA%/practising-piano-easily/`. Existing installations may continue using their earlier location. The distribution does not contain anyone's practice history or downloaded music.

## Scope

The app checks pitch and octave, not timing, fingering or expression. Generated MIDI notation and inferred hand assignments are practice aids, not a perfect reconstruction of an engraved score. A PDF alone cannot supply key-detection practice.

`Source` contains the source and design documents; `THIRD_PARTY` contains dependency notices. Online score use follows the original site's terms. See `VERIFICATION.md` for what was and was not checked.
