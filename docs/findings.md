# Finding-Schließungsbericht

Stand: 2026-08-02
Basis: `docs/virtual-playtest-audit.md`
Ziel: alle im virtuellen Playtest reproduzierten P0-, P1- und P2-Findings im
gemeinsamen Quellstand schließen und anschließend kollisionsfrei integrieren.

## Ergebnis

Alle 19 priorisierten Code-, Regel-, Match- und Assetfindings des Audits sind im
Quellstand geschlossen. Drei zusätzliche Integrationsfehler wurden erst durch den
anschließenden vollständigen Release-Bot-Lauf sichtbar und ebenfalls behoben:

1. Listenformat der Szenariofolgen kollidierte beim Eintritt in den Bossvertrag mit
   einem alten Dictionary-Leser.
2. Der erste gemeinsame Eid konnte nach einer AP-intensiven Bossrunde in einen
   0-AP-Softlock geraten.
3. Rider einer Mehrfacheffektkarte konnten nach Zerstörung des letzten Bossziels eine
   bereits entfernte Ziel-ID adressieren.

## Schließungsmatrix

| ID | Ursprüngliches Finding | Integrierte Lösung | Nachweis |
|---|---|---|---|
| P0.1 | Endbossphasen und letzter Eid umgehbar | Eigenständiger `BossContract` mit Eidtor, zwei Wächtern, drei Ankern, vier Rüstungsteilen, drei HP-Böden, Eidkraft und gemeinsamer 5-AP-Aktion beider Spieler. Jede Stufe ist unüberspringbar. | Boss- und Runtime-Tests; vollständige Expedition und Saga |
| P0.2 | Postgame, Legacy und New Game+ fehlen | Geheime Konsenswahl, vier Ending-Zweige, persönliche Legacy-Auswahl, Meta-Fortschritt, Level und Weltrang-Folgekampagne. | `test_postgame.py`, Release-Bot bis Weltrang 2 |
| P0.3 | Tokenverlust und unsicheres HTTP | Einmaliger Recovery-Code, Rotation von Recovery- und Gerätetoken, Replay-Schutz sowie HTTPS/WSS-Pflicht außerhalb Loopback. | Match-Lifecycle- und Transporttests |
| P1.1 | Szenarioregeln nur Text | Sechs autoritative Zieltypen mit Schutz-LP, Bedrohung, Fluch, Hinterhalt und expliziter Jagdvorbereitung; Folgen werden persistiert. | `test_scenario_rules.py` |
| P1.2 | DoT-/Fallen-Wellenwechsel beschädigt Phase | Gemeinsamer `WaveTransitionRules`-Pfad setzt Runde, AP, Phase, Starter und Passstatus atomar zurück. | Wellen-Regressionstests |
| P1.3 | Reaktion, Kooperation und Zielwahl fehlen | Telegraphierte Intents, serverseitige Reaktionsfenster, Partnerbestätigung und Kosten, 1–3 adressierbare Ziele sowie geschützte Zielobjekte. | Combat-Protocol-/Action-Tests |
| P1.4 | Bossvertrag fehlt | Sechs mögliche Thronlose, Hinweise, problemabhängiger Druck, Bedrohung, Eidkraft, wechselnde Arenen und eigene Bossziele. | `test_boss_contract.py` |
| P1.5 | Weltkarte linear | Deterministische Alternativknoten, Kanten und geheime gemeinsame Szenarioabstimmung; eigener Marker pro Alternative. | Weltgenerator- und Runtime-Tests |
| P1.6 | Ready/Reconnect/Pause fehlerhaft | Explizites, idempotentes Ready; sofortiger Viewer-Snapshot; Pause bei Disconnect/Restart; zwei neue Ready-Bestätigungen; Completed ist terminal. | `test_match_lifecycle.py` |
| P1.7 | Kein Kampagnenbrowser/Lobby-Screen | Auswählbare Kampagnenliste, explizite Lobby-Mitglieder, Status und Ready; Lobby/Hauptmenü und laufende Partie sind getrennte Ansichten. | Client-Runtime-Vertrag im Projektvalidator |
| P1.8 | Letzter Eid als normale Progression | Reservierte Bosskarte wird aus Starterdeck und Fortschrittsbelohnungen gefiltert und vom normalen Kartenhandler abgelehnt. | Boss- und Contenttests |
| P2.1 | Wirkungslose Werte/Effects | `bound`, Spieler-Bann, Blutung/Gift, Waffen-Kombo, Talente, `armor_break` und `heal_all` besitzen erreichbare Laufzeitpfade. Alle 26 Wetterwerte haben mechanische Profile. | Combat-Action- und Wettertests |
| P2.2 | Heilbonus stammt vom Ziel | `EffectRules.heal` erhält explizit Heiler-ID und Heilerboni. | Heilungs-Regressionstest |
| P2.3 | Ausrüstung nicht steuerbar | Autoritative Equip-Nachricht, Inventarmenü zwischen Szenarien, Boni/Tooltip, kompatible Waffen und sauberes Entfernen gewährter Karten. | Equipmenttest und Client-Vertrag |
| P2.4 | Loot-UI erlaubt zweiten Claim | Claimstatus deaktiviert weitere Claims, zeigt „Warte auf Partner“ und ermöglicht dem ersten Spieler bereits die Ausrüstungswahl. | Engine- und Clientprüfung |
| P2.5 | Progression läuft aus | Kartenfreischaltung geht in Talent- und Charakterlevel-Fortschritt über; Legacy und Weltrang setzen danach fort. | Progressions-/Postgame-Tests |
| P2.6 | Verlauf wächst unbeschränkt | Historie auf 500 Events begrenzt; Checkpoint enthält weder sich selbst noch alte Historie. | Export-/Größentest |
| P2.7 | Schema und Pydantic driften | Strikt diskriminierte Nachrichtenunion deckt alle Kampf-, Auswahl-, Cinematic- und Postgame-Aktionen ab. | Protokolltests und JSON-Schema |
| P2.8 | Cinematics nicht reconnectfest | Serverpersistierter Cinematic-Fortschritt mit blockierendem Zwei-Spieler-Ack, Queue, Skip und Viewer-State. | Cinematic-Progress- und Restore-Tests |

## Kollisionsrefactoring

- `CampaignRuntime` ist die einzige Orchestrierungs- und Persistenzgrenze für
  `GameEngine`, `BossContract`, `Postgame` und `CinematicProgress`.
- Der WebSocket-Handler validiert nur Nachrichten und delegiert; er verändert keine
  parallelen Teilzustände mehr.
- Kartenauflösung kann intern ohne Zwischenaufzeichnung laufen. Kooperation und
  Reaktion schreiben deshalb jedes Ereignis genau einmal in die Historie.
- Bossziele verwenden denselben Multi-Target-Vertrag wie normale Gegner. DoT, Fallen,
  Rüstungsbruch und Mehrfacheffekt-Rider werden gemeinsam behandelt.
- Alle Save-Teilzustände liegen in einem versionierten Runtime-Dokument; alte rohe
  `GameEngine`-Saves werden importiert.
- Alembic 0001 ist der Produktions-Schemavertrag. Ein bestehender Pre-0.5-Prototyp wird
  einmal additiv vervollständigt und anschließend auf den Head gestempelt.

## Validierter Lieferumfang

| Klasse | Anzahl |
|---|---:|
| Karten | 128 |
| Gegenstände | 128 |
| regionale Gegner | 140 |
| GLB-Modelle | 309 |
| SVG-Assets | 440 |
| PNG-Assets | 25 |
| Audio ohne Voice | 37 |
| deutsche Voice-Zeilen | 336 |
| Cinematics | 48 |
| Manifestreferenzen | 1.151 |

Alle 309 GLBs besitzen gültige glTF-2.0-Strukturen. Figuren enthalten eine gebackene
Bind-Pose, sieben semantische Gelenke, Skins, Weights, inverse Bind-Matrizen, eingebettete
Textur, Materialparameter, LOD-Metadaten und 14 benannte Animationsclips. Der offizielle
Khronos-Validator meldet 0 Fehler und 0 Warnungen über die komplette Modellbibliothek.

## Abschlussprüfung

- 101 Python-Regel-, Match-, Persistenz- und Integrationstests bestanden
- zehn GDScript-Dateien erfolgreich geparst
- sämtliche JSON-Dateien und der Python-Quellcode erfolgreich geladen/kompiliert
- frische Alembic-Migration auf SQLite erfolgreich ausgeführt
- Asset-Neugenerierung erzeugt identischen Gesamtdigest
- vollständige Expedition: 18 Szenarien bis Ending, Legacy und New Game+
- vollständige Saga: 39 Szenarien, alle sechs Bossstufen, Ending, Legacy und New Game+

## Externe Release-Gates

Diese Punkte sind keine offenen Quellcodefindings, konnten in der aktuellen Umgebung
aber nicht praktisch ausgeführt werden:

- Godot-Import und Windows-11-Export mit offiziellen Exporttemplates
- Docker-/PostgreSQL-/Caddy-Start auf einem Ubuntu-VPS
- realer Zwei-PC-Lauf mit Latenz, Paketverlust, DPI- und Eingabetest
- finale Abnahme der Offline-TTS-Stimmen und prozeduralen Figuren durch Audio-/Art-Direction

Für eine kommerzielle Veröffentlichung bleiben Studio-Sprecher, Facial Rig/Viseme,
Motion-Capture und manuell gesculptete Hero-Assets Qualitätsupgrades. Die vorhandenen
stabilen IDs, Skeletons und Manifeste erlauben den Austausch ohne Regel- oder
Protokolländerung.
