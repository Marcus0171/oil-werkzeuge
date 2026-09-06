# -*- coding: utf-8 -*-
"""Richtet den Telegram-Bot fuer den Lieferwaechter ein.

Ablauf:

  1. Bei @BotFather einen Bot anlegen und den Token in token.txt schreiben,
     nur den Token, sonst nichts.
  2. Dem eigenen Bot in Telegram "hallo" schreiben oder auf Start druecken.
     In einer Gruppe: den Bot hinzufuegen und dort etwas schreiben.
  3. python bot_einrichten.py

Das Skript prueft den Token, sucht die Chats heraus, traegt beides in
oi_config.json ein, loescht token.txt und schickt eine Probenachricht.

Der Umweg ueber die Datei hat einen Grund: So steht der Token weder in der
Kommandozeile noch in der Verlaufsdatei der Shell, wo ihn spaeter niemand
vermutet und deshalb auch niemand loescht.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import oi_konfiguration as k

HIER = os.path.dirname(os.path.abspath(__file__))
TOKENDATEI = os.path.join(HIER, "token.txt")

API = "https://api.telegram.org/bot%s/%s"


def rufe(token, methode, daten=None):
    """Ein Telegram-Aufruf. Gibt das Feld "result" zurueck."""
    url = API % (token, methode)
    rumpf = urllib.parse.urlencode(daten).encode("utf-8") if daten else None
    try:
        antwort = urllib.request.urlopen(url, data=rumpf, timeout=20).read()
    except urllib.error.HTTPError as e:
        antwort = e.read()
    except Exception as e:
        sys.exit("Telegram nicht erreichbar: %s" % e)

    try:
        ergebnis = json.loads(antwort.decode("utf-8"))
    except ValueError:
        sys.exit("Telegram antwortete unverstaendlich.")

    if not ergebnis.get("ok"):
        sys.exit("Telegram lehnte ab: %s"
                 % ergebnis.get("description", "ohne Begruendung"))
    return ergebnis.get("result")


def lies_token():
    if not os.path.exists(TOKENDATEI):
        sys.exit("token.txt fehlt.\n"
                 "Bei @BotFather einen Bot anlegen und den Token in %s\n"
                 "schreiben - nur den Token, sonst nichts." % TOKENDATEI)
    with open(TOKENDATEI, "r", encoding="utf-8-sig") as f:
        token = f.read().strip()
    if ":" not in token:
        sys.exit("Das sieht nicht nach einem Token aus. Erwartet wird etwas "
                 "der Form 123456789:AA... - nur diese eine Zeile.")
    return token


def finde_chats(token):
    """Chats, aus denen der Bot zuletzt etwas gehoert hat.

    getUpdates zeigt nur, was seit dem letzten Abruf eingegangen ist, und
    haelt es rund einen Tag vor. Wer nichts geschrieben hat, taucht hier
    nicht auf - deshalb der Hinweis, vorher etwas zu senden.
    """
    gefunden = {}
    for eintrag in rufe(token, "getUpdates") or []:
        for feld in ("message", "edited_message", "channel_post",
                     "my_chat_member"):
            chat = (eintrag.get(feld) or {}).get("chat")
            if not chat:
                continue
            name = (chat.get("title")
                    or " ".join(filter(None, [chat.get("first_name"),
                                              chat.get("last_name")]))
                    or chat.get("username") or "ohne Namen")
            gefunden[str(chat["id"])] = "%s (%s)" % (name, chat.get("type", "?"))
    return gefunden


def main():
    try:
        cfg = k.lade()
    except k.KonfigFehler as e:
        sys.exit("%s\n\nDer Bot wird erst danach eingerichtet." % e)

    token = lies_token()

    ich = rufe(token, "getMe")
    print("Bot erkannt: @%s (%s)"
          % (ich.get("username", "?"), ich.get("first_name", "")))

    chats = finde_chats(token)
    if not chats:
        sys.exit("Kein Chat gefunden.\n"
                 "Schreibe dem Bot in Telegram etwas - oder fuege ihn einer "
                 "Gruppe hinzu und\nschreibe dort - und starte dieses Skript "
                 "erneut. Telegram zeigt nur\nNachrichten der letzten Zeit.")

    print("\nGefundene Chats:")
    for kennung, name in chats.items():
        print("   %-16s %s" % (kennung, name))

    cfg.setdefault("telegram", {})
    cfg["telegram"]["token"] = token
    cfg["telegram"]["chat_ids"] = sorted(chats)
    k.schreibe_json(k.CONFIG, cfg)
    print("\nIn %s eingetragen." % os.path.basename(k.CONFIG))

    try:
        os.remove(TOKENDATEI)
        print("token.txt geloescht.")
    except OSError as e:
        print("token.txt konnte nicht geloescht werden (%s) - bitte von Hand."
              % e)

    probe = ("<b>%s - Lieferwaechter</b>\nEingerichtet. Ab jetzt melde ich "
             "mich vor jeder Lieferung." % k.konzernname(cfg))
    for ziel in cfg["telegram"]["chat_ids"]:
        rufe(token, "sendMessage",
             {"chat_id": ziel, "text": probe, "parse_mode": "HTML"})
    print("Probenachricht verschickt.")


if __name__ == "__main__":
    main()
