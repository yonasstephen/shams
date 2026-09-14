#!/bin/sh
# Docker entrypoint script for frontend
# Replaces runtime configuration placeholders with actual environment values
# and picks the nginx listener based on whether TLS certificates are mounted.

set -e

HTML_DIR="/usr/share/nginx/html"
CONFIG_FILE="$HTML_DIR/config.js"
CERT_DIR="/etc/nginx/certs"
LISTEN_INC="/etc/nginx/listen.inc"

# The API is proxied at /api on this same origin (see nginx.conf), so the
# default is a relative URL. That is what keeps the session cookie same-site
# and avoids baking a hostname into the image. Set VITE_API_URL to an absolute
# URL only when the API really lives on another origin.
API_URL="${VITE_API_URL:-/}"

echo "=== Debug: Initial permissions ==="
ls -la "$HTML_DIR/"

echo "Setting API_URL to: $API_URL"

# Completely recreate config.js with the correct API URL
# Using rm + cat heredoc to avoid any file modification issues
rm -f "$CONFIG_FILE"
cat > "$CONFIG_FILE" << EOF
window.APP_CONFIG = { API_URL: '$API_URL' };
EOF

# Serve HTTPS when certificates are mounted. The SPA must use the same scheme
# as the proxied API for the pair to be same-site, and Yahoo's OAuth
# redirect_uri has to be HTTPS, so TLS here is the normal case; the HTTP
# fallback exists so a certless run still starts.
if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
  echo "TLS certificates found in $CERT_DIR; listening on 443 (HTTPS)."
  cat > "$LISTEN_INC" << EOF
listen 443 ssl;
ssl_certificate     $CERT_DIR/cert.pem;
ssl_certificate_key $CERT_DIR/key.pem;
ssl_protocols       TLSv1.2 TLSv1.3;
ssl_session_cache   shared:SSL:10m;
EOF
else
  echo "No TLS certificates in $CERT_DIR; listening on 80 (HTTP)."
  echo "Yahoo OAuth needs HTTPS, so mount ./certs to :$CERT_DIR for login to work."
  echo "listen 80;" > "$LISTEN_INC"
fi

# Ensure all files are world-readable (critical for UGOS/NAS with user namespace remapping)
chmod 755 "$HTML_DIR"
chmod 755 "$HTML_DIR/assets" 2>/dev/null || true
find "$HTML_DIR" -type f -exec chmod 644 {} \;

echo "=== Debug: Final permissions ==="
ls -la "$HTML_DIR/"

echo "Final config.js contents:"
cat "$CONFIG_FILE"

# Start nginx
echo "Starting nginx..."
exec nginx -g "daemon off;"
