set -eu
export FYAG_MONGO_PASSWORD="$(cat /run/secrets/mongo_app_password)"
if [ "${1:-}" = health ]; then
    exec mongosh --quiet /opt/fyag/database/health_mongodb.js
fi
exec /usr/local/bin/docker-entrypoint.sh "$@"
