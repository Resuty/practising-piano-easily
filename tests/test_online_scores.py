import io
import json
import os
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
import pytest
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from practising_piano_easily.analysis import online_scores
from practising_piano_easily.analysis.midi_file import load_midi
from practising_piano_easily.analysis.online_scores import (BASE, CatalogParser, checked_url, download_score, downloaded_scores,
                                                       import_musescore_score, musescore_search_url)
from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.midi.state import MidiEvent
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.midi_score import attack_groups, MidiScoreFollower
from practising_piano_easily.ui.downloaded_score_page import DownloadedScorePage


HTML = '''<table class="outer-table"><tr><td><table class="table-bordered result-table">
<tr><td>Melody &amp; variation</td><td>by Test Composer</td></tr>
<tr><td>for Piano</td></tr>
<tr><td>Old edition</td><td><a href="../legal.html#publicdomain">Public Domain</a></td>
<td><a href="piece-info.cgi?id=123">More Information</a></td></tr>
<tr><td><a href="https://www.mutopiaproject.org/ftp/Test/piece.mid">.mid file</a></td></tr>
<tr><td><a href="https://www.mutopiaproject.org/ftp/Test/piece-a4.pdf">A4 .pdf file</a></td></tr>
</table></td></tr></table>'''


def source():
    parser = CatalogParser()
    parser.feed(HTML)
    return parser.scores[0]


def midi_bytes():
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.extend([
        mido.Message("note_on", note=60, velocity=90, time=0),
        mido.Message("note_on", note=64, velocity=90, time=0),
        mido.Message("note_off", note=60, time=480),
        mido.Message("note_off", note=64, time=0),
        mido.Message("note_on", note=60, velocity=90, time=0),
        mido.Message("note_off", note=60, time=480),
    ])
    stream = io.BytesIO()
    midi.save(file=stream)
    return stream.getvalue()


def test_catalog_extracts_licensed_pairs_and_resolves_relative_links():
    score = source()
    assert score.id == "123" and score.title == "Melody & variation"
    assert score.source_url == BASE + "/cgibin/piece-info.cgi?id=123"
    assert score.license == "Public Domain"
    parser = CatalogParser()
    parser.feed(HTML.replace("Public Domain", "All rights reserved"))
    assert parser.scores == []
    parser = CatalogParser()
    parser.feed(HTML.replace(BASE + "/ftp/Test/piece.mid", "https://example.org/private.mid"))
    assert parser.scores == []


@pytest.mark.parametrize("url", ["http://www.mutopiaproject.org/x", "file:///x", "https://127.0.0.1/x",
                                     "https://www.mutopiaproject.org.evil.test/x", "https://user@www.mutopiaproject.org/x"])
def test_catalog_urls_stay_on_the_source(url):
    with pytest.raises(ValueError):
        checked_url(url)


def test_search_uses_solo_piano_and_composer_aliases(monkeypatch):
    urls = []
    def fetch(url, limit):
        urls.append(url)
        return HTML.encode()
    monkeypatch.setattr(online_scores, "fetch_bytes", fetch)
    result = online_scores.search_scores("舒曼", 10)
    query = parse_qs(urlparse(urls[0]).query)
    assert query == {"Instrument": ["Piano"], "solo": ["1"], "searchingfor": ["Schumann"], "startat": ["10"]}
    assert result[0].id == "123"


def test_download_preserves_attribution_and_reopens_without_network(tmp_path, monkeypatch):
    score = source()
    monkeypatch.setattr(online_scores, "fetch_bytes", lambda url: midi_bytes() if url.endswith(".mid") else b"%PDF-1.4\nfixture")
    folder = download_score(score, tmp_path)
    assert load_midi(folder / "score.mid").notes
    metadata = json.loads((folder / "source.json").read_text(encoding="utf-8"))
    assert metadata["license"] == "Public Domain" and metadata["source_url"] == score.source_url
    assert downloaded_scores(tmp_path) == [score]
    def no_network(url):
        raise AssertionError("Offline cache must not use the network")
    monkeypatch.setattr(online_scores, "fetch_bytes", no_network)
    assert download_score(score, tmp_path) == folder


def test_invalid_downloads_never_create_an_offline_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(online_scores, "fetch_bytes", lambda url: b"<html>Server error</html>")
    with pytest.raises(ValueError):
        download_score(source(), tmp_path)
    assert downloaded_scores(tmp_path) == []
    with pytest.raises(ValueError):
        download_score(replace(source(), id="../../outside"), tmp_path)
    with pytest.raises(ValueError):
        download_score(replace(source(), license="Unknown"), tmp_path)


def test_midi_follower_requires_new_attacks_but_allows_sustained_previous_notes():
    summary = load_midi(mido.MidiFile(file=io.BytesIO(midi_bytes())))
    groups = attack_groups(summary)
    assert [group.notes for group in groups] == [frozenset({60, 64}), frozenset({60})]
    follower = MidiScoreFollower(groups)
    assert follower.event(MidiEvent("note_on", note=60, velocity=90)) == "waiting"
    assert follower.event(MidiEvent("note_on", note=60, velocity=90)) == "ignored"
    assert follower.event(MidiEvent("note_on", note=64, velocity=90)) == "advanced"
    assert follower.event(MidiEvent("note_on", note=60, velocity=90)) == "ignored"
    follower.event(MidiEvent("note_on", note=60, velocity=0))
    assert follower.event(MidiEvent("note_on", note=60, velocity=90)) == "finished"
    assert 64 in follower.held


def test_downloaded_pdf_and_midi_practice_complete_in_the_gui(tmp_path):
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "piece"
    folder.mkdir()
    (folder / "score.mid").write_bytes(midi_bytes())
    writer = QPdfWriter(str(folder / "score.pdf"))
    painter = QPainter(writer)
    painter.drawText(100, 100, "PDF score fixture")
    painter.end()
    del painter, writer
    db = Database(":memory:")
    controller = MidiController()
    page = DownloadedScorePage(controller, db, db.start_session())
    try:
        page.open_score(source(), folder)
        assert page.document.pageCount() == 1
        page.show()
        app.processEvents()
        page.start_practice()
        controller.demo_note(61, True)
        controller.demo_note(61, False)
        controller.demo_note(60, True)
        controller.demo_note(64, True)
        controller.demo_note(60, False)
        controller.demo_note(60, True)
        assert page.follower.finished
        row = db.connection.execute("SELECT * FROM attempts").fetchone()
        assert row["trainer_type"] == "downloaded_score" and not row["correct"]
        assert json.loads(row["metadata_json"])["license"] == "Public Domain"
        page._save_result()
        assert db.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
    finally:
        page.close()
        page.document.close()
        controller.close()
        db.close()


def test_musescore_import_keeps_originals_source_and_permission_separate_from_open_license(tmp_path, monkeypatch):
    midi_path, pdf_path = tmp_path / "original.mid", tmp_path / "original.pdf"
    midi_path.write_bytes(midi_bytes())
    pdf_path.write_bytes(b"%PDF-1.4\nfixture")
    original_midi = midi_path.read_bytes()
    directory = tmp_path / "library"
    url = "https://musescore.com/openscore/scores/123456"
    with pytest.raises(ValueError):
        import_musescore_score(midi_path, pdf_path, "Song", url, False, directory)
    for invalid in ("https://evil.test/score/1", "file:///score/1", "https://musescore.com.evil.test/score/1", "https://musescore.com/openscore"):
        with pytest.raises(ValueError):
            import_musescore_score(midi_path, pdf_path, "Song", invalid, True, directory)
    score, folder = import_musescore_score(midi_path, pdf_path, "Song", url, True, directory)
    assert score.provider == "musescore" and score.source_url == url
    assert "not an open-license claim" in score.license
    assert downloaded_scores(directory) == [score]
    assert midi_path.read_bytes() == original_midi and pdf_path.exists()
    assert folder.name.startswith("musescore-")
    monkeypatch.setattr(online_scores, "fetch_bytes", lambda url: pytest.fail("Local import must work offline"))
    assert download_score(score, directory) == folder
    query = parse_qs(urlparse(musescore_search_url("小星星 + easy piano")).query)
    assert query["text"] == ["小星星 + easy piano"]
    midi_path.write_bytes(b"MThd-invalid")
    with pytest.raises(ValueError):
        import_musescore_score(midi_path, pdf_path, "Song", url, True, directory)


def test_musescore_gui_import_opens_pdf_and_midi_follower(tmp_path, monkeypatch):
    from practising_piano_easily.ui.musescore_page import MuseScorePage

    app = QApplication.instance() or QApplication([])
    midi_path, pdf_path = tmp_path / "song.mid", tmp_path / "song.pdf"
    midi_path.write_bytes(midi_bytes())
    writer = QPdfWriter(str(pdf_path))
    painter = QPainter(writer)
    painter.drawText(100, 100, "MuseScore import fixture")
    painter.end()
    del painter, writer
    original = online_scores.import_musescore_score
    monkeypatch.setattr("practising_piano_easily.ui.musescore_page.import_musescore_score",
                        lambda *args: original(*args, directory=tmp_path / "library"))
    page = MuseScorePage()
    page.set_source("musescore")
    received = []
    page.imported.connect(received.append)
    page.midi_path, page.pdf_path = midi_path, pdf_path
    page.title_input.setText("Imported song")
    page.source_input.setText("https://musescore.com/score/123456")
    page.permission.setChecked(True)
    page.import_button.click()
    assert len(received) == 1
    score, folder = received[0]
    db = Database(":memory:")
    controller = MidiController()
    practice = DownloadedScorePage(controller, db, db.start_session())
    practice.open_score(score, folder)
    assert practice.document.pageCount() == 1 and len(practice.groups) == 2
    practice.show()
    app.processEvents()
    practice.start_practice()
    for note, pressed in ((60, True), (64, True), (60, False), (60, True)):
        controller.demo_note(note, pressed)
    row = db.connection.execute("SELECT * FROM attempts").fetchone()
    assert row["question"].startswith("musescore:")
    practice.close()
    practice.document.close()
    page.close()
    controller.close()
    db.close()
