#!/usr/bin/env bash
# Daily backup of the database and uploaded files. Cron example (3am daily):
#   0 3 * * * /path/to/immaculate-crest/backup.sh >> /path/to/immaculate-crest/backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./.env; set +a
mkdir -p backups; ts=$(date +%F_%H%M)
docker compose exec -T db mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE" | gzip > "backups/db_$ts.sql.gz"
docker compose exec -T app tar czf - -C /data uploads > "backups/uploads_$ts.tar.gz"
find backups -type f -name '*.gz' -mtime +14 -delete
echo "backup $ts done"
