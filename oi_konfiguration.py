# -*- coding: utf-8 -*-
"""Konfiguration lesen und pruefen.

Alles, was eine Installation von einer anderen unterscheidet, steht in
`oi_config.json`: Konzernname, Kennung, Zugangscode, Telegram, Vertraege.
Im Code steht davon nichts - auch keine Vorgabe, die zufaellig zu einer
bestimmten Installation passt. Wer dieses Werkzeug benutzt, findet darin
nirgends den Konzern eines anderen.

Die Vorlage `oi_config.example.json` ist versioniert, die ausgefuellte
`oi_config.json` nicht.
"""
import json
import os

HIER = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HIER, "oi_config.json")
VORLAGE = os.path.join(HIER, "oi_config.example.json")

# Wer die Vorlage kopiert, aber nicht ausgefuellt hat, hat einen anderen
# Fehler gemacht als jemand, dem die Datei ganz fehlt - und braucht eine
# andere Auskunft. Daran erkennen wir den Fall.
PLATZHALTER = "HIER-"


class KonfigFehler(Exception):
    """Die Konfiguration fehlt, ist kaputt oder noch nicht ausgefuellt."""


# ------------------------------------------------------------------ Dateien

def lade_json(pfad, standard=None):
    """JSON lesen, ohne bei Fehlern zu sterben.

    `utf-8-sig` statt `utf-8`: Editoren unter Windows schreiben gern eine
    Bytefolge an den Anfang, an der ein strenger JSON-Leser scheitert.
    """
    try:
        with open(pfad, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return standard


def schreibe_json(pfad, daten):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------- Pruefen

def maengel(cfg):
    """Was fehlt, damit die Schnittstelle abgefragt werden kann.

    Gibt eine Liste von Klartextsaetzen zurueck; leer heisst brauchbar.
    Bewusst als Liste statt als Ausnahme: Das Dashboard soll die Maengel
    anzeigen koennen, statt beim Start zu sterben.
    """
    fehler = []
    if not isinstance(cfg, dict):
        return ["Die Konfiguration ist kein JSON-Objekt."]

    kid = (cfg.get("konzern") or {}).get("kid")
    try:
        kid = int(kid)
    except (TypeError, ValueError):
        kid = 0
    if kid <= 0:
        fehler.append("konzern.kid fehlt - die Konzernkennung aus dem Spiel.")

    spiel = cfg.get("spiel") or {}
    code = str(spiel.get("code") or "").strip()
    if not code or PLATZHALTER in code.upper():
        fehler.append("spiel.code fehlt - der Schnittstellencode aus den "
                      "Konzerneinstellungen.")
    if not str(spiel.get("welt") or "").strip():
        fehler.append("spiel.welt fehlt - der Server, auf dem gespielt wird.")

    return fehler


def lade(pfad=None):
    """Konfiguration laden. Wirft KonfigFehler mit einem brauchbaren Satz."""
    pfad = pfad or CONFIG
    if not os.path.exists(pfad):
        raise KonfigFehler(
            "%s fehlt. Aus der Vorlage anlegen und ausfuellen:\n"
            "    cp %s %s"
            % (os.path.basename(pfad), os.path.basename(VORLAGE),
               os.path.basename(pfad)))

    cfg = lade_json(pfad)
    if cfg is None:
        raise KonfigFehler(
            "%s laesst sich nicht lesen - vermutlich ein Tippfehler im JSON "
            "(fehlendes Komma, Anfuehrungszeichen)." % os.path.basename(pfad))

    schlimm = maengel(cfg)
    if schlimm:
        raise KonfigFehler("In %s fehlt noch etwas:\n  - %s"
                           % (os.path.basename(pfad), "\n  - ".join(schlimm)))
    return cfg


# ------------------------------------------------------------------ Zugriffe

def konzernname(cfg):
    """Der Name, unter dem sich die Werkzeuge melden.

    Ohne Eintrag schlicht "Konzern" - das Werkzeug soll auch dann laufen.
    """
    return ((cfg.get("konzern") or {}).get("name") or "").strip() or "Konzern"


def kennung(cfg):
    return int((cfg.get("konzern") or {}).get("kid") or 0)


def welt(cfg):
    return str((cfg.get("spiel") or {}).get("welt") or "").strip()


def code(cfg):
    return str((cfg.get("spiel") or {}).get("code") or "").strip()


def vertraege(cfg, nur_aktive=True):
    """Die Vertraege aus der Konfiguration, ohne die Hinweiszeilen."""
    alle = [v for v in (cfg.get("vertraege") or [])
            if isinstance(v, dict) and v.get("bedarf")]
    if nur_aktive:
        # Fehlt der Schluessel, gilt ein Vertrag als aktiv. "aktiv": false
        # ist die Art, einen Eintrag stillzulegen, ohne ihn zu loeschen.
        alle = [v for v in alle if v.get("aktiv", True)]
    return alle


def person(cfg, konto):
    """Anzeigename fuer ein Spielkonto.

    Die Zuordnung ist optional und steht in der Konfiguration, nicht im
    Code. Ohne Eintrag wird der Kontoname unveraendert zurueckgegeben -
    dieses Werkzeug kennt von sich aus niemanden.
    """
    eintrag = (cfg.get("mitglieder") or {}).get(konto)
    if isinstance(eintrag, dict):
        return (eintrag.get("person") or "").strip() or konto
    return konto


def status(cfg, konto):
    """"aktiv" oder "ruhend"; ohne Eintrag gilt ein Konto als aktiv."""
    eintrag = (cfg.get("mitglieder") or {}).get(konto)
    if isinstance(eintrag, dict):
        return (eintrag.get("status") or "aktiv").strip() or "aktiv"
    return "aktiv"


# ------------------------------------------------------------------ Telegram

def telegram_empfaenger(cfg):
    tg = cfg.get("telegram") or {}
    return [str(x).strip() for x in (tg.get("chat_ids") or []) if str(x).strip()]


def telegram_bereit(cfg):
    """Echte Zugangsdaten hinterlegt, oder nur die leere Vorlage?

    Ein Telegram-Token enthaelt immer einen Doppelpunkt. Das ist die
    billigste Probe, die einen vergessenen Platzhalter noch erkennt.
    """
    token = str((cfg.get("telegram") or {}).get("token") or "").strip()
    if not token or PLATZHALTER in token.upper() or ":" not in token:
        return False
    return bool(telegram_empfaenger(cfg))
