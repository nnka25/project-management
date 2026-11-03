"""Text aus .txt, .md, .docx, .odt und .pdf lesen.

Bei .docx bleiben Fußnoten erhalten: An der Stelle des Fußnotenzeichens
steht im Text eine Marke [^n], der Fußnotentext liegt getrennt vor. So kann
die Belegprüfung auch Arbeiten mit Fußnotenzitierweise auswerten.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ODF_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"

ENDUNGEN = {".txt", ".md", ".docx", ".odt", ".pdf"}


@dataclass
class Dokument:
    pfad: Path
    text: str
    fussnoten: dict = field(default_factory=dict)
    seiten: list = field(default_factory=list)   # Zeichenanfang je PDF-Seite

    def seite_bei(self, zeichen: int):
        """PDF-Seite (ab 1) zu einer Zeichenposition, sonst None."""
        if not self.seiten:
            return None
        seite = 1
        for i, a in enumerate(self.seiten, start=1):
            if a <= zeichen:
                seite = i
            else:
                break
        return seite


def lies(pfad) -> Dokument:
    pfad = Path(pfad)
    endung = pfad.suffix.lower()
    if endung in (".txt", ".md"):
        return Dokument(pfad, _lies_klartext(pfad))
    if endung == ".docx":
        return _lies_docx(pfad)
    if endung == ".odt":
        return Dokument(pfad, _lies_odt(pfad))
    if endung == ".pdf":
        return _lies_pdf(pfad)
    raise ValueError(f"Dateiformat nicht unterstützt: {pfad.name}")


def _lies_klartext(pfad: Path) -> str:
    roh = pfad.read_bytes()
    for kodierung in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return roh.decode(kodierung)
        except UnicodeDecodeError:
            continue
    return roh.decode("utf-8", errors="replace")


def _absatztext(p, fussnoten_marken=True) -> str:
    teile = []
    for el in p.iter():
        if el.tag == W + "t":
            teile.append(el.text or "")
        elif el.tag == W + "tab":
            teile.append("\t")
        elif el.tag in (W + "br", W + "cr"):
            teile.append("\n")
        elif el.tag in (W + "footnoteReference", W + "endnoteReference") and fussnoten_marken:
            nr = el.get(W + "id")
            art = "^" if el.tag.endswith("footnoteReference") else "^E"
            teile.append(f"[{art}{nr}]")
    return "".join(teile)


def _lies_docx(pfad: Path) -> Dokument:
    with zipfile.ZipFile(pfad) as z:
        wurzel = ET.fromstring(z.read("word/document.xml"))
        absaetze = [_absatztext(p) for p in wurzel.iter(W + "p")]
        fussnoten = {}
        for teil, praefix in (("word/footnotes.xml", "^"), ("word/endnotes.xml", "^E")):
            if teil not in z.namelist():
                continue
            fw = ET.fromstring(z.read(teil))
            for fn in fw:
                nr = fn.get(W + "id")
                if nr is None or fn.get(W + "type") in ("separator", "continuationSeparator"):
                    continue
                t = " ".join(_absatztext(p, False) for p in fn.iter(W + "p")).strip()
                if t:
                    fussnoten[f"{praefix}{nr}"] = t
    text = "\n\n".join(a for a in absaetze if a.strip())
    return Dokument(pfad, text, fussnoten)


def _lies_odt(pfad: Path) -> str:
    with zipfile.ZipFile(pfad) as z:
        wurzel = ET.fromstring(z.read("content.xml"))
    absaetze = []
    for el in wurzel.iter():
        if el.tag in (ODF_TEXT + "p", ODF_TEXT + "h"):
            absaetze.append("".join(el.itertext()))
    return "\n\n".join(a for a in absaetze if a.strip())


def _lies_pdf(pfad: Path) -> Dokument:
    try:
        from pypdf import PdfReader
    except ImportError as fehler:
        raise RuntimeError("Für PDF-Dateien wird pypdf benötigt: pip install pypdf") from fehler
    leser = PdfReader(str(pfad))
    teile, seiten, pos = [], [], 0
    for seite in leser.pages:
        try:
            t = seite.extract_text() or ""
        except Exception:
            t = ""
        t = bereinige_pdf_text(t)
        seiten.append(pos)
        teile.append(t)
        pos += len(t) + 2
    return Dokument(pfad, "\n\n".join(teile), seiten=seiten)


def bereinige_pdf_text(t: str) -> str:
    """Silbentrennung am Zeilenende auflösen, harte Zeilenumbrüche glätten."""
    t = t.replace("­", "")
    t = re.sub(r"(\w)-\n\s*([a-zäöüß])", r"\1\2", t)
    t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t


VERZEICHNIS = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(Literaturverzeichnis|Quellenverzeichnis|Literatur|"
    r"Literatur- und Quellenverzeichnis|Bibliographie|Bibliografie|References|Bibliography|"
    r"Works Cited)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def schneide_verzeichnis(text: str) -> tuple:
    """Kürzt den Text vor dem Literaturverzeichnis.

    Gesucht wird nur in der hinteren Hälfte, damit ein Eintrag im
    Inhaltsverzeichnis den Text nicht abschneidet. Rückgabe: (Text, gekürzt?).
    """
    treffer = [m for m in VERZEICHNIS.finditer(text) if m.start() > len(text) * 0.5]
    if not treffer:
        return text, False
    return text[:treffer[-1].start()], True


def quellen_im_ordner(ordner) -> list:
    ordner = Path(ordner)
    return sorted(p for p in ordner.rglob("*")
                  if p.is_file() and p.suffix.lower() in ENDUNGEN and not p.name.startswith(("~$", ".")))
