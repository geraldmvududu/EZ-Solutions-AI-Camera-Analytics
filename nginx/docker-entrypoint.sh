#!/bin/sh
set -e

CERT_DIR="/etc/nginx/certs"
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/server.crt" ] || [ ! -f "$CERT_DIR/server.key" ]; then
    echo "No TLS certificate found — generating a self-signed one for lab use."
    echo "For production, replace $CERT_DIR/server.crt and server.key with a real certificate."
    openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
        -keyout "$CERT_DIR/server.key" \
        -out "$CERT_DIR/server.crt" \
        -subj "/C=US/ST=Lab/L=Lab/O=EZ Solutions/CN=ez-camera-analytics.local"
fi
