#!/usr/bin/env bash
# Deploy (or roll back to) an image built by GitHub Actions:  deploy/deploy.sh <full commit sha>
# Copies compose.prod.yaml + Caddyfile to the server, records the sha in the server's .env (IMAGE_TAG),
# pulls the image and restarts the app; migrations run in the container entrypoint before gunicorn starts.
set -euo pipefail

SERVER=${DEPLOY_SERVER:-deploy@2.28.193.254}
DIR=${DEPLOY_DIR:-/srv/artai}
SHA=${1:-}

if [[ ! $SHA =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: $0 <full 40-char commit sha>   (an image ghcr.io/sni10/image-gallery:<sha> must exist)" >&2
  exit 1
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
scp -q "$ROOT/compose.prod.yaml" "$SERVER:$DIR/compose.prod.yaml"
scp -q "$ROOT/deploy/caddy/Caddyfile" "$SERVER:$DIR/Caddyfile"

ssh "$SERVER" bash -s -- "$DIR" "$SHA" <<'REMOTE'
set -euo pipefail
cd "$1"
if grep -q '^IMAGE_TAG=' .env; then sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$2/" .env; else echo "IMAGE_TAG=$2" >> .env; fi
compose() { docker compose -f compose.prod.yaml "$@"; }
compose pull --quiet app
compose up -d --remove-orphans
compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || true
compose ps --format '{{.Service}}\t{{.Status}}\t{{.Image}}'
REMOTE
