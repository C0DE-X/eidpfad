# Serververwaltung und Backups

Das Adminwerkzeug wird ausschließlich offline im Servercontainer ausgeführt. Stoppe
den Server vor Löschungen oder Wiederherstellungen, damit kein Spielzustand im
Arbeitsspeicher einen restaurierten Stand wieder überschreibt.

```bash
docker compose stop server
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backups" server \
  python -m app.admin_cli backup --output /backups/eidpfad-$(date +%F-%H%M%S).json
docker compose run --rm --no-deps server python -m app.admin_cli list-profiles
```

Ein Profil wird nur über seine UUID und eine doppelte Bestätigung gelöscht. Eigene
Kampagnen werden dabei vollständig entfernt; fremde Mitgliedschaften werden gelöst.

```bash
docker compose run --rm --no-deps server python -m app.admin_cli \
  delete-profile --profile-id UUID --confirm UUID
```

Ein einzelnes Profil kann mit seinen Kampagnenmitgliedschaften und fehlenden
Kampagnen aus einem vollständigen Backup wiederhergestellt werden:

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backups:ro" server python -m app.admin_cli \
  restore-profile --input /backups/DATEI.json --profile-id UUID
docker compose start server
```

Backups enthalten Token- und Recovery-Hashes und müssen wie die Datenbank selbst
geschützt werden. Vor jeder Löschung sollte ein neues Backup erstellt werden.
