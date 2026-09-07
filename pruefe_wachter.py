# -*- coding: utf-8 -*-
"""Prueft die Rechenteile des Lieferwaechters.

Laeuft ohne Netz, ohne Konfiguration und ohne Spielkonto. Die Zahlen sind
erfunden, aber in sich stimmig - jede Erwartung ist von Hand nachgerechnet
und im Kommentar begruendet. Wer eine Erwartung anpassen muss, weil der
Code sie nicht mehr trifft, sollte zuerst nachrechnen, wer recht hat.

    python pruefe_wachter.py
"""
from datetime import datetime

import oi_konfiguration as k
import oi_wachter as w

fehler = 0


def pruefe(was, bedingung, zusatz=""):
    global fehler
    print(("  ok   " if bedingung else "  FEHL ") + was
          + ("" if bedingung else "  ->  " + str(zusatz)))
    if not bedingung:
        fehler += 1


# Ein erfundener Konzern mit einem erfundenen Vertrag: zwei Lieferungen am
# Tag, vier Tage lang.
VERTRAG = {
    "nummer": "01-02-3-04-05",
    "aktiv": True,
    "slots": ["09:35", "20:15"],
    "bedarf": {"Diesel": 100_000, "Pipeline": 50},
    "bis": "2026-01-05",
}
CFG = {
    "konzern": {"name": "Beispielkonzern", "kid": 1},
    "spiel": {"welt": "beispiel.invalid", "code": "irgendwas"},
    "vertraege": [VERTRAG],
}

FREITAG_MITTAG = datetime(2026, 1, 2, 12, 0)


print("== Termine ==")
termin, fenster = w.naechster_termin(VERTRAG, FREITAG_MITTAG)
# Um 12:00 ist 09:35 vorbei, 20:15 kommt noch.
pruefe("naechster Termin ist 20:15 desselben Tages",
       termin == datetime(2026, 1, 2, 20, 15), termin)
pruefe("das Fenster oeffnet vier Stunden vorher",
       fenster == datetime(2026, 1, 2, 16, 15), fenster)

# Nach der letzten Lieferung des Tages muss der naechste Termin am
# Folgetag liegen - genau hier scheitert eine Rechnung, die nur den
# heutigen Tag betrachtet.
spaet, _ = w.naechster_termin(VERTRAG, datetime(2026, 1, 2, 21, 0))
pruefe("nach dem letzten Slot zaehlt der Folgetag",
       spaet == datetime(2026, 1, 3, 9, 35), spaet)

pruefe("ohne Slots gibt es keinen Termin",
       w.naechster_termin({"nummer": "x", "bedarf": {"Diesel": 1}},
                          FREITAG_MITTAG) == (None, None))

print("\n== Annahmesperre ==")
# Fuenf Minuten nach 09:35 laeuft die Sperre, sie endet 09:35 + 1:01.
pruefe("kurz nach der Lieferung gesperrt bis 10:36",
       w.sperrzeit(CFG, datetime(2026, 1, 2, 9, 40))
       == datetime(2026, 1, 2, 10, 36),
       w.sperrzeit(CFG, datetime(2026, 1, 2, 9, 40)))
pruefe("um 11:00 keine Sperre mehr",
       w.sperrzeit(CFG, datetime(2026, 1, 2, 11, 0)) is None)

print("\n== Deckung einer Teillieferung ==")
gedeckt, fehlend = w.deckung(VERTRAG, {"Diesel": 150_000, "Pipeline": 30})
pruefe("Diesel ist gedeckt", [g[0] for g in gedeckt] == ["Diesel"], gedeckt)
pruefe("Pipeline fehlt mit 20 Stueck",
       fehlend == [("Pipeline", 50, 30)], fehlend)

print("\n== Offene Lieferungen ==")
# Vom 02.01. 12:00 bis einschliesslich 05.01.: heute noch 20:15, dann drei
# volle Tage mit je zwei Lieferungen = 1 + 6 = 7.
offen = w.offene_lieferungen(VERTRAG, FREITAG_MITTAG, {})
pruefe("sieben offene Lieferungen", len(offen) == 7, len(offen))

erledigt = {w.schluessel(VERTRAG, datetime(2026, 1, 2, 20, 15)):
            {"erledigt_gemeldet": True}}
pruefe("eine als erledigt gemeldete zaehlt nicht mehr",
       len(w.offene_lieferungen(VERTRAG, FREITAG_MITTAG, erledigt)) == 6)

print("\n== Gesamtbedarf und Lage ==")
summe, anzahl = w.gesamtbedarf(CFG, FREITAG_MITTAG, {})
# 7 Lieferungen a 100.000 Diesel und 50 Pipeline.
pruefe("Bedarf ist siebenfach", summe == {"Diesel": 700_000, "Pipeline": 350},
       summe)
pruefe("sieben Lieferungen gezaehlt", anzahl == 7, anzahl)

text, knapp = w.baue_gesamtlage(CFG, {"Diesel": 700_000, "Pipeline": 350},
                                FREITAG_MITTAG, {})
pruefe("genau aufgehender Bestand gilt nicht als knapp", knapp is False)

text, knapp = w.baue_gesamtlage(CFG, {"Diesel": 699_999, "Pipeline": 350},
                                FREITAG_MITTAG, {})
pruefe("ein einziges Stueck zu wenig gilt als knapp", knapp is True)
pruefe("die Fehlmenge steht im Text", "1 fehlen" in text, text)

print("\n== Wann wird gemeldet ==")
pruefe("beim Oeffnen des Fensters",
       w._naechster_ausloeser({}, False, 200) == "start_gemeldet")
pruefe("danach nicht noch einmal",
       w._naechster_ausloeser({"start_gemeldet": True}, False, 200) is None)
pruefe("45 Minuten vorher erneut",
       w._naechster_ausloeser({"start_gemeldet": True}, False, 40)
       == "erinnert_45")
pruefe("15 Minuten vorher erneut",
       w._naechster_ausloeser({"start_gemeldet": True, "erinnert_45": True},
                              False, 10) == "erinnert_15")
pruefe("erledigt wird gemeldet",
       w._naechster_ausloeser({}, True, 5) == "erledigt_gemeldet")
pruefe("erledigt nur einmal",
       w._naechster_ausloeser({"erledigt_gemeldet": True}, True, 5) is None)

print("\n== Ausgangswert bei Fensteroeffnung ==")
# Der Fall, der im Betrieb schiefging: Fenster oeffnet 09:45, der Takt
# laeuft auf :43 und :53, geliefert wird um 09:52. Wer den Stand von 09:53
# als Ausgangswert nimmt, misst gegen einen Wert NACH der Lieferung und
# sieht den Rueckgang nie.
import os as _os, tempfile as _tempfile
_ordner = _tempfile.mkdtemp()
_csv = _os.path.join(_ordner, "lager_verlauf.csv")
with open(_csv, "w", encoding="utf-8") as _f:
    _f.write("zeit;Rohoel;Kerosin;Diesel;Benzin;Turm;Tank;Pipeline\n")
    _f.write("2026-09-07 09:33:10;0;500000;0;0;0;0;0\n")   # vor dem Fenster
    _f.write("2026-09-07 09:43:33;0;500000;0;0;0;0;0\n")   # richtig: hier
    _f.write("2026-09-07 09:53:34;0;207610;0;0;0;0;0\n")   # schon geliefert

_fenster = datetime(2026, 9, 7, 9, 45)
_stand = w.stand_bei(_fenster, pfad=_csv)
pruefe("nimmt die Zeile VOR der Fensteroeffnung",
       _stand and _stand["Kerosin"] == 500_000, _stand)
pruefe("nicht die danach", _stand and _stand["Kerosin"] != 207_610, _stand)
pruefe("vor der ersten Zeile gibt es nichts",
       w.stand_bei(datetime(2026, 9, 7, 9, 0), pfad=_csv) is None)
pruefe("ohne Datei ebenfalls nichts",
       w.stand_bei(_fenster, pfad=_os.path.join(_ordner, "fehlt.csv")) is None)

# Mit dem richtigen Ausgangswert wird die Lieferung erkannt.
_v = {"nummer": "07-09", "bedarf": {"Kerosin": 292_390}}
_eintrag = {"start": _stand}
pruefe("Lieferung wird erkannt", w.ist_erledigt(_v, _eintrag, {"Kerosin": 207_610}))

# Mit dem falschen Ausgangswert - dem Stand NACH der Lieferung - nicht.
_falsch = {"start": {"Kerosin": 207_610}}
pruefe("mit dem Stand danach bliebe sie unsichtbar",
       not w.ist_erledigt(_v, _falsch, {"Kerosin": 207_610}))

print("\n== Erledigt bleibt erledigt ==")
# Wird nach der Lieferung nachgeliefert, schrumpft der gemessene Rueckgang.
# Ohne Gedaechtnis erschiene der Termin wieder als offen - mitsamt neuer
# Meldung fuer etwas, das laengst durch ist.
_e = {"start": {"Kerosin": 500_000}}
pruefe("erst erkannt", w.ist_erledigt(_v, _e, {"Kerosin": 207_610}))
pruefe("im Eintrag vermerkt", _e.get("erledigt") is True, _e)
pruefe("bleibt erledigt, auch wenn wieder aufgefuellt wird",
       w.ist_erledigt(_v, _e, {"Kerosin": 500_000}))

print("\n== Konsolentauglichkeit ==")
# nur_text verspricht, Text fuer die Windows-Konsole zu entschaerfen. Die
# laeuft oft auf cp1252 - was sich dort nicht kodieren laesst, bringt die
# Ausgabe zum Absturz, und eine Meldung, die niemand sieht, ist keine.
_lage, _ = w.baue_gesamtlage(CFG, {"Diesel": 1, "Pipeline": 1},
                             FREITAG_MITTAG, {})
_einzeln = w.baue_meldung(CFG, VERTRAG, {"Diesel": 1, "Pipeline": 1},
                          datetime(2026, 1, 2, 20, 15), False, FREITAG_MITTAG)
for _name, _roh in (("Gesamtlage", _lage), ("Einzelmeldung", _einzeln)):
    try:
        w.nur_text(_roh).encode("cp1252")
        pruefe("%s laesst sich auf cp1252 ausgeben" % _name, True)
    except UnicodeEncodeError as _e:
        pruefe("%s laesst sich auf cp1252 ausgeben" % _name, False, _e)

print("\n== Kein Name im Code ==")
meldung = w.baue_meldung(CFG, VERTRAG, {"Diesel": 0, "Pipeline": 0},
                         datetime(2026, 1, 2, 20, 15), False)
pruefe("der Name kommt aus der Konfiguration",
       "Beispielkonzern" in meldung, meldung.splitlines()[0])
pruefe("ohne Eintrag steht dort neutral 'Konzern'",
       k.konzernname({}) == "Konzern", k.konzernname({}))
pruefe("ein unbekanntes Konto behaelt seinen Namen",
       k.person({}, "IrgendeinKonto") == "IrgendeinKonto")

print("\n%s" % ("Alles in Ordnung." if not fehler
                else "%d Pruefung(en) fehlgeschlagen." % fehler))
raise SystemExit(1 if fehler else 0)
