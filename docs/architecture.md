# Architektur

## Laufzeitaufteilung

```text
Windows-11-Client -- HTTPS/WSS --> Caddy -- HTTP/WS --> FastAPI -- SQL --> PostgreSQL
```

Godot zeigt Hauptmenue, Lobby, 2.5D-Welt, Karten, Portraits und W12-Animationen
an. Der Client sendet nur Absichten wie `play_card`, `pass_phase` oder
`claim_loot`. FastAPI prueft Phase, aktiven Spieler, Aktionspunkte, Kartenhand,
Ziele und Beute. Erst danach wird der kanonische Zustand in PostgreSQL gesichert
und an alle Teilnehmer der Kampagne verteilt.

## Transport und Authentifizierung

- REST erzeugt Profile, erstellt Kampagnen, tritt per Einladungscode bei und
  liefert fortsetzbare Kampagnen.
- Ein WebSocket pro Spieler uebertraegt Lobby- und Spielereignisse.
- Der Godot-Client reserviert vor dem Handshake einen 8-MiB-Eingangspuffer, weil
  der erste autoritative Zustand auch Karten-, Gegenstands-, Gegner- und
  Weltdefinitionen enthaelt und damit groesser als Godots 64-KiB-Standard ist.
- Der native Client sendet sein Geraete-Token im `Authorization: Bearer`-Header
  des WebSocket-Handshakes. Es steht nicht in Query-Parametern oder Logs.
- Protokollversion 2 verwendet eine strikt diskriminierte Nachrichtenunion fuer Ready,
  Karten, Reaktionen, Kooperation, Phasen, Loot, Szenariowahl, Ausruestung,
  Boss-Eid, Ending, Legacy, New Game+ und Cinematic-Acks.
- Auf dem VPS terminiert Caddy TLS. Uvicorn akzeptiert Proxy-Header nur in der
  Produktions-Compose-Erweiterung.

## Autoritative Wuerfel

Der Server leitet fuer jeden Pool einen reproduzierbaren Zufallsstrom aus
Kampagnen-Seed und fortlaufendem Wurfindex ab. Ein Ereignis enthaelt Zweck,
Zielwert, einzelne Werte, Erfolge und kritische Erfolge. Godot reiht die
Ereignisse ein und animiert sie nacheinander. Lokale Physik oder ein
Animationsabbruch veraendern kein Ergebnis.

## Orchestrierung, Persistenz und Rollback

`CampaignRuntime` ist die einzige serialisierbare Grenze fuer normale Szenarien,
Bossvertrag, Postgame und Cinematic-Fortschritt. Der WebSocket-Handler delegiert
Spielerabsichten an diese Runtime und speichert danach genau ein versioniertes Dokument.

Nach jeder gueltigen Nachricht wird `campaigns.live_state` aktualisiert. Nach
Lootauswahl und Aufbau des naechsten Szenarios wird ein vollstaendiger
`checkpoint_state` erzeugt. Faellt ein Spieler, wird dieser Snapshot fuer beide
Söldner wiederhergestellt. Der Seed und bereits bestaetigte Beute bleiben damit
stabil.

Vor dem Produktionsstart fuehrt der Container Alembic-Migrationen aus. Alte
Pre-0.5-Datenbanken erhalten einmalig die fehlenden additiven Tabellen und werden danach
wie neue Installationen revisionsbasiert migriert.

## Nebenlaeufigkeit

Eine asynchrone Sperre pro Kampagne serialisiert gleichzeitig eintreffende
WebSocket-Aktionen. Der aktuelle Prozess besitzt Lobbys und Sperren im Speicher;
daher muss der Container mit einem Uvicorn-Prozess betrieben werden. Horizontale
Skalierung benoetigt einen gemeinsamen Event-Bus, verteilte Sperren und ein
Presence-System.

## Containergrenzen

Der Server laeuft als Benutzer `10001`, mit read-only Root-Dateisystem,
entfernten Linux-Capabilities und einem beschraenkten `/tmp`. PostgreSQL ist
nicht am Host veroeffentlicht. Der FastAPI-Port ist nur an `127.0.0.1` gebunden;
Caddy erreicht ihn ueber das interne Compose-Netz.
