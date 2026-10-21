# Training model

## Modes and records

Learn shows target notes and formulas. Practice supplies correction feedback. Test records results without answer hints. The selected curriculum stage is manual, not date-based.

An attempt stores the question ID, expected and played notes, correctness, time, difficulty and metadata. `metadata.completed` and `correct` are separate: completion after corrections is not recorded as a correction-free answer. Interrupted work, demonstrations and rest-only passages do not create completion records.

## Chord construction

The default learning flow shows the target before accepting input. Missing tones wait; extra tones can be released without clearing correct keys. A complete input stable for approximately 300 ms is confirmed automatically. Releasing all keys separates consecutive questions.

Root-position and slash-bass questions check the lowest physical pitch. Practical omission rules for extended chords are distinct from the full theoretical tone list.

## Beginner course

The course has 24 lessons and a separate repertoire of 12 pieces. Each score step checks exact MIDI pitch and octave, allows gradual chord entry, then requires a complete release before advancing. Repeated notes require a fresh key press.

Finishing a lesson writes one completion record. Corrections are allowed for course progression. This follower does not grade rhythm or held duration.

## Score practice

The standalone score page shares one follower with library imports. Selection uses actual MIDI measure boundaries and defaults to bars 1–4. Start and end fields remain independent; an invalid range disables starting until corrected.

The follower groups new note attacks. Previous non-repeated notes may remain held, but a repeated pitch needs a new release/press. Notes sustained across a passage boundary must be attacked again at the start of the selected passage.

Optional looping restarts the selected range after successful saving and release of physical keys. Without looping, completion stops. Failed saving prevents automatic restarts.

## Falling-note practice

The notation and falling blocks use the same MIDI timeline. The session waits at unmatched targets, allowing corrections. The default speed is 100%; changing speed does not transpose pitches. Falling block length indicates written duration but is not a duration assessment.

Each passage defaults to four measures. A separate switch controls whether a demonstration precedes practice; another controls repetition. Both are persisted without automatically starting playback on reopening.

After saving a completed passage, a fixed two-second decision window accepts a fresh key press as a repeat request. Otherwise the next passage begins. With looping enabled, the current range repeats regardless of an extra request. Keys must be released before the next pass. Pause, navigation and changes to the selection cancel pending transitions.

Demonstrations do not submit input or create grades. The full-song demonstration returns to the selected practice range. Tutorial return uses a three-second countdown and preserves the previous location.

## Left/right assignment and display

Built-in scores carry explicit left/right parts. Imported MIDI uses either a manually selected track or an adjustable register split, initially C4: lower pitches are assigned left, others right. This assignment is not recognition of the original arranger's fingering.

Hand-filtered practice retains the original timing and rests. Single-hand and both-hand question records are distinct. A silent hand passage is not graded.

Score zoom and bars-per-line affect layout only. The falling view shows two staff systems; score practice provides a continuous score. MIDI notation uses approximate rhythm symbols and does not reconstruct original engraving or PDF note coordinates.

Chord references use the complete pitched MIDI material in the current beat, not the learner's partly entered answer. Ambiguous matches remain candidates, and insufficient material is marked undetermined.

## Mastery and weighting

- New: no attempts
- Learning: started but below the following thresholds
- Familiar: at least 5 attempts, 80% accuracy and a streak of 3
- Mastered: at least 10 attempts, 90% accuracy and a streak of 5

Hints are allowed; speed is not a course-progression requirement. Recalculation updates derived labels without deleting raw attempts.

Adaptive weight is `1 + 3 * recent_error_rate + min(average_response_ms / 5000, 2)`. Recent errors use a transparent 0.7-old / 0.3-new decay. Major/minor balance is maintained in Level 1.

Voice-leading measurements report semitone movement, largest leap and common tones, not aesthetic quality. With unequal voice counts, only matched voices contribute to the movement total.
