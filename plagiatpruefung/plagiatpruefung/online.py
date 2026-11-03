"""Optionale Online-Suche nach Quellen, die nicht im Ordner liegen.

Durchsucht werden:
- Wikipedia (Deutsch und Englisch) über die MediaWiki-Such-API mit
  exakter Phrasensuche. Wikipedia ist eine häufige, oft unterschätzte
  Herkunft unbelegter Übernahmen.
- OpenAlex (offener Katalog wissenschaftlicher Arbeiten). Gefunden
  werden Titel und Abstracts; liegt eine frei zugängliche PDF-Fassung vor,
  wird sie geladen und vollständig verglichen. OpenAlex verlangt für
  nennenswerte Abfragemengen einen kostenlosen API-Schlüssel.

Datenschutz: An die Dienste gehen kurze Wortfolgen (rund zehn Wörter) aus
der Arbeit, nie der ganze Text. Die Online-Suche ist abgeschaltet, bis sie
mit --online ausdrücklich eingeschaltet wird.

Gefundene Texte werden im Zwischenspeicher abgelegt (Vorgabe:
online_quellen/ neben dem Bericht). Ein zweiter Lauf lädt sie nicht neu.
"""

import io
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .text import Tokens, saetze

WIKI_API = "https://{sprache}.wikipedia.org/w/api.php"
OPENALEX_API = "https://api.openalex.org/works"


@dataclass
class OnlineQuelle:
    schluessel: str      # Anzeigename im Bericht
    text: str
    autoren: list
    url: str


class Client:
    def __init__(self, kontakt: str = "", pause: float = 1.0, zeitlimit: int = 30):
        ua = "plagiatpruefung/0.1 (wissenschaftliche Selbstprüfung"
        ua += f"; {kontakt})" if kontakt else ")"
        self.kopf = {"User-Agent": ua, "Accept": "application/json"}
        self.pause = pause
        self.zeitlimit = zeitlimit
        self._letzte = 0.0

    def hole(self, url: str, params: dict | None = None, roh: bool = False):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        warten = self.pause - (time.time() - self._letzte)
        if warten > 0:
            time.sleep(warten)
        self._letzte = time.time()
        anfrage = urllib.request.Request(url, headers=self.kopf)
        with urllib.request.urlopen(anfrage, timeout=self.zeitlimit) as antwort:
            daten = antwort.read()
        return daten if roh else json.loads(daten.decode("utf-8"))


def suchphrasen(tok: Tokens, anzahl: int = 40, laenge: int = 10, ausschluss=None) -> list:
    """Wortfolgen für die Suche, gleichmäßig über die Arbeit verteilt.

    Genommen wird die Mitte längerer Sätze. Sätze in Anführungszeichen
    (ausschluss: Zeichenbereiche) werden übersprungen, sie sind ohnehin
    als Zitat gekennzeichnet.
    """
    ausschluss = ausschluss or []
    kandidaten = []
    for von, bis in saetze(tok):
        if bis - von + 1 < laenge + 6:
            continue
        mitte = von + (bis - von + 1 - laenge) // 2
        a, e = tok.anfang[mitte], tok.ende[mitte + laenge - 1]
        if any(b0 < e and a < b1 for b0, b1 in ausschluss):
            continue
        phrase = tok.text[a:e]
        if re.search(r"[\[\]()\d]", phrase):
            continue
        kandidaten.append(re.sub(r"\s+", " ", phrase))
    if len(kandidaten) <= anzahl:
        return kandidaten
    schritt = len(kandidaten) / anzahl
    return [kandidaten[int(i * schritt)] for i in range(anzahl)]


def _cache_name(schluessel: str) -> str:
    return re.sub(r"[^\w\-]+", "_", schluessel)[:120] + ".json"


def _aus_cache(ordner: Path, schluessel: str):
    p = ordner / _cache_name(schluessel)
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        return OnlineQuelle(**d)
    return None


def _in_cache(ordner: Path, q: OnlineQuelle):
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / _cache_name(q.schluessel)).write_text(
        json.dumps(q.__dict__, ensure_ascii=False), encoding="utf-8")


def wikipedia(client: Client, phrasen: list, cache: Path, sprachen=("de", "en"),
              protokoll=print) -> list:
    titel = {}
    for sprache in sprachen:
        for phrase in phrasen:
            try:
                d = client.hole(WIKI_API.format(sprache=sprache), {
                    "action": "query", "list": "search", "srsearch": f'"{phrase}"',
                    "srlimit": 3, "srprop": "", "format": "json", "formatversion": 2})
            except Exception as fehler:
                protokoll(f"  Wikipedia ({sprache}) nicht erreichbar: {fehler}")
                break
            for eintrag in d.get("query", {}).get("search", []):
                titel[(sprache, eintrag["title"])] = True
    quellen = []
    for sprache, t in titel:
        schluessel = f"Wikipedia ({sprache}): {t}"
        q = _aus_cache(cache, schluessel)
        if q is None:
            try:
                d = client.hole(WIKI_API.format(sprache=sprache), {
                    "action": "query", "prop": "extracts", "explaintext": 1, "titles": t,
                    "format": "json", "formatversion": 2})
                seite = d["query"]["pages"][0]
                url = f"https://{sprache}.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"))
                q = OnlineQuelle(schluessel, seite.get("extract", ""), ["wikipedia"], url)
                _in_cache(cache, q)
            except Exception as fehler:
                protokoll(f"  Artikel {t} nicht geladen: {fehler}")
                continue
        quellen.append(q)
    return quellen


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = {}
    for wort, stellen in inv.items():
        for s in stellen:
            pos[s] = wort
    return " ".join(pos[i] for i in sorted(pos))


def _pdf_text(daten: bytes) -> str:
    from pypdf import PdfReader
    from .einlesen import bereinige_pdf_text
    leser = PdfReader(io.BytesIO(daten))
    return "\n\n".join(bereinige_pdf_text(s.extract_text() or "") for s in leser.pages)


def openalex(client: Client, phrasen: list, cache: Path, api_schluessel: str = "",
             volltext: bool = True, protokoll=print) -> list:
    werke = {}
    for phrase in phrasen:
        params = {"search": phrase, "per-page": 3,
                  "select": "id,doi,title,publication_year,authorships,abstract_inverted_index,best_oa_location"}
        if api_schluessel:
            params["api_key"] = api_schluessel
        try:
            d = client.hole(OPENALEX_API, params)
        except Exception as fehler:
            protokoll(f"  OpenAlex nicht erreichbar oder Kontingent erschöpft: {fehler}")
            break
        for w in d.get("results", []):
            werke.setdefault(w["id"], w)
    quellen = []
    for w in werke.values():
        namen = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])]
        nachnamen = [n.split()[-1] for n in namen if n]
        jahr = w.get("publication_year") or "o.J."
        kurz = (", ".join(nachnamen[:2]) + (" u. a." if len(nachnamen) > 2 else "")) or "o.V."
        schluessel = f"OpenAlex: {kurz} {jahr}, {(w.get('title') or '')[:80]}"
        q = _aus_cache(cache, schluessel)
        if q is None:
            text = (w.get("title") or "") + "\n\n" + _abstract(w.get("abstract_inverted_index"))
            oa = w.get("best_oa_location") or {}
            url = oa.get("pdf_url") or w.get("doi") or w["id"]
            if volltext and oa.get("pdf_url"):
                try:
                    text = _pdf_text(client.hole(oa["pdf_url"], roh=True))
                except Exception as fehler:
                    protokoll(f"  Volltext nicht geladen ({kurz} {jahr}): {fehler}")
            from .text import normalisiere
            q = OnlineQuelle(schluessel, text, [normalisiere(n) for n in nachnamen], url)
            _in_cache(cache, q)
        quellen.append(q)
    return quellen
