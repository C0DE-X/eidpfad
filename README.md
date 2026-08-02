# Eidpfad

Spielbarer, inhaltlich ausgebauter Vertical Slice fuer ein kooperatives,
rundenbasiertes Dark-Fantasy-Kartenspiel fuer zwei Spieler.

Der Repository-Stand ist fuer GitHub vorbereitet. Die binaeren Laufzeitassets
werden ueber Git LFS verwaltet; die Anleitung fuer den ersten Import steht in
[`docs/github.md`](docs/github.md).

## Zielplattformen

- **Client:** native Godot-4-Anwendung fuer Windows 11 x86_64
- **Server:** autoritativer FastAPI-Server auf einem Ubuntu-VPS
- **Deployment:** Docker Compose, PostgreSQL und optional Caddy fuer HTTPS/WSS
- **Protokoll:** REST fuer Profile/Kampagnen, WebSocket-Protokoll Version 2 fuer das Spiel

Der Windows-Export enthaelt keinen Server. Kartenregeln, Kampagnenzustand,
Weltgenerierung, W12-Ergebnisse, Loot und Rollbacks werden ausschliesslich im
Servercontainer berechnet. Der Client sendet nur Spielerabsichten und rendert
den bestaetigten Zustand.

## Lokal starten

Voraussetzungen sind Docker Engine und das Compose-Plugin.

```bash
cp .env.example .env
# POSTGRES_PASSWORD in .env ersetzen
docker compose up --build -d
curl http://127.0.0.1:8080/health/ready
```

Die lokale Serveradresse im Client lautet `http://127.0.0.1:8080`. API-Dokumente
sind in der Entwicklungsumgebung unter `http://127.0.0.1:8080/docs` verfuegbar.

## Ubuntu-VPS starten

1. Einen DNS-A/AAAA-Eintrag, beispielsweise `game.example.com`, auf den VPS setzen.
2. TCP 80/443 und UDP 443 in der Firewall freigeben.
3. `.env.example` als `.env` kopieren, ein langes Datenbankpasswort und
   `SERVER_DOMAIN` setzen.
4. Den Produktionsstack starten:

```bash
docker compose -f docker-compose.yml -f docker-compose.vps.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.vps.yml ps
curl https://game.example.com/health/ready
```

Caddy fordert das TLS-Zertifikat automatisch an und leitet HTTPS sowie WSS an
den internen Server weiter. Im Windows-Client wird danach
`https://game.example.com` eingetragen. Weitere Details stehen in
[`docs/deployment.md`](docs/deployment.md).
Profilverwaltung, vollständige Backups und die Wiederherstellung einzelner
Charaktere sind in [`docs/server-administration.md`](docs/server-administration.md) beschrieben.

## Windows-11-Client bauen

Godot in der Version aus `.godot-version` und die exakt dazu passenden
Export-Templates muessen installiert sein. Unter Windows kann der Export direkt
aus PowerShell erzeugt werden:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\client\build-windows.ps1 -Godot "C:\Tools\Godot\godot.exe"
```

Das Ergebnis liegt als `dist/client/eidpfad-windows-x86_64.zip` vor. Alternativ:

```bash
make client-windows GODOT=/pfad/zu/godot
```

Serveradresse, Profil-Token und letzte Kampagne werden im Godot-Verzeichnis
`user://` des angemeldeten Windows-Benutzers gespeichert. Das Token wird nie in
die WebSocket-URL geschrieben, sondern als Bearer-Header beim Handshake gesendet.

## Implementierter Spielstand

- vier Phasen: Angriff, Verteidigung, Magie und Vorbereitung
- fuenf Aktionspunkte pro Spieler und Runde, gemeinsam ueber alle Phasen
- serverautoritatives W12-System mit kritischen Doppelerfolgen
- Ausruestungs-, Ruestungs- und Talentboni auf Treffer- und Blockpools
- animierte, nacheinander dargestellte Treffer-, Block-, Magie- und Bannwuerfe
- 128 Karten in vier Phasen, neun Schulen und sechs Seltenheiten
- 128 Gegenstaende mit 96 Waffen und 32 Ruestungs-/Supportobjekten
- 140 Gegner: zehn Namen pro Land, acht Körperfamilien und 14 aktive Regionsmechaniken
- deterministische Welten mit 6, 9 oder 13 Laendern und je drei Szenarien
- zwei bis drei Gegnerwellen je Szenario ohne regionale Wiederholung
- Szenariotypen, Laenderbosse und vierstufiger finaler Boss
- vollstaendige Heilung und gemeinsamer Savepoint nach abgeschlossenen Szenarien
- Bossbeute in den Stufen normal, selten, verbessert, aussergewoehnlich,
  legendaer und unique
- PostgreSQL-Persistenz nach jeder gueltigen Aktion
- 2.5D-Weltdiorama mit kompletter Route, echten GLB-Modellen und festem Charakterbereich rechts unten
- 309 animierte 3D-Modelle: 140 Gegner, 128 Gegenstaende, vier Waffencharaktere, Laender, Bossziele, Props und W12
- Figuren mit sieben Gelenken, Skin/Weights, Bind-Pose, eingebetteter Textur, LOD und 14 Animationsclips
- 440 semantische SVG-Assets, 25 Rasterbilder, 8 VFX-Overlays und ein eigenes Logo
- 48 datengetriebene Motion-Comic-/Realtime-Cinematics mit serverpersistiertem Zwei-Spieler-Ack
- 336 deutsche Voice-/Untertitelzeilen fuer Plot, Laender, Bosse, vier Helden, Endings und Tutorial
- 18 Audio-Cues, 13 laengere Stereo-Atmosphaeren und 6 dynamische Stereo-Musikbetten
- vollstaendiger Bossvertrag, vier Endings, Legacy-Transfer, Charakterlevel und New Game+
- Kampagnenbrowser, Lobby/Ready, Pause/Reconnect und Profilwiederherstellung
- Alembic-Migrationen fuer frische und bestehende VPS-Datenbanken
- serielle Eventpraesentation fuer Wuerfel, Treffer, Tod, Spawn, Audio und VFX
- Audio-Busse, Voice-Ducking, Lautstaerkeregler, Untertitel und 3D-Renderqualitaet
- manifest- und referenzgepruefte Karten-, Gegenstands-, Gegner-, Laender-, UI- und Modellassets

## Tests

Die lokale Python-Umgebung wird einmalig eingerichtet und anschliessend fuer alle
Regel-, Protokoll- und Assettests verwendet:

```bash
make setup
make validate
```

Der aktuelle Satz umfasst 101 Tests fuer Regeln, Match-Lifecycle, Recovery,
Persistenz, Szenarioziele, Bossvertrag und Postgame. Der Projektvalidator prueft
zusaetzlich 1.151 Manifestreferenzen, 309 GLB-Strukturen, 336 Voice-Dauern,
48 Cinematic-Timelines, PNG/SVG/WAV-Dateien, Raritaeten und jede Kampagnenlaenge.
Der Referenzlauf bis New Game+ kann mit
`python scripts/virtual_release_playthrough.py --campaign-length saga` wiederholt werden.

## Projektstruktur

```text
client/                    Godot-Projekt und Windows-Exportskript
server/                    FastAPI-Anwendung und schlankes Runtime-Image
shared/                    Karten, Gegenstaende, Gegner und Protokollschema
scripts/                   reproduzierbare Content-/Asset-Generatoren und Validator
deploy/                    Caddy-Konfiguration fuer den VPS
.github/workflows/          GitHub-CI und reproduzierbarer Windows-Export
docker-compose.yml         Server und PostgreSQL
docker-compose.vps.yml     HTTPS/WSS-Erweiterung fuer Ubuntu
docs/                      Architektur, Deployment und Spielentwurf
```

## Bewusste Grenzen

Der Server laeuft absichtlich mit genau einem Prozess, weil Lobbyverbindungen
im Speicher gehalten werden. Fuer mehrere Replikate werden Redis oder ein
vergleichbarer gemeinsamer Event-Bus und verteilte Sperren benoetigt. Der
Produktionscontainer fuehrt vor dem Start `alembic upgrade head` aus; bestehende
Pre-0.5-Prototypdatenbanken werden einmal additiv auf den Migrationsstand gehoben.

Das Assetmanifest deckt jede Laufzeitreferenz des Source-Vertical-Slice ab.
Die Figuren verwenden hochdetaillierte prozedurale Runtime-GLBs mit Skeleton,
Skin-Weights und eingebetteten Animationsclips. Sie ersetzen die frueheren
Platzhalter, sind aber keine manuell gesculpteten Hero-Assets mit Motion Capture,
Facial Rig oder Visemen. Die deutschen Offline-Produktionsstimmen sind
vollstaendig eingebunden und koennen anhand stabiler Line-IDs durch
Studioaufnahmen ersetzt werden. Cinematics sind Motion-Comic-/Realtime-Sequenzen
mit serverseitigem Zwei-Client-Ack.

Der lokale Docker-Compose-Stack und der Serverstart wurden im ersten realen
Setup erreicht. Ein erneuter vollstaendiger Godot-Import nach den drei
GDScript-Parsefixes, der Windows-Export, das VPS-Deployment und ein echter
Zwei-PC-Test bleiben zwingende Release-Gates. Die GitHub-CI prueft Import und
Containerbuild bei kuenftigen Commits automatisch. Details stehen in
[`docs/asset-audit.md`](docs/asset-audit.md),
[`docs/cinematic-production.md`](docs/cinematic-production.md) und
[`docs/findings.md`](docs/findings.md).
