# Deployment auf einem Ubuntu-VPS

## Voraussetzungen

- 64-Bit Ubuntu-VPS
- Docker Engine und Docker Compose Plugin
- Domain mit A- und optional AAAA-Eintrag auf den VPS
- offene Ports TCP 80/443 und UDP 443

Der Server benoetigt keine Godot-Installation. Godot wird nur auf dem
Entwicklungsrechner zum Erzeugen der Windows-Datei verwendet.

## Erstinstallation

```bash
cp .env.example .env
openssl rand -hex 32
```

Den ausgegebenen Wert in `.env` als `POSTGRES_PASSWORD` eintragen und
`SERVER_DOMAIN` auf die echte Domain setzen. Danach:

```bash
docker compose -f docker-compose.yml -f docker-compose.vps.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.vps.yml ps
docker compose -f docker-compose.yml -f docker-compose.vps.yml logs --tail=100 server caddy
```

Pruefung:

```bash
curl https://game.example.com/health
curl https://game.example.com/health/ready
```

Die erste Route prueft den Prozess, die zweite zusaetzlich PostgreSQL.

## Aktualisierung

```bash
git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.vps.yml build --pull server
docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d
docker image prune -f
```

Der Servercontainer fuehrt vor jedem Start `python -m app.migrate` und damit
`alembic upgrade head` aus. Eine bestehende Pre-0.5-Prototypdatenbank ohne
`alembic_version` wird einmal additiv vervollstaendigt und auf den aktuellen Head
gestempelt. Vor jeder weiteren Modellaenderung ist eine neue Revision unter
`server/migrations/versions/` anzulegen; ein Datenbankbackup bleibt Pflicht.

## Backup

Ein einfaches logisches Backup kann auf dem Host erzeugt werden:

```bash
docker compose exec -T db pg_dump -U eidpfad -d eidpfad -Fc > eidpfad-$(date +%F).dump
```

Backups sollten anschliessend verschluesselt auf einen zweiten Speicherort
kopiert und regelmaessig testweise wiederhergestellt werden. Das Docker-Volume
`postgres-data` darf bei `docker compose down` nicht mit `-v` geloescht werden.

## Betriebshinweise

- Nur eine Serverreplik betreiben, bis Lobby und Sperren externalisiert sind.
- Port 5432 nicht oeffentlich freigeben.
- Den lokalen Port 8080 nur ueber SSH oder direkt auf dem VPS verwenden.
- `.env` nicht committen.
- Caddy-Datenvolumes sichern, wenn Zertifikatszustand erhalten bleiben soll.
- Logs werden durch Compose auf drei Dateien zu je 10 MiB begrenzt.
