# GitHub-Repository einrichten

Der Quellbaum ist fuer ein privates GitHub-Repository vorbereitet. Die grossen
Laufzeitassets unter `client/assets/` werden ueber Git LFS versioniert. Lokale
Konfigurationen, virtuelle Umgebungen, Godot-Importdaten, Node-Module und
Buildartefakte sind ausgeschlossen.

## Voraussetzungen

- Git 2.28 oder neuer
- Git LFS
- Python 3.12 oder neuer fuer lokale Tests
- Godot in der Version aus `.godot-version` fuer Clienttests und Exporte

Unter Debian/WSL:

```bash
sudo apt update
sudo apt install git git-lfs make python3 python3-venv
git lfs install
```

## Erster Import

Auf GitHub zuerst ein leeres **privates** Repository ohne automatisch erzeugte
README-, Lizenz- oder `.gitignore`-Datei anlegen. Danach im Projektwurzelverzeichnis:

```bash
git init -b main
git lfs install
make setup
git add .
make repository-check
git status --short
git commit -m "chore: import Eidpfad vertical slice"
git remote add origin git@github.com:BENUTZER/EIDPFAD-REPOSITORY.git
git push -u origin main
```

`make repository-check` muss nach `git add .` laufen. Es prueft den tatsaechlich
zu commitenden Git-Index, lehnt lokale/generierte Dateien und zu grosse Git-Blobs
ab und stellt sicher, dass `GLB`, `PNG` und `WAV` als LFS-Pointer gespeichert
werden. Die erwartete Kontrolle zeigt 707 LFS-Assets.

Vor dem Commit sollten insbesondere keine Eintraege aus `dist/`, `node_modules/`,
`.venv/`, `.godot/` oder eine echte `.env` in `git status` erscheinen.

## Weitere Arbeitskopien

Auf jedem Rechner Git LFS einmal installieren, bevor das Repository geklont wird:

```bash
git lfs install
git clone git@github.com:BENUTZER/EIDPFAD-REPOSITORY.git
cd EIDPFAD-REPOSITORY
make setup
make validate
```

Fehlen nach einem Clone Assets, koennen sie explizit nachgeladen werden:

```bash
git lfs pull
```

## GitHub Actions

Der Workflow `CI` startet bei jedem Pull Request und bei Pushes nach `main`:

- Repository- und LFS-Pruefung
- 101 Server-Regressions- und Integrationstests plus Assetvalidator
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

## Bestehende Git-Historie

Die obige Reihenfolge gilt fuer den ersten Commit. Falls die binaeren Assets
bereits als normale Git-Blobs committed wurden, reicht ein spaeteres
`.gitattributes` nicht aus. Dann muss die Historie mit `git lfs migrate import`
neu geschrieben und anschliessend kontrolliert gepusht werden. Vor einer solchen
Historienumschreibung ist ein separates Backup erforderlich.

## Lizenz und Sichtbarkeit

Im Projekt ist bewusst keine Lizenzdatei enthalten, weil Code-, Bild-, Audio-
und Markenrechte zuerst festgelegt werden muessen. Bis diese Entscheidung
getroffen ist, sollte das GitHub-Repository privat bleiben. Ein oeffentliches
Repository ohne Lizenz erlaubt Dritten nicht automatisch die Nutzung, macht den
vollstaendigen Quell- und Assetstand aber sichtbar.
