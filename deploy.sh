#!/bin/bash

set -e

echo "=== VS Code Server On-Demand Management System Deployment ==="
echo "This script will build and deploy the VS Code Server on-demand management system to Minikube."

# Check if Minikube is running
if ! minikube status | grep -q "Running"; then
  echo "Starting Minikube..."
  minikube start --cpus 3 --memory 6144
  
  # Enable the ingress addon
  echo "Enabling the Ingress addon..."
  minikube addons enable ingress
else
  echo "Minikube is already running."
fi

# Generate TLS certificates
echo "Generating TLS certificates..."
chmod +x generate-tls-cert.sh
./generate-tls-cert.sh

# Add an entry to your hosts file
MINIKUBE_IP=$(minikube ip)
echo "Adding entries to hosts file..."
echo "You may be prompted for your password."

# Check if entries already exist
if grep -q "vscode.local" /etc/hosts; then
  echo "Host entry already exists."
else
  echo "$MINIKUBE_IP vscode.local" | sudo tee -a /etc/hosts
fi

# Build FastAPI app image
echo "Building FastAPI app image..."
cd fastapi-app
docker build -t vscode-manager:latest -f Dockerfile .
cd ..

# Load images into Minikube
echo "Loading images into Minikube..."
minikube image load vscode-manager:latest

# Deploy FastAPI application
echo "Deploying FastAPI application..."
kubectl apply -f fastapi-app-k8s.yaml

# Wait for deployment to be ready
echo "Waiting for deployment to be ready..."
kubectl rollout status deployment/vscode-manager

# Display access information
echo "=== Deployment Complete ==="
echo "FastAPI Management API is available at: https://vscode.local/api"
echo "VS Code Server instances will be available at: https://vscode.local/instances/<instance-id>"

echo "You can test the API using the client.py script:"
echo "python client.py create --user-id user1 --base-image mcr.microsoft.com/devcontainers/python:1-3.12"
echo "Or with curl:"
echo "curl -k https://vscode.local/api/instances -H 'Content-Type: application/json' -d '{\"user_id\":\"user1\", \"base_image\":\"mcr.microsoft.com/devcontainers/python:1-3.12\"}'"