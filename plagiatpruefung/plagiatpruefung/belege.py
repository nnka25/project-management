"""Ist eine Fundstelle als Zitat gekennzeichnet und belegt?

Geprüft wird rein formal:
- Anführungszeichen: Liegt die Fundstelle (fast) vollständig innerhalb
  eines Paares von Anführungszeichen?
- Beleg: Folgt im selben Absatz kurz nach der Stelle ein Kurzbeleg
  (Autor Jahr: Seite), eine Fußnotenmarke oder eine Nummer [12]?
- Bezug: Nennt dieser Beleg die gefundene Quelle? Dazu werden die
  Autorennamen aus dem Dateinamen der Quelle genommen
  (Mueller_Schmidt_2021.pdf -> Mueller, Schmidt).

Daraus ergibt sich die Einstufung. Sie ist ein Prüfhinweis, kein Urteil.
"""

import re
from dataclasses import dataclass

from .text import normalisiere

ZITATPAARE = [
    ("„", "“"), ("„", "”"), ("“", "”"), ("»", "«"), ("«", "»"), ('"', '"'), ("‚", "‘"),
]

KLAMMERBELEG = re.compile(
    r"\((?:[^()]{0,40}?\b)?(?:vgl\.|siehe|cf\.|see)?\s*[A-ZÄÖÜ][\w'’\-]+[^()]{0,120}?"
    r"\b(?:1[5-9]|20)\d{2}[a-z]?\b[^()]{0,60}\)")
ERZAEHLEND = re.compile(r"[A-ZÄÖÜ][\w'’\-]+(?:\s+(?:et al\.|u\.\s?a\.))?\s*\(\s*(?:1[5-9]|20)\d{2}[a-z]?\b")
NUMMER = re.compile(r"\[\d+(?:[,–\-]\s*\d+)*\]")
FUSSNOTE = re.compile(r"\[\^E?\d+\]")
HOCHZAHL = re.compile(r"[\w.,;:!?\"“”»«)][¹²³⁴⁵⁶⁷⁸⁹⁰]+")
EBENDA = re.compile(r"\b(?:ebd|ebenda|ibid|a\.\s?a\.\s?O)\b\.?", re.IGNORECASE)

NACHLAUF = 250   # Zeichen nach der Fundstelle, in denen ein Beleg gesucht wird


@dataclass
class Belegbefund:
    in_anfuehrung: bool
    beleg: str            # gefundener Beleg (gekürzt) oder ""
    verweist_auf_quelle: bool | None   # None: Autor unbekannt oder kein Beleg


def zitatbereiche(text: str) -> list:
    """Zeichenbereiche, die zwischen Anführungszeichen stehen."""
    bereiche = []
    for auf, zu in ZITATPAARE:
        muster = re.compile(re.escape(auf) + r"([^\n" + re.escape(zu) + r"]{1,4000}?)" + re.escape(zu))
        bereiche += [(m.start(), m.end()) for m in muster.finditer(text)]
    # Einrückungen ohne Anführungszeichen (Blockzitate) erkennt die Prüfung
    # nicht; sie stehen im Bericht als "ohne Anführungszeichen".
    return sorted(bereiche)


def anteil_in_bereichen(a: int, e: int, bereiche: list) -> float:
    if e <= a:
        return 0.0
    abgedeckt = 0
    for b0, b1 in bereiche:
        if b1 <= a:
            continue
        if b0 >= e:
            break
        abgedeckt += min(e, b1) - max(a, b0)
    return min(1.0, abgedeckt / (e - a))


def autoren_aus_dateiname(name: str) -> list:
    """'Mueller_Schmidt_2021a_Titel.pdf' -> ['mueller', 'schmidt']."""
    stamm = re.sub(r"\.[A-Za-z0-9]+$", "", name)
    teile = re.split(r"[_\s,;]+|(?<=[a-zäöü])-(?=[A-ZÄÖÜ])", stamm)
    autoren = []
    for t in teile:
        if re.fullmatch(r"(1[5-9]|20)\d{2}[a-z]?", t):
            break
        if re.fullmatch(r"[A-Za-zÄÖÜäöüß'\-]{2,}", t) and t.lower() not in ("et", "al", "etal", "und", "and", "u"):
            autoren.append(normalisiere(t))
    return autoren


def _absatzende(text: str, pos: int) -> int:
    e = text.find("\n\n", pos)
    return len(text) if e < 0 else e


def pruefe(text: str, zeichen_von: int, zeichen_bis: int, bereiche: list,
           fussnoten: dict, autoren: list) -> Belegbefund:
    in_anf = anteil_in_bereichen(zeichen_von, zeichen_bis, bereiche) >= 0.8

    # Beleg suchen: in der Stelle selbst (Beleg mitten im Satz) und kurz danach.
    ende = min(_absatzende(text, zeichen_bis), zeichen_bis + NACHLAUF)
    fenster = text[zeichen_von:ende]
    funde = []
    for muster in (KLAMMERBELEG, ERZAEHLEND, FUSSNOTE, NUMMER, HOCHZAHL, EBENDA):
        funde += [m for m in muster.finditer(fenster)]
    # Vor der Stelle im selben Satz: erzählende Zitation "Müller (2020) zeigt, dass ..."
    satzbeginn = max(text.rfind(". ", 0, zeichen_von), text.rfind("\n", 0, zeichen_von), 0)
    funde += list(ERZAEHLEND.finditer(text[satzbeginn:zeichen_von]))
    if not funde:
        return Belegbefund(in_anf, "", None)

    belegtexte = []
    for m in funde:
        t = m.group()
        if FUSSNOTE.fullmatch(t):
            t = t + " " + fussnoten.get(t[1:-1], "")
        belegtexte.append(t.strip())
    kurz = "; ".join(b[:120] for b in belegtexte[:3])

    if not autoren:
        return Belegbefund(in_anf, kurz, None)
    gesamt = normalisiere(" ".join(belegtexte))
    if EBENDA.search(" ".join(belegtexte)) and not any(a in gesamt for a in autoren):
        return Belegbefund(in_anf, kurz, None)
    return Belegbefund(in_anf, kurz, any(a in gesamt for a in autoren))


# Einstufung: (Kürzel, Bezeichnung, Stufe). Stufen wie in den übrigen
# Prüfwerkzeugen: schwer, pruefen, hinweis, ok.
def einstufen(art: str, befund: Belegbefund) -> tuple:
    belegt = bool(befund.beleg)
    if art == "woertlich":
        if befund.in_anfuehrung and belegt:
            if befund.verweist_auf_quelle is False:
                return "ZF", "Wörtliches Zitat, Beleg nennt eine andere Quelle", "pruefen"
            return "ZK", "Wörtliches Zitat, gekennzeichnet und belegt", "ok"
        if befund.in_anfuehrung:
            return "ZO", "Wörtliches Zitat ohne Beleg", "pruefen"
        if belegt:
            return "WB", "Wörtlich übernommen ohne Anführungszeichen, Beleg vorhanden", "schwer"
        return "WU", "Wörtlich übernommen ohne Kennzeichnung und ohne Beleg", "schwer"
    if belegt:
        if befund.verweist_auf_quelle is False:
            return "PF", "Umformuliert, Beleg nennt eine andere Quelle", "pruefen"
        return "PB", "Umformuliert, Beleg vorhanden", "hinweis"
    return "PU", "Umformuliert ohne Beleg", "pruefen"
