"""Pure music-theory code. This package must not depend on UI, MIDI, or audio."""

from .music_theory import Chord, Interval, Note, interval_between, parse_chord, parse_note, transpose
from .harmony import HarmonyFinding, Key, analyze_progression, diatonic_chords, minor_functional_dominant, parse_key, roman_to_chord, scale_notes
from .voice_leading import VoiceLeadingMetrics, measure_progression, measure_voice_leading

__all__ = ["Chord", "Interval", "Note", "interval_between", "parse_chord", "parse_note", "transpose"]
__all__ += ["HarmonyFinding", "Key", "analyze_progression", "diatonic_chords", "minor_functional_dominant", "parse_key", "roman_to_chord", "scale_notes"]
__all__ += ["VoiceLeadingMetrics", "measure_progression", "measure_voice_leading"]
