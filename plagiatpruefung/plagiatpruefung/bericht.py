"""Ausgabe als HTML-Bericht, JSON und CSV."""

import csv
import html
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

FARBEN = {"schwer": "#d9534f", "pruefen": "#f0ad4e", "hinweis": "#5bc0de", "ok": "#5cb85c"}
STUFENNAME = {"schwer": "Zuerst klären", "pruefen": "Prüfen", "hinweis": "Hinweis", "ok": "Korrekt zitiert"}

CSS = """
:root{--bg:#fff;--fg:#1d2330;--muted:#5d6675;--line:#dfe3ea;--card:#f6f7f9}
@media (prefers-color-scheme:dark){:root{--bg:#15181e;--fg:#e6e8ec;--muted:#9aa3b2;--line:#2c313a;--card:#1d2129}}
body{background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}
main{max-width:1100px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.2rem;margin-top:2em;border-bottom:1px solid var(--line);padding-bottom:.3em}
.muted{color:var(--muted)}table{border-collapse:collapse;width:100%;font-size:.92rem}
td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.kacheln{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}
.kachel{background:var(--card);border-radius:8px;padding:12px;border-left:5px solid var(--line)}
.kachel b{display:block;font-size:1.5rem}
.fund{background:var(--card);border-radius:8px;padding:12px 14px;margin:12px 0;border-left:5px solid}
.paar{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:700px){.paar{grid-template-columns:1fr}}
.paar div{font-size:.92rem;white-space:pre-wrap;word-wrap:break-word}
.label{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.volltext{white-space:pre-wrap;font-size:.95rem}
mark{color:inherit;border-radius:2px;padding:0 1px}
mark a{color:inherit;text-decoration:none}
.badge{display:inline-block;font-size:.8rem;font-weight:600;padding:1px 7px;border-radius:10px;color:#fff}
details summary{cursor:pointer}
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _hex_rgba(hex_farbe: str, alpha: float) -> str:
    r, g, b = (int(hex_farbe[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def html_bericht(erg, ziel: Path, volltext: bool = True):
    a = erg.anteile()
    teile = [f"<!doctype html><html lang='de'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Plagiatsbericht</title><style>{CSS}</style></head><body><main>"]
    teile.append(f"<h1>Plagiatsbericht</h1><p class='muted'>{_e(Path(erg.arbeit).name)} · "
                 f"{erg.woerter_gesamt:,} Wörter · {len(erg.quellen)} Quellen verglichen · "
                 f"{datetime.now():%d.%m.%Y %H:%M} · Laufzeit {erg.dauer} s</p>".replace(",", "."))
    teile.append("<div class='kacheln'>")
    teile.append(f"<div class='kachel'><span class='muted'>Übereinstimmung gesamt</span><b>{a['uebereinstimmung']} %</b></div>")
    for stufe in ("schwer", "pruefen", "hinweis", "ok"):
        anzahl = sum(1 for f in erg.funde if f.stufe == stufe)
        teile.append(f"<div class='kachel' style='border-left-color:{FARBEN[stufe]}'>"
                     f"<span class='muted'>{STUFENNAME[stufe]}</span><b>{a[stufe]} %</b>"
                     f"<span class='muted'>{anzahl} {'Stelle' if anzahl == 1 else 'Stellen'}</span></div>")
    teile.append("</div>")
    teile.append("<p class='muted'>Prozentwerte: Anteil der Wörter der Arbeit. Jede Markierung ist ein "
                 "Prüfhinweis, kein Urteil. Ob eine Übereinstimmung ein Plagiat ist, lässt sich nur "
                 "durch Lesen von Arbeit und Quelle entscheiden. Verglichen wurde nur mit den "
                 "aufgeführten Quellen.</p>")
    if erg.verzeichnis_gekuerzt:
        teile.append("<p class='muted'>Das Literaturverzeichnis wurde nicht geprüft.</p>")
    for h in erg.hinweise:
        teile.append(f"<p><b>Hinweis:</b> {_e(h)}</p>")

    teile.append("<h2>Legende</h2><table>")
    for kz, bez, stufe in [("WU", "Wörtlich übernommen ohne Kennzeichnung und ohne Beleg", "schwer"),
                           ("WB", "Wörtlich übernommen ohne Anführungszeichen, Beleg vorhanden", "schwer"),
                           ("ZO", "Wörtliches Zitat ohne Beleg", "pruefen"),
                           ("ZF / PF", "Beleg nennt eine andere Quelle als die gefundene", "pruefen"),
                           ("PU", "Umformuliert ohne Beleg", "pruefen"),
                           ("PB", "Umformuliert, Beleg vorhanden (Nähe zum Original prüfen)", "hinweis"),
                           ("ZK", "Wörtliches Zitat, gekennzeichnet und belegt", "ok")]:
        teile.append(f"<tr><td><span class='badge' style='background:{FARBEN[stufe]}'>{kz}</span></td>"
                     f"<td>{_e(bez)}</td></tr>")
    teile.append("</table>")

    teile.append("<h2>Quellen mit Treffern</h2><table><tr><th>Quelle</th><th>Stellen</th><th>Wörter</th></tr>")
    for q in erg.quellen:
        if not q["treffer"]:
            continue
        name = _e(q["name"])
        if q.get("url", "").startswith("http"):
            name = f"<a href='{_e(q['url'])}'>{name}</a>"
        teile.append(f"<tr><td>{name}</td><td>{q['treffer']}</td><td>{q['woerter_treffer']}</td></tr>")
    teile.append("</table>")

    teile.append("<h2>Fundstellen</h2>")
    reihenfolge = {"schwer": 0, "pruefen": 1, "hinweis": 2, "ok": 3}
    for f in sorted(erg.funde, key=lambda f: (reihenfolge[f.stufe], f.zeichen_von)):
        if f.stufe == "ok":
            continue
        teile.append(_fund_html(f))
    ok = [f for f in erg.funde if f.stufe == "ok"]
    if ok:
        teile.append(f"<details><summary>{len(ok)} korrekt gekennzeichnete Zitate anzeigen</summary>")
        teile += [_fund_html(f) for f in ok]
        teile.append("</details>")

    if volltext:
        teile.append("<h2>Text mit Markierungen</h2><div class='volltext'>")
        pos = 0
        for f in sorted(erg.funde, key=lambda f: f.zeichen_von):
            if f.zeichen_von < pos:
                continue
            teile.append(_e(erg.text[pos:f.zeichen_von]))
            teile.append(f"<mark id='t{f.nummer}' style='background:{_hex_rgba(FARBEN[f.stufe], .35)}'>"
                         f"<a href='#f{f.nummer}' title='{_e(f.kuerzel)}: {_e(f.quelle)}'>"
                         f"{_e(erg.text[f.zeichen_von:f.zeichen_bis])}</a></mark>")
            pos = f.zeichen_bis
        teile.append(_e(erg.text[pos:]) + "</div>")
    teile.append("</main></body></html>")
    ziel.write_text("".join(teile), encoding="utf-8")


def _fund_html(f) -> str:
    farbe = FARBEN[f.stufe]
    seite = f", S. {f.quelle_seite} (PDF-Seite)" if f.quelle_seite else ""
    weitere = f"<br><span class='muted'>Auch in: {_e(', '.join(f.weitere_quellen))}</span>" if f.weitere_quellen else ""
    beleg = _e(f.beleg) if f.beleg else "kein Beleg gefunden"
    bezug = {True: " (nennt diese Quelle)", False: " (nennt eine andere Quelle)", None: ""}[f.verweist_auf_quelle]
    return (f"<div class='fund' id='f{f.nummer}' style='border-left-color:{farbe}'>"
            f"<span class='badge' style='background:{farbe}'>{_e(f.kuerzel)}</span> "
            f"<b>Nr. {f.nummer}</b> · {_e(f.bezeichnung)} · {f.woerter} Wörter · "
            f"Ähnlichkeit {round(100 * f.aehnlichkeit)} % · <a href='#t{f.nummer}'>im Text</a>"
            f"<div class='paar'><div><div class='label'>Arbeit</div>{_e(f.text_auszug)}</div>"
            f"<div><div class='label'>{_e(f.quelle)}{_e(seite)}</div>{_e(f.quelle_auszug)}</div></div>"
            f"<div class='muted' style='font-size:.85rem;margin-top:6px'>Anführungszeichen: "
            f"{'ja' if f.in_anfuehrung else 'nein'} · Beleg: {beleg}{bezug}{weitere}</div></div>")


def json_bericht(erg, ziel: Path):
    d = {"arbeit": erg.arbeit, "woerter": erg.woerter_gesamt, "anteile": erg.anteile(),
         "dauer_s": erg.dauer, "hinweise": erg.hinweise, "quellen": erg.quellen,
         "funde": [asdict(f) for f in erg.funde]}
    ziel.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def csv_bericht(erg, ziel: Path):
    with ziel.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Nr", "Kürzel", "Stufe", "Bezeichnung", "Quelle", "Seite", "Wörter",
                    "Ähnlichkeit", "Anführungszeichen", "Beleg", "Text", "Quelltext"])
        for f in erg.funde:
            w.writerow([f.nummer, f.kuerzel, f.stufe, f.bezeichnung, f.quelle, f.quelle_seite or "",
                        f.woerter, f"{f.aehnlichkeit:.2f}".replace(".", ","),
                        "ja" if f.in_anfuehrung else "nein", f.beleg, f.text_auszug, f.quelle_auszug])
