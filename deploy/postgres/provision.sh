#!/bin/bash
set -euo pipefail
export LC_ALL=C
unset PGHOST PGHOSTADDR PGPORT PGSERVICE PGOPTIONS
export PGPASSWORD="$(cat /run/secrets/postgres_password)"
declare -A seen
for role in migration web security alerts documents attachments chat mail; do
    value=$(cat "/run/secrets/postgres_${role}_password")
    if [[ ! $value =~ ^[0-9a-f]{64}$ || $value == "$PGPASSWORD" || ${seen[$value]+yes} ]]; then
        echo "Secreto SQL inválido o no independiente: $role" >&2
        exit 1
    fi
    seen[$value]=1
    export "fyag_${role}=$value"
done
exec psql -X --quiet --no-password --host=/var/run/postgresql --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" --set=ON_ERROR_STOP=1 --file=/opt/fyag/provision.sql
