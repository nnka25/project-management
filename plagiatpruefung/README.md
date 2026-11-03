# Plagiatprüfung für wissenschaftliche Texte

Prüft eine umfangreiche Arbeit (Dissertation, Artikel, Abschlussarbeit) auf
Übereinstimmungen mit Quellen und wertet aus, ob die Fundstellen als Zitat
gekennzeichnet und belegt sind. Läuft lokal, ohne Konto und ohne
Hochladen der Arbeit.

## Was das Programm leistet

- **Wörtliche Übernahmen** über Wortfolgen-Abgleich (5-Gramme). Kleine
  Änderungen, Einschübe und Auslassungen werden überbrückt, die Passage
  wird als Ganzes gemeldet.
- **Umformulierte Stellen** über den Vergleich der Inhaltswörter je Satz.
- **Belegprüfung** für jede Fundstelle: Anführungszeichen ja/nein,
  Kurzbeleg (Autor Jahr: Seite), Fußnote (bei .docx), Nummernbeleg [12],
  und ob der Beleg die gefundene Quelle nennt.
- **Online-Suche (optional)** in Wikipedia (de/en) und OpenAlex; frei
  zugängliche Volltexte werden geladen und mitverglichen.
- **Bericht** als HTML (Übersicht, Fundstellen nebeneinander mit der
  Quelle, markierter Volltext), dazu JSON und CSV (Excel).
- Für große Texte gebaut: 136.000 Wörter gegen 200 Quellen mit zusammen
  1,8 Mio. Wörtern dauern im Test rund 3 Sekunden bei ca. 100 MB Speicher.

## Was es nicht leistet

- Es kennt **nur die Quellen, die es bekommt**. Kommerzielle Dienste
  (z. B. Turnitin) vergleichen mit Milliarden Webseiten und
  Verlagsdatenbanken. Die meisten Hochschulen stellen einen solchen Dienst
  bereit; dieses Programm ersetzt ihn nicht, sondern ergänzt ihn um die
  eigene Literatur und die Belegprüfung.
- **Übersetzungsplagiate** (Quelle englisch, Arbeit deutsch) werden nicht erkannt.
- **Gescannte PDFs** ohne Textebene liefern keinen Text (vorher OCR).
- Blockzitate ohne Anführungszeichen gelten als „ohne Anführungszeichen“.
- Jede Markierung ist ein Prüfhinweis, kein Urteil. Auch professionelle
  Software findet nicht alle Plagiate und meldet unproblematische Stellen;
  die Berichte müssen von Menschen gelesen werden (Foltýnek et al. 2020).

## Installation

Python 3.10 oder neuer. Für PDF-Quellen zusätzlich:

```bash
pip install -r requirements.txt
```

## Aufruf

```bash
cd plagiatpruefung
python -m plagiatpruefung Arbeit.docx --quellen Quellen
```

Die Berichte landen neben der Arbeit:
`plagiatsbericht_Arbeit.html`, `.json`, `.csv`.

### Quellen benennen

Dateiname = Kurzbeleg, damit die Belegprüfung den Autor kennt:

```
Quellen/
  Mueller_2020.pdf
  Mueller_Schmidt_2021a_Verwaltungsreform.pdf
  Weber 2019.docx
```

Formate: .pdf, .docx, .odt, .txt, .md (Unterordner werden mitgelesen).
Eigene frühere Veröffentlichungen gehören ebenfalls in den Ordner
(Selbstplagiat).

### Optionen

| Option | Wirkung |
|---|---|
| `--quellen ORDNER` | Quellenordner, mehrfach möglich |
| `--online` | zusätzlich Wikipedia und OpenAlex durchsuchen |
| `--nur-wikipedia` | online nur Wikipedia |
| `--anfragen 40` | Zahl der Suchphrasen je Dienst |
| `--kontakt name@uni.de` | Kontaktadresse im User-Agent (von Wikimedia erbeten) |
| `--openalex-key KEY` | kostenloser OpenAlex-Schlüssel (oder Umgebungsvariable `OPENALEX_API_KEY`) |
| `--min-woerter 12` | Mindestlänge einer wörtlichen Übereinstimmung |
| `--schwelle 0.6` | Empfindlichkeit für Umformulierungen (niedriger = mehr Treffer) |
| `--nur-woertlich` | keine Suche nach Umformulierungen |
| `--mit-verzeichnis` | Literaturverzeichnis mitprüfen (Vorgabe: abgeschnitten) |
| `--ausgabe ORDNER` | Zielordner der Berichte |

**Datenschutz bei `--online`:** Übertragen werden nur kurze Wortfolgen
(zehn Wörter) aus der Arbeit, nie der ganze Text. Ohne `--online` verlässt
nichts den Rechner. OpenAlex verlangt seit 2026 für größere
Abfragemengen einen kostenlosen API-Schlüssel.

## Einstufung der Fundstellen

| Kürzel | Bedeutung | Stufe |
|---|---|---|
| WU | wörtlich übernommen, ohne Kennzeichnung und ohne Beleg | zuerst klären |
| WB | wörtlich übernommen ohne Anführungszeichen, Beleg vorhanden (z. B. nur „vgl.“) | zuerst klären |
| ZO | wörtliches Zitat ohne Beleg | prüfen |
| ZF / PF | Beleg nennt eine andere Quelle als die gefundene | prüfen |
| PU | umformuliert ohne Beleg | prüfen |
| PB | umformuliert mit Beleg (Nähe zum Original prüfen) | Hinweis |
| ZK | wörtliches Zitat, gekennzeichnet und belegt | korrekt |

WB ist der klassische Fall, den Belegprüfungen übersehen: Die Quelle ist
genannt, aber der Wortlaut wird als eigener ausgegeben.

## Verhältnis zu `textpruefung-dissertation`

`uebernahme.py` aus jenem Werkzeugkasten prüft satzweise nur Sätze ohne
Beleg. Dieses Programm prüft zusätzlich belegte Stellen (Fall WB),
erkennt satzübergreifende Passagen, sucht online und ist auf ganze
Dissertationen in einem Lauf ausgelegt. Die Kürzel folgen demselben
vierstufigen Schema (schwer, prüfen, Hinweis, ok).

## Tests

```bash
python -m unittest discover -s tests
```

## Literatur

Foltýnek, Tomáš / Dlabolová, Dita / Anohina-Naumeca, Alla / Razı, Salim /
Kravjar, Július / Kamzola, Laima / Guerrero-Dib, Jean / Çelik, Özgür /
Weber-Wulff, Debora (2020): Testing of support tools for plagiarism
detection, in: International Journal of Educational Technology in Higher
Education, 17. Jg., Art. 46, https://doi.org/10.1186/s41239-020-00192-4
(Vorabfassung: arXiv:2002.04279).
