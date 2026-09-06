# -*- coding: utf-8 -*-
"""Lieferwaechter fuer Konzernvertraege in Oil Imperium.

Ein Konzernvertrag wird in Teillieferungen zu festen Uhrzeiten erfuellt.
Ist zum Termin nicht genug im Lager, platzt der Vertrag und es wird eine
Strafe faellig. Dieser Waechter prueft die Deckung vor jedem Termin und
meldet sich rechtzeitig - ueber Telegram, ueber Windows, oder beides.

Rein lesend. Es wird abgefragt und gerechnet, nie etwas im Spiel gesetzt.

    python oi_wachter.py            Dauerbetrieb
    python oi_wachter.py --status   Lage einmal ausgeben, nichts senden
    python oi_wachter.py --test     Meldewege und Verbindung pruefen

Alles Installationsabhaengige steht in oi_config.json, nichts davon hier.
"""
import os
import sys
import time
from datetime import datetime, timedelta

import oi_konfiguration as k
import oi_melden
import oi_schnittstelle as schnitt
from oi_text import konsole_auf_utf8, nur_text, zahl

HIER = os.path.dirname(os.path.abspath(__file__))
ZUSTAND = os.path.join(HIER, "oi_state.json")
VERLAUF = os.path.join(HIER, "lager_verlauf.csv")

# Wie lange vor dem Termin der Waechter aufmerksam wird. Vier Stunden sind
# genug, um noch etwas nachzuliefern.
VORLAUF = timedelta(hours=4)

# Nach einer Lieferung nimmt das Spiel eine Stunde lang nichts an. Die eine
# Minute Zuschlag ist Sicherheitsabstand gegen ungenaue Uhren.
ANNAHMESPERRE = timedelta(hours=1, minutes=1)

# Eine Lieferung gilt als erfolgt, wenn der Lagerstand der ersten Ware des
# Vertrags um mindestens diesen Anteil der Liefermenge gefallen ist. Nicht
# 100 %, weil zwischen zwei Abfragen auch anderes zu- und abgehen kann.
ERKENNUNGSSCHWELLE = 0.9

# Wie weit die Gesamtlage vorausrechnet. Ein Vertrag darf ein Enddatum weit
# in der Zukunft haben; ohne Grenze wuerde "reicht das Lager fuer alle
# offenen Lieferungen" ueber Jahre summiert - eine Zahl, die niemandem
# hilft, und eine Schleife, die bei jedem Abruf ueber jeden Tag laeuft.
# Vierzehn Tage sind der Zeitraum, in dem man noch etwas unternehmen kann.
HORIZONT_TAGE = 14

# Reihenfolge der Spalten in lager_verlauf.csv.
SPALTEN = ["Rohoel", "Kerosin", "Diesel", "Benzin", "Turm", "Tank", "Pipeline"]


# ------------------------------------------------------------- Zeitfenster

def laufende_vertraege(cfg, jetzt=None):
    """Aktive Vertraege, deren Enddatum noch nicht vorbei ist."""
    heute = (jetzt or datetime.now()).strftime("%Y-%m-%d")
    return [v for v in k.vertraege(cfg)
            if not v.get("bis") or v["bis"] >= heute]


def slots(v):
    """Die Lieferzeiten eines Vertrags als (Stunde, Minute)."""
    ergebnis = []
    for eintrag in v.get("slots") or []:
        try:
            stunde, minute = [int(x) for x in str(eintrag).split(":")]
        except ValueError:
            continue
        ergebnis.append((stunde, minute))
    return ergebnis


def alle_slots(cfg, jetzt=None):
    """Alle Lieferzeiten ueber alle Vertraege, als sortierte Menge.

    Bewusst aus den Vertraegen abgeleitet und nicht fest eingetragen: Eine
    voreingestellte Uhrzeit waere die eines fremden Konzerns.

    `jetzt` wird durchgereicht, nicht aus der Uhr geholt. Sonst wuerde die
    Frage "welche Vertraege laufen" gegen die echte Zeit beantwortet,
    waehrend der Aufrufer ueber einen anderen Zeitpunkt spricht.
    """
    gesammelt = set()
    for v in laufende_vertraege(cfg, jetzt):
        gesammelt.update(slots(v))
    return sorted(gesammelt)


def naechster_termin(v, jetzt):
    """(Liefertermin, Beginn des Beobachtungsfensters) fuer einen Vertrag.

    Auch ueber Mitternacht: Es werden heutige und morgige Termine gebildet
    und der naechste noch kommende genommen.
    """
    kandidaten = []
    for versatz in (0, 1):
        tag = (jetzt + timedelta(days=versatz)).date()
        for stunde, minute in slots(v):
            kandidaten.append(datetime.combine(tag, datetime.min.time())
                              .replace(hour=stunde, minute=minute))
    kommend = [t for t in kandidaten if t > jetzt]
    if not kommend:
        return None, None
    termin = min(kommend)
    return termin, termin - VORLAUF


def sperrzeit(cfg, jetzt):
    """Laeuft gerade eine Annahmesperre? Gibt deren Ende zurueck, sonst None."""
    for stunde, minute in alle_slots(cfg, jetzt):
        beginn = jetzt.replace(hour=stunde, minute=minute,
                               second=0, microsecond=0)
        if beginn <= jetzt < beginn + ANNAHMESPERRE:
            return beginn + ANNAHMESPERRE
    return None


def offene_lieferungen(v, jetzt, zustand, horizont=HORIZONT_TAGE):
    """Noch ausstehende Termine eines Vertrags, hoechstens `horizont` Tage weit.

    Termine, die bereits als erledigt gemeldet wurden, zaehlen nicht mit.
    Das Enddatum des Vertrags begrenzt zusaetzlich - es gilt, was frueher
    kommt.
    """
    grenze = (jetzt + timedelta(days=horizont)).date()
    if v.get("bis"):
        try:
            ende = min(datetime.strptime(v["bis"], "%Y-%m-%d").date(), grenze)
        except ValueError:
            ende = jetzt.date()
    else:
        ende = jetzt.date()

    termine = []
    tag = jetzt.date()
    while tag <= ende:
        for stunde, minute in slots(v):
            termin = datetime.combine(tag, datetime.min.time()).replace(
                hour=stunde, minute=minute)
            if termin <= jetzt:
                continue
            eintrag = zustand.get(schluessel(v, termin), {})
            if not eintrag.get("erledigt_gemeldet"):
                termine.append(termin)
        tag += timedelta(days=1)
    return sorted(termine)


def schluessel(v, termin):
    """Kennung eines einzelnen Liefertermins im Zustand."""
    return "%s %s" % (v.get("nummer", "?"), termin.strftime("%Y-%m-%d %H:%M"))


# ----------------------------------------------------------------- Deckung

def deckung(v, bestand):
    """(gedeckt, fehlend) fuer EINE Teillieferung, je (Ware, noetig, da)."""
    gedeckt, fehlend = [], []
    for ware, menge in (v.get("bedarf") or {}).items():
        da = bestand.get(ware, 0)
        (gedeckt if da >= menge else fehlend).append((ware, menge, da))
    return gedeckt, fehlend


def gesamtbedarf(cfg, jetzt, zustand):
    """(Bedarf aller offenen Lieferungen je Ware, Anzahl der Lieferungen)."""
    summe, anzahl = {}, 0
    for v in laufende_vertraege(cfg, jetzt):
        offen = offene_lieferungen(v, jetzt, zustand)
        anzahl += len(offen)
        for _ in offen:
            for ware, menge in (v.get("bedarf") or {}).items():
                summe[ware] = summe.get(ware, 0) + menge
    return summe, anzahl


def baue_gesamtlage(cfg, bestand, jetzt, zustand):
    """(Text, knapp) - reicht das Lager fuer ALLE offenen Lieferungen?

    Der wichtigere Teil der Meldung. Eine einzelne Lieferung kann gedeckt
    sein, waehrend die uebernaechste schon nicht mehr aufgeht.
    """
    summe, anzahl = gesamtbedarf(cfg, jetzt, zustand)
    if not summe:
        return "", False

    knapp = False
    zeilen = []
    for ware in sorted(summe, key=lambda w: -summe[w]):
        noetig, da = summe[ware], bestand.get(ware, 0)
        rest = da - noetig
        if rest < 0:
            knapp = True
            zeilen.append("❌ %s: %s da, %s noetig → <b>%s fehlen</b>"
                          % (ware, zahl(da), zahl(noetig), zahl(-rest)))
        else:
            anteil = (rest / noetig * 100) if noetig else 0
            if anteil >= 100:
                zeilen.append("✔ %s: %s da, %s noetig → Reserve %s (reichlich)"
                              % (ware, zahl(da), zahl(noetig), zahl(rest)))
            else:
                hinweis = " ⚠ knapp" if anteil < 10 else ""
                zeilen.append("✔ %s: %s da, %s noetig → Reserve %s (%.0f %%)%s"
                              % (ware, zahl(da), zahl(noetig), zahl(rest),
                                 anteil, hinweis))

    kopf = ("<b>Gesamtlage - %d offene Lieferung%s in den naechsten %d "
            "Tagen</b>" % (anzahl, "" if anzahl == 1 else "en", HORIZONT_TAGE))
    return "\n".join([kopf] + zeilen), knapp


def baue_meldung(cfg, v, bestand, termin, erledigt):
    """Der Text zu EINER anstehenden Teillieferung."""
    gedeckt, fehlend = deckung(v, bestand)
    kopf = "<b>%s - Vertrag %s</b>" % (k.konzernname(cfg), v.get("nummer", "?"))

    if erledigt:
        return ("%s\n\n✅ <b>%s erledigt.</b>\nDer Lagerstand ist um die "
                "Liefermenge gesunken." % (kopf, termin.strftime("%H:%M")))

    zeilen = [kopf, ""]
    if fehlend:
        zeilen.append("\U0001F534 <b>%s - es fehlt Ware!</b>"
                      % termin.strftime("%H:%M"))
    else:
        zeilen.append("\U0001F7E2 <b>%s - Fenster offen, alles da.</b>"
                      % termin.strftime("%H:%M"))
    zeilen.append("")
    for ware, noetig, da in fehlend:
        zeilen.append("❌ %s: %s noetig, nur %s da → <b>%s fehlen</b>"
                      % (ware, zahl(noetig), zahl(da), zahl(noetig - da)))
    for ware, noetig, da in gedeckt:
        zeilen.append("✔ %s: %s noetig, %s da" % (ware, zahl(noetig), zahl(da)))
    if fehlend:
        zeilen.append("\nJemand muss nachliefern, sonst platzt der Vertrag.")
    return "\n".join(zeilen)


# -------------------------------------------------------------------- Lauf

def protokolliere(bestand):
    """Haengt den Lagerstand an lager_verlauf.csv an.

    Eine Zeile je Pruefung. Daraus laesst sich spaeter ablesen, wann
    Nachschub eintrifft und wie schnell - die Schnittstelle selbst hat
    dafuer kein Gedaechtnis.
    """
    try:
        neu = not os.path.exists(VERLAUF)
        with open(VERLAUF, "a", encoding="utf-8") as f:
            if neu:
                f.write("zeit;" + ";".join(SPALTEN) + "\n")
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ";"
                    + ";".join(str(bestand.get(s, "")) for s in SPALTEN) + "\n")
    except Exception as e:
        print(">> Verlauf konnte nicht geschrieben werden: %s" % e)


def _naechster_ausloeser(eintrag, erledigt, minuten_bis):
    """Welche Meldung ist jetzt faellig - oder keine?

    Jede Art wird je Termin nur einmal gemeldet. Sonst schriebe der
    Waechter alle zehn Minuten dieselbe Nachricht.
    """
    if erledigt and not eintrag.get("erledigt_gemeldet"):
        return "erledigt_gemeldet"
    if erledigt:
        return None
    if not eintrag.get("start_gemeldet"):
        return "start_gemeldet"
    if minuten_bis <= 15 and not eintrag.get("erinnert_15"):
        return "erinnert_15"
    if minuten_bis <= 45 and not eintrag.get("erinnert_45"):
        return "erinnert_45"
    return None


def einmal(cfg, senden=True):
    """Eine Pruefung. Der ganze Waechter in einem Durchlauf."""
    jetzt = datetime.now()
    aktive = laufende_vertraege(cfg, jetzt)
    if not aktive:
        print("[%s] Kein laufender Vertrag - nichts zu pruefen."
              % jetzt.strftime("%H:%M:%S"))
        return

    zustand = k.lade_json(ZUSTAND, {}) or {}

    faellig, wartend = [], []
    for v in aktive:
        termin, fenster = naechster_termin(v, jetzt)
        if termin is not None:
            (faellig if jetzt >= fenster else wartend).append((termin, fenster, v))

    bestand = schnitt.lagerstand(cfg)
    protokolliere(bestand)
    lage, knapp = baue_gesamtlage(cfg, bestand, jetzt, zustand)
    if lage:
        print(nur_text(lage))

    if not faellig:
        if wartend:
            termin, fenster, v = min(wartend, key=lambda x: x[1])
            minuten = max(0, int((fenster - jetzt).total_seconds() // 60))
            print("[%s] Naechstes Fenster %s (Vertrag %s) oeffnet in %d:%02d Std."
                  % (jetzt.strftime("%H:%M:%S"), termin.strftime("%H:%M"),
                     v.get("nummer", "?"), minuten // 60, minuten % 60))

        # Bei Knappheit einmal am Tag vorwarnen, auch ausserhalb der
        # Fenster - sonst erfaehrt man es erst vier Stunden vor knapp.
        marke = "knappheit %s" % jetzt.strftime("%Y-%m-%d")
        if knapp and senden and not zustand.get(marke):
            text = ("<b>%s - Vorwarnung</b>\n\n%s\n\nBitte nachliefern oder "
                    "nichts davon verbrauchen." % (k.konzernname(cfg), lage))
            wege = oi_melden.melde(cfg, "%s - Vorwarnung" % k.konzernname(cfg),
                                   text)
            if wege:
                zustand[marke] = {"termin": jetzt.strftime("%Y-%m-%d %H:%M")}
                print(">> Knappheit gemeldet ueber %s." % " und ".join(wege))

        k.schreibe_json(ZUSTAND, zustand)
        return

    for termin, _fenster, v in sorted(faellig, key=lambda x: x[0]):
        eintrag = zustand.setdefault(schluessel(v, termin), {})
        eintrag["termin"] = termin.strftime("%Y-%m-%d %H:%M")

        # Der Lagerstand bei Fensteroeffnung ist der Bezugspunkt, an dem
        # spaeter die erfolgte Lieferung erkannt wird.
        if "start" not in eintrag:
            eintrag["start"] = bestand

        bedarf = list((v.get("bedarf") or {}).items())
        erledigt = False
        if bedarf:
            ware, menge = bedarf[0]
            rueckgang = eintrag["start"].get(ware, 0) - bestand.get(ware, 0)
            erledigt = menge > 0 and rueckgang >= menge * ERKENNUNGSSCHWELLE

        text = baue_meldung(cfg, v, bestand, termin, erledigt)
        if lage:
            text = text + "\n\n" + lage
        print(nur_text(text))
        print("-" * 60)

        if not senden:
            continue

        minuten_bis = int((termin - jetzt).total_seconds() // 60)
        ausloeser = _naechster_ausloeser(eintrag, erledigt, minuten_bis)
        if not ausloeser:
            continue

        wege = oi_melden.melde(
            cfg, "%s - Vertrag %s" % (k.konzernname(cfg), v.get("nummer", "?")),
            text)
        if wege:
            eintrag[ausloeser] = True
            print(">> Gemeldet ueber %s (%s, Vertrag %s)"
                  % (" und ".join(wege), ausloeser, v.get("nummer", "?")))
        else:
            print(">> Kein Meldeweg erreichbar - neuer Versuch im naechsten "
                  "Durchlauf.")

    # Termine, die lange vorbei sind, aus dem Zustand nehmen. Ohne das
    # waechst die Datei unbegrenzt.
    grenze = (jetzt - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    for alt in [s for s, e in list(zustand.items())
                if isinstance(e, dict) and e.get("termin", "9999") < grenze]:
        del zustand[alt]
    k.schreibe_json(ZUSTAND, zustand)


def probe(cfg):
    """--test: Sind Meldewege und Schnittstelle in Ordnung?"""
    text = ("<b>Lieferwaechter</b>\nVerbindung steht. Ab jetzt melde ich "
            "mich vor jeder Lieferung.")

    print("Windows-Benachrichtigung ...")
    print("  Zugestellt." if oi_melden.windows("Lieferwaechter - Test", text)
          else "  Nicht zugestellt.")

    print("Telegram ...")
    if not k.telegram_bereit(cfg):
        print("  Uebersprungen - Token oder Chat-ID fehlen in oi_config.json.")
    else:
        print("  Zugestellt." if oi_melden.telegram(cfg, text)
              else "  Telegram meldete einen Fehler.")

    print("Schnittstelle ...")
    try:
        bestand = schnitt.lagerstand(cfg)
        print("  Lagerstand: " + ", ".join(
            "%s %s" % (ware, zahl(menge))
            for ware, menge in sorted(bestand.items()) if menge))
    except schnitt.SchnittstellenFehler as e:
        print("  %s" % e)

    offen = laufende_vertraege(cfg)
    print("Vertraege: %d laufend%s" % (len(offen), "" if offen else
                                       " - in oi_config.json eintragen"))


def main():
    konsole_auf_utf8()
    try:
        cfg = k.lade()
    except k.KonfigFehler as e:
        sys.exit(str(e))

    if "--test" in sys.argv:
        probe(cfg)
        return

    if "--status" in sys.argv:
        einmal(cfg, senden=False)
        return

    takt = max(1, int(cfg.get("takt_minuten", 10)))
    print("Lieferwaechter fuer %s. Pruefung alle %d Minuten. "
          "Beenden mit Strg+C." % (k.konzernname(cfg), takt))
    while True:
        try:
            einmal(cfg)
        except schnitt.SchnittstellenFehler as e:
            # Ein Aussetzer der Schnittstelle darf den Waechter nicht
            # beenden - gerade dann soll er weiterlaufen.
            print(">> %s" % e)
        except Exception as e:
            print(">> Unerwarteter Fehler: %s" % e)
        time.sleep(takt * 60)


if __name__ == "__main__":
    main()
