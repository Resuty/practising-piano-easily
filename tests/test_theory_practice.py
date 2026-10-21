import random

from practising_piano_easily.trainers.theory_practice import TheoryPracticeGenerator, TheoryQuestion, check_answer, check_notes


def test_all_theory_practice_kinds_generate_checkable_questions():
    generator = TheoryPracticeGenerator(random.Random(5))
    for kind in ("Interval construction", "Scale", "Diatonic chord", "Roman: symbol → chord",
                 "Roman: chord → function", "Inversion"):
        question = generator.question(kind)
        assert question.prompt and question.answer_text
        if question.answer is not None:
            assert check_answer(question, question.answer)


def test_scale_requires_order_and_inversion_requires_bass():
    generator = TheoryPracticeGenerator(random.Random(9))
    scale = generator.question("Scale")
    start = 60 + ((scale.expected_sequence[0] - 0) % 12)
    notes = [start]
    for pitch_class in scale.expected_sequence[1:]:
        note = notes[-1] + 1
        while note % 12 != pitch_class:
            note += 1
        notes.append(note)
    assert check_notes(scale, notes)
    assert not check_notes(scale, list(reversed(notes)))

    inversion = generator.question("Inversion")
    bass_note = 48 + inversion.bass_pitch_class
    correct = [bass_note]
    for pitch_class in inversion.expected_pitch_classes - {inversion.bass_pitch_class}:
        note = bass_note + 1
        while note % 12 != pitch_class:
            note += 1
        correct.append(note)
    assert min(correct) % 12 == inversion.bass_pitch_class
    assert check_notes(inversion, correct)


def test_octave_interval_requires_two_ascending_notes():
    octave = TheoryQuestion(
        "Interval construction", "Octave above C", "C C", frozenset({0}),
        expected_sequence=(0, 0), bass_pitch_class=0,
    )
    assert check_notes(octave, [60, 72])
    assert not check_notes(octave, [60])
    assert not check_notes(octave, [72, 60])
