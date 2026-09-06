# -*- coding: utf-8 -*-
"""Textwerkzeuge fuer Meldungen und Konsolenausgabe.

Telegram bekommt HTML mit Emojis, die Windows-Konsole nicht. Beides aus
derselben Quelle zu bedienen ist der Grund, warum es dieses Modul gibt.
"""
import re
import sys

# Emojis, die in Meldungen vorkommen, mit ihrer Entsprechung in reinem Text.
SYMBOLE = {
    "\U0001F534": "[!]",     # roter Kreis
    "\U0001F7E2": "[ok]",    # gruener Kreis
    "✅": "[ok]",        # Haken im Kasten
    "❌": " - ",         # Kreuz
    "✔": " + ",         # Haken
    "⚠": "(!)",         # Warndreieck
    "→": "->",          # Pfeil - der haeufigste Ausrutscher: kein
                        # Emoji, aber in cp1252 trotzdem nicht darstellbar
}


def zahl(n):
    """1136665 -> "1.136.665". Punkt als Tausendertrenner, wie im Spiel."""
    try:
        return "{:,}".format(int(n)).replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def nur_text(s):
    """HTML-Auszeichnung und Emojis heraus.

    Nicht bloss der Schoenheit wegen: Windows-Konsolen laufen oft auf
    cp1252 und brechen beim Schreiben eines Emojis mit einem Fehler ab.
    Eine Meldung, die sich nicht ausgeben laesst, ist keine Meldung.
    """
    s = re.sub(r"<[^>]+>", "", s or "")
    for zeichen, ersatz in SYMBOLE.items():
        s = s.replace(zeichen, ersatz)
    return s


def kurzfassung(s, laenge=200):
    """Fuer Benachrichtigungen, die nur wenige Zeilen zeigen koennen."""
    kurz = re.sub(r"\n{2,}", "\n", nur_text(s)).strip()
    return kurz if len(kurz) <= laenge else kurz[:laenge - 3] + "..."


def konsole_auf_utf8():
    """Die Ausgabe vertraegt danach auch Zeichen jenseits von cp1252.

    Schlaegt das fehl, ist es kein Grund aufzuhoeren - `nur_text` faengt
    den haeufigsten Fall ohnehin ab.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
