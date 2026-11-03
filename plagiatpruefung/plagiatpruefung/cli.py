"""Kommandozeile.

Beispiele:
    python -m plagiatpruefung Arbeit.docx --quellen Quellen
    python -m plagiatpruefung Arbeit.docx --quellen Quellen --online --kontakt name@uni.de
"""

import argparse
import os
import sys
from pathlib import Path

from . import __version__, bericht, belege, einlesen, online, pruefung
from .text import zerlege


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plagiatpruefung",
                                 description="Prüft einen wissenschaftlichen Text auf Übereinstimmungen mit Quellen.")
    ap.add_argument("arbeit", help="zu prüfende Arbeit (.docx, .odt, .pdf, .txt, .md)")
    ap.add_argument("--quellen", action="append", default=[],
                    help="Ordner mit Vergleichsquellen (mehrfach möglich). Dateiname als Kurzbeleg, "
                         "z. B. Mueller_Schmidt_2021.pdf")
    ap.add_argument("--ausgabe", help="Zielordner für die Berichte (Vorgabe: Ordner der Arbeit)")
    ap.add_argument("--online", action="store_true", help="zusätzlich Wikipedia und OpenAlex durchsuchen")
    ap.add_argument("--nur-wikipedia", action="store_true", help="online nur Wikipedia, kein OpenAlex")
    ap.add_argument("--anfragen", type=int, default=40, help="Zahl der Suchphrasen je Dienst (Vorgabe 40)")
    ap.add_argument("--kontakt", default="", help="E-Mail für den User-Agent (von Wikimedia erbeten)")
    ap.add_argument("--openalex-key", default=os.environ.get("OPENALEX_API_KEY", ""),
                    help="OpenAlex-API-Schlüssel (oder Umgebungsvariable OPENALEX_API_KEY)")
    ap.add_argument("--min-woerter", type=int, default=12,
                    help="Mindestzahl gleicher Wörter für einen wörtlichen Treffer (Vorgabe 12)")
    ap.add_argument("--schwelle", type=float, default=0.6,
                    help="Ähnlichkeitsschwelle 0..1 für umformulierte Sätze (Vorgabe 0,6)")
    ap.add_argument("--nur-woertlich", action="store_true", help="keine Suche nach Umformulierungen")
    ap.add_argument("--mit-verzeichnis", action="store_true", help="Literaturverzeichnis mitprüfen")
    ap.add_argument("--ohne-volltext", action="store_true", help="markierten Volltext nicht in den Bericht")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    arbeit = Path(args.arbeit)
    if not arbeit.is_file():
        print(f"Datei nicht gefunden: {arbeit}", file=sys.stderr)
        return 2
    if not args.quellen and not args.online:
        print("Bitte mindestens --quellen <Ordner> oder --online angeben.", file=sys.stderr)
        return 2
    ausgabe = Path(args.ausgabe) if args.ausgabe else arbeit.parent
    ausgabe.mkdir(parents=True, exist_ok=True)

    quellen = []
    for ordner in args.quellen:
        if not Path(ordner).is_dir():
            print(f"Quellenordner nicht gefunden: {ordner}", file=sys.stderr)
            return 2
        print(f"Lese Quellen aus {ordner} ...")
        quellen += pruefung.lokale_quellen(ordner, arbeit)

    if args.online:
        print("Online-Suche (es werden nur kurze Wortfolgen übertragen) ...")
        dok = einlesen.lies(arbeit)
        text = dok.text if args.mit_verzeichnis else einlesen.schneide_verzeichnis(dok.text)[0]
        tok = zerlege(text)
        phrasen = online.suchphrasen(tok, args.anfragen, ausschluss=belege.zitatbereiche(text))
        client = online.Client(args.kontakt)
        cache = ausgabe / "online_quellen"
        gefunden = online.wikipedia(client, phrasen, cache)
        if not args.nur_wikipedia:
            gefunden += online.openalex(client, phrasen, cache, args.openalex_key)
        print(f"  {len(gefunden)} Online-Texte gefunden")
        quellen += [pruefung.Quelle(q.schluessel, q.text, q.autoren, q.url) for q in gefunden if q.text.strip()]

    if not quellen:
        print("Keine lesbaren Quellen gefunden.", file=sys.stderr)
        return 1
    print(f"Vergleiche mit {len(quellen)} Quellen ...")
    erg = pruefung.pruefe(arbeit, quellen, mit_verzeichnis=args.mit_verzeichnis,
                          umformuliert=not args.nur_woertlich, min_woerter=args.min_woerter,
                          schwelle=args.schwelle)

    name = arbeit.stem
    html_pfad = ausgabe / f"plagiatsbericht_{name}.html"
    bericht.html_bericht(erg, html_pfad, volltext=not args.ohne_volltext)
    bericht.json_bericht(erg, ausgabe / f"plagiatsbericht_{name}.json")
    bericht.csv_bericht(erg, ausgabe / f"plagiatsbericht_{name}.csv")

    a = erg.anteile()
    print(f"\nÜbereinstimmung: {a['uebereinstimmung']} % der Wörter, davon "
          f"zuerst klären {a['schwer']} %, prüfen {a['pruefen']} %, "
          f"Hinweis {a['hinweis']} %, korrekt zitiert {a['ok']} %")
    print(f"{len(erg.funde)} Fundstellen, Bericht: {html_pfad}")
    for h in erg.hinweise:
        print("Hinweis:", h)
    return 0
