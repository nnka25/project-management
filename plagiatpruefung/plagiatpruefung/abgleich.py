"""Abgleich der Arbeit mit einer Quelle.

Zwei Verfahren laufen nacheinander:

1. Wörtlich: Die Arbeit wird in überlappende Wortfolgen (n-Gramme) zerlegt
   und in einem Verzeichnis abgelegt. Jede Quelle wird einmal durchlaufen;
   gemeinsame n-Gramme werden zu zusammenhängenden Passagen verkettet.
   Kleine Einschübe, Auslassungen und umgestellte Wörter überbrückt die
   Verkettung. Speicherbedarf und Laufzeit wachsen linear mit der Textmenge.

2. Umformuliert: Satz für Satz wird verglichen, wie viele Inhaltswörter
   (grob auf den Stamm gekürzt) ein Satz der Arbeit mit einem Satz der
   Quelle teilt. Das findet Stellen, an denen nur Satzbau und einzelne
   Wörter verändert wurden. Übersetzungen findet es nicht.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .text import Tokens, inhaltswoerter, saetze


@dataclass
class Treffer:
    quelle: str          # Schlüssel der Quelle
    art: str             # "woertlich" oder "umformuliert"
    t_von: int           # Wortindex in der Arbeit (einschließlich)
    t_bis: int
    q_von: int           # Wortindex in der Quelle (einschließlich)
    q_bis: int
    aehnlichkeit: float  # 0..1
    gleiche_woerter: int
    weitere: list = field(default_factory=list)   # weitere Quellen mit derselben Stelle

    @property
    def laenge(self):
        return self.t_bis - self.t_von + 1


class Pruefling:
    """Die zu prüfende Arbeit mit vorberechneten Verzeichnissen."""

    def __init__(self, tok: Tokens, n: int = 5, max_haeufigkeit: int = 25):
        self.tok = tok
        self.n = n
        self.index = defaultdict(list)
        norm = tok.norm
        for i in range(len(norm) - n + 1):
            self.index[tuple(norm[i:i + n])].append(i)
        # Floskeln, die in der Arbeit sehr oft vorkommen, tragen nichts zur
        # Zuordnung bei und blähen nur die Trefferlisten auf.
        for k in [k for k, v in self.index.items() if len(v) > max_haeufigkeit]:
            del self.index[k]

        self.saetze = saetze(tok)
        self.satz_woerter = []
        self.satz_index = defaultdict(set)
        for s, (von, bis) in enumerate(self.saetze):
            w = set(inhaltswoerter(tok, von, bis))
            self.satz_woerter.append(w)
            for wort in w:
                self.satz_index[wort].add(s)
        grenze = max(20, len(self.saetze) // 50)
        self.haeufig = {w for w, s in self.satz_index.items() if len(s) > grenze}


def finde_woertlich(p: Pruefling, quelle: Tokens, schluessel: str,
                    luecke: int = 6, min_woerter: int = 12) -> list:
    n = p.n
    qn = quelle.norm
    paare = []
    for j in range(len(qn) - n + 1):
        stellen = p.index.get(tuple(qn[j:j + n]))
        if stellen:
            for i in stellen:
                paare.append((i, j))
    if not paare:
        return []
    paare.sort()

    # Verkettung: ein Paar setzt eine Kette fort, wenn es in Arbeit und
    # Quelle kurz hinter deren Ende liegt und der Versatz ähnlich bleibt.
    ketten = []   # [t_start, t_ende, q_start, q_ende, anzahl]
    offen = []
    for i, j in paare:
        offen = [k for k in offen if i - k[1] <= luecke + n]
        bester = None
        for k in offen:
            dt, dq = i - k[1], j - k[3]
            if 0 < dt <= luecke + 1 and 0 < dq <= luecke + 1 and abs(dt - dq) <= luecke:
                if bester is None or abs(dt - dq) < abs(i - bester[1] - (j - bester[3])):
                    bester = k
        if bester is not None:
            bester[1], bester[3] = i, j
            bester[4] += 1
        else:
            k = [i, i, j, j, 1]
            ketten.append(k)
            offen.append(k)

    treffer = []
    for t0, t1, q0, q1, _ in ketten:
        t_bis, q_bis = t1 + n - 1, q1 + n - 1
        a = p.tok.norm[t0:t_bis + 1]
        b = qn[q0:q_bis + 1]
        sm = SequenceMatcher(None, a, b, autojunk=False)
        gleich = sum(blk.size for blk in sm.get_matching_blocks())
        if gleich < min_woerter:
            continue
        treffer.append(Treffer(schluessel, "woertlich", t0, t_bis, q0, q_bis,
                               round(2 * gleich / (len(a) + len(b)), 3), gleich))
    return treffer


def finde_umformuliert(p: Pruefling, quelle: Tokens, schluessel: str,
                       schwelle: float = 0.6, min_inhalt: int = 6) -> list:
    """Satzvergleich über gemeinsame Inhaltswörter."""
    treffer = []
    bestes = {}   # Satz der Arbeit -> (Wert, Quellsatz, gemeinsam)
    for q_von, q_bis in saetze(quelle):
        qw = set(inhaltswoerter(quelle, q_von, q_bis))
        if len(qw) < min_inhalt:
            continue
        zaehler = defaultdict(int)
        for wort in qw:
            if wort in p.haeufig:
                continue
            for s in p.satz_index.get(wort, ()):
                zaehler[s] += 1
        for s, anzahl in zaehler.items():
            if anzahl < min_inhalt - 2:
                continue
            tw = p.satz_woerter[s]
            if len(tw) < min_inhalt:
                continue
            gemeinsam = len(tw & qw)
            wert = gemeinsam / min(len(tw), len(qw)) * 0.5 + 2 * gemeinsam / (len(tw) + len(qw)) * 0.5
            if wert >= schwelle and wert > bestes.get(s, (0,))[0]:
                bestes[s] = (wert, q_von, q_bis, gemeinsam)
    for s, (wert, q_von, q_bis, gemeinsam) in bestes.items():
        t_von, t_bis = p.saetze[s]
        treffer.append(Treffer(schluessel, "umformuliert", t_von, t_bis, q_von, q_bis,
                               round(wert, 3), gemeinsam))
    return treffer


def vergleiche(p: Pruefling, quelle: Tokens, schluessel: str, umformuliert: bool = True,
               min_woerter: int = 12, schwelle: float = 0.6) -> list:
    woertlich = finde_woertlich(p, quelle, schluessel, min_woerter=min_woerter)
    if not umformuliert:
        return woertlich
    abgedeckt = set()
    for t in woertlich:
        abgedeckt.update(range(t.t_von, t.t_bis + 1))
    # Ein Satz, der eine wörtliche Passage derselben Quelle nur anschneidet,
    # ist deren Rand und keine eigene Fundstelle.
    weitere = [t for t in finde_umformuliert(p, quelle, schluessel, schwelle)
               if not any(i in abgedeckt for i in range(t.t_von, t.t_bis + 1))]
    return woertlich + weitere


def bereinige(treffer: list) -> list:
    """Überlappende Treffer verschiedener Quellen: der stärkere bleibt.

    Wörtliche Treffer gehen vor umformulierten, danach zählt die Zahl
    gleicher Wörter. Ein schwächerer Treffer bleibt nur, wenn er zu mehr
    als der Hälfte außerhalb der schon belegten Bereiche liegt.
    """
    rang = sorted(treffer, key=lambda t: (t.art != "woertlich", -t.gleiche_woerter))
    belegt = set()
    behalten = []
    for t in rang:
        bereich = range(t.t_von, t.t_bis + 1)
        frei = sum(1 for i in bereich if i not in belegt)
        if frei > 0.5 * t.laenge:
            behalten.append(t)
            belegt.update(bereich)
        else:
            for b in behalten:
                if b.quelle != t.quelle and b.t_von <= t.t_bis and t.t_von <= b.t_bis \
                        and t.quelle not in b.weitere:
                    b.weitere.append(t.quelle)
                    break
    return sorted(behalten, key=lambda t: t.t_von)
