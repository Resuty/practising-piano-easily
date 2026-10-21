import random

from practising_piano_easily.core import Chord, parse_note
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.chord_construction import ChordConstructionTrainer, match_chord


def test_octave_doubling_missing_extra_and_inversions():
    chord = Chord(parse_note("C"), "major")
    assert match_chord(chord, {48, 52, 55, 60}, False).correct
    assert not match_chord(chord, {48, 52}, False).correct
    assert not match_chord(chord, {48, 52, 55, 62}, False).correct
    inversion = {52, 55, 60}
    assert not match_chord(chord, inversion, False).correct
    assert match_chord(chord, inversion, True).correct


def test_settling_attempt_is_scored_once_and_saved():
    database = Database(":memory:")
    session_id = database.start_session()
    trainer = ChordConstructionTrainer(database, session_id, random.Random(2))
    trainer.current_chord = Chord(parse_note("D"), "minor")
    trainer.question_started = 10.0
    assert trainer.set_active_notes({50, 53, 57}) == "settle"
    result = trainer.evaluate(now=11.25)
    assert result.correct
    assert result.response_time_ms == 1250
    assert trainer.evaluate(now=12.0) is None
    assert database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
    assert trainer.set_active_notes(set()) == "advance"
    database.close()


def test_wrong_attempt_retries_after_full_release_and_question_bag_is_balanced():
    database = Database(":memory:")
    trainer = ChordConstructionTrainer(database, database.start_session(), random.Random(4))
    trainer.current_chord = Chord(parse_note("E"), "minor")
    trainer.question_started = 0.0
    trainer.set_active_notes({52, 56, 59})
    assert not trainer.evaluate(now=1.0).correct
    assert trainer.set_active_notes(set()) == "released"
    trainer.set_active_notes({52, 55, 59})
    assert trainer.evaluate(now=2.0).correct

    symbols = []
    trainer._bag = []
    previous = trainer.current_chord
    for index in range(14):
        trainer.next_question(now=float(index))
        assert trainer.current_chord != previous
        symbols.append(trainer.current_chord)
        previous = trainer.current_chord
    assert sum(chord.quality == "major" for chord in symbols) == 7
    assert sum(chord.quality == "minor" for chord in symbols) == 7
    database.close()


def test_adaptive_weighting_makes_a_weak_item_more_likely():
    class WeightedDatabase:
        def mastery_for_skill(self, skill):
            return {"C": (1.0, 10_000.0)}

    trainer = ChordConstructionTrainer(WeightedDatabase(), 1, random.Random(8))
    counts = {root: 0 for root in "CDEFGAB"}
    for _ in range(600):
        if trainer.current_chord.quality == "major":
            counts[str(trainer.current_chord.root)] += 1
        trainer.next_question()
    assert counts["C"] > 100
    assert counts["C"] > max(value for root, value in counts.items() if root != "C")
