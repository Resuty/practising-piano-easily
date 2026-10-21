from practising_piano_easily.midi import MidiEvent, MidiState


def test_velocity_zero_duplicate_events_and_release_order():
    state = MidiState()
    assert state.process(MidiEvent("note_on", note=60, velocity=90))
    assert not state.process(MidiEvent("note_on", note=60, velocity=90))
    state.process(MidiEvent("note_on", note=64, velocity=80))
    state.process(MidiEvent("note_on", note=60, velocity=0))
    assert state.physically_pressed == {64}
    assert state.sounding_notes == {64}
    assert not state.process(MidiEvent("note_off", note=60))


def test_sustain_keeps_sounding_notes_but_not_physical_notes():
    state = MidiState()
    state.process(MidiEvent("note_on", note=60, velocity=90))
    state.process(MidiEvent("control_change", control=64, value=127))
    state.process(MidiEvent("note_off", note=60))
    assert state.physically_pressed == set()
    assert state.sounding_notes == {60}
    assert state.sustain_down
    state.process(MidiEvent("control_change", control=64, value=0))
    assert state.sounding_notes == set()
    assert not state.sustain_down

