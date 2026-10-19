#!/bin/sh
# Starts the server. With a backup bucket configured (`fly storage create` sets BUCKET_NAME),
# Litestream restores the database if the volume is empty, then runs the server and streams every
# change to the bucket. Without one, the server runs on its own.
set -e
APP="uvicorn --factory ailing.app:production_app --host 0.0.0.0 --port 8080"
if [ -n "$BUCKET_NAME" ]; then
  exec litestream replicate -config /etc/litestream.yml -restore-if-db-not-exists -exec "$APP"
fi
exec $APP
