#!/bin/sh
# Docker entrypoint script for frontend
# Replaces runtime configuration placeholders with actual environment values

set -e

HTML_DIR="/usr/share/nginx/html"
CONFIG_FILE="$HTML_DIR/config.js"

echo "=== Debug: Initial permissions ==="
ls -la "$HTML_DIR/"

# Check VITE_API_URL is set
if [ -z "$VITE_API_URL" ]; then
  echo "ERROR: VITE_API_URL environment variable is not set."
  echo "Please set VITE_API_URL to your backend API URL (e.g., https://api.yourdomain.com)"
  exit 1
fi

echo "Setting API_URL to: $VITE_API_URL"

# Completely recreate config.js with the correct API URL
# Using rm + cat heredoc to avoid any file modification issues
rm -f "$CONFIG_FILE"
cat > "$CONFIG_FILE" << EOF
window.APP_CONFIG = { API_URL: '$VITE_API_URL' };
EOF

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

