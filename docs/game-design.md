# Spielentwurf des Vertical Slice

## Kampfrunde

Jeder Spieler erhaelt zu Rundenbeginn fuenf Aktionspunkte. Sie gelten gemeinsam
ueber vier Phasen und verfallen am Rundenende:

1. Angriff
2. Verteidigung
3. Magie
4. Vorbereitung

Der Startspieler wechselt jede Runde. Innerhalb einer Phase handelt zuerst der
Startspieler, bis er passt, danach der Partner. Karten werden serverseitig
abgelehnt, wenn Phase, aktive Person, Handkarte oder AP nicht passen.

## W12-Pools

```text
Angriffspool = Kartenwuerfel + Waffenbonus + Talent + Vorbereitung - Zustand
Blockpool    = Ruestung + Waffenparade + Verteidigungskarte + Talent - Durchdringung
```

Pools sind auf acht W12 begrenzt. Ergebnisse ab dem Zielwert sind Erfolge; eine
natuerliche 12 zaehlt doppelt. Legendäre oder Unique-Gegenstaende koennen diese
Regel gezielt veraendern. Nur die Differenz aus Treffern und Blocks verursacht
Schaden.

## Szenario und Heilung

Ein Szenario kann mehrere Runden und zwei bis drei Gegnerwellen enthalten.
Heilung, Regeneration, Fallen und Aetzoel werden in der Vorbereitungsphase
gespielt. Nach dem Szenariosieg werden beide Söldner vollstaendig geheilt,
kurzfristige Zustaende entfernt und ein neuer gemeinsamer Savepoint angelegt.
Verbrauchte oder erschoepfte Inhalte bleiben verbraucht.

## Welt

Der Seed kombiniert handgefertigte Laender-, Gebiets-, Wetter-, Gegner- und
Szenariobausteine. Jedes Land besitzt zehn eigene Gegner (acht normale Rollen,
eine Elite und einen Boss). Ein Land nutzt auf einer Route sieben davon genau
einmal. Die drei Kampagnenlaengen erzeugen 18, 27 oder 39 Szenarien mit 42, 63
oder 91 Begegnungen. Die letzte Station ist immer die Weltennaht mit der Krone
ohne Namen.

## Beute

Jeder Sieg bietet drei Gegenstaende. Laenderbosse garantieren mindestens einen
aussergewoehnlichen, der Endboss mindestens einen legendaeren Gegenstand. Beide
Spieler waehlen je ein Objekt; erst danach wird der naechste Savepoint gesetzt.
Passende staerkere Ausruestung wird im Slice automatisch angelegt.

Seltenheiten:

- normal
- selten
- verbessert
- aussergewoehnlich
- legendaer
- unique

## Endboss

Der Boss an der Weltennaht wechselt bei 75, 50 und 25 Prozent Lebenspunkten in
eine neue Phase und erhaelt jeweils einen Angriffswuerfel. Das bildet das
technische Fundament fuer Arenawechsel, Fraktionshilfen und die kooperative
Abschlusskarte `Der letzte Eid`.
