# -*- coding: utf-8 -*-
"""Prueft das Dashboard: Datenblock, Anmeldung, Auslieferung.

Laeuft ohne Spielkonto. Als Spielwelt wird ein Name aus der Domaene
`.invalid` benutzt, die es laut RFC 2606 garantiert nicht gibt - damit
schlaegt jeder Abruf sofort und zuverlaessig fehl. Genau das soll geprueft
werden: Die Seite muss auch dann noch etwas zeigen.

    python pruefe_dashboard.py
"""
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
from base64 import b64encode
from http.server import ThreadingHTTPServer

import oi_dashboard as d

fehler = 0


def pruefe(was, bedingung, zusatz=""):
    global fehler
    print(("  ok   " if bedingung else "  FEHL ") + was
          + ("" if bedingung else "  ->  " + str(zusatz)))
    if not bedingung:
        fehler += 1


CFG = {
    "konzern": {"name": "Beispielkonzern", "kid": 1},
    "spiel": {"welt": "keine-solche-welt.invalid", "code": "irgendwas"},
    "vertraege": [{
        "nummer": "01-02-3-04-05",
        "aktiv": True,
        "slots": ["09:35", "20:15"],
        "bedarf": {"Diesel": 100_000},
        "bis": "2099-12-31",
    }],
    "dashboard": {"adresse": "127.0.0.1", "port": 0},
}


def hole(server, pfad, benutzer=None, passwort=None):
    """(Status, Rumpf). Fehlerantworten gelten hier nicht als Ausnahme."""
    adresse, port = server.server_address[:2]
    anfrage = urllib.request.Request("http://%s:%d%s" % (adresse, port, pfad))
    if benutzer is not None:
        roh = ("%s:%s" % (benutzer, passwort)).encode("utf-8")
        anfrage.add_header("Authorization",
                           "Basic " + b64encode(roh).decode("ascii"))
    try:
        antwort = urllib.request.urlopen(anfrage, timeout=15)
        return antwort.status, antwort.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


print("== Verlauf einlesen ==")
with tempfile.TemporaryDirectory() as ordner:
    pfad = os.path.join(ordner, "verlauf.csv")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("zeit;Rohoel;Kerosin;Diesel;Benzin;Turm;Tank;Pipeline\n")
        f.write("2026-01-02 09:00:00;10;20;30;40;1;2;3\n")
        f.write("2026-01-02 09:10:00;11;21;31;41;1;2;3\n")
    gelesen = d.verlauf(pfad=pfad)
    pruefe("zwei Zeilen gelesen", len(gelesen) == 2, len(gelesen))
    pruefe("Zahlen sind Zahlen", gelesen[1]["Diesel"] == 31, gelesen[1])
    pruefe("die Zeit bleibt Text", gelesen[0]["zeit"] == "2026-01-02 09:00:00")

    pruefe("eine fehlende Datei ist kein Fehler",
           d.verlauf(pfad=os.path.join(ordner, "gibtsnicht.csv")) == [])

print("\n== Datenblock trotz toter Schnittstelle ==")
lage = d.lage(CFG)
pruefe("es gibt einen Block", isinstance(lage, dict))
pruefe("der Konzernname steht drin", lage["konzern"] == "Beispielkonzern",
       lage.get("konzern"))
pruefe("die Ausfaelle sind vermerkt", len(lage["fehler"]) >= 1, lage["fehler"])
pruefe("die naechste Lieferung wird trotzdem berechnet",
       lage["naechste_lieferung"] is not None)
pruefe("offene Lieferungen wurden gezaehlt",
       lage["offene_lieferungen"] > 0, lage["offene_lieferungen"])
pruefe("der Block ist als JSON darstellbar",
       isinstance(json.dumps(lage, ensure_ascii=False), str))

print("\n== Auslieferung ohne Anmeldung ==")
d.Handler.cfg = CFG
server = ThreadingHTTPServer(("127.0.0.1", 0), d.Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    status, rumpf = hole(server, "/")
    pruefe("die Seite kommt", status == 200, status)
    pruefe("es ist die Morgenlage", "<title>Morgenlage</title>" in rumpf)

    status, rumpf = hole(server, "/api/lage")
    pruefe("die Daten kommen", status == 200, status)
    pruefe("und sind gueltiges JSON",
           json.loads(rumpf).get("konzern") == "Beispielkonzern")

    status, _ = hole(server, "/gesundheit")
    pruefe("der Gesundheitsruf antwortet", status == 200, status)

    status, _ = hole(server, "/gibtsnicht")
    pruefe("unbekannte Pfade ergeben 404", status == 404, status)
finally:
    server.shutdown()
    server.server_close()

print("\n== Auslieferung mit Anmeldung ==")
GESCHUETZT = dict(CFG)
GESCHUETZT["dashboard"] = {"adresse": "127.0.0.1", "port": 0,
                           "benutzer": "wache", "passwort": "geheim"}
d.Handler.cfg = GESCHUETZT
server = ThreadingHTTPServer(("127.0.0.1", 0), d.Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    status, _ = hole(server, "/")
    pruefe("ohne Anmeldung abgewiesen", status == 401, status)

    status, _ = hole(server, "/", "wache", "falsch")
    pruefe("falsches Passwort abgewiesen", status == 401, status)

    status, _ = hole(server, "/", "jemand", "geheim")
    pruefe("falscher Benutzer abgewiesen", status == 401, status)

    status, rumpf = hole(server, "/", "wache", "geheim")
    pruefe("richtige Anmeldung kommt durch", status == 200, status)
    pruefe("und bekommt die Seite", "<title>Morgenlage</title>" in rumpf)

    status, _ = hole(server, "/api/lage", "wache", "geheim")
    pruefe("die Daten sind ebenfalls geschuetzt und erreichbar", status == 200)
finally:
    server.shutdown()
    server.server_close()

print("\n%s" % ("Alles in Ordnung." if not fehler
                else "%d Pruefung(en) fehlgeschlagen." % fehler))
raise SystemExit(1 if fehler else 0)
