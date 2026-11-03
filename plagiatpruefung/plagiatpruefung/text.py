"""Zerlegung in Wörter und Sätze mit Zeichenpositionen."""

import re
import unicodedata
from dataclasses import dataclass, field

WORT = re.compile(r"\w+(?:[-'’]\w+)*")
SATZENDE = re.compile(r"(?<=[.!?])[\"“”»«']?\s+(?=[\"„“»«(\[]?[A-ZÄÖÜ0-9])|\n{2,}")

# Abkürzungen, nach denen kein Satz endet.
ABKUERZUNGEN = {
    "vgl", "bzw", "usw", "ggf", "z.b", "d.h", "u.a", "s", "ebd", "hrsg", "aufl",
    "bspw", "ca", "etc", "et al", "al", "dr", "prof", "nr", "abb", "tab", "kap",
    "e.g", "i.e", "cf", "vol", "pp", "p", "ed", "eds", "no", "fig",
}

STOPPWOERTER = set("""
aber alle allem allen aller alles als also am an ander andere anderen auch auf aus bei beim bin bis bist
da damit dann das dass dem den denn der des dessen die dies diese diesem diesen dieser dieses doch dort du
durch ein eine einem einen einer eines einige er es etwa euch für gegen hat hatte hatten hier hin hinter
ich ihr ihre im in indem ins ist jede jedem jeden jeder jedes jedoch kann kein keine können könnte man
mehr mit muss nach nicht nichts noch nun nur ob oder ohne sehr sei seien sein seine seinem seinen seiner
sich sie sind so solche soll sollte sondern sowie über um und uns unter vom von vor wann war waren was
weil welche welchem welchen welcher wenn wer werden wie wieder wir wird wo wurde wurden zu zum zur zwar
zwischen sowohl bereits dabei daher dazu hierbei insbesondere somit wobei zudem sodass werden worden
a about above after again against all also an and any are as at be because been before being between both
but by can could did do does doing during each few for from further had has have having he her here hers
him his how i if in into is it its itself may might more most must no nor not of off on once only or other
our out over own same she should so some such than that the their them then there these they this those
through to too under until up very was we were what when where which while who whom why will with would
you your however therefore thus within without whether
""".split())


def normalisiere(wort: str) -> str:
    """Vergleichsform: Kleinschreibung, Ligaturen aufgelöst, Umlaute einheitlich."""
    w = unicodedata.normalize("NFKC", wort).lower()
    w = w.replace("’", "'").replace("ß", "ss")
    w = w.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return w


def stamm(norm: str) -> str:
    """Grobe Stammform durch Kürzen auf sechs Zeichen.

    Reicht für den Paraphrasen-Abgleich aus und kommt ohne Wörterbuch aus.
    """
    return norm[:6]


@dataclass
class Tokens:
    """Wörter eines Textes in Vergleichsform samt Zeichenpositionen."""
    text: str
    norm: list = field(default_factory=list)
    anfang: list = field(default_factory=list)
    ende: list = field(default_factory=list)

    def __len__(self):
        return len(self.norm)

    def zeichen(self, t_von: int, t_bis: int) -> tuple:
        """Zeichenbereich zu den Wörtern t_von..t_bis (einschließlich)."""
        return self.anfang[t_von], self.ende[t_bis]

    def auszug(self, t_von: int, t_bis: int) -> str:
        a, e = self.zeichen(t_von, t_bis)
        return self.text[a:e]


def zerlege(text: str) -> Tokens:
    tok = Tokens(text)
    for m in WORT.finditer(text):
        tok.norm.append(normalisiere(m.group()))
        tok.anfang.append(m.start())
        tok.ende.append(m.end())
    return tok


def saetze(tok: Tokens) -> list:
    """Sätze als Bereiche von Wortindizes [(von, bis), ...] (bis einschließlich)."""
    grenzen = []
    for m in SATZENDE.finditer(tok.text):
        davor = tok.text[max(0, m.start() - 8):m.start()].lower()
        letztes = re.split(r"[\s(]", davor)[-1].rstrip(".!?\"“”»«'")
        if letztes in ABKUERZUNGEN or re.fullmatch(r"[a-zäöü]", letztes or "x"):
            continue
        grenzen.append(m.start())
    ergebnis, w, start = [], 0, 0
    n = len(tok)
    for g in grenzen + [len(tok.text) + 1]:
        while w < n and tok.anfang[w] < g:
            w += 1
        if w > start:
            ergebnis.append((start, w - 1))
            start = w
    return ergebnis


STOPP_NORM = {normalisiere(w) for w in STOPPWOERTER}


def inhaltswoerter(tok: Tokens, von: int, bis: int) -> list:
    return [stamm(w) for w in tok.norm[von:bis + 1]
            if len(w) > 2 and w not in STOPP_NORM and not w.isdigit()]
