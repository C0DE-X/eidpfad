# Cinematic- und Voice-Produktion

## Produktionsumfang

Die 48 Timelines setzen sich aus Prolog, Aufbruch, 14 Länder-Reveals, sechs Szenariotyp-Briefings, 14 Boss-Reveals, drei Finalboss-Phasen, Finalboss-Tod, Epilog, Rollback-Stinger, Sprach-Tutorial, vier Ending-Zweigen und Legacy-Transfer zusammen. Der Seed wählt die benötigten Länder; Timelines werden nicht als starre Videos dupliziert.

Vier neue 16:9-Plates tragen die Hauptgeschichte:

- `prologue.png`: Zerbrechen der Reliquie und die zwei Eidzeichen
- `journey.png`: Reise durch neu zusammengesetzte Länder
- `finale.png`: Enthüllung der Krone ohne Namen
- `world_echo.png`: Übergang in die nächste Welt

`ending_crossroads.png` trägt als fünfte Plate die vier Abschlusswege und den
Legacy-Übergang.

Länder- und Szenariosequenzen verwenden die 13 vorhandenen Biome weiter. `CinematicPlayer` steuert Letterbox, Pan/Zoom, Fade, Untertitel, Voice und Skip.

## Voice-Manifest

`shared/narrative/voice_manifest.de-DE.json` ist die verbindliche Zuordnung aus stabiler Line-ID, Sprecher, deutschem Text, WAV-Datei und Dauer. Es umfasst:

- 40 Plotzeilen
- 42 Länderzeilen
- 18 Szenariobriefings
- 56 Bosszeilen
- vier Finalboss-Zusätze
- 96 Heldenbarks für vier getrennte Sprecherprofile
- 60 Gegnerrollen-Barks
- zehn Tutorial-/Accessibility-Zeilen
- acht Ending- und zwei Legacy-Zeilen

Die Produktionsstimmen werden offline durch `npm run voice` erzeugt. Studioersatz behält Pfad und Line-ID bei; danach muss nur die Dauer im Manifest aktualisiert werden.

## Audiofluss

Godot-Busse: Master, Music, Ambience, SFX, Voice und UI. Voice senkt Musik und Atmosphäre während der Wiedergabe. Master, Musik und Stimmen sind im Client einstellbar; Untertitel können separat aktiviert werden.

## Release-Gates

- zwei Windows-Clients spielen dieselbe Cinematic-Reihenfolge
- Skip und Reconnect verlieren keine Gameplay-Ereignisse
- Voice-Datei und Untertitel stimmen für alle 336 IDs überein
- 16:9, 21:9 und 1280×720 schneiden Untertitel nicht ab
- Studio-Voice wird auf Lautheit, Klicks, Atemschnitt und Aussprache geprüft
- Facial Close-ups erst nach Skin-, Face-Rig- und Viseme-Produktion einsetzen
