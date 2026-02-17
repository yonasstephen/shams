#!/bin/bash
# Generate self-signed SSL certificate for local development

CERT_DIR="./certs"
mkdir -p "$CERT_DIR"

echo "Generating self-signed SSL certificate for localhost..."

openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout "$CERT_DIR/key.pem" \
  -out "$CERT_DIR/cert.pem" \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "SSL certificate generated in $CERT_DIR/"
echo "  - Certificate: $CERT_DIR/cert.pem"
echo "  - Private Key: $CERT_DIR/key.pem"

