"""Ablauf einer Prüfung: einlesen, abgleichen, Belege prüfen, auswerten."""

import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import abgleich, belege, einlesen
from .text import zerlege


@dataclass
class Fund:
    nummer: int
    art: str
    kuerzel: str
    bezeichnung: str
    stufe: str
    quelle: str
    weitere_quellen: list
    zeichen_von: int
    zeichen_bis: int
    woerter: int
    gleiche_woerter: int
    aehnlichkeit: float
    text_auszug: str
    quelle_auszug: str
    quelle_seite: int | None
    in_anfuehrung: bool
    beleg: str
    verweist_auf_quelle: bool | None


@dataclass
class Ergebnis:
    arbeit: str
    text: str
    woerter_gesamt: int
    funde: list
    quellen: list
    verzeichnis_gekuerzt: bool
    dauer: float
    hinweise: list = field(default_factory=list)

    def anteile(self) -> dict:
        """Wortanteile je Stufe und insgesamt (in Prozent der Arbeit)."""
        je_stufe = Counter()
        for f in self.funde:
            je_stufe[f.stufe] += f.woerter
        gesamt = max(1, self.woerter_gesamt)
        a = {s: round(100 * je_stufe[s] / gesamt, 2) for s in ("schwer", "pruefen", "hinweis", "ok")}
        a["uebereinstimmung"] = round(100 * sum(je_stufe.values()) / gesamt, 2)
        a["problematisch"] = round(a["schwer"] + a["pruefen"], 2)
        return a


@dataclass
class Quelle:
    schluessel: str
    text: str
    autoren: list
    url: str = ""
    dokument: object = None


def lokale_quellen(ordner, arbeit_pfad=None, protokoll=print) -> list:
    quellen = []
    for pfad in einlesen.quellen_im_ordner(ordner):
        if arbeit_pfad and pfad.resolve() == Path(arbeit_pfad).resolve():
            continue
        try:
            dok = einlesen.lies(pfad)
        except Exception as fehler:
            protokoll(f"  übersprungen: {pfad.name} ({fehler})")
            continue
        if len(dok.text.strip()) < 200:
            protokoll(f"  übersprungen: {pfad.name} (kaum Text, evtl. Scan ohne Textebene)")
            continue
        quellen.append(Quelle(pfad.name, dok.text, belege.autoren_aus_dateiname(pfad.name),
                              str(pfad), dok))
    return quellen


def pruefe(arbeit_pfad, quellen, mit_verzeichnis=False, umformuliert=True,
           min_woerter=12, schwelle=0.6, ngramm=5, protokoll=print) -> Ergebnis:
    start = time.time()
    dok = einlesen.lies(arbeit_pfad)
    text, gekuerzt = (dok.text, False) if mit_verzeichnis else einlesen.schneide_verzeichnis(dok.text)
    tok = zerlege(text)
    protokoll(f"Arbeit: {Path(arbeit_pfad).name}, {len(tok):,} Wörter".replace(",", "."))
    pruefling = abgleich.Pruefling(tok, n=ngramm)

    alle = []
    info = {}
    hinweise = []
    for nr, q in enumerate(quellen, start=1):
        qtok = zerlege(q.text)
        treffer = abgleich.vergleiche(pruefling, qtok, q.schluessel, umformuliert,
                                      min_woerter=min_woerter, schwelle=schwelle)
        abgedeckt = sum(t.laenge for t in treffer if t.art == "woertlich")
        if len(tok) and abgedeckt > 0.9 * len(tok):
            hinweise.append(f"{q.schluessel} enthält fast die ganze Arbeit (eigene ältere Fassung?) "
                            "und wurde nicht gewertet.")
            continue
        for t in treffer:
            a, e = qtok.zeichen(t.q_von, t.q_bis)
            t.q_auszug = q.text[a:e]
            t.q_seite = q.dokument.seite_bei(a) if q.dokument is not None else None
        info[q.schluessel] = {"name": q.schluessel, "autoren": q.autoren, "url": q.url,
                              "woerter": len(qtok), "treffer": 0, "woerter_treffer": 0}
        alle += treffer
        if treffer or nr % 25 == 0:
            protokoll(f"  [{nr}/{len(quellen)}] {q.schluessel}: {len(treffer)} Treffer")

    behalten = abgleich.bereinige(alle)
    bereiche = belege.zitatbereiche(text)
    funde = []
    for nr, t in enumerate(behalten, start=1):
        za, ze = tok.zeichen(t.t_von, t.t_bis)
        befund = belege.pruefe(text, za, ze, bereiche, dok.fussnoten, info[t.quelle]["autoren"])
        kuerzel, bez, stufe = belege.einstufen(t.art, befund)
        funde.append(Fund(nr, t.art, kuerzel, bez, stufe, t.quelle, t.weitere, za, ze,
                          t.laenge, t.gleiche_woerter, t.aehnlichkeit, text[za:ze],
                          t.q_auszug, t.q_seite, befund.in_anfuehrung, befund.beleg,
                          befund.verweist_auf_quelle))
        info[t.quelle]["treffer"] += 1
        info[t.quelle]["woerter_treffer"] += t.laenge

    quellen_info = sorted(info.values(), key=lambda i: -i["woerter_treffer"])
    return Ergebnis(str(arbeit_pfad), text, len(tok), funde, quellen_info, gekuerzt,
                    round(time.time() - start, 1), hinweise)
