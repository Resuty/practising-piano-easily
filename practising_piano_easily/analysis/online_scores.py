"""Source-checked score downloads and local, attributed PDF/MIDI imports."""

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
import json
import hashlib
import io
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode, urljoin, urlparse, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler

from practising_piano_easily.paths import data_directory


BASE = "https://www.mutopiaproject.org"
SCORES_DIRECTORY = data_directory() / "scores"
MAX_BYTES = 15 * 1024 * 1024
COMPOSER_ALIASES = {"巴赫": "Bach", "莫扎特": "Mozart", "贝多芬": "Beethoven",
                    "舒曼": "Schumann", "舒伯特": "Schubert", "肖邦": "Chopin"}
SOURCE_HOSTS = {
    "mutopia": {"www.mutopiaproject.org", "mutopiaproject.org"},
    "ichigos": {"ichigos.com", "www.ichigos.com"},
    "ninsheetmusic": {"www.ninsheetmusic.org", "ninsheetmusic.org"},
    "musescore": {"musescore.com", "www.musescore.com"},
}
ICHIGO_LICENSE = "Personal non-commercial use only; no redistribution"
SOURCE_NAMES = {"mutopia": "Mutopia", "ichigos": "Ichigo's", "ninsheetmusic": "NinSheetMusic", "musescore": "MuseScore", "local": "Local MIDI"}
POLICY_URLS = {
    "mutopia": BASE + "/legal.html", "ichigos": "https://ichigos.com/legal",
    "ninsheetmusic": "https://www.ninsheetmusic.org/info/about", "musescore": "https://musescore.com/legal/terms",
}


@dataclass(frozen=True)
class OnlineScore:
    id: str
    title: str
    composer: str
    license: str
    license_url: str
    source_url: str
    midi_url: str
    pdf_url: str
    provider: str = "mutopia"
    instrumentation: str = ""


def checked_url(url: str, provider: str = "mutopia") -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in SOURCE_HOSTS.get(provider, set())
            or parsed.port not in {None, 443} or parsed.username or parsed.password):
        raise ValueError("Only HTTPS links on the selected score source are accepted")
    return url


class _Redirects(HTTPRedirectHandler):
    def __init__(self, provider="mutopia"):
        self.provider = provider
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, checked_url(newurl, self.provider))


def fetch_bytes(url: str, limit: int = MAX_BYTES, *, provider="mutopia", data=None) -> bytes:
    request = Request(checked_url(url, provider), data=data,
                      headers={"User-Agent": "practising-piano-easily/1.0 (personal music learning)"})
    with build_opener(_Redirects(provider)).open(request, timeout=20) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("The score exceeds the download size limit")
    return data


class CatalogParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scores = []
        self.depth = 0
        self.rows = []
        self.row = []
        self.cell = None
        self.links = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if self.depth:
                self.depth += 1
            elif "result-table" in attrs.get("class", "").split():
                self.depth = 1
                self.rows, self.links = [], []
        if not self.depth:
            return
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []
        elif tag == "a":
            self.anchor = [urljoin(BASE + "/cgibin/make-table.cgi", attrs.get("href", "")), []]

    def handle_data(self, data):
        if self.depth:
            if self.cell is not None:
                self.cell.append(data)
            if self.anchor is not None:
                self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "a" and self.anchor is not None:
            self.links.append((self.anchor[0], " ".join("".join(self.anchor[1]).split())))
            self.anchor = None
        elif tag == "td" and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr":
            self.rows.append(self.row)
        elif tag == "table":
            self.depth -= 1
            if self.depth == 0:
                self._piece()

    def _piece(self):
        midi = next((url for url, label in self.links if urlparse(url).path.endswith(".mid")), "")
        pdf = next((url for url, label in self.links if "A4" in label and urlparse(url).path.endswith(".pdf")), "")
        source = next((url for url, label in self.links if "piece-info.cgi" in url), "")
        license_item = next(((url, label) for url, label in self.links if label == "Public Domain" or label.startswith("Creative Commons Attribution")), None)
        id = parse_qs(urlparse(source).query).get("id", [""])[0]
        if not (midi and pdf and license_item and re.fullmatch(r"\d+", id) and self.rows and len(self.rows[0]) >= 2):
            return
        try:
            for url in (midi, pdf, source, license_item[0]):
                checked_url(url)
        except ValueError:
            return
        self.scores.append(OnlineScore(id, self.rows[0][0], self.rows[0][1], license_item[1], license_item[0], source, midi, pdf))


def search_scores(query: str = "", offset: int = 0) -> list[OnlineScore]:
    for chinese, canonical in COMPOSER_ALIASES.items():
        query = query.replace(chinese, canonical)
    params = urlencode({"Instrument": "Piano", "solo": "1", "searchingfor": query[:200], "startat": max(0, offset)})
    parser = CatalogParser()
    parser.feed(fetch_bytes(BASE + "/cgibin/make-table.cgi?" + params, limit=2_000_000).decode("utf-8"))
    return parser.scores


def score_folder(score: OnlineScore, directory: Path = SCORES_DIRECTORY) -> Path:
    if score.provider not in SOURCE_NAMES or not re.fullmatch(r"\d{1,30}", score.id):
        raise ValueError("Invalid catalog score ID")
    return directory / (score.provider + "-" + score.id)


def _atomic_save(path: Path, data: bytes):
    descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def download_score(score: OnlineScore, directory: Path = SCORES_DIRECTORY, *, personal_use=False) -> Path:
    if score.provider == "mutopia" and score.license != "Public Domain" and not score.license.startswith("Creative Commons Attribution"):
        raise ValueError("An explicit public-domain or Creative Commons license is required")
    folder = score_folder(score, directory)
    if (folder / "source.json").exists() and (folder / "score.mid").exists():
        return folder
    if not score.midi_url or not score.pdf_url:
        raise ValueError("A matching PDF and MIDI are required for key-detection practice")
    if score.provider == "ichigos":
        if not personal_use or score.license != ICHIGO_LICENSE:
            raise ValueError("Confirm personal non-commercial use and keep the source credits first")
        from .fan_scores import refresh_ichigos_score
        score = refresh_ichigos_score(score)
        midi = fetch_bytes(score.midi_url, provider=score.provider)
        pdf = fetch_bytes(score.pdf_url, provider=score.provider)
    elif score.provider == "mutopia":
        midi = fetch_bytes(score.midi_url)
        pdf = fetch_bytes(score.pdf_url)
    else:
        raise ValueError("Download the permitted PDF and MIDI in your browser, then import both files here")
    if not midi.startswith(b"MThd") or not pdf.startswith(b"%PDF-"):
        raise ValueError("The source did not return valid MIDI and PDF files")
    folder.mkdir(parents=True, exist_ok=True)
    _atomic_save(folder / "score.mid", midi)
    _atomic_save(folder / "score.pdf", pdf)
    _atomic_save(folder / "source.json", json.dumps(asdict(score), ensure_ascii=False, indent=2).encode("utf-8"))
    return folder


def musescore_search_url(query: str) -> str:
    return "https://musescore.com/sheetmusic?" + urlencode({"text": query.strip()[:200]})


def import_musescore_score(midi_path: Path, pdf_path: Path | None, title: str, source_url: str,
                           authorized: bool, directory: Path = SCORES_DIRECTORY) -> tuple[OnlineScore, Path]:
    return import_score_files(midi_path, pdf_path, title, source_url, authorized, directory, provider="musescore")


def import_score_files(midi_path: Path, pdf_path: Path | None, title: str, source_url: str,
                       authorized: bool, directory: Path = SCORES_DIRECTORY, *, provider: str,
                       arranger: str = "") -> tuple[OnlineScore, Path]:
    """Copy permitted MIDI with an optional PDF; never fetch restricted website assets."""
    from .midi_file import load_midi
    import mido

    paths = {
        "musescore": r"/(?:score/\d+|(?:user/\d+|[A-Za-z0-9_-]+)/scores/\d+)/?",
        "ichigos": r"/sheets/(?:\d+|[a-z]+)/?",
        "ninsheetmusic": r"/(?:browse(?:/[A-Za-z0-9_./%-]+)?/?|forum/index\.php)",
    }
    if provider == "local":
        if source_url.strip():
            raise ValueError("For a website source, select that source and keep its original score-page link")
    else:
        checked_url(source_url.strip(), provider)
        parsed = urlparse(source_url.strip())
        if provider not in paths or not re.fullmatch(paths[provider], parsed.path):
            raise ValueError("Paste the original HTTPS score-page link for the selected source")
    if not authorized or not title.strip():
        raise ValueError("A title and confirmation of permission for personal practice are required")
    for path in (midi_path,) + ((pdf_path,) if pdf_path is not None else ()):
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Select MIDI and optional PDF files, each no larger than 15 MiB")
    midi, pdf = midi_path.read_bytes(), pdf_path.read_bytes() if pdf_path is not None else b""
    if not midi.startswith(b"MThd") or (pdf_path is not None and not pdf.startswith(b"%PDF-")):
        raise ValueError("Select a valid MIDI and PDF pair, not MSCZ, MusicXML or ZIP")
    try:
        midi_file = mido.MidiFile(file=io.BytesIO(midi))
        if midi_file.type == 2 or midi_file.ticks_per_beat <= 0:
            raise ValueError("Unsupported MIDI timeline")
        if any(event.type == "set_tempo" and event.tempo <= 0 for track in midi_file.tracks for event in track):
            raise ValueError("MIDI tempo must be positive")
        summary = load_midi(midi_file)
    except (ValueError, OSError, EOFError) as exc:
        raise ValueError("The selected MIDI could not be read") from exc
    if not any(note.channel != 9 for note in summary.notes) or len(summary.notes) > 100_000:
        raise ValueError("The MIDI is empty or too large for interactive practice")
    id = str(int.from_bytes(hashlib.sha256(midi + pdf).digest()[:8], "big"))
    score = OnlineScore(id, title.strip()[:200], arranger.strip()[:200] or ("MuseScore import" if provider == "musescore" else "Local import; see original credits"),
                        "User-confirmed personal-use permission (not an open-license claim)",
                        source_url.strip(), source_url.strip(), "", "", provider)
    folder = score_folder(score, directory)
    folder.mkdir(parents=True, exist_ok=True)
    _atomic_save(folder / "score.mid", midi)
    if pdf_path is not None:
        _atomic_save(folder / "score.pdf", pdf)
    _atomic_save(folder / "source.json", json.dumps(asdict(score), ensure_ascii=False, indent=2).encode("utf-8"))
    return score, folder


def downloaded_scores(directory: Path = SCORES_DIRECTORY) -> list[OnlineScore]:
    result = []
    if directory.exists():
        for path in sorted(directory.glob("*/source.json")):
            try:
                score = OnlineScore(**json.loads(path.read_text(encoding="utf-8")))
                folder = score_folder(score, directory)
                if folder == path.parent and (folder / "score.mid").is_file():
                    result.append(score)
            except (OSError, ValueError, TypeError):
                continue
    return result
