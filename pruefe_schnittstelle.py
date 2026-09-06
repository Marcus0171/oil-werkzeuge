# -*- coding: utf-8 -*-
"""Prueft die Auswertung der Antworten - ohne Netz.

Die Antwortformen sind hier als Text nachgebaut. Das ist der Teil, an dem
sich falsche Annahmen raechen: Die Schnittstelle antwortet auf eine
abgelehnte Anfrage nicht mit einem Fehler, sondern mit einem Wert.

    python pruefe_schnittstelle.py
"""
import oi_schnittstelle as s

fehler = 0


def pruefe(was, bedingung, zusatz=""):
    global fehler
    print(("  ok   " if bedingung else "  FEHL ") + was
          + ("" if bedingung else "  ->  " + str(zusatz)))
    if not bedingung:
        fehler += 1


def hebt_ab(text, op="probe"):
    """True, wenn _auswerten einen SchnittstellenFehler wirft."""
    try:
        s._auswerten(text, op)
        return False
    except s.SchnittstellenFehler:
        return True


MAP = """<SOAP-ENV:Envelope><SOAP-ENV:Body><ns1:getCorporateGroupLevelResponse>
<return><item><key xsi:type="xsd:int">0</key><value xsi:type="xsd:string">12345</value></item>
<item><key xsi:type="xsd:int">4</key><value xsi:type="xsd:string">67890</value></item>
</return></ns1:getCorporateGroupLevelResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>"""

LISTE = """<SOAP-ENV:Envelope><SOAP-ENV:Body><ns1:getOilPriceResponse>
<return><item xsi:type="xsd:string">111.61</item><item xsi:type="xsd:string">345.00</item>
<item xsi:type="xsd:string">295.86</item><item xsi:type="xsd:string">83.22</item>
</return></ns1:getOilPriceResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>"""

EINZELN = """<SOAP-ENV:Envelope><SOAP-ENV:Body><ns1:getCorporateGroupBalanceResponse>
<return xsi:type="xsd:string">1234567</return>
</ns1:getCorporateGroupBalanceResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>"""

ABGEWIESEN = """<SOAP-ENV:Envelope><SOAP-ENV:Body><ns1:getCorporateGroupLevelResponse>
<return xsi:type="xsd:string">not authorized</return>
</ns1:getCorporateGroupLevelResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>"""

FAULT = """<SOAP-ENV:Envelope><SOAP-ENV:Body><SOAP-ENV:Fault>
<faultcode>SOAP-ENV:Server</faultcode><faultstring>Method not found</faultstring>
</SOAP-ENV:Fault></SOAP-ENV:Body></SOAP-ENV:Envelope>"""


print("== Antwortformen ==")
karte = s._auswerten(MAP)
pruefe("Schluessel-Wert-Paare werden ein Dict", isinstance(karte, dict), karte)
pruefe("mit ganzzahligen Schluesseln", karte == {0: "12345", 4: "67890"}, karte)

# Der Fallstrick: In einer Map steckt jedes Paar selbst in einem <item>.
# Wer Listen zuerst erkennt, macht aus jeder Map eine Liste.
pruefe("eine Map wird nicht als Liste gelesen", not isinstance(karte, list))

liste = s._auswerten(LISTE)
pruefe("eine <item>-Folge wird eine Liste", liste ==
       ["111.61", "345.00", "295.86", "83.22"], liste)

pruefe("ein einzelner Wert bleibt Text",
       s._auswerten(EINZELN) == "1234567", s._auswerten(EINZELN))

pruefe("eine leere Antwort ergibt None", s._auswerten("<leer/>") is None)

print("\n== Abweisung und Fehler ==")
pruefe("'not authorized' wird als Abweisung erkannt", hebt_ab(ABGEWIESEN))
pruefe("ein SOAP-Fault wird erkannt", hebt_ab(FAULT))
pruefe("ein gewoehnlicher Wert nicht", not hebt_ab(EINZELN))

print("\n== Marktpreise ==")
# Die Reihenfolge ist nicht dokumentiert und darf nicht stillschweigend
# verrutschen - deshalb steht sie als Konstante da und wird hier geprueft.
pruefe("vier Waren in fester Reihenfolge",
       s.PREIS_REIHENFOLGE == ["Rohoel", "Kerosin", "Diesel", "Benzin"],
       s.PREIS_REIHENFOLGE)

print("\n== Lagerschluessel ==")
pruefe("die Kraftstoffschluessel sind nicht 0-3",
       sorted(s.ROHSTOFF_KEYS) == [0, 1, 4, 7], sorted(s.ROHSTOFF_KEYS))
pruefe("Equipment deckt neun Plaetze ab", len(s.EQUIPMENT_KEYS) == 9)
pruefe("und faellt auf drei Arten zusammen",
       sorted({art for art, _ in s.EQUIPMENT_KEYS.values()})
       == ["Pipeline", "Tank", "Turm"])

print("\n%s" % ("Alles in Ordnung." if not fehler
                else "%d Pruefung(en) fehlgeschlagen." % fehler))
raise SystemExit(1 if fehler else 0)
