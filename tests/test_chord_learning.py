import pytest

from practising_piano_easily.chord_learning import quality_label, tutorial_topic
from practising_piano_easily.core import parse_chord
from practising_piano_easily.trainers.chord_construction import LEVEL_SUFFIXES
from practising_piano_easily.tutorial import load_lessons
from practising_piano_easily.ui.i18n import language, tr


@pytest.mark.parametrize("symbol, chinese, topic", [
    ("C", "大三和弦", "triads"), ("Am", "小三和弦", "triads"),
    ("F#dim", "减三和弦", "triads"), ("Caug", "增三和弦", "triads"),
    ("G7", "属七和弦", "sevenths"), ("Cmaj7", "大七和弦", "sevenths"),
    ("Am7", "小七和弦", "sevenths"), ("Bm7b5", "半减七和弦", "sevenths"),
    ("Cdim7", "减七和弦", "sevenths"), ("CmMaj7", "小大七和弦", "sevenths"),
    ("Dsus4", "挂四和弦", "colors"), ("Cadd9", "加九音和弦", "colors"),
    ("C6/9", "六九和弦", "colors"), ("Cmaj13", "大十三和弦", "colors"),
    ("Am7/C", "小七和弦", "inversions"), ("G7b9", "属七和弦 (b9)", "colors"),
])
def test_names_and_tutorial_topics(symbol, chinese, topic):
    original = language.code
    try:
        language.set_language("zh_CN")
        chord = parse_chord(symbol)
        assert tr(quality_label(chord)) == chinese
        assert tutorial_topic(chord) == topic
    finally:
        language.set_language(original)


def test_every_supported_training_chord_has_a_name_and_an_existing_tutorial_topic():
    chapters = {lesson.id for lesson in load_lessons()}
    for suffixes in LEVEL_SUFFIXES.values():
        for suffix in suffixes:
            for root in ("C", "F#", "Bb"):
                chord = parse_chord(root + suffix)
                assert quality_label(chord)
                assert tutorial_topic(chord) in chapters
    assert tuple(map(str, parse_chord("Cdim7").notes)) == ("C", "Eb", "Gb", "Bbb")
