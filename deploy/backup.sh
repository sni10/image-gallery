#!/usr/bin/env bash
# Pull a full production backup to this PC:  deploy/backup.sh [target dir]
# Same layout as the restore set: artai.dump (pg_dump -Fc), media.tar, originals.tar, .env, compose.prod.yaml, Caddyfile.
# Everything streams over ssh (nothing is staged on the server); dump/tar run niced so the site keeps serving.
# Restore: DEPLOY.md, "Восстановление из бэкапа".
set -euo pipefail

SERVER=${DEPLOY_SERVER:-deploy@198.98.52.9}
DIR=${DEPLOY_DIR:-/srv/artai}
OUT=${1:-/c/backups/artai/$(date +%F)}

mkdir -p "$OUT"
echo "-> $OUT"

ssh "$SERVER" "cd $DIR && docker compose -f compose.prod.yaml exec -T db sh -c 'nice pg_dump -Fc -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\"'" > "$OUT/artai.dump"
for v in media originals; do
  ssh "$SERVER" "docker run --rm -v artai_$v:/src:ro alpine nice tar -cf - -C /src ." > "$OUT/$v.tar"
done
scp -q "$SERVER:$DIR/.env" "$SERVER:$DIR/compose.prod.yaml" "$SERVER:$DIR/Caddyfile" "$OUT/"

# Check: dump is readable, archive file counts match the live volumes.
pg_tables=$(ssh "$SERVER" "cd $DIR && docker compose -f compose.prod.yaml exec -T db pg_restore --list" < "$OUT/artai.dump" | grep -c ' TABLE DATA ')
echo "artai.dump: $pg_tables tables with data"
for v in media originals; do
  live=$(ssh "$SERVER" "docker run --rm -v artai_$v:/src:ro alpine find /src -type f" | wc -l)
  got=$(tar -tf "$OUT/$v.tar" | grep -vc '/$')
  echo "$v.tar: $got files (server: $live)"
  [[ $got -eq $live ]] || { echo "MISMATCH in $v" >&2; exit 1; }
done
ls -la "$OUT"
