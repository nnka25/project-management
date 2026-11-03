import tempfile
import unittest
import zipfile
from pathlib import Path

from plagiatpruefung import abgleich, belege, einlesen, online, pruefung
from plagiatpruefung.text import saetze, zerlege

QUELLE_A = (
    "Die Organisationsforschung hat sich lange auf formale Strukturen konzentriert. "
    "Informelle Netzwerke innerhalb von Verwaltungen beeinflussen die Umsetzung politischer "
    "Programme in einem Ausmaß, das in der bisherigen Forschung systematisch unterschätzt wurde. "
    "Dabei zeigen Fallstudien aus drei Bundesländern, dass Sachbearbeiterinnen und Sachbearbeiter "
    "ihre Ermessensspielräume vor allem dann nutzen, wenn klare Vorgaben der Leitungsebene fehlen. "
    "Die Bedeutung kommunaler Spitzenverbände für die Koordination wird in der Literatur kaum behandelt. "
    "Verwaltungen reagieren auf neue Aufgaben häufig mit der Gründung zusätzlicher Stabsstellen, "
    "deren Wirkung auf die Entscheidungsqualität bislang kaum untersucht worden ist."
)

QUELLE_B = (
    "Digitale Verwaltungsleistungen setzen voraus, dass Register zuverlässig miteinander verknüpft sind. "
    "Ohne eine einheitliche Identifikationsnummer bleiben viele Verfahren auf Papierformulare angewiesen, "
    "weil Behörden die Angaben der Antragstellenden nicht automatisiert prüfen können."
)

ARBEIT = (
    "1 Einleitung\n\n"
    "Diese Arbeit untersucht Steuerung in öffentlichen Verwaltungen am Beispiel von Kommunen. "
    "Informelle Netzwerke innerhalb von Verwaltungen beeinflussen die Umsetzung politischer "
    "Programme in einem Ausmaß, das in der bisherigen Forschung systematisch unterschätzt wurde. "
    "Daraus folgt die Frage nach geeigneten Erhebungsmethoden.\n\n"
    "Fallstudien aus drei Bundesländern zeigen, dass Sachbearbeiterinnen und Sachbearbeiter "
    "ihre Ermessensspielräume vor allem dann nutzen, wenn klare Vorgaben der Leitungsebene fehlen "
    "(vgl. Mueller 2020: 14).\n\n"
    "Mueller betont: „Verwaltungen reagieren auf neue Aufgaben häufig mit der Gründung zusätzlicher "
    "Stabsstellen, deren Wirkung auf die Entscheidungsqualität bislang kaum untersucht worden ist“ "
    "(Mueller 2020: 17).\n\n"
    "Ohne einheitliche Identifikationsnummer sind zahlreiche Verfahren weiterhin auf Formulare aus Papier "
    "angewiesen, da Behörden Angaben von Antragstellenden nicht automatisiert prüfen können.\n\n"
    "Im Folgenden wird das methodische Vorgehen beschrieben, das eigene Interviews mit Beschäftigten "
    "aus zwölf Ämtern umfasst und diese mit Dokumentenanalysen verbindet.\n\n"
    "Literaturverzeichnis\n\n"
    "Mueller, Anna (2020): Informelle Netzwerke in Verwaltungen. Berlin."
)


class TestAbgleich(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "quellen").mkdir()
        (self.tmp / "quellen" / "Mueller_2020.txt").write_text(QUELLE_A, encoding="utf-8")
        (self.tmp / "quellen" / "Schulz_2019.txt").write_text(QUELLE_B, encoding="utf-8")
        self.arbeit = self.tmp / "arbeit.txt"
        self.arbeit.write_text(ARBEIT, encoding="utf-8")

    def _erg(self):
        quellen = pruefung.lokale_quellen(self.tmp / "quellen", protokoll=lambda *_: None)
        return pruefung.pruefe(self.arbeit, quellen, min_woerter=10, protokoll=lambda *_: None)

    def test_einstufungen(self):
        erg = self._erg()
        kuerzel = {f.kuerzel for f in erg.funde}
        self.assertIn("WU", kuerzel)     # wörtlich, ohne alles
        self.assertIn("WB", kuerzel)     # wörtlich mit vgl.-Beleg
        self.assertIn("ZK", kuerzel)     # korrektes Zitat
        self.assertIn("PU", kuerzel)     # umformuliert ohne Beleg
        self.assertTrue(erg.verzeichnis_gekuerzt)
        eigen = [f for f in erg.funde if "zwölf Ämtern" in f.text_auszug]
        self.assertEqual(eigen, [])

    def test_quelle_zugeordnet(self):
        erg = self._erg()
        pu = [f for f in erg.funde if f.kuerzel == "PU"][0]
        self.assertEqual(pu.quelle, "Schulz_2019.txt")
        zk = [f for f in erg.funde if f.kuerzel == "ZK"][0]
        self.assertTrue(zk.verweist_auf_quelle)

    def test_falsche_quelle(self):
        text = ARBEIT.replace("(Mueller 2020: 17)", "(Meier 2018: 3)")
        self.arbeit.write_text(text, encoding="utf-8")
        erg = self._erg()
        self.assertIn("ZF", {f.kuerzel for f in erg.funde})

    def test_berichte(self):
        from plagiatpruefung import bericht
        erg = self._erg()
        bericht.html_bericht(erg, self.tmp / "b.html")
        bericht.json_bericht(erg, self.tmp / "b.json")
        bericht.csv_bericht(erg, self.tmp / "b.csv")
        inhalt = (self.tmp / "b.html").read_text(encoding="utf-8")
        self.assertIn("Plagiatsbericht", inhalt)
        self.assertNotIn("\u2014", inhalt)

    def test_luecken_werden_ueberbrueckt(self):
        q = zerlege(QUELLE_A)
        geaendert = QUELLE_A.replace("systematisch unterschätzt", "deutlich unterschätzt")
        p = abgleich.Pruefling(zerlege(geaendert))
        t = abgleich.finde_woertlich(p, q, "q", min_woerter=10)
        laengster = max(t, key=lambda x: x.laenge)
        self.assertGreater(laengster.laenge, len(p.tok) * 0.9)


class TestBelege(unittest.TestCase):
    def test_autoren(self):
        self.assertEqual(belege.autoren_aus_dateiname("Mueller_Schmidt_2021a_Titel.pdf"), ["mueller", "schmidt"])
        self.assertEqual(belege.autoren_aus_dateiname("Müller 2020.pdf"), ["mueller"])

    def test_saetze_abkuerzungen(self):
        tok = zerlege("Das gilt z. B. für Kommunen (vgl. Mueller 2020: 14). Ein zweiter Satz folgt hier.")
        self.assertEqual(len(saetze(tok)), 2)


class FalscherClient:
    """Ersetzt die Netzabfragen durch feste Antworten im Format der APIs."""

    def hole(self, url, params=None, roh=False):
        if "wikipedia" in url and params.get("list") == "search":
            return {"query": {"search": [{"title": "Verwaltung"}]}}
        if "wikipedia" in url:
            return {"query": {"pages": [{"title": "Verwaltung", "extract": QUELLE_B}]}}
        return {"results": [{"id": "https://openalex.org/W1", "title": "Netzwerke",
                             "publication_year": 2020,
                             "authorships": [{"author": {"display_name": "Anna Müller"}}],
                             "abstract_inverted_index": {"Informelle": [0], "Netzwerke": [1]},
                             "best_oa_location": None}]}


class TestOnline(unittest.TestCase):
    def test_phrasen_und_dienste(self):
        tok = zerlege(ARBEIT)
        phrasen = online.suchphrasen(tok, 5, ausschluss=belege.zitatbereiche(ARBEIT))
        self.assertTrue(phrasen)
        self.assertFalse(any("Stabsstellen" in ph for ph in phrasen))   # Zitat ausgelassen
        cache = Path(tempfile.mkdtemp())
        wiki = online.wikipedia(FalscherClient(), phrasen[:1], cache, sprachen=("de",))
        self.assertEqual(wiki[0].schluessel, "Wikipedia (de): Verwaltung")
        oa = online.openalex(FalscherClient(), phrasen[:1], cache)
        self.assertEqual(oa[0].autoren, ["mueller"])
        self.assertIn("Informelle Netzwerke", oa[0].text)
        # zweiter Lauf kommt aus dem Zwischenspeicher
        self.assertEqual(len(list(cache.glob("*.json"))), 2)


class TestDocx(unittest.TestCase):
    def test_fussnoten(self):
        w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        doc = (f'<w:document {w}><w:body><w:p><w:r><w:t>Ein Satz mit Beleg.</w:t></w:r>'
               f'<w:r><w:footnoteReference w:id="2"/></w:r></w:p></w:body></w:document>')
        fn = (f'<w:footnotes {w}><w:footnote w:type="separator" w:id="0"><w:p/></w:footnote>'
              f'<w:footnote w:id="2"><w:p><w:r><w:t>Vgl. Mueller 2020, S. 14.</w:t></w:r></w:p></w:footnote></w:footnotes>')
        pfad = Path(tempfile.mkdtemp()) / "t.docx"
        with zipfile.ZipFile(pfad, "w") as z:
            z.writestr("word/document.xml", doc)
            z.writestr("word/footnotes.xml", fn)
        d = einlesen.lies(pfad)
        self.assertIn("[^2]", d.text)
        self.assertEqual(d.fussnoten["^2"], "Vgl. Mueller 2020, S. 14.")


if __name__ == "__main__":
    unittest.main()
