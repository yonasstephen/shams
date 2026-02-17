#!/bin/bash
# Production startup script for Shams web app

set -e

echo "🚀 Starting Shams Web App (Production Mode)"
echo "=============================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ No .env file found."
    echo "   Copy env.example to .env and configure your settings."
    exit 1
fi

# Check required env vars
source .env
if [ -z "$SESSION_SECRET" ] || [ "$SESSION_SECRET" = "dev-secret-key" ]; then
    echo "❌ SESSION_SECRET must be set to a secure value for production."
    echo "   Generate one with: openssl rand -base64 32"
    exit 1
fi

if [ -z "$BACKEND_URL" ]; then
    echo "❌ BACKEND_URL must be set (e.g., https://localhost:8000)"
    exit 1
fi

if [ -z "$FRONTEND_URL" ]; then
    echo "❌ FRONTEND_URL must be set (e.g., http://localhost)"
    exit 1
fi

# Check if Docker is running (via Colima or Docker Desktop)
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running or not accessible."
    echo "   Try: colima start"
    echo "   Or start Docker Desktop"
    exit 1
fi

# Check if SSL certs exist
if [ ! -f certs/key.pem ] || [ ! -f certs/cert.pem ]; then
    echo "❌ SSL certificates not found in certs/"
    echo "   Run: ./scripts/generate-ssl-cert.sh"
    exit 1
fi

# Set proxy for Docker builds and runtime (Colima VM accessible address)
# Convert localhost proxy to Docker-accessible IP since containers can't reach host's localhost
PROXY_PORT="${HTTP_PROXY##*:}"  # Extract port from existing proxy if set
PROXY_PORT="${PROXY_PORT:-10054}"  # Default to 10054
export HTTP_PROXY="http://192.168.5.2:${PROXY_PORT}"
export HTTPS_PROXY="http://192.168.5.2:${PROXY_PORT}"

echo ""
echo "📦 Starting services with Docker Compose (Production)..."
echo "   Using proxy: $HTTP_PROXY"
docker-compose -f docker-compose.prod.yml up "$@"

echo ""
echo "✅ Shams Web App stopped."
