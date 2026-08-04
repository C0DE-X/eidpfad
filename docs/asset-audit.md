# Assetaudit und 2D-/3D-/Cinematic-Entscheidung

## Darstellungsentscheidung

| Assetklasse | Darstellung | Grund |
|---|---|---|
| Karten, Inventar, HUD | 2D-SVG | Lesbarkeit, schnelle Erkennung und scharfe Skalierung. |
| Portraits und Cinematic-Plates | 2D-Raster | Gesichter, Atmosphäre und filmische Bildkomposition ohne unnötige 3D-Nahaufnahme-Kosten. |
| Helden und Gegner | animiertes 3D-GLB | Licht, Silhouette, getrennte Trefferreaktionen, Rollen und Bossphasen. |
| Loot | 2D-SVG + animiertes 3D-GLB | Icon für Auswahl, `reveal`/`loot_hover` für räumliche Präsentation. |
| Länder und Props | animiertes 3D-GLB | 2.5D-Tiefe, Parallaxe und subtile Umgebungsbewegung. |
| Würfel | 3D-GLB + serverbestimmte Labels | Physischer W12-Eindruck bei autoritativem Ergebnis. |
| Cinematics | Motion Comic/Realtime | Keyframes, Pan/Zoom/Fade, Voice und Untertitel passen zum 2.5D-Stil und sind sofort skip-/lokalisierbar. |

## Vollständige Abdeckung

| Klasse | Anzahl | Laufzeitverwendung |
|---|---:|---|
| Karten-/Item-/Gegnericons | 144 + 152 + 140 | Hand, Loot, Inventar, Zielanzeige |
| Gegenstands-/Gegnermodelle | 152 + 140 | Loot-Reveal, Gegnerwellen |
| Heldenmodelle | 5 | Axt, Bogen, Doppelklingen, Armbrust, Langschwert |
| Länder-Landmarks / Props / D12 | 14 + 22 + 1 | Weltkarte, Szenario, Bossziele, Würfel |
| Figure-Clips | 14 je Figur | Idle, Walk, Run, Attack, Cast, Guard, Dodge, Hit, Defeat, Spawn, Victory und Varianten |
| UI/VFX/Logo | 21 + 8 + 1 | HUD, Feedback, Boss/Postgame, Branding |
| Raster | 26 | 13 Biome, Screens, fünf Portraits und fünf Cinematic-Plates |

Das Hauptmenü verwendet ein kuratiertes, originales Dark-Fantasy-Key-Art mit
bewusst ruhiger linker Navigationsfläche. Die eingecheckte Designquelle unter
`assets/concepts/main_menu_background.png` wird vom Rastergenerator bytegenau
nach `client/assets/backgrounds/main_menu.png` übernommen; Texte und Buttons
bleiben native Godot-Controls.
| Voice | 360 | Plot, Länder, Szenarien, 14 Bosse, fünf Helden, Gegner, Endings, Tutorial |
| Cinematics | 48 | Prolog, Länder, Szenarien, Bosse, vier Endings, Legacy, Rollback, Tutorial |
| Audio ohne Voice | 37 | 18 SFX, 13 Stereo-Ambiences, sechs Stereo-Musikzustände |

Das Manifest enthält 1.241 geprüfte Laufzeitreferenzen. Jede der 140 Gegnerdefinitionen besitzt eine eindeutige 2D-/3D-Zuordnung sowie Körperfamilie, Animationssatz und Voice-Profil.

## Modell- und Animationsstandard

- glTF 2.0/GLB mit eingebetteten Materialien und Clips
- Figuren mit sieben semantischen Gelenken, Skin/Weights, inversen Bind-Matrizen und gebackter Bind-Pose
- eingebettete Base-Color-Textur und LOD-Metadaten
- mindestens 4.000 tatsächlich instanziierte Dreiecke pro Figur
- acht Körperfamilien: Humanoid, Quadruped, Schlange, Arthropode, Harpyie, Geist, Schwarm und Riese
- fünf Helden-Silhouetten für alle Waffenstarts
- 14 Figure-Clips: `idle`, `combat_idle`, `walk`, `run`, `attack`, `heavy_attack`, `cast`, `guard`, `dodge`, `hit`, `stagger`, `defeat`, `spawn`, `victory`
- getrennte Animationen für Loot, Landschaft, Props und D12
- Event-Presentation Queue verhindert Tod/Spawn- und Würfel-/Treffer-Überlagerungen

Diese Assets sind detaillierte, prozedural erzeugte Runtime-Modelle. „High Poly“ bezeichnet hier die deutlich höhere Gameplay-Geometrie gegenüber dem früheren Platzhalter. Skeleton, Skinning, Textur und Runtime-LOD sind vorhanden. Manuelle Sculpt-Quellen, Retopologie, hochauflösende PBR-Bakes, Facial Rigs, Viseme und Motion Capture bleiben externe Art-Produktion.

## Prüfungen

- alle 334 GLB-Strukturen, Binärchunks, Materialien, Skins und Animationskanäle intern geparst
- offizieller Khronos-glTF-Validator: 0 Fehler und 0 Warnungen über alle 334 Modelle
- erwartete Clipnamen pro Modellklasse geprüft
- Mindestdreieckbudget jeder Figur geprüft
- 360 Voice-WAV-Dateien auf Monoformat, Sample-Rate und Manifestdauer geprüft
- 48 Cinematics auf gültige Voice- und Bildreferenzen geprüft
- alle Kampagnenlängen auf regionale Gegnerwiederholung geprüft
- alle Manifestpfade vorhanden; keine verwaisten GLBs
- 110 Tests sowie vollständige Single- und Multiplayer-Saga bis New Game+

Ein echter Godot-Import, Windows-Export und GPU-Screenshotvergleich ist weiterhin erforderlich, sobald Godot 4 und Exporttemplates verfügbar sind.
