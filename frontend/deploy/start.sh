set -eu
export LC_ALL=C
label='[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?'
test "${#FYAG_PUBLIC_HOST}" -le 253
test "$(printf '%s' "$FYAG_PUBLIC_HOST" | tr -d '\n\r')" = "$FYAG_PUBLIC_HOST"
printf '%s\n' "$FYAG_PUBLIC_HOST" | grep -Eq "^$label(\.$label)+$"
printf '%s\n' "$FYAG_HTTPS_PORT" | grep -Eq '^[1-9][0-9]{0,4}$'
test "$FYAG_HTTPS_PORT" -le 65535
FYAG_PUBLIC_ORIGIN="https://$FYAG_PUBLIC_HOST"
if [ "$FYAG_HTTPS_PORT" != 443 ]; then FYAG_PUBLIC_ORIGIN="$FYAG_PUBLIC_ORIGIN:$FYAG_HTTPS_PORT"; fi
export FYAG_PUBLIC_ORIGIN
export FYAG_WSS_ORIGIN="wss://${FYAG_PUBLIC_ORIGIN#https://}"
envsubst '${FYAG_PUBLIC_HOST} ${FYAG_PUBLIC_ORIGIN} ${FYAG_WSS_ORIGIN}' < /etc/fyag/site.conf.template > /tmp/site.conf
exec nginx -g 'daemon off;'
