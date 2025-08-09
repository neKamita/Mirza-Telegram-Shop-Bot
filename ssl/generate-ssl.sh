#!/bin/bash

# SSL Certificate Generation Script for Development
# Usage: ./generate-ssl.sh [domain]

DOMAIN=${1:-localhost}
CERT_DIR="./ssl"

echo "Generating SSL certificates for domain: $DOMAIN"
echo "Certificate directory: $CERT_DIR"

# Create certificate directory if it doesn't exist
mkdir -p "$CERT_DIR"

# Generate private key
openssl genrsa -out "$CERT_DIR/key.pem" 2048

# Generate certificate signing request
openssl req -new -key "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.csr" -subj "/C=US/ST=State/L=City/O=Organization/CN=$DOMAIN"

# Generate self-signed certificate
openssl x509 -req -days 365 -in "$CERT_DIR/cert.csr" -signkey "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem"

# Clean up CSR file
rm "$CERT_DIR/cert.csr"

# Set appropriate permissions
chmod 600 "$CERT_DIR/key.pem"
chmod 644 "$CERT_DIR/cert.pem"

echo "SSL certificates generated successfully!"
echo "Certificate: $CERT_DIR/cert.pem"
echo "Private key: $CERT_DIR/key.pem"
echo ""
echo "For production use, replace these with certificates from a trusted CA"
