"""Display names and tutorial topics derived from the existing chord model."""

from practising_piano_easily.core import Chord


QUALITY_LABELS = {
    "": "Major triad", "m": "Minor triad", "dim": "Diminished triad", "aug": "Augmented triad",
    "maj7": "Major seventh chord", "7": "Dominant seventh chord", "m7": "Minor seventh chord",
    "mMaj7": "Minor-major seventh chord", "m7b5": "Half-diminished seventh chord", "dim7": "Diminished seventh chord",
    "sus2": "Suspended second chord", "sus4": "Suspended fourth chord",
    "add9": "Added ninth chord", "add11": "Added eleventh chord",
    "6": "Major sixth chord", "m6": "Minor sixth chord", "6/9": "Six-nine chord",
    "9": "Dominant ninth chord", "maj9": "Major ninth chord", "m9": "Minor ninth chord",
    "11": "Dominant eleventh chord", "m11": "Minor eleventh chord",
    "13": "Dominant thirteenth chord", "maj13": "Major thirteenth chord", "m13": "Minor thirteenth chord",
}


def quality_label(chord: Chord) -> str:
    suffix = chord.canonical_suffix
    for alteration in reversed(chord.alterations):
        suffix = suffix.removesuffix(alteration)
    return QUALITY_LABELS[suffix] + (" (" + ", ".join(chord.alterations) + ")" if chord.alterations else "")


def tutorial_topic(chord: Chord) -> str:
    if chord.bass:
        return "inversions"
    if chord.extension or chord.suspension or chord.added_tones or chord.sixth or chord.alterations:
        return "colors"
    return "sevenths" if chord.seventh else "triads"
