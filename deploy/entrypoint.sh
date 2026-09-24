#!/bin/sh
# Start the app. With LITESTREAM_REPLICA_URL set, restore the database from Cloud Storage
# first and keep replicating every change back while the app runs.
set -e
APP="uvicorn best_deal.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips=*"

if [ -n "$LITESTREAM_REPLICA_URL" ]; then
  litestream restore -config /etc/litestream.yml -if-db-not-exists -if-replica-exists "$BEST_DEAL_DB"
  exec litestream replicate -config /etc/litestream.yml -exec "$APP"
fi
exec $APP
