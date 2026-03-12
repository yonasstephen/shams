#!/bin/bash
# Generate SSL certificates for local dev (mkcert) or production (Let's Encrypt)
#
# Usage:
#   ./scripts/generate-ssl-cert.sh --dev
#   ./scripts/generate-ssl-cert.sh --prod <domain>

set -euo pipefail

CERT_DIR="./certs"

usage() {
  echo "Usage:"
  echo "  $0 --dev"
  echo "  $0 --prod <domain>"
  exit 1
}

dev_mode() {
  if ! command -v mkcert &>/dev/null; then
    echo "Error: mkcert is not installed."
    echo ""
    echo "Install it with:"
    echo "  macOS:   brew install mkcert"
    echo "  Linux:   https://github.com/FiloSottile/mkcert#linux"
    echo "  Windows: choco install mkcert"
    exit 1
  fi

  mkdir -p "$CERT_DIR"

  echo "Installing local CA (no-op if already done)..."
  mkcert -install

  echo "Generating mkcert certificate for localhost..."
  mkcert -key-file "$CERT_DIR/key.pem" -cert-file "$CERT_DIR/cert.pem" \
    localhost 127.0.0.1 ::1

  echo ""
  echo "Done. Certificates written to $CERT_DIR/"
  echo "  Certificate: $CERT_DIR/cert.pem"
  echo "  Private key: $CERT_DIR/key.pem"
  echo ""
  echo "Browsers will trust these certs automatically (via mkcert local CA)."
}

prod_mode() {
  local domain="$1"

  if ! command -v certbot &>/dev/null; then
    echo "Error: certbot is not installed."
    echo ""
    echo "Install it with:"
    echo "  Ubuntu/Debian: sudo apt install certbot"
    echo "  macOS:         brew install certbot"
    echo "  Other:         https://certbot.eff.org/instructions"
    exit 1
  fi

  echo "Requesting Let's Encrypt certificate for $domain..."
  echo "Note: port 80 must be free for the HTTP-01 challenge."
  echo ""

  certbot certonly --standalone -d "$domain"

  local live_dir="/etc/letsencrypt/live/$domain"

  mkdir -p "$CERT_DIR"
  cp "$live_dir/privkey.pem" "$CERT_DIR/key.pem"
  cp "$live_dir/fullchain.pem" "$CERT_DIR/cert.pem"
  chmod 644 "$CERT_DIR/key.pem" "$CERT_DIR/cert.pem"

  echo ""
  echo "Done. Certificates written to $CERT_DIR/"
  echo "  Certificate: $CERT_DIR/cert.pem"
  echo "  Private key: $CERT_DIR/key.pem"
  echo ""
  echo "Reminder: Let's Encrypt certs expire in 90 days."
  echo "Run 'certbot renew' (or re-run this script) before expiry."
}

# Parse arguments
if [[ $# -lt 1 ]]; then
  usage
fi

case "$1" in
  --dev)
    dev_mode
    ;;
  --prod)
    if [[ $# -lt 2 || -z "$2" ]]; then
      echo "Error: --prod requires a domain argument."
      usage
    fi
    prod_mode "$2"
    ;;
  *)
    usage
    ;;
esac
