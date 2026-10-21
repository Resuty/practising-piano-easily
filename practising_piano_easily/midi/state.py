"""MIDI state independent of mido and the GUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MidiEvent:
    event_type: str
    note: int | None = None
    velocity: int = 0
    control: int | None = None
    value: int = 0


class MidiState:
    def __init__(self) -> None:
        self.physically_pressed: set[int] = set()
        self.sounding_notes: set[int] = set()
        self.sustain_down = False

    def process(self, event: MidiEvent) -> bool:
        before = (self.physically_pressed.copy(), self.sounding_notes.copy(), self.sustain_down)
        if event.event_type == "note_on" and event.note is not None:
            if event.velocity > 0:
                self.physically_pressed.add(event.note)
                self.sounding_notes.add(event.note)
            else:
                self._note_off(event.note)
        elif event.event_type == "note_off" and event.note is not None:
            self._note_off(event.note)
        elif event.event_type == "control_change" and event.control == 64:
            self.sustain_down = event.value >= 64
            if not self.sustain_down:
                self.sounding_notes.intersection_update(self.physically_pressed)
        return before != (self.physically_pressed, self.sounding_notes, self.sustain_down)

    def _note_off(self, note: int) -> None:
        self.physically_pressed.discard(note)
        if not self.sustain_down:
            self.sounding_notes.discard(note)

    def clear(self) -> None:
        self.physically_pressed.clear()
        self.sounding_notes.clear()
        self.sustain_down = False

