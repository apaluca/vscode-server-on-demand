#!/bin/bash

# Set variables
CERT_NAME="vscode-tls"
DOMAIN="vscode.local"

# Create directory for certificates
mkdir -p ./certs

# Generate a private key and self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ./certs/$CERT_NAME.key \
  -out ./certs/$CERT_NAME.crt \
  -subj "/CN=$DOMAIN/O=VSCode Server/C=US" \
  -addext "subjectAltName = DNS:$DOMAIN"

# Create Kubernetes secret from the generated certificates
kubectl create secret tls vscode-server-tls \
  --key=./certs/$CERT_NAME.key \
  --cert=./certs/$CERT_NAME.crt \
  --dry-run=client -o yaml | kubectl apply -f -

echo "TLS certificate created and stored in Kubernetes secret 'vscode-server-tls'"