#!/bin/sh
# Generate a self-signed certificate for local HTTPS only.
# Usage: generate-certs.sh [output-directory]
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT_DIR=${1:-"$SCRIPT_DIR/../nginx/certs"}
CERT_FILE="$OUT_DIR/fullchain.pem"
KEY_FILE="$OUT_DIR/privkey.pem"

mkdir -p "$OUT_DIR"

if [ -s "$CERT_FILE" ] && [ -s "$KEY_FILE" ]; then
    echo "Certificates already exist in $OUT_DIR"
    exit 0
fi

umask 077
openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/C=XX/O=Slotwise Development/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:nginx,IP:127.0.0.1"

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"
echo "Generated development certificate in $OUT_DIR"
