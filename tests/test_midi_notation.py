import pytest

from practising_piano_easily.trainers.falling_notes import FallingNote, FallingScore
from practising_piano_easily.trainers.score_timeline import ScoreTimeline
from practising_piano_easily.ui.midi_notation_widget import MidiNotationWidget
from test_falling_piano import app


def notation_score(bars=20, attacks=4):
    timeline = ScoreTimeline(((0, 0, .5),), ((0, 4, 4),), bars * 4)
    notes = tuple(FallingNote(60 + index % 8, bar * 2 + index * 2 / attacks,
                              bar * 2 + (index + 1) * 2 / attacks, "track:0")
                  for bar in range(bars) for index in range(attacks))
    return FallingScore(notes, timeline)


@pytest.fixture
def notation(app):
    widget = MidiNotationWidget()
    widget.resize(1200, 360)
    widget.show()
    app.processEvents()
    widget.set_score(notation_score())
    yield widget
    widget.close()


def test_two_systems_hold_measure_geometry_until_a_whole_line_finishes(notation):
    assert notation.systems[:3] == ((0, 4), (4, 8), (8, 12))
    rects = [notation.measure_rect(index) for index in range(8)]
    assert rects[0].top() == rects[3].top() < rects[4].top() == rects[7].top()
    assert not notation.viewport().rect().intersects(notation.measure_rect(8).toAlignedRect())
    for seconds in (-3, 0, .5, 2, 4, 7.999999):
        notation.set_position(seconds, "C")
        assert notation.first_system == 0
        assert [notation.measure_rect(index) for index in range(8)] == rects
        assert notation.horizontalScrollBar().value() == 0
    notation.set_position(8)
    assert notation.current_measure == 4 and notation.first_system == 1
    assert notation.measure_rect(4).top() == rects[0].top()
    assert notation.measure_rect(8).top() == rects[4].top()
    notation.grab()


def test_seek_repeat_and_song_end_choose_the_right_visible_systems(notation):
    for seconds, measure, first_system in ((20, 10, 2), (0, 0, 0), (10, 5, 1), (999, 19, 3), (8, 4, 1)):
        notation.set_position(seconds)
        assert notation.current_measure == measure and notation.first_system == first_system
        assert notation.viewport().rect().contains(notation.measure_rect(measure).toAlignedRect())
    assert notation.measure_rect(4).left() <= notation.beat_x(16) * notation.scale < notation.measure_rect(4).right()


def test_resizing_reflows_whole_lines_without_changing_score_or_position(notation, app):
    notation.set_position(18, "Am")
    score, segments = notation.score, notation.segments
    notation.resize(600, 500)
    app.processEvents()
    assert notation.position == 18 and notation.current_measure == 9 and notation.chord_text == "Am"
    assert notation.score is score and notation.segments is segments
    assert notation.systems[0][1] < 4
    assert notation.viewport().rect().contains(notation.measure_rect(9).toAlignedRect())
    notation.grab()


@pytest.mark.parametrize("bars,attacks", [(1, 4), (3, 4), (12, 32)])
def test_short_and_dense_scores_fit_without_horizontal_scrolling(notation, bars, attacks):
    notation.set_score(notation_score(bars, attacks))
    if attacks == 32:
        assert notation.systems[0][1] < 4
    for first, last in notation.systems:
        notation.set_position(notation.timeline.seconds_at(first * 4))
        assert 1 <= last - first <= 4
        for index in range(first, last):
            assert notation.viewport().rect().contains(notation.measure_rect(index).toAlignedRect())
        notation.grab()
    assert notation.horizontalScrollBar().maximum() == 0 and notation.verticalScrollBar().maximum() == 0


def test_meter_changes_ties_rests_and_explicit_hands_remain_in_the_generated_score(notation):
    timeline = ScoreTimeline(((0, 0, .5), (8, 4, 1)), ((0, 4, 4), (8, 3, 4)), 19)
    score = FallingScore((FallingNote(60, 0, 10, "left"), FallingNote(48, 6, 7, "right")), timeline)
    notation.set_score(score)
    assert notation._meter_change(2)
    assert not notation._meter_change(0)
    assert notation._hand(score.notes[0]) == "left" and notation._hand(score.notes[1]) == "right"
    assert notation.segments[0][0][4] and notation.segments[1][0][3]
    assert notation.segments[-1] == ()
    notation.set_position(6, "C")
    assert notation.current_measure == 2
    notation.grab()


@pytest.mark.parametrize("zoom,bars", [(50, 1), (100, 2), (125, 4), (200, 8)])
def test_explicit_line_density_and_zoom_preserve_notes_timing_and_position(notation, zoom, bars):
    notation.set_position(18, "Am")
    score, segments, original_scale = notation.score, notation.segments, notation.scale
    notation.set_layout_options(zoom, bars)
    assert notation.scale == pytest.approx(original_scale * zoom / 100)
    assert all(last - first == min(bars, 20 - first) for first, last in notation.systems)
    assert notation.score is score and notation.segments is segments
    assert notation.position == 18 and notation.current_measure == 9 and notation.chord_text == "Am"
    if zoom == 200:
        assert notation.horizontalScrollBar().maximum() > 0 and notation.verticalScrollBar().maximum() > 0
    notation.grab()


def test_full_score_can_browse_all_lines_and_follow_without_relaying_out_each_bar(app):
    widget = MidiNotationWidget(full_score=True)
    widget.resize(1200, 850)
    widget.show()
    app.processEvents()
    widget.set_layout_options(75, 4)
    widget.set_score(notation_score(40))
    try:
        assert widget.scale == .75 and len(widget.systems) == 10
        assert widget.verticalScrollBar().maximum() > 0
        bounds = widget.measure_bounds
        widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())
        assert widget.measure_rect(39).bottom() <= widget.viewport().height()
        widget.grab()
        widget.set_position(0)  # Reading by hand is not snapped back on a redundant update.
        assert widget.verticalScrollBar().value() == widget.verticalScrollBar().maximum()
        widget.set_position(.5)
        assert widget.verticalScrollBar().value() == 0  # A new target returns to an off-screen current line.
        widget.set_position(40)
        assert widget.current_measure == 20 and widget.first_system == 0
        assert widget.verticalScrollBar().value() > 0
        assert widget.viewport().rect().contains(widget.measure_rect(20).toAlignedRect())
        scroll = widget.verticalScrollBar().value()
        widget.set_position(42)
        assert widget.current_measure == 21 and widget.verticalScrollBar().value() == scroll
        assert widget.measure_bounds is bounds
        widget.set_score(notation_score(1))
        assert widget.current_measure == 0 and widget.verticalScrollBar().maximum() == 0
        widget.grab()
    finally:
        widget.close()


@pytest.mark.parametrize("zoom,bars", [(49, 0), (201, 4), (100, -1), (100, 9)])
def test_invalid_layout_options_are_rejected(notation, zoom, bars):
    with pytest.raises(ValueError):
        notation.set_layout_options(zoom, bars)
