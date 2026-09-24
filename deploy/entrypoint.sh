#!/bin/sh
# Start the app. With LITESTREAM_REPLICA_URL set, restore the database from Cloud Storage
# first and keep replicating every change back while the app runs.
set -e

# Hosts that mount a volume at /data (Railway, Render, Docker volumes) usually hand it over
# owned by root. Start as root, give the volume to the app user, then drop privileges.
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$(dirname "$BEST_DEAL_DB")"
  chown -R app:app "$(dirname "$BEST_DEAL_DB")"
  exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

APP="uvicorn best_deal.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips=*"

if [ -n "$LITESTREAM_REPLICA_URL" ]; then
  litestream restore -config /etc/litestream.yml -if-db-not-exists -if-replica-exists "$BEST_DEAL_DB"
  exec litestream replicate -config /etc/litestream.yml -exec "$APP"
fi
exec $APP
