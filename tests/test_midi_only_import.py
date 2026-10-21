import mido
import pytest

from practising_piano_easily.analysis import online_scores
from practising_piano_easily.analysis.online_scores import import_score_files, downloaded_scores, download_score
from practising_piano_easily.ui.localized_widgets import QFileDialog
from practising_piano_easily.ui.falling_piano_page import FallingPianoPage
from test_falling_piano import app, win, make_midi


@pytest.mark.parametrize("provider,url", [("local", ""), ("musescore", "https://musescore.com/score/123"),
                                          ("ichigos", "https://ichigos.com/sheets/42"),
                                          ("ninsheetmusic", "https://www.ninsheetmusic.org/browse/series/Test")])
def test_midi_only_import_is_offline_keeps_original_and_survives_rescan(tmp_path, monkeypatch, provider, url):
    original = tmp_path / "song.mid.mid"
    make_midi(original)
    contents = original.read_bytes()
    directory = tmp_path / "library"
    with pytest.raises(ValueError):
        import_score_files(original, None, "Song", url, False, directory, provider=provider)
    monkeypatch.setattr(online_scores, "fetch_bytes", lambda *a, **k: pytest.fail("No network on local import/open"))
    score, folder = import_score_files(original, None, "Song", url, True, directory, provider=provider, arranger="Original credit")
    assert original.read_bytes() == contents == (folder / "score.mid").read_bytes()
    assert not (folder / "score.pdf").exists()
    assert score.composer == "Original credit" and score.source_url == url
    assert "not an open-license claim" in score.license
    assert downloaded_scores(directory) == [score]
    assert download_score(score, directory) == folder
    assert import_score_files(original, None, "Song", url, True, directory, provider=provider, arranger="Original credit") == (score, folder)
    assert len(list(directory.glob("*/source.json"))) == 1


@pytest.mark.parametrize("invalid", ["header", "empty", "drums", "type2", "tempo", "oversize"])
def test_invalid_midi_only_import_does_not_create_partial_library_entries(tmp_path, monkeypatch, invalid):
    original = tmp_path / "invalid.mid"
    if invalid == "header":
        original.write_bytes(b"not midi")
    else:
        midi = mido.MidiFile(type=2 if invalid == "type2" else 1)
        track = mido.MidiTrack()
        if invalid != "empty":
            track.extend((mido.Message("note_on", channel=9 if invalid == "drums" else 0, note=60, velocity=90),
                          mido.Message("note_off", channel=9 if invalid == "drums" else 0, note=60, time=480)))
        if invalid == "tempo":
            track.append(mido.MetaMessage("set_tempo", tempo=0))
        midi.tracks.append(track)
        midi.save(original)
    if invalid == "oversize":
        monkeypatch.setattr(online_scores, "MAX_BYTES", 8)
    directory = tmp_path / "library"
    with pytest.raises(ValueError):
        import_score_files(original, None, "Song", "", True, directory, provider="local")
    assert not directory.exists()


def test_local_source_does_not_enable_network_links_or_skip_website_checks(tmp_path):
    original = tmp_path / "song.mid"
    make_midi(original)
    with pytest.raises(ValueError):
        import_score_files(original, None, "Song", "https://example.com/song", True, tmp_path / "library", provider="local")
    with pytest.raises(ValueError):
        import_score_files(original, None, "Song", "https://evil.test/score/1", True, tmp_path / "library", provider="musescore")
    with pytest.raises(ValueError):
        online_scores.checked_url("https://example.com/song", "local")


def test_midi_only_gui_import_enters_both_libraries_and_generated_score_and_restores(win, tmp_path, monkeypatch, app):
    original = tmp_path / "Anime Piano.midi"
    make_midi(original)
    directory = tmp_path / "library"
    service = import_score_files
    monkeypatch.setattr("practising_piano_easily.ui.musescore_page.import_score_files",
                        lambda *a, **k: service(*a, **k, directory=directory))
    monkeypatch.setattr("practising_piano_easily.ui.online_library_page.downloaded_scores", lambda: downloaded_scores(directory))
    monkeypatch.setattr("practising_piano_easily.ui.online_library_page.score_folder", lambda score: online_scores.score_folder(score, directory))
    imported = win.online_library.musescore
    assert imported.source_provider.currentData() == "local"
    assert not imported.source_input.isEnabled() and not imported.clear_pdf.isEnabled()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(original), ""))
    imported.midi_button.click()
    assert imported.title_input.text() == "Anime Piano"
    imported.import_button.click()
    assert "Import failed" in imported.status.source_text
    imported.permission.setChecked(True)
    imported.import_button.click()
    source = downloaded_scores(directory)[0]
    folder = online_scores.score_folder(source, directory)
    practice = win.online_library.practice
    assert practice.source == source and practice.document.pageCount() == 0
    assert practice.score_views.currentWidget() is practice.midi_staff
    win.online_library.show_downloaded()
    assert win.online_library.table.rowCount() == 1
    assert win.online_library.download_button.isEnabled() and not win.online_library.source_button.isEnabled()
    assert win.online_library.table.item(0, 3).text() == "仅 MIDI"
    key = f"local:{source.id}"
    page = win.falling
    assert page.source_picker.findData(key) >= 0
    page.source_picker.setCurrentIndex(page.source_picker.findData(key))
    win.navigation.setCurrentRow(14)
    assert page.source_info == source and page.session is not None
    assert page.range_mode.currentIndex() == 0 and not page.score_mode.isEnabled()
    assert page.score_views.currentWidget() is page.midi_staff and page.document.pageCount() == 0
    page.score_mode.setCurrentIndex(1)  # A programmatic request must not reveal a blank PDF view either.
    assert page.score_views.currentWidget() is page.midi_staff
    page.save_last_song()
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.downloaded_scores", lambda: [source])
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.score_folder", lambda item: folder)
    restored = FallingPianoPage(win.controller, win.database, win.session_id)
    assert restored.source_picker.currentData() == key and restored.session is not None
    assert not restored.session.running and restored.document.pageCount() == 0
    restored.setParent(win)
