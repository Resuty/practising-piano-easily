"""Follow fresh MIDI note attacks, allowing previous notes to remain held across groups."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AttackGroup:
    tick: int
    notes: frozenset[int]


def attack_groups(summary, track: int | None = None) -> tuple[AttackGroup, ...]:
    groups = {}
    for event in summary.notes:
        if event.channel != 9 and (track is None or event.track == track):
            groups.setdefault(event.start_tick, set()).add(event.note)
    return tuple(AttackGroup(tick, frozenset(notes)) for tick, notes in sorted(groups.items()))


class MidiScoreFollower:
    def __init__(self, groups, *, allow_empty=False):
        if not groups and not allow_empty:
            raise ValueError("No pitched notes in the selected MIDI section")
        self.groups = groups
        self.index = 0
        self.held = set()
        self.hits = set()
        self.mistakes = 0

    @property
    def finished(self):
        return self.index == len(self.groups)

    @property
    def expected(self):
        return frozenset() if self.finished else self.groups[self.index].notes - self.hits

    def event(self, event):
        note = event.note
        if note is None:
            return "ignored"
        if event.event_type == "note_off" or (event.event_type == "note_on" and event.velocity == 0):
            self.held.discard(note)
            return "released"
        if event.event_type != "note_on" or note in self.held or self.finished:
            return "ignored"
        self.held.add(note)
        if note not in self.groups[self.index].notes:
            self.mistakes += 1
            return "extra"
        self.hits.add(note)
        if self.hits == self.groups[self.index].notes:
            self.index += 1
            self.hits.clear()
            return "finished" if self.finished else "advanced"
        return "waiting"
