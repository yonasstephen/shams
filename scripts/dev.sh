#!/bin/bash
# Development startup script for Shams web app

set -e

echo "🚀 Starting Shams Web App (Development Mode)"
echo "=============================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from env.example..."
    cp env.example .env
    echo "✅ Created .env file. Please edit it with your Yahoo credentials."
    echo ""
    read -p "Press Enter to continue after editing .env, or Ctrl+C to exit..."
fi

# Check if Docker is running (via Colima or Docker Desktop)
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running or not accessible."
    echo "   Try: colima start"
    echo "   Or start Docker Desktop"
    exit 1
fi

# Handle proxy settings for Docker
# Only set proxy if one is configured AND accessible
if [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ]; then
    # Extract port from existing proxy if set
    PROXY_PORT="${HTTP_PROXY##*:}"
    PROXY_PORT="${PROXY_PORT:-10054}"
    
    # Check if proxy is accessible (try to connect to it)
    if nc -z localhost "$PROXY_PORT" 2>/dev/null; then
        # Convert localhost to Docker-accessible IP (for Colima)
        export HTTP_PROXY="http://192.168.5.2:${PROXY_PORT}"
        export HTTPS_PROXY="http://192.168.5.2:${PROXY_PORT}"
        echo ""
        echo "📦 Starting services with Docker Compose..."
        echo "   Using proxy: $HTTP_PROXY"
    else
        echo ""
        echo "⚠️  Proxy configured but not accessible at localhost:$PROXY_PORT"
        echo "   Starting without proxy (direct internet access)"
        unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
    fi
else
    echo ""
    echo "📦 Starting services with Docker Compose..."
    echo "   No proxy configured (direct internet access)"
fi
docker-compose up

echo ""
echo "✅ Shams Web App stopped."
