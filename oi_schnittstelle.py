# -*- coding: utf-8 -*-
"""Zugriff auf die SOAP-Schnittstelle von Oil Imperium.

Rein lesend. Es wird abgefragt und ausgewertet, nie etwas gesetzt.

Die Schnittstelle spricht das alte RPC/encoded-SOAP; eine fertige
Bibliothek dafuer waere schwerer als der Umschlag selbst, deshalb steht er
hier ausgeschrieben. Geantwortet wird entweder mit einer Liste von
Schluessel-Wert-Paaren oder mit einem einzelnen <return>.

    python oi_schnittstelle.py        Verbindung und Lagerstand pruefen
"""
import re
import urllib.request

import oi_konfiguration as k

URL = "http://{welt}/interface/soap_oi.php"
NS = "urn:OilImperium"

# Die Schluessel der Antwort-Maps sind NICHT 0-3 beziehungsweise 0-8, wie
# die Dokumentation der Schnittstelle behauptet. Diese Tabellen stammen aus
# dem Abgleich mit dem Lagerbestand im Spiel. Wer sie "korrigiert", bekommt
# stillschweigend falsche Zahlen - der Abruf meldet keinen Fehler.
ROHSTOFF_KEYS = {0: "Rohoel", 1: "Kerosin", 4: "Diesel", 7: "Benzin"}
EQUIPMENT_KEYS = {
    1: ("Turm", "A"), 2: ("Tank", "A"), 3: ("Pipeline", "A"),
    4: ("Turm", "B"), 5: ("Tank", "B"), 6: ("Pipeline", "B"),
    7: ("Turm", "C"), 8: ("Tank", "C"), 9: ("Pipeline", "C"),
}

# Lagertyp fuer Kraftstoffe und fuer Equipment.
TYP_TANKLAGER = 4
TYP_EQUIPMENT = 9

UMSCHLAG = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope
 xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:ns1="{ns}"
 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<SOAP-ENV:Body><ns1:{op}>{args}</ns1:{op}></SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""


class SchnittstellenFehler(Exception):
    """Die Gegenseite hat einen Fehler gemeldet oder war nicht erreichbar."""


def rufe(welt, op, args, timeout=25):
    """Eine Abfrage. `args` ist eine Liste von (Name, Typ, Wert).

    Typ ist einer aus int, string, boolean. Rueckgabe ist ein Dict, wenn
    die Antwort Schluessel-Wert-Paare enthaelt, sonst der Text des
    einzelnen Rueckgabewerts, sonst None.
    """
    xml = "".join(
        '<{n} xsi:type="xsd:{t}">{v}</{n}>'.format(n=n, t=t, v=v)
        for n, t, v in args
    )
    anfrage = urllib.request.Request(
        URL.format(welt=welt),
        data=UMSCHLAG.format(ns=NS, op=op, args=xml).encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8",
                 "SOAPAction": '"urn:OilImperiumAction"'})

    try:
        roh = urllib.request.urlopen(anfrage, timeout=timeout)
        roh = roh.read().decode("utf-8", "replace")
    except Exception as e:
        raise SchnittstellenFehler("%s nicht erreichbar: %s" % (welt, e))

    fehler = re.search(r"<faultstring>(.*?)</faultstring>", roh, re.S)
    if fehler:
        raise SchnittstellenFehler("Fehler bei %s: %s"
                                   % (op, fehler.group(1).strip()))

    paare = re.findall(
        r"<key[^>]*>(.*?)</key>\s*<value[^>]*>(.*?)</value>", roh, re.S)
    if paare:
        return {int(s.strip()): w.strip() for s, w in paare}

    # Erst nach den Paaren pruefen, nicht davor: In einer Map steckt jedes
    # Schluessel-Wert-Paar seinerseits in einem <item>, und eine zu frueh
    # greifende Listenerkennung wuerde die Map als Liste ausgeben.
    eintraege = re.findall(r"<item[^>]*>(.*?)</item>", roh, re.S)
    if eintraege:
        return [re.sub(r"<[^>]+>", "", e).strip() for e in eintraege]

    einzeln = re.search(r"<return[^>]*>(.*?)</return>", roh, re.S)
    if einzeln:
        return re.sub(r"<[^>]+>", "", einzeln.group(1)).strip()
    return None


def lagerstand(cfg):
    """Der Konzernbestand als {"Diesel": 1136665, "Pipeline": 544, ...}.

    Equipment wird ueber alle drei Stufen summiert, weil Vertraege jede
    Stufe annehmen - ein Turm A erfuellt dieselbe Zeile wie ein Turm C.
    """
    welt, kid, code = k.welt(cfg), k.kennung(cfg), k.code(cfg)
    zugang = [("kid", "int", kid), ("code", "string", code)]

    kraftstoff = rufe(welt, "getCorporateGroupLevel",
                      zugang + [("typ", "int", TYP_TANKLAGER)]) or {}
    equipment = rufe(welt, "getCorporateGroupStock",
                     zugang + [("typ", "int", TYP_EQUIPMENT)]) or {}

    bestand = {}
    for schluessel, name in ROHSTOFF_KEYS.items():
        bestand[name] = int(kraftstoff.get(schluessel, 0) or 0)
    for schluessel, (art, _stufe) in EQUIPMENT_KEYS.items():
        bestand[art] = bestand.get(art, 0) + int(equipment.get(schluessel, 0) or 0)
    return bestand


# Reihenfolge der vier Werte von getOilPrice. Sie ist NICHT dokumentiert,
# sondern gegen die Preisanzeige im Spiel abgeglichen. Wer sie fuer
# selbstverstaendlich haelt, vertauscht irgendwann Rohoel mit Benzin, ohne
# dass irgendetwas einen Fehler meldet.
PREIS_REIHENFOLGE = ["Rohoel", "Kerosin", "Diesel", "Benzin"]


def oelpreise(welt, typ=4):
    """Die aktuellen Marktpreise als {"Rohoel": 111.61, ...}.

    Braucht weder Kennung noch Code - damit laesst sich eine Installation
    pruefen, bevor die Zugangsdaten stimmen.
    """
    werte = rufe(welt, "getOilPrice", [("code", "int", typ)]) or []
    if not isinstance(werte, list):
        return {}
    preise = {}
    for name, wert in zip(PREIS_REIHENFOLGE, werte):
        try:
            preise[name] = float(wert)
        except (TypeError, ValueError):
            pass
    return preise


def kontostand(cfg):
    """Das Konzernkonto."""
    return rufe(k.welt(cfg), "getCorporateGroupBalance",
                [("kid", "int", k.kennung(cfg)),
                 ("code", "string", k.code(cfg))])


if __name__ == "__main__":
    import sys

    try:
        cfg = k.lade()
    except k.KonfigFehler as e:
        sys.exit(str(e))

    print("Welt %s, Konzern %s (%d)"
          % (k.welt(cfg), k.konzernname(cfg), k.kennung(cfg)))
    try:
        print("\nMarktpreise:", oelpreise(k.welt(cfg)))
        print("Kontostand: ", kontostand(cfg))
        print("\nLagerstand:")
        for ware, menge in sorted(lagerstand(cfg).items()):
            print("   %-12s %s" % (ware, menge))
    except SchnittstellenFehler as e:
        sys.exit("\n%s" % e)
