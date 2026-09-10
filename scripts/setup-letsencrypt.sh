#!/bin/bash
# Replaces the lab self-signed certificate with a real Let's Encrypt certificate.
#
# Prerequisites (only you can set these up — this script can't provision them):
#   - A real domain name (or subdomain) you own
#   - Its DNS A record pointing at this Ubuntu Server's public IP
#   - Port 80 reachable from the internet (for the HTTP-01 challenge)
#
# Usage:
#   sudo ./scripts/setup-letsencrypt.sh yourdomain.example.com you@example.com
set -euo pipefail

DOMAIN="${1:?Usage: sudo ./scripts/setup-letsencrypt.sh <domain> <email>}"
EMAIL="${2:?Usage: sudo ./scripts/setup-letsencrypt.sh <domain> <email>}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
CERT_DIR="data/nginx-certs"

if ! command -v certbot >/dev/null 2>&1; then
    echo "Installing certbot..."
    sudo apt update
    sudo apt install -y certbot
fi

echo "Stopping nginx container to free port 80 for the HTTP-01 challenge..."
docker compose stop nginx

echo "Requesting certificate for $DOMAIN..."
sudo certbot certonly --standalone \
    --non-interactive --agree-tos \
    -m "$EMAIL" \
    -d "$DOMAIN"

echo "Copying certificate into $CERT_DIR..."
sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$CERT_DIR/server.crt"
sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$CERT_DIR/server.key"
sudo chmod 644 "$CERT_DIR/server.crt"
sudo chmod 600 "$CERT_DIR/server.key"

echo "Restarting nginx with the real certificate..."
docker compose up -d nginx

RENEW_HOOK="/etc/letsencrypt/renewal-hooks/deploy/ez-camera-analytics.sh"
echo "Installing a renewal hook at $RENEW_HOOK so future renewals redeploy automatically..."
sudo mkdir -p "$(dirname "$RENEW_HOOK")"
sudo tee "$RENEW_HOOK" > /dev/null <<EOF
#!/bin/bash
cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$PROJECT_ROOT/$CERT_DIR/server.crt"
cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$PROJECT_ROOT/$CERT_DIR/server.key"
cd "$PROJECT_ROOT" && docker compose restart nginx
EOF
sudo chmod +x "$RENEW_HOOK"

echo "Done. Certbot's own systemd timer (certbot.timer) already checks for renewal"
echo "twice daily; the hook above will redeploy the cert here whenever it renews."
echo "Verify with: sudo certbot renew --dry-run"
