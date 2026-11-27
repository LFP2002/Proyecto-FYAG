#!/bin/sh
# CA y certificado de un solo laboratorio. Nunca reutilizarlos en producción.
set -eu
umask 077
cd "${1:?directorio de certificados}"
host=${2:?nombre DNS del servicio Redis de QA}
case "$host" in *[!a-zA-Z0-9.-]*) exit 2;; esac
test ! -e ca.key
test ! -e server.key
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 2 \
  -subj /CN=FYAG-Redis-QA-CA -addext basicConstraints=critical,CA:TRUE \
  -addext keyUsage=critical,keyCertSign,cRLSign
openssl req -new -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=$host"
cat > server.ext <<EOF
subjectAltName=DNS:$host
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
authorityKeyIdentifier=keyid
subjectKeyIdentifier=hash
EOF
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 2 -extfile server.ext
openssl verify -x509_strict -purpose sslserver -verify_hostname "$host" -CAfile ca.crt server.crt
