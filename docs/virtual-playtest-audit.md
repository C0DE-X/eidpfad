# Virtueller End-to-End-Playtest – Abschlussaudit

Stand: 2026-08-02
Prüfpfad: Profil/Match → Lobby/Ready → Weltwahl → alle Szenariotypen → Länderbosse →
Weltennaht → Bossvertrag → gemeinsamer Eid → Ending → Legacy → New Game+

## Urteil

Die im ursprünglichen Audit reproduzierten P0-, P1- und P2-Codefindings sind geschlossen.
Der autoritative Spielpfad ist in Expedition und Saga ohne manuelle Zustandsmanipulation
bis zur Folgekampagne durchspielbar. Der Stand erreicht damit die technischen
Quellcodekriterien für eine öffentliche Alpha; reale Plattform- und Zwei-PC-Tests bleiben
als externe Release-Gates verpflichtend.

## Virtueller Ablauf

1. Profile können erstellt, über einen einmaligen Code wiederhergestellt und ihre Tokens
   rotiert werden.
2. Host und Partner erstellen/finden eine Kampagne, verbinden sich und bestätigen Ready.
3. Disconnect pausiert die Partie; Reconnect liefert sofort Lobby und eigenen State.
4. Beide stimmen geheim über alternative Szenarioknoten ab.
5. Der Bot spielt legal mit Hand, AP, Phasen, Reaktionen, Kooperation, Zielwahl,
   Szenarioaktionen, Loot und Ausrüstung.
6. Alle Szenarioziele und regionalen Gegnermechaniken werden vom Server ausgewertet.
7. Der finale Boss durchläuft zwingend Eidtor, Wächter, Anker, gepanzerte Gestalt,
   zerrissene Welt und den gemeinsamen letzten Eid.
8. Beide Spieler einigen sich auf ein Ending, wählen je ein Vermächtnis und bestätigen
   die Folgekampagne auf Weltrang 2.

## Gemessene Läufe

| Lauf | Szenarien | Botaktionen | Rollbacks | Cinematic-Acks | Ergebnis |
|---|---:|---:|---:|---:|---|
| Expedition, Seed 17 | 18 | 3.355 | 11 | 26 | Ending, Legacy, NG+ |
| Saga, Seed 23 | 39 | 24.494 | 189 | 41 | Ending, Legacy, NG+ |

Der Bot ist absichtlich eine einfache Baseline und optimiert weder Builds noch Risiko.
Die hohe Rollbackzahl der Saga ist daher ein Stresswert, kein menschlicher Balancewert;
entscheidend für diesen Audit ist, dass kein deterministischer Würfel-, Ziel-, Phasen-
oder Persistenz-Softlock verbleibt.

## Während des Abschlusslaufs zusätzlich gefundene Fehler

| Übergang | Reproduktion | Korrektur |
|---|---|---|
| letzter normaler Loot → Bossvertrag | Folgenliste wurde als Dictionary gelesen | Legacy-Map und aktuelle Folgenliste werden normalisiert |
| Namenlose Form → letzter Eid | beide Spieler konnten unter 5 AP stehen | Eintritt öffnet ein frisches gemeinsames 5-AP-Fenster |
| letzter Anker → nächste Bossstufe | zweiter Karten-Rider nutzte alte Ziel-ID | Rider laufen auf besiegten/entfernten Zielen kontrolliert aus |

Alle drei Fälle besitzen Regressionstests.

## Vollständigkeitsstatus

| Bereich | Status |
|---|---|
| Profil, Recovery, Rotation | implementiert und getestet |
| Kampagnenerstellung, Join, Browser | implementiert und getestet |
| Ready, Pause, Reconnect, Completed | implementiert und getestet |
| Weltverzweigung und gemeinsame Auswahl | implementiert und getestet |
| vier Phasen, AP, W12, Ward, Rüstung | implementiert und getestet |
| mehrere Ziele, Reaktion, Kooperation | implementiert und getestet |
| sechs Szenariozieltypen | implementiert und getestet |
| 26 Wetterprofile und 14 Regionsmechaniken | implementiert und getestet |
| Loot, Inventar, Equipment, Kartenlebenszyklus | implementiert und getestet |
| Karte/Talent/Level/Meta-Fortschritt | implementiert und getestet |
| vollständiger Bossvertrag | implementiert und getestet |
| Ending, Legacy und New Game+ | implementiert und getestet |
| serverpersistierte Cinematics/Acks | implementiert und getestet |
| alle Runtime-Assets referenziert | 1.241/1.241 vorhanden |
| 3D-Modellstruktur | 334/334 intern valide |
| Windows-/Docker-/Zwei-PC-Runtime | extern noch auszuführen |

## Release-Gates außerhalb dieser Umgebung

- Windows-11-Build mit Godot 4 und Exporttemplates erzeugen und signieren.
- Ubuntu-Stack per Compose starten; Migration, Readiness, HTTPS und WSS prüfen.
- Zwei reale Clients von Profilanlage bis NG+ spielen, einschließlich Disconnect in jeder
  Phase und Serverrestart.
- GPU-/DPI-Matrix, Controller-/Mausbedienung, Audio-Ducking und Cinematic-Timing abnehmen.
- Menschliche Balance- und Accessibility-Runden durchführen.

Der automatisierbare Referenzlauf liegt in `scripts/virtual_release_playthrough.py`.
