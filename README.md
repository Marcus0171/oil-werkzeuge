# Oil-Imperium-Werkzeuge

Zwei Werkzeuge für Konzernverträge im Browserspiel Oil Imperium:

- **Lieferwächter** — prüft vor jedem Liefertermin, ob genug im Lager ist, und meldet sich über Telegram und Windows, solange man noch etwas tun kann.
- **Morgenlage** — eine Seite, die zeigt, was man beim Aufwachen wissen muss: nächstes Lieferfenster, Deckung aller offenen Lieferungen, Lagerverlauf, Marktpreise, Konzernkonto.

Beide sind **rein lesend**. Sie fragen die offizielle SOAP-Schnittstelle ab und rechnen; im Spiel wird nichts verändert.

## Wozu

Ein Konzernvertrag wird in Teillieferungen zu festen Uhrzeiten erfüllt. Fehlt zum Termin auch nur eine Ware, platzt der Vertrag und es wird eine Strafe fällig. Das Spiel warnt nicht vor. Wer zweimal am Tag zum Termin nachsehen muss, verliert entweder Schlaf oder Verträge.

## Voraussetzungen

- Python 3.8 oder neuer. Keine weiteren Bibliotheken — alles steht in der Standardbibliothek.
- Ein Konzern in Oil Imperium, dessen Kennung (KID) und Schnittstellencode man kennt. Beides steht in den Konzerneinstellungen.
- Für Telegram-Meldungen: ein Bot, angelegt bei [@BotFather](https://t.me/BotFather). Optional — ohne ihn meldet der Wächter nur über Windows.

## Einrichten

```bash
git clone <dieses Repo>
cd oil-werkzeuge
cp oi_config.example.json oi_config.json
```

In `oi_config.json` mindestens diese drei Werte eintragen:

```json
"konzern": { "name": "Konzernname", "kid": 4711 },
"spiel":   { "welt": "s1.oilimperium.de", "code": "der-code-aus-dem-spiel" }
```

Ob es stimmt, sagt:

```bash
python oi_schnittstelle.py
```

Kommen Marktpreise, aber ein `Abgewiesen` beim Lagerstand, sind Kennung oder Code falsch — die Preise braucht die Schnittstelle nämlich ohne beides.

Für Telegram: bei @BotFather einen Bot anlegen, den Token in `token.txt` schreiben, dem Bot in Telegram etwas schreiben (oder ihn in eine Gruppe holen und dort schreiben), dann

```bash
python bot_einrichten.py
```

Das Skript prüft den Token, sucht die Chats, trägt beides ein, **löscht `token.txt`** und schickt eine Probenachricht. Der Umweg über die Datei ist Absicht: So steht der Token nie in der Shell-History.

## Betrieb

```bash
python oi_wachter.py            # Dauerbetrieb, prüft alle zehn Minuten
python oi_wachter.py --status   # Lage einmal ausgeben, nichts senden
python oi_wachter.py --test     # Meldewege und Verbindung prüfen

python oi_dashboard.py          # Morgenlage auf http://127.0.0.1:8099
python oi_dashboard.py --einmal # Datenblock einmal als JSON
```

## Die Konfiguration

| Schlüssel | Bedeutung |
|---|---|
| `konzern.name` | Name in Meldungen und Betreffzeilen. Ohne Eintrag steht dort „Konzern". |
| `konzern.kid` | Konzernkennung aus dem Spiel |
| `spiel.welt` | Server, auf dem der Konzern spielt |
| `spiel.code` | Schnittstellencode — ein Geheimnis |
| `telegram.token`, `telegram.chat_ids` | trägt `bot_einrichten.py` ein |
| `windows_meldung` | Windows-Benachrichtigung an oder aus |
| `takt_minuten` | Abstand zwischen zwei Prüfungen, Standard 10 |
| `vertraege[]` | je Vertrag: `nummer`, `slots`, `bedarf`, `bis`, `aktiv` |
| `dashboard.adresse`, `.port` | Bindung der Seite, Standard `127.0.0.1:8099` |
| `dashboard.benutzer`, `.passwort` | HTTP-Basic. Leer heißt: ungeschützt. |
| `mitglieder` | optional; ordnet Spielkonten einer Person zu, wenn jemand mehrere hat |

`oi_config.json` enthält Zugangsdaten und ist deshalb von der Versionsverwaltung ausgenommen. Versioniert ist nur die Vorlage.

**Die erste Ware in `bedarf` dient zur Erkennung**, ob eine Lieferung stattgefunden hat: Der Wächter merkt sich den Lagerstand bei Fensteröffnung und hält die Lieferung für erfolgt, wenn dieser Stand um mindestens 90 % der Liefermenge gefallen ist. Nicht 100 %, weil zwischen zwei Abfragen auch anderes zu- und abgehen kann.

## Prüfskripte

```bash
python pruefe_schnittstelle.py   # Antwortformen, nachgebaut
python pruefe_wachter.py         # Termine, Deckung, Meldeschwellen
python pruefe_dashboard.py       # Datenblock, Anmeldung, Auslieferung
```

Alle drei laufen **ohne Netz und ohne Spielkonto**. Die Zahlen darin sind erfunden, aber von Hand nachgerechnet. Wer eine Erwartung anpassen muss, weil der Code sie nicht mehr trifft, sollte zuerst nachrechnen, wer recht hat.

## Vier Eigenheiten der Schnittstelle

Sie ist alt, spärlich dokumentiert, und jede dieser vier Stellen liefert bei falscher Annahme **stillschweigend falsche Zahlen** statt eines Fehlers.

**1. Die Lagerschlüssel sind nicht 0–3 und nicht 0–8.** Die Dokumentation sagt das, die Antworten sagen etwas anderes: Kraftstoffe stehen unter 0, 1, 4 und 7. Die Tabellen in `oi_schnittstelle.py` stammen aus dem Abgleich mit dem Lagerbestand im Spiel.

**2. `not authorized` ist kein Fehler, sondern eine Antwort.** Stimmen Kennung oder Code nicht, kommt kein SOAP-Fault, sondern ein gewöhnlicher Rückgabewert mit diesem Text. Wer nur auf `<faultstring>` prüft, hält ihn für ein Ergebnis.

**3. Der Kontostand lügt dann.** `getCorporateGroupBalance` antwortet bei falschem Code mit `0` — von einem echten Kontostand null nicht zu unterscheiden. Ein einzelner Abruf kann das nicht erkennen. Deshalb fragt die Morgenlage zuerst den Lagerstand ab, der sich wehrt, und unterdrückt den Kontostand, wenn dieser Abruf abgewiesen wurde.

**4. Die Reihenfolge der Marktpreise ist nirgends dokumentiert.** Vier Werte ohne Beschriftung. Dass es Rohöl, Kerosin, Diesel, Benzin sind, ist gegen die Anzeige im Spiel abgeglichen, nicht nachgelesen.

## Auf einem Server betreiben

Für die Morgenlage lohnt sich ein kleiner Server: Sie ist dann auch dann erreichbar, wenn der eigene Rechner aus ist.

Die Seite bringt einen eigenen HTTP-Server mit, aber **kein TLS**. Sie gehört deshalb hinter einen Webserver wie Caddy oder nginx, der die Verschlüsselung übernimmt und an `127.0.0.1:8099` weiterreicht. Die Bindung in der Konfiguration bleibt dabei auf `127.0.0.1` — sonst ist die Seite am Webserver vorbei direkt erreichbar. Ein Benutzer und ein Passwort unter `dashboard` sollten trotzdem gesetzt sein; ohne sie liest jeder mit, der die Adresse kennt.

Alle Dateien gehören dabei **flach in ein Verzeichnis**. Die Module laden einander aus dem eigenen Ordner; eine verschachtelte Struktur zerbricht das.

Der Wächter selbst läuft am sinnvollsten dort, wo die Meldung ankommen soll. Unter Windows als geplante Aufgabe — mit einer Falle: Startet die Aufgabe eine `.cmd` oder `powershell.exe` direkt und läuft in der Desktopsitzung, blitzt bei jedem Lauf ein Konsolenfenster auf. `-WindowStyle Hidden` hilft nicht, es verbirgt nur das PowerShell-Fenster, nicht die bereits offene Konsole. Der Ausweg ist ein VBScript-Starter:

```vbs
Dim shell, code
Set shell = CreateObject("WScript.Shell")
code = shell.Run("python.exe ""C:\Pfad\oi_wachter.py""", 0, True)
WScript.Quit code
```

`wscript.exe` ist kein Konsolenprogramm; mit Fensterstil `0` wird die Konsole von vornherein verborgen erzeugt. Das `True` lässt es auf das Ende warten und reicht den Rückgabewert weiter — ohne das meldet die Aufgabe immer sofort Erfolg.

### Ein Telegram-Rückkanal mit n8n

Der Wächter meldet von sich aus. Wer umgekehrt **den Bot fragen** will („wie ist die Lage?"), braucht etwas, das auf Telegram-Nachrichten wartet. Dafür eignet sich eine Ablaufsteuerung wie [n8n](https://n8n.io): Ein Telegram-Auslöser nimmt den Befehl entgegen, ein HTTP-Knoten holt `/api/lage` von der Morgenlage — mit denselben Zugangsdaten aus `dashboard` —, ein kleiner Formatierer macht daraus eine Nachricht.

Das ist bewusst **nicht Teil dieses Repos**: Ein n8n-Ablauf enthält Verweise auf die Zugänge der eigenen Instanz und ist ohne sie wertlos. `/api/lage` liefert alles Nötige als JSON, und das ist die ganze Schnittstelle, die man dafür braucht.

Nützlich ist derselbe Aufbau auch als Totmannschalter: ein Zeitplan, der regelmäßig `/gesundheit` abruft und Alarm schlägt, wenn nichts antwortet. Mit einer Einschränkung, die man kennen sollte — läuft n8n auf demselben Server, schweigt es mit, wenn der Server stirbt. Eine zweite Prüfung von einem anderen Rechner deckt erst den Fall ab, in dem der ganze Server weg ist.

## Grenzen

- Der Wächter erkennt eine erfolgte Lieferung am Rückgang des Lagerstands, nicht an einer Meldung des Spiels. Wer im selben Zeitfenster große Mengen derselben Ware anderweitig verbraucht, kann ihn täuschen.
- Die Gesamtlage rechnet höchstens 14 Tage voraus (`HORIZONT_TAGE`). Ein Vertrag mit fernem Enddatum ergäbe sonst eine Zahl, die niemandem hilft.
- Zwischen zwei Prüfungen liegen standardmäßig zehn Minuten. Was dazwischen passiert, sieht der Wächter erst danach.
- Die Morgenlage speichert ihre Daten bis zu 60 Sekunden zwischen. Mehrere offene Browserfenster sollen die Schnittstelle nicht vervielfachen.

## Lizenz

MIT — siehe [LICENSE](LICENSE). Nutzung, Änderung und Weitergabe sind frei, solange der Copyright-Hinweis erhalten bleibt. Ohne Gewähr.
