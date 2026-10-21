"""Conservative, explicitly inferred harmony from the score's current quarter-note beat."""

from functools import lru_cache
import math

from .midi_file import chord_candidates
from practising_piano_easily.core.music_theory import BASE_SPECS


@lru_cache(maxsize=256)
def harmony_names(notes):
    if len({note % 12 for note in notes}) < 3:
        return ()
    candidates = chord_candidates(notes, limit=12, suffixes=tuple(BASE_SPECS))
    exact = tuple(item.symbol for item in candidates if not item.missing and not item.extra)
    if exact:
        return exact[:3]
    # Non-chord tones and incomplete voicings must not be presented as a definite chord.
    return ()


def harmony_at(score, seconds):
    timeline = score.timeline
    if timeline is None:
        return (), ()
    beat = min(max(0, timeline.beat_at(seconds)), max(0, timeline.end_beat - 1e-8))
    measure = timeline.measures[timeline.measure_index(seconds)]
    start = max(measure.start_beat, math.floor(beat + 1e-8))
    end = min(measure.end_beat, math.floor(beat + 1e-8) + 1)
    begin, finish = timeline.seconds_at(start), timeline.seconds_at(end)
    notes = tuple(sorted({note.pitch for note in score.visible_notes(begin, finish - begin)
                          if note.start < finish - 1e-8 and note.end > begin + 1e-8}))
    return harmony_names(notes), notes
