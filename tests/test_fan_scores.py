import io
import json
import os
from dataclasses import replace
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QPainter, QPdfWriter, QDesktopServices
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from practising_piano_easily.analysis import online_scores, fan_scores
from practising_piano_easily.analysis.fan_scores import IchigosParser, search_ichigos, fan_search_url
from practising_piano_easily.analysis.online_scores import download_score, downloaded_scores, import_score_files, checked_url
from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.storage import Database
from practising_piano_easily.ui.online_library_page import OnlineLibraryPage
from practising_piano_easily.ui.i18n import language


HTML = '''<span class='title2'><a href='/sheets/42'>Test Anime &amp; Game</a></span><br><br>
Same Song (Transcribed by Alpha)<br><i>for Piano</i> |
<a href='/res/getfile.php?id=101&type=pdf&token=old'>pdf</a> |
<a href='/res/getfile.php?id=101&type=midi&token=old'>midi</a> | <br><br>
Same Song (Transcribed by Beta)<br><i>for easier piano</i> |
<a href='/res/getfile.php?id=102&type=pdf&token=old'>pdf</a> | <br><br>
Violin Song (Transcribed by Other)<br><i>for Violin</i> |
<a href='/res/getfile.php?id=103&type=pdf'>pdf</a> |
<a href='/res/getfile.php?id=103&type=midi'>midi</a> | <br><br>
Unsafe (Transcribed by Other)<br><i>for Piano</i> |
<a href='https://evil.test/res/getfile.php?id=104&type=pdf'>pdf</a> |
<a href='/res/getfile.php?id=104&type=midi'>midi</a> | <br><br>
Mismatched IDs (Transcribed by Other)<br><i>for Piano</i> |
<a href='/res/getfile.php?id=105&type=pdf'>pdf</a> |
<a href='/res/getfile.php?id=106&type=midi'>midi</a> | <br><br>
Ensemble (Transcribed by Gamma)<br><i>for Piano and Flute</i> |
<a href='/res/getfile.php?id=107&type=pdf'>pdf</a> |
<a href='/res/getfile.php?id=107&type=midi'>midi</a>'''


def parse(html=HTML):
    parser = IchigosParser()
    parser.feed(html)
    parser.close()
    return parser.scores


def midi_bytes():
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    for note in (60, 62):
        track.extend((mido.Message("note_on", note=note, velocity=90),
                      mido.Message("note_off", note=note, time=480)))
    stream = io.BytesIO()
    midi.save(file=stream)
    return stream.getvalue()


def pdf_bytes(tmp_path):
    QApplication.instance() or QApplication([])
    path = tmp_path / "original.pdf"
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    painter.drawText(100, 100, "Fan score fixture; original credits")
    painter.end()
    del painter, writer
    return path.read_bytes()


def run_until(signal, action):
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    spy = QSignalSpy(signal)
    signal.connect(loop.quit)
    action()
    if not spy.count():
        timer.start(3000)
        loop.exec()
    timer.stop()
    signal.disconnect(loop.quit)
    assert spy.count(), "The asynchronous operation did not complete"
    # The spy can see a worker emission before Qt has delivered the GUI's queued slot.
    QApplication.processEvents()


def test_ichigos_keeps_versions_separate_and_marks_pdf_only_without_mixing_links():
    scores = parse()
    assert [score.id for score in scores] == ["101", "102", "105", "107"]
    assert scores[0].title == "Test Anime & Game · Same Song"
    assert scores[0].composer == "Alpha" and scores[1].composer == "Beta"
    assert scores[0].source_url == "https://ichigos.com/sheets/42"
    assert scores[0].license == online_scores.ICHIGO_LICENSE
    assert scores[0].license_url == "https://ichigos.com/legal"
    assert not scores[1].midi_url and not scores[2].midi_url
    assert scores[-1].instrumentation == "for Piano and Flute"


def test_ichigos_posts_actual_search_fields_and_translates_known_titles(monkeypatch):
    calls = []
    def fetch(url, limit, *, provider, data):
        calls.append((url, provider, parse_qs(data.decode())))
        return HTML.encode()
    monkeypatch.setattr(fan_scores, "fetch_bytes", fetch)
    assert len(search_ichigos("原神")) == 4
    assert calls == [("https://ichigos.com/sheets", "ichigos", {
        "qtitle": ["Genshin Impact"], "qdesc": ["piano"], "q": ["1"],
    })]
    with pytest.raises(ValueError):
        search_ichigos(" ")
    assert len(calls) == 1


@pytest.mark.parametrize("provider,host", [("ichigos", "ichigos.com"), ("ninsheetmusic", "www.ninsheetmusic.org")])
def test_fan_sources_reject_other_hosts_credentials_http_and_redirects(provider, host):
    assert checked_url("https://" + host + "/browse", provider)
    for url in ("http://" + host + "/x", "https://" + host + ".evil.test/x",
                "https://user@" + host + "/x", "https://127.0.0.1/x", "file:///x",
                "https://" + host + ":8443/x"):
        with pytest.raises(ValueError):
            checked_url(url, provider)
    with pytest.raises(ValueError):
        online_scores._Redirects(provider).redirect_request(Request("https://" + host), None, 302, "", {}, "https://evil.test/file")
    with pytest.raises(ValueError):
        checked_url("https://ichigos.com/x")  # Mutopia's default trust boundary is unchanged.


def test_ichigos_permission_refresh_download_attribution_and_offline_reopen(tmp_path, monkeypatch):
    pdf = pdf_bytes(tmp_path)
    calls = []
    def fetch(url, *args, **kwargs):
        calls.append(url)
        if "/sheets/42" in url:
            return HTML.replace("token=old", "token=fresh").encode()
        params = parse_qs(urlparse(url).query)
        assert params["token"] == ["fresh"]
        return midi_bytes() if params["type"] == ["midi"] else pdf
    monkeypatch.setattr(fan_scores, "fetch_bytes", fetch)
    monkeypatch.setattr(online_scores, "fetch_bytes", fetch)
    score = parse()[0]
    with pytest.raises(ValueError):
        download_score(score, tmp_path)
    assert calls == []
    folder = download_score(score, tmp_path, personal_use=True)
    assert len(calls) == 3
    saved = downloaded_scores(tmp_path)[0]
    assert saved.composer == "Alpha" and saved.provider == "ichigos"
    assert saved.license == score.license and saved.source_url == score.source_url
    assert "token=fresh" in saved.midi_url
    assert download_score(score, tmp_path) == folder and len(calls) == 3
    assert (folder / "score.pdf").read_bytes() == pdf
    with pytest.raises(ValueError):
        download_score(parse()[1], tmp_path, personal_use=True)
    assert not (tmp_path / "ichigos-102").exists()
    with pytest.raises(ValueError):
        download_score(replace(score, id="../outside"), tmp_path, personal_use=True)


def test_ichigos_failed_pair_download_never_adds_to_offline_library(tmp_path, monkeypatch):
    monkeypatch.setattr(fan_scores, "fetch_bytes", lambda *args, **kwargs: HTML.encode())
    monkeypatch.setattr(online_scores, "fetch_bytes", lambda *args, **kwargs: b"<html>Server error</html>")
    with pytest.raises(ValueError):
        download_score(parse()[0], tmp_path, personal_use=True)
    assert downloaded_scores(tmp_path) == []


@pytest.mark.parametrize("provider,url", [("ichigos", "https://ichigos.com/sheets/42"),
                                           ("ninsheetmusic", "https://www.ninsheetmusic.org/browse/series/TestGame")])
def test_fan_file_import_preserves_originals_and_requires_permission(tmp_path, provider, url):
    midi_path, pdf_path = tmp_path / "original.mid", tmp_path / "original.pdf"
    midi_path.write_bytes(midi_bytes())
    pdf = pdf_bytes(tmp_path)
    with pytest.raises(ValueError):
        import_score_files(midi_path, pdf_path, "Game song", url, False, tmp_path, provider=provider)
    score, folder = import_score_files(midi_path, pdf_path, "Game song", url, True, tmp_path,
                                       provider=provider, arranger="Original arranger")
    assert folder.name.startswith(provider + "-")
    assert score.composer == "Original arranger" and score.source_url == url
    assert "not an open-license claim" in score.license
    assert downloaded_scores(tmp_path) == [score]
    assert download_score(score, tmp_path) == folder
    assert midi_path.read_bytes() == midi_bytes() and pdf_path.read_bytes() == pdf
    with pytest.raises(ValueError):
        import_score_files(midi_path, pdf_path, "Song", "https://evil.test/browse", True, tmp_path, provider=provider)


def test_ninsheetmusic_browser_search_is_site_restricted_and_has_a_catalog_fallback():
    assert fan_search_url("ninsheetmusic") == "https://www.ninsheetmusic.org/browse"
    query = parse_qs(urlparse(fan_search_url("ninsheetmusic", "原神 & piano")).query)["q"][0]
    assert query.startswith("site:ninsheetmusic.org ") and "Genshin Impact & piano" in query
    with pytest.raises(ValueError):
        fan_search_url("unknown", "Song")


def test_ninsheetmusic_does_not_attempt_to_bypass_browser_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(online_scores, "fetch_bytes", lambda *args, **kwargs: pytest.fail("No restricted download attempts"))
    with pytest.raises(ValueError, match="browser"):
        download_score(replace(parse()[0], provider="ninsheetmusic"), tmp_path, personal_use=True)


def test_library_ichigos_search_filter_download_and_follow_in_gui(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    pdf = pdf_bytes(tmp_path)
    directory = tmp_path / "library"
    def fetch(url, *args, **kwargs):
        if "/sheets" in url:
            return HTML.encode()
        params = parse_qs(urlparse(url).query)
        return midi_bytes() if params["type"] == ["midi"] else pdf
    monkeypatch.setattr(fan_scores, "fetch_bytes", fetch)
    monkeypatch.setattr(online_scores, "fetch_bytes", fetch)
    monkeypatch.setattr("practising_piano_easily.ui.online_library_page.download_score",
                        lambda score, **kwargs: download_score(score, directory, **kwargs))
    monkeypatch.setattr("practising_piano_easily.ui.online_library_page.score_folder",
                        lambda score: online_scores.score_folder(score, directory))
    monkeypatch.setattr("practising_piano_easily.ui.online_library_page.downloaded_scores", lambda: downloaded_scores(directory))
    db = Database(":memory:")
    controller = MidiController()
    page = OnlineLibraryPage(controller, db, db.start_session())
    page.resize(1000, 720)
    page.show()
    app.processEvents()
    assert page.currentIndex() == 0 and page.provider.currentData() == "ichigos"
    run_until(page.search_ready, page.search_button.click)
    assert page.table.rowCount() == 2
    assert not page.download_button.isEnabled()
    page.pairs_only.setChecked(False)
    assert page.table.rowCount() == 4
    page.table.selectRow(1)
    assert not page.download_button.isEnabled()
    language.set_language("en")
    assert page.table.currentRow() == 1 and not page.download_button.isEnabled()
    language.set_language("zh_CN")
    page.table.selectRow(0)
    page.personal_use.setChecked(True)
    assert page.download_button.isEnabled()
    run_until(page.download_ready, page.download_button.click)
    assert page.currentWidget() is page.practice and page.practice.document.pageCount() == 1
    page.practice.start_practice()
    for note in (60, 62):
        controller.demo_note(note, True)
        controller.demo_note(note, False)
    row = db.connection.execute("SELECT * FROM attempts").fetchone()
    assert row["question"].startswith("ichigos:101:")
    assert json.loads(row["metadata_json"])["license"] == online_scores.ICHIGO_LICENSE
    page.setCurrentIndex(0)
    page.local_button.click()
    assert page.table.rowCount() == 1 and page.download_button.isEnabled()
    assert not page.previous.isEnabled() and not page.next.isEnabled()
    page.close()
    page.practice.document.close()
    controller.close()
    db.close()


def test_ninsheetmusic_browser_handoff_and_local_import_open_the_same_follower(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    pdf_bytes(tmp_path)
    midi_path = tmp_path / "game.mid"
    midi_path.write_bytes(midi_bytes())
    urls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: urls.append(url.toString()) or True)
    original = import_score_files
    monkeypatch.setattr("practising_piano_easily.ui.musescore_page.import_score_files",
                        lambda *args, **kwargs: original(*args, **kwargs, directory=tmp_path / "library"))
    db = Database(":memory:")
    controller = MidiController()
    page = OnlineLibraryPage(controller, db, db.start_session())
    page.show()
    app.processEvents()
    page.provider.setCurrentIndex(page.provider.findData("ninsheetmusic"))
    language.set_language("en")
    assert page.provider.currentData() == "ninsheetmusic"
    language.set_language("zh_CN")
    page.query.setText("原神")
    page.search_button.click()
    assert page.currentWidget() is page.musescore
    assert "site:ninsheetmusic.org" in parse_qs(urlparse(urls[-1]).query)["q"][0]
    imported = page.musescore
    assert imported.source_provider.currentData() == "ninsheetmusic"
    imported.midi_path, imported.pdf_path = midi_path, tmp_path / "original.pdf"
    imported.title_input.setText("Angel Beats! · My Soul, Your Beats")
    imported.arranger_input.setText("Arranger")
    imported.source_input.setText("https://www.ninsheetmusic.org/browse/series/TestGame")
    imported.permission.setChecked(True)
    imported.import_button.click()
    assert page.currentWidget() is page.practice
    assert page.practice.source.provider == "ninsheetmusic"
    assert page.practice.title.text().startswith("Angel Beats! · My Soul, Your Beats · Arranger")
    language.set_language("en")
    assert page.practice.title.text().startswith("Angel Beats! · My Soul, Your Beats · Arranger")
    language.set_language("zh_CN")
    page.practice.start_practice()
    for note in (60, 62):
        controller.demo_note(note, True)
        controller.demo_note(note, False)
    row = db.connection.execute("SELECT * FROM attempts").fetchone()
    assert row["question"].startswith("ninsheetmusic:")
    page.close()
    page.practice.document.close()
    controller.close()
    db.close()
