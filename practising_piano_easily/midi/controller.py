"""Threaded mido adapter; slow device discovery never blocks the window."""

from __future__ import annotations

import logging
import json
import subprocess
import sys
import threading
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .state import MidiEvent, MidiState


LOGGER = logging.getLogger(__name__)


class MidiController(QObject):
    devices_ready = Signal(list)
    status_changed = Signal(str)
    event_received = Signal(object)
    notes_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.state = MidiState()
        self._port = None
        self._lock = threading.Lock()
        self._closing = False
        self._scan_process: subprocess.Popen | None = None

    def refresh_devices(self) -> None:
        self.status_changed.emit("Searching for MIDI inputs…")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="mtl-midi-")
        output = Path(temporary.name) / "devices.json"
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--midi-scan", str(output)]
        else:
            command = [sys.executable, "-m", "practising_piano_easily.app", "--midi-scan", str(output)]
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._lock:
                if self._closing:
                    process.kill()
                    return
                self._scan_process = process
            stdout, stderr = process.communicate(timeout=8)
            if self._closing:
                return
            result = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
            if process.returncode or not isinstance(result, list):
                error = result.get("error") if isinstance(result, dict) else None
                raise RuntimeError(error or stderr.strip() or "MIDI scan process failed")
            names = result
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            if not self._closing:
                self.status_changed.emit("MIDI device scan timed out. Check the driver, then click Refresh.")
            names = []
        except Exception as exc:
            if not self._closing:
                LOGGER.exception("MIDI device discovery failed")
                self.status_changed.emit(f"MIDI unavailable: {exc}")
            names = []
        finally:
            with self._lock:
                self._scan_process = None
            temporary.cleanup()
        if not self._closing:
            self.devices_ready.emit(names)

    def connect_device(self, name: str) -> None:
        if not name:
            self.status_changed.emit("Choose a MIDI input first.")
            return
        self.status_changed.emit(f"Connecting to {name}…")
        threading.Thread(target=self._connect_worker, args=(name,), daemon=True).start()

    def _connect_worker(self, name: str) -> None:
        try:
            import mido

            new_port = mido.open_input(name, callback=self._receive)
            with self._lock:
                if self._closing:
                    new_port.close()
                    return
                self._close_locked()
                self._port = new_port
        except Exception as exc:
            LOGGER.exception("Could not open MIDI input")
            self.status_changed.emit(f"Could not open MIDI input: {exc}")
        else:
            self.status_changed.emit(f"Connected: {name}")

    def _receive(self, message: object) -> None:
        event_type = getattr(message, "type", "")
        if event_type not in {"note_on", "note_off", "control_change"}:
            return
        event = MidiEvent(
            event_type=event_type,
            note=getattr(message, "note", None),
            velocity=int(getattr(message, "velocity", 0)),
            control=getattr(message, "control", None),
            value=int(getattr(message, "value", 0)),
        )
        self._process(event)

    def demo_note(self, note: int, pressed: bool) -> None:
        self._process(MidiEvent("note_on" if pressed else "note_off", note=note, velocity=90 if pressed else 0))

    @property
    def pressed_notes(self) -> frozenset[int]:
        with self._lock:
            return frozenset(self.state.physically_pressed)

    def _process(self, event: MidiEvent) -> None:
        with self._lock:
            changed = self.state.process(event)
            pressed = frozenset(self.state.physically_pressed)
            pedal = self.state.sustain_down
        payload = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "event": event,
            "pedal": pedal,
        }
        LOGGER.debug("MIDI event: %s", payload)
        self.event_received.emit(payload)
        if changed:
            self.notes_changed.emit(pressed)

    def close(self) -> None:
        scan_process = None
        with self._lock:
            self._closing = True
            scan_process = self._scan_process
            self._close_locked()
            self.state.clear()
        if scan_process is not None and scan_process.poll() is None:
            scan_process.kill()
            try:
                scan_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass

    def _close_locked(self) -> None:
        if self._port is not None:
            self._port.close()
            self._port = None
