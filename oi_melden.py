# -*- coding: utf-8 -*-
"""Meldewege: Telegram und Windows-Benachrichtigung.

Getrennt vom Waechter, weil das Dashboard dieselben Wege benutzt und es
nur eine Fassung davon geben soll.

Beide Wege duerfen fehlschlagen, ohne den Aufrufer zu stoeren - `melde`
gibt zurueck, welche Wege tatsaechlich erreicht wurden. Erst wenn diese
Liste leer ist, gilt eine Meldung als nicht zugestellt, und der Waechter
versucht es im naechsten Durchlauf erneut.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request

import oi_konfiguration as k
from oi_text import kurzfassung

HIER = os.path.dirname(os.path.abspath(__file__))
MELDUNG_PS = os.path.join(HIER, "meldung.ps1")

TELEGRAM_URL = "https://api.telegram.org/bot%s/sendMessage"

# CREATE_NO_WINDOW. Ohne dieses Flag blitzt bei jeder Windows-Meldung ein
# Konsolenfenster auf - und der Waechter meldet sich oft. Wer eine geplante
# Aufgabe daraus macht, sieht das Flackern sonst rund um die Uhr.
OHNE_FENSTER = 0x08000000


def telegram(cfg, text):
    """Schickt an alle hinterlegten Empfaenger.

    True, sobald mindestens einer erreicht wurde. Ein einzelner blockierter
    Empfaenger soll die Meldung an die anderen nicht verhindern.
    """
    token = str((cfg.get("telegram") or {}).get("token") or "").strip()
    if not token:
        return False

    erfolge = 0
    for ziel in k.telegram_empfaenger(cfg):
        daten = urllib.parse.urlencode({
            "chat_id": ziel,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        try:
            antwort = urllib.request.urlopen(TELEGRAM_URL % token, data=daten,
                                             timeout=20).read()
            if json.loads(antwort.decode("utf-8")).get("ok"):
                erfolge += 1
            else:
                print("   Telegram lehnte %s ab." % ziel)
        except Exception as e:
            print("   Telegram an %s fehlgeschlagen: %s" % (ziel, e))
    return erfolge > 0


def windows(titel, text, ton=True):
    """Windows-Benachrichtigung ueber meldung.ps1.

    Gibt False zurueck, wenn das Betriebssystem nicht passt oder das
    Skript fehlt - beides ist kein Fehler, nur ein fehlender Weg.
    """
    if os.name != "nt" or not os.path.exists(MELDUNG_PS):
        return False

    befehl = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
              "-File", MELDUNG_PS, "-Titel", titel,
              "-Text", kurzfassung(text)]
    if ton:
        befehl.append("-Ton")
    try:
        lauf = subprocess.run(befehl, capture_output=True, text=True,
                              timeout=60, creationflags=OHNE_FENSTER)
    except Exception as e:
        print("   Windows-Meldung fehlgeschlagen: %s" % e)
        return False
    return lauf.returncode == 0


def melde(cfg, titel, text):
    """Ueber alle eingerichteten Wege melden.

    Rueckgabe ist die Liste der Wege, die geklappt haben - leer heisst:
    niemand wurde erreicht.
    """
    erreicht = []

    if k.telegram_bereit(cfg):
        try:
            if telegram(cfg, text):
                erreicht.append("Telegram")
        except Exception as e:
            print("   Telegram fehlgeschlagen: %s" % e)
    elif (cfg.get("telegram") or {}).get("token"):
        print("   Telegram uebersprungen - Token oder Chat-ID unvollstaendig.")

    if cfg.get("windows_meldung", True):
        if windows(titel, text):
            erreicht.append("Windows")

    return erreicht
