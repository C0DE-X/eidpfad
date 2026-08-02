# GitHub-Repository einrichten

Der Quellbaum ist fuer ein privates GitHub-Repository vorbereitet. Binaere
Laufzeitassets unter `client/assets/` werden reproduzierbar aus eingecheckten
Python-/Node-Generatoren erzeugt und nicht im Repository gespeichert. Lokale
Konfigurationen, virtuelle Umgebungen, Godot-Importdaten, Node-Module und
Buildartefakte sind ausgeschlossen.

## Voraussetzungen

- Git 2.28 oder neuer
- Python 3.12 oder neuer fuer lokale Tests
- Node.js 24 fuer die Offline-Voice-Erzeugung
- Godot in der Version aus `.godot-version` fuer Clienttests und Exporte

Unter Debian/WSL:

```bash
sudo apt update
sudo apt install git make python3 python3-venv nodejs npm
```

## Erster Import

Auf GitHub zuerst ein leeres **privates** Repository ohne automatisch erzeugte
README-, Lizenz- oder `.gitignore`-Datei anlegen. Danach im Projektwurzelverzeichnis:

```bash
git init -b main
make setup
make content
git add .
make repository-check
git status --short
git commit -m "chore: import Eidpfad vertical slice"
git remote add origin git@github.com:BENUTZER/EIDPFAD-REPOSITORY.git
git push -u origin main
```

`make repository-check` muss nach `git add .` laufen. Es prueft den tatsaechlich
zu commitenden Git-Index, lehnt lokale und zu grosse Git-Blobs ab und stellt
sicher, dass generierte `GLB`, `PNG` und `WAV` nicht versehentlich eingecheckt
werden. Die CI erzeugt diese Dateien vor Assetvalidierung und Godot-Import neu.

Vor dem Commit sollten insbesondere keine Eintraege aus `dist/`, `node_modules/`,
`.venv/`, `.godot/` oder eine echte `.env` in `git status` erscheinen.

## Weitere Arbeitskopien

Auf jedem Rechner werden nach dem Klonen Abhaengigkeiten und Laufzeitassets erzeugt:

```bash
git clone git@github.com:BENUTZER/EIDPFAD-REPOSITORY.git
cd EIDPFAD-REPOSITORY
make setup
make content
make validate
```

## GitHub Actions

Der Workflow `CI` startet bei jedem Pull Request und bei Pushes nach `main`:

- Repository- und Generatorhygiene
- 110 Server-Regressions- und Integrationstests plus Assetvalidator
- Import mit der in `.godot-version` festgelegten Godot-Version, einschliesslich
  Ablehnung von GDScript-Parserfehlern
- Compose-Konfigurationspruefung und Build des Servercontainers

Der Workflow `Windows client` kann unter **Actions -> Windows client -> Run
workflow** manuell gestartet werden. Er laedt den offiziellen Godot-Editor und
die passenden Exporttemplates, prueft ihre SHA-512-Summen, erzeugt den
Windows-x86_64-Export und stellt das ZIP 14 Tage als Workflow-Artefakt bereit.
Ein Tag wie `v0.5.0` startet denselben Export automatisch.

Als Branch-Schutz fuer `main` sollten mindestens die vier CI-Checks
`Repository hygiene`, `Rules and asset references`, `Godot import and GDScript
parse` und `Server container` verpflichtend sein.

## Reproduzierbarkeit

`make content` erzeugt Karten-/Gegenstandsdefinitionen, Rasterbilder, Audio,
Voice und GLB-Modelle deterministisch. Aenderungen an eingecheckten generierten
JSON-/SVG-Quellen werden von der CI mit `git diff --exit-code` erkannt. So bleibt
ein frischer Clone ohne externe Assetablage vollstaendig baubar.

## Lizenz und Sichtbarkeit

Im Projekt ist bewusst keine Lizenzdatei enthalten, weil Code-, Bild-, Audio-
und Markenrechte zuerst festgelegt werden muessen. Bis diese Entscheidung
getroffen ist, sollte das GitHub-Repository privat bleiben. Ein oeffentliches
Repository ohne Lizenz erlaubt Dritten nicht automatisch die Nutzung, macht den
vollstaendigen Quell- und Assetstand aber sichtbar.
