# -*- coding: utf-8 -*-
"""Morgenlage - eine Seite mit dem, was man beim Aufwachen wissen muss.

Naechstes Lieferfenster, Deckung aller offenen Lieferungen, Lagerstand,
Marktpreise, Konzernkonto und der Lagerverlauf der letzten Stunden.

Rein lesend. Die Rechenlogik kommt aus oi_wachter.py - es gibt bewusst
keine zweite Wahrheit neben dem Waechter. Was hier steht, ist Darstellung.

    python oi_dashboard.py            Dauerbetrieb
    python oi_dashboard.py --einmal   Datenblock einmal als JSON ausgeben

Erreichbar ist die Seite standardmaessig nur vom selben Rechner. Wer sie
von aussen erreichen will, stellt einen Webserver mit TLS davor und laesst
die Bindung auf 127.0.0.1 stehen.
"""
import base64
import hmac
import json
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import oi_konfiguration as k
import oi_schnittstelle as schnitt
import oi_wachter as w
from oi_text import konsole_auf_utf8

HIER = os.path.dirname(os.path.abspath(__file__))
SEITE = os.path.join(HIER, "dashboard.html")

# Die Schnittstelle ist langsam und mag keine Sturzfluten. Mehrere offene
# Browserfenster sollen sie nicht vervielfachen, deshalb wird die Lage
# zwischengespeichert und hoechstens so oft neu geholt.
CACHE_SEKUNDEN = 60

_cache = {"zeit": 0.0, "daten": None}
_sperre = threading.Lock()


# ------------------------------------------------------------------- Daten

def verlauf(zeilen=72, pfad=None):
    """Die letzten Zeilen aus lager_verlauf.csv, aelteste zuerst.

    Der Waechter schreibt sie bei jeder Pruefung. Faengt er gerade erst an,
    ist die Datei leer - das ist kein Fehler, nur ein leerer Verlauf.

    `pfad` ist fuer den Selbsttest da, damit er nicht die echte Datei
    braucht und auch keine anlegt.
    """
    pfad = pfad or w.VERLAUF
    if not os.path.exists(pfad):
        return []
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            roh = [z.strip() for z in f if z.strip()]
    except Exception:
        return []
    if len(roh) < 2:
        return []

    kopf = roh[0].split(";")
    ergebnis = []
    for zeile in roh[-zeilen:]:
        teile = zeile.split(";")
        if len(teile) != len(kopf) or teile[0] == kopf[0]:
            continue
        eintrag = {"zeit": teile[0]}
        for name, wert in zip(kopf[1:], teile[1:]):
            try:
                eintrag[name] = int(wert)
            except (TypeError, ValueError):
                eintrag[name] = None
        ergebnis.append(eintrag)
    return ergebnis


def letzte_zeile_alter(pfad):
    """(Alter der letzten Verlaufszeile in Sekunden, ihr Zeitstempel).

    Liest nur das Dateiende. Der Verlauf waechst mit jedem Durchlauf; ihn
    fuer eine Zustandspruefung ganz zu lesen, waere Verschwendung.
    """
    if not os.path.exists(pfad):
        return None, None
    try:
        with open(pfad, "rb") as f:
            f.seek(0, os.SEEK_END)
            groesse = f.tell()
            f.seek(max(0, groesse - 4096))
            zeilen = [z for z in f.read().decode("utf-8", "replace").splitlines()
                      if z.strip()]
        if not zeilen:
            return None, None
        zeit = zeilen[-1].split(";")[0]
        stand = datetime.strptime(zeit, "%Y-%m-%d %H:%M:%S")
        return int((datetime.now() - stand).total_seconds()), zeit
    except (OSError, ValueError):
        return None, None


def gesundheit(cfg, pfad=None):
    """Laeuft der Waechter noch? Ohne Aufruf der Spielschnittstelle.

    Fuer einen Totmannschalter gedacht, der alle paar Minuten fragen darf,
    ohne Last zu erzeugen. Massgeblich ist `lager_verlauf.csv`: Der Waechter
    schreibt sie bei JEDEM Durchlauf fort, auch wenn kein Vertrag laeuft.

    Eine Pruefung, die nur meldet "der Webserver antwortet", waere wertlos -
    er antwortet auch dann noch, wenn der Waechter seit Stunden tot ist.

    Die Schwellen leiten sich aus dem Takt ab: ab dem 2,5-fachen fehlt
    mindestens ein Durchlauf, ab dem Vierfachen mehrere.

    `pfad` ist fuer den Selbsttest da.
    """
    takt = max(1, int(cfg.get("takt_minuten", 10))) * 60
    warnung_ab, alarm_ab = int(takt * 2.5), takt * 4

    alter, zeit = letzte_zeile_alter(pfad or w.VERLAUF)
    if alter is None:
        stufe, text = "alarm", "Kein Lagerverlauf vorhanden."
    elif alter >= alarm_ab:
        stufe = "alarm"
        text = ("Der Lieferwaechter meldet sich seit %d Minuten nicht mehr."
                % (alter // 60))
    elif alter >= warnung_ab:
        stufe = "warnung"
        text = ("Letzter Durchlauf des Lieferwaechters vor %d Minuten."
                % (alter // 60))
    else:
        stufe, text = "ok", "Lieferwaechter laeuft."

    return {
        "stufe": stufe,
        "ok": stufe == "ok",
        "meldung": text,
        "alter_sekunden": alter,
        "letzte_zeile": zeit,
        "grenzen": {"warnung_sekunden": warnung_ab, "alarm_sekunden": alarm_ab},
        "jetzt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def naechste_lieferung(cfg, jetzt):
    """Der zeitlich naechste Termin ueber alle Vertraege."""
    kandidaten = []
    for v in w.laufende_vertraege(cfg, jetzt):
        termin, fenster = w.naechster_termin(v, jetzt)
        if termin is not None:
            kandidaten.append((termin, fenster, v))
    if not kandidaten:
        return None

    termin, fenster, v = min(kandidaten, key=lambda x: x[0])
    return {
        "vertrag": v.get("nummer", "?"),
        "termin": termin.strftime("%Y-%m-%d %H:%M"),
        "uhrzeit": termin.strftime("%H:%M"),
        "in_minuten": max(0, int((termin - jetzt).total_seconds() // 60)),
        "fenster_offen": jetzt >= fenster,
        "bedarf": v.get("bedarf") or {},
    }


def deckungsliste(cfg, bestand, jetzt, zustand):
    """Je Ware: wie viel fuer alle offenen Lieferungen noetig ist.

    Dieselbe Rechnung, die der Waechter fuer seine Meldungen benutzt - nur
    als Daten statt als Text.
    """
    summe, anzahl = w.gesamtbedarf(cfg, jetzt, zustand)
    zeilen = []
    for ware in sorted(summe, key=lambda x: -summe[x]):
        noetig = summe[ware]
        da = bestand.get(ware, 0)
        zeilen.append({
            "ware": ware,
            "noetig": noetig,
            "da": da,
            "rest": da - noetig,
            "fehlt": max(0, noetig - da),
        })
    return zeilen, anzahl


def lage(cfg):
    """Alles, was die Seite zeigt, in einem Datenblock.

    Einzelne Ausfaelle der Schnittstelle machen den Block nicht ungueltig:
    Was fehlt, steht unter "fehler", der Rest wird trotzdem geliefert. Eine
    Seite, die wegen des Kontostands gar nichts mehr zeigt, waere schlechter
    als eine, die ihn weglaesst.
    """
    jetzt = datetime.now()
    zustand = k.lade_json(w.ZUSTAND, {}) or {}
    fehler = []

    abgewiesen = False
    try:
        bestand = schnitt.lagerstand(cfg)
    except schnitt.SchnittstellenFehler as e:
        bestand = {}
        abgewiesen = "Abgewiesen" in str(e)
        fehler.append("Lagerstand: %s" % e)

    try:
        preise = schnitt.oelpreise(k.welt(cfg))
    except schnitt.SchnittstellenFehler as e:
        preise = {}
        fehler.append("Marktpreise: %s" % e)

    try:
        konto = schnitt.kontostand(cfg)
    except schnitt.SchnittstellenFehler as e:
        konto = None
        fehler.append("Kontostand: %s" % e)

    # Wurde der Lagerstand abgewiesen, stimmen Kennung oder Code nicht -
    # und dann antwortet die Kontoabfrage mit "0", ohne sich zu wehren.
    # Diese Null als Kontostand anzuzeigen waere schlimmer als eine Luecke:
    # Sie sieht aus wie eine Auskunft.
    if abgewiesen:
        konto = None

    zeilen, anzahl = deckungsliste(cfg, bestand, jetzt, zustand)
    sperre = w.sperrzeit(cfg, jetzt)

    return {
        "stand": jetzt.strftime("%Y-%m-%d %H:%M:%S"),
        "konzern": k.konzernname(cfg),
        "lager": bestand,
        "preise": preise,
        "konto": konto,
        "naechste_lieferung": naechste_lieferung(cfg, jetzt),
        "sperre_bis": sperre.strftime("%H:%M") if sperre else None,
        "offene_lieferungen": anzahl,
        "horizont_tage": w.HORIZONT_TAGE,
        "deckung": zeilen,
        "knapp": any(z["fehlt"] > 0 for z in zeilen),
        "verlauf": verlauf(),
        "fehler": fehler,
    }


def lage_gepuffert(cfg):
    """Die Lage, hoechstens einmal je CACHE_SEKUNDEN frisch geholt.

    Ein fehlerhafter Block verdraengt einen guten nicht. Sonst wuerde ein
    einzelner Aussetzer der Schnittstelle die Seite fuer eine ganze Minute
    leeren - obwohl eben noch brauchbare Zahlen dastanden. Stattdessen
    bleiben die letzten guten stehen, mit dem Vermerk `veraltet` und den
    aktuellen Fehlern; ihr Alter ist am Feld `stand` abzulesen.
    """
    with _sperre:
        if _cache["daten"] is not None and \
                time.time() - _cache["zeit"] <= CACHE_SEKUNDEN:
            return _cache["daten"]

        frisch = lage(cfg)
        gut = _cache["daten"]
        if frisch["fehler"] and gut is not None and not gut.get("veraltet"):
            ersatz = dict(gut)
            ersatz["veraltet"] = True
            ersatz["fehler"] = frisch["fehler"]
            # Nicht zwischenspeichern: Beim naechsten Abruf soll es sofort
            # wieder mit den echten Daten versucht werden.
            return ersatz

        frisch["veraltet"] = False
        _cache["daten"] = frisch
        _cache["zeit"] = time.time()
        return frisch


# ------------------------------------------------------------------ Server

class Handler(BaseHTTPRequestHandler):

    server_version = "Morgenlage"
    cfg = {}

    # ---------------------------------------------------------- Anmeldung

    def anmeldung_noetig(self):
        d = self.cfg.get("dashboard") or {}
        return bool(str(d.get("benutzer") or "").strip())

    def angemeldet(self):
        """HTTP-Basic gegen die Konfiguration.

        `compare_digest` statt `==`: Ein einfacher Vergleich bricht beim
        ersten falschen Zeichen ab und verraet ueber die Laufzeit, wie weit
        man gekommen ist.
        """
        if not self.anmeldung_noetig():
            return True

        kopf = self.headers.get("Authorization") or ""
        if not kopf.startswith("Basic "):
            return False
        try:
            roh = base64.b64decode(kopf[6:]).decode("utf-8")
            benutzer, _, passwort = roh.partition(":")
        except Exception:
            return False

        d = self.cfg.get("dashboard") or {}
        richtig_b = str(d.get("benutzer") or "")
        richtig_p = str(d.get("passwort") or "")
        # Beide Vergleiche immer ausfuehren, nicht mit "and" abkuerzen.
        stimmt_b = hmac.compare_digest(benutzer, richtig_b)
        stimmt_p = hmac.compare_digest(passwort, richtig_p)
        return stimmt_b and stimmt_p

    def verlange_anmeldung(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Morgenlage"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ------------------------------------------------------------ Antwort

    def sende(self, inhalt, typ="text/html; charset=utf-8", status=200):
        if isinstance(inhalt, str):
            inhalt = inhalt.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(inhalt)))
        # Die Seite holt ihre Daten selbst; zwischengespeicherte Antworten
        # wuerden einen alten Stand zeigen, ohne dass man es merkt.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(inhalt)

    def do_GET(self):
        if not self.angemeldet():
            return self.verlange_anmeldung()

        pfad = self.path.split("?", 1)[0].rstrip("/") or "/"

        if pfad == "/api/lage":
            daten = json.dumps(lage_gepuffert(self.cfg), ensure_ascii=False)
            return self.sende(daten, "application/json; charset=utf-8")

        if pfad == "/gesundheit":
            zustand = gesundheit(self.cfg)
            # Bei Alarm auch im Statuscode, damit ein schlichter Wachdienst
            # anschlaegt, der nur auf die Zahl schaut und nicht in den Rumpf.
            code = 503 if zustand["stufe"] == "alarm" else 200
            return self.sende(json.dumps(zustand, ensure_ascii=False),
                              "application/json; charset=utf-8", code)

        if pfad == "/":
            try:
                with open(SEITE, "r", encoding="utf-8") as f:
                    return self.sende(f.read())
            except OSError:
                return self.sende("dashboard.html fehlt neben oi_dashboard.py.",
                                  "text/plain; charset=utf-8", 500)

        self.sende("Nicht gefunden.\n", "text/plain; charset=utf-8", 404)

    def log_message(self, format, *args):
        # Eine Zeile je Abruf waere bei einer Seite, die sich jede Minute
        # selbst auffrischt, in einer Woche ein Protokoll ohne Nutzen.
        pass


def main():
    konsole_auf_utf8()
    try:
        cfg = k.lade()
    except k.KonfigFehler as e:
        sys.exit(str(e))

    if "--einmal" in sys.argv:
        print(json.dumps(lage(cfg), ensure_ascii=False, indent=2))
        return

    d = cfg.get("dashboard") or {}
    adresse = str(d.get("adresse") or "127.0.0.1")
    port = int(d.get("port") or 8099)

    Handler.cfg = cfg
    if not str(d.get("benutzer") or "").strip():
        print("Hinweis: kein Benutzer in dashboard.benutzer - die Seite ist "
              "ungeschuetzt.")
        if adresse not in ("127.0.0.1", "localhost", "::1"):
            print("         Sie ist zugleich von aussen erreichbar (%s). "
                  "Das sollte nicht so bleiben." % adresse)

    server = ThreadingHTTPServer((adresse, port), Handler)
    print("Morgenlage fuer %s auf http://%s:%d - Beenden mit Strg+C."
          % (k.konzernname(cfg), adresse, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
