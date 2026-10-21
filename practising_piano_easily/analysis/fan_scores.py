"""Ichigo's public search and browser-based NinSheetMusic discovery, without scraping challenges."""

from html.parser import HTMLParser
import re
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

from .online_scores import OnlineScore, ICHIGO_LICENSE, checked_url, fetch_bytes


ICHIGOS = "https://ichigos.com"
NINSHEETMUSIC = "https://www.ninsheetmusic.org"
TITLE_ALIASES = {
    "原神": "Genshin Impact", "明日方舟": "Arknights", "蔚蓝档案": "Blue Archive",
    "碧蓝档案": "Blue Archive", "未闻花名": "Ano hi Mita Hana no Namae o Bokutachi wa Mada Shiranai",
    "轻音少女": "K-ON", "你的名字": "Kimi no Na wa", "命运石之门": "Steins;Gate",
    "进击的巨人": "Attack on Titan", "葬送的芙莉莲": "sousou no Frieren", "东方": "Touhou",
}


def canonical_query(query):
    for title in sorted(TITLE_ALIASES, key=len, reverse=True):
        query = query.replace(title, TITLE_ALIASES[title])
    return query.strip()[:200]


def fan_search_url(provider, query=""):
    if provider == "ichigos":
        base, domain = ICHIGOS + "/search", "ichigos.com"
    elif provider == "ninsheetmusic":
        base, domain = NINSHEETMUSIC + "/browse", "ninsheetmusic.org"
    else:
        raise ValueError("Unknown anime/game score source")
    if not query.strip():
        return base
    return "https://www.google.com/search?" + urlencode({
        "q": "site:" + domain + " " + canonical_query(query) + " piano sheet music",
    })


class IchigosParser(HTMLParser):
    """Keep links inside one arrangement, never mix different authors' PDF/MIDI files."""

    def __init__(self, source_url=ICHIGOS + "/sheets"):
        super().__init__()
        self.source_url = checked_url(source_url, "ichigos")
        self.scores = []
        self.series = ""
        self.series_url = self.source_url
        self.heading = False
        self.heading_text = []
        self.in_description = False
        self.description_seen = False
        self.title = []
        self.description = []
        self.links = {}
        self.breaks = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "span" and "title2" in attrs.get("class", "").split():
            self._finish()
            self.heading, self.heading_text = True, []
            self.series_url = self.source_url
        elif tag == "a" and self.heading:
            url = urljoin(ICHIGOS, attrs.get("href", ""))
            if re.fullmatch(r"/sheets/\d+", urlparse(url).path):
                try:
                    self.series_url = checked_url(url, "ichigos")
                except ValueError:
                    pass
        elif tag == "i" and self.series:
            self.in_description, self.description_seen = True, True
        elif tag == "a" and self.series and self.description_seen:
            url = urljoin(ICHIGOS, attrs.get("href", ""))
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            id = params.get("id", [""])[0]
            kind = params.get("type", [""])[0]
            if parsed.path == "/res/getfile.php" and re.fullmatch(r"\d{1,30}", id) and kind in {"pdf", "midi"}:
                try:
                    checked_url(url, "ichigos")
                except ValueError:
                    return
                self.links.setdefault(id, {})[kind] = url
        elif tag == "br":
            self.breaks += 1
            if self.breaks >= 2:
                self._finish()
        if tag != "br":
            self.breaks = 0

    def handle_endtag(self, tag):
        if tag == "span" and self.heading:
            self.series = " ".join("".join(self.heading_text).split())
            self.heading = False
        elif tag == "i":
            self.in_description = False

    def handle_data(self, data):
        if data.strip():
            self.breaks = 0
        if self.heading:
            self.heading_text.append(data)
        elif self.in_description:
            self.description.append(data)
        elif self.series and not self.description_seen:
            self.title.append(data)

    def _finish(self):
        title = " ".join("".join(self.title).split())
        description = " ".join("".join(self.description).split())
        match = re.fullmatch(r"(.+)\s+\(Transcribed by ([^()]*)\)", title, re.IGNORECASE)
        song, arranger = match.groups() if match else (title, "See original credits")
        if self.series and song and "piano" in description.casefold():
            for id, links in self.links.items():
                if "pdf" in links:
                    self.scores.append(OnlineScore(
                        id, self.series + " · " + song, arranger, ICHIGO_LICENSE, ICHIGOS + "/legal",
                        self.series_url, links.get("midi", ""), links["pdf"], "ichigos", description,
                    ))
        self.title, self.description, self.links = [], [], {}
        self.description_seen = self.in_description = False

    def close(self):
        super().close()
        self._finish()


def search_ichigos(query):
    query = canonical_query(query)
    if not query:
        raise ValueError("Enter an anime, game or song title first")
    data = urlencode({"qtitle": query, "qdesc": "piano", "qauthor": "", "q": "1"}).encode()
    parser = IchigosParser()
    parser.feed(fetch_bytes(ICHIGOS + "/sheets", limit=2_000_000, provider="ichigos", data=data).decode("utf-8", errors="replace"))
    parser.close()
    return list({score.id: score for score in parser.scores}.values())


def refresh_ichigos_score(score):
    checked_url(score.source_url, "ichigos")
    if not re.fullmatch(r"/sheets/(?:\d+|[a-z]+)", urlparse(score.source_url).path):
        raise ValueError("The arrangement's source page is missing; search again")
    parser = IchigosParser(score.source_url)
    parser.feed(fetch_bytes(score.source_url, limit=2_000_000, provider="ichigos").decode("utf-8", errors="replace"))
    parser.close()
    current = next((item for item in parser.scores if item.id == score.id), None)
    if current is None or not current.midi_url:
        raise ValueError("This arrangement no longer provides a matching PDF and MIDI")
    return current
