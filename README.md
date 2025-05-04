# VS Code Server On-Demand Management System with Customizable Base Images

This system provides on-demand deployment and management of VS Code Server instances in a Minikube Kubernetes cluster. It consists of a FastAPI application that manages the lifecycle of VS Code Server pods, allowing them to be created and deleted on request, with persistent workspaces and customizable base images from any public registry.

## Key Features

- **Customizable Development Environments**: Choose any base image from public registries like Docker Hub or Microsoft Container Registry
- **Devcontainer Support**: Use Microsoft's devcontainer images for language-specific development environments
- **On-Demand Creation**: Create VS Code Server instances when needed
- **Persistent Workspaces**: User workspaces persist across all instances
- **Path-Based Routing**: Access VS Code Server instances via unique URLs

## System Components

1. **FastAPI Management API**
   - REST API for deploying and deleting VS Code Server instances
   - Runs inside the Kubernetes cluster
   - Exposed via path-based routing at `https://vscode.local/api`

2. **VS Code Server Pods**
   - Created on demand with user-specified base images
   - VS Code Server installed at runtime
   - Deleted when no longer needed
   - Each instance has its own URL: `https://vscode.local/instances/<instance-id>`

3. **Persistent Workspaces**
   - User workspaces persist across all instances
   - Each user has a dedicated workspace volume
   - All instances for a user share the same workspace data

## Prerequisites

- Minikube installed and running
- kubectl configured to work with your Minikube cluster
- Docker installed for building images
- OpenSSL for generating self-signed certificates

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/apaluca/vscode-server-on-demand.git
cd vscode-server-on-demand
```

### 2. Deploy the System

Run the deployment script to build and deploy the entire system:

```bash
chmod +x deploy.sh
./deploy.sh
```

This script will:
- Start Minikube (if not already running)
- Enable the NGINX Ingress controller
- Generate TLS certificates
- Add the required host entry to your `/etc/hosts` file
- Build and load the Docker images
- Deploy the FastAPI application
- Configure access to the system

### 3. Verify the Deployment

Check that the FastAPI application is running:

```bash
kubectl get pods
```

You should see the `vscode-manager` pod running.

## Using the System

You can interact with the system in two ways:

### 1. Using the Client Script

The included `client.py` script provides a command-line interface to the API:

```bash
# Create a new VS Code Server instance with default Ubuntu base image
python client.py create --user-id user1

# Create a new VS Code Server instance with Python devcontainer
python client.py create --user-id user1 --base-image mcr.microsoft.com/devcontainers/python:1-3.12

# Create a new VS Code Server instance with Node.js devcontainer
python client.py create --user-id user1 --base-image mcr.microsoft.com/devcontainers/javascript-node:1-20

# Create a new VS Code Server instance with Go devcontainer
python client.py create --user-id user1 --base-image mcr.microsoft.com/devcontainers/go:1-1.21

# List all instances for a user
python client.py list --user-id user1

# Get details of a specific instance
python client.py get --instance-id user1-abc123

# Delete an instance
python client.py delete --instance-id user1-abc123

# Check the status of an instance
python client.py status --instance-id user1-abc123
```

### 2. Using Direct API Calls

You can also interact with the API directly using curl or any HTTP client:

```bash
# Create a new instance with a Python devcontainer base image
curl -k https://vscode.local/api/instances -H "Content-Type: application/json" -d '{"user_id":"user1", "base_image":"mcr.microsoft.com/devcontainers/python:1-3.12"}'

# List instances for a user
curl -k "https://vscode.local/api/instances?user_id=user1"

# Get instance details
curl -k https://vscode.local/api/instances/user1-abc123

# Delete an instance
curl -k -X DELETE https://vscode.local/api/instances/user1-abc123

# Check instance status
curl -k "https://vscode.local/api/status?instance_id=user1-abc123"

# Check user workspace status
curl -k "https://vscode.local/api/workspaces/user1"
```

## Accessing VS Code Server

Once an instance is created, you can access it at the URL provided in the API response:

```
https://vscode.local/instances/<instance-id>?tkn=<access_token>
```

Since the system uses self-signed certificates, you'll need to accept the security warning in your browser.

## Available Base Images

You can use any public Docker image as your base image. Here are some recommended options:

### Microsoft Devcontainer Images

- **Python**: `mcr.microsoft.com/devcontainers/python:1-3.12`
- **Node.js**: `mcr.microsoft.com/devcontainers/javascript-node:1-20`
- **Go**: `mcr.microsoft.com/devcontainers/go:1-1.21`
- **Java**: `mcr.microsoft.com/devcontainers/java:1-17`
- **PHP**: `mcr.microsoft.com/devcontainers/php:1-8.2`
- **Ruby**: `mcr.microsoft.com/devcontainers/ruby:1-3.2`
- **Rust**: `mcr.microsoft.com/devcontainers/rust:1-bullseye`
- **.NET**: `mcr.microsoft.com/devcontainers/dotnet:1-8.0`

### Other Base Images

- **Ubuntu**: `ubuntu:24.04` (default if not specified)
- **Debian**: `debian:bookworm-slim`
- **Alpine**: `alpine:3.19`
- **CentOS**: `centos:7`
- **Amazon Linux**: `amazonlinux:2023`

## How It Works

This system uses a unique approach to provide VS Code Server instances with customizable development environments:

1. **Base Image Selection**: Users specify their preferred base image from any public registry (e.g., a Python devcontainer)
2. **Runtime Installation**: When the container starts, a script detects the package manager and installs VS Code Server
3. **Persistent Storage**: User files are stored in a persistent volume that remains even when instances are deleted
4. **Path-Based Routing**: Each instance is accessible via a unique URL with a secure access token

## Workspace Persistence

### How It Works

1. **User-Based Workspaces**: Each user gets a dedicated persistent volume for their workspace data
2. **Shared Across Instances**: All VS Code Server instances for a user share the same workspace volume
3. **Instance-Specific Configuration**: Each instance still has its own configuration volume for VS Code settings
4. **Persistent Files**: Files created in `/workspaces` directory persist across all instances and instance restarts

### Directory Structure

- `/workspaces`: User's persistent workspace files (shared across all instances)
- `/root/.vscode`: VS Code Server configuration (unique to each instance)
  - `cli-data`: CLI-related data
  - `user-data`: User settings and preferences
  - `server-data`: Server-specific data
  - `extensions`: Installed extensions

## System Architecture

The system architecture follows this pattern:

```
User Request → FastAPI App → Kubernetes API → VS Code Server Pod Created/Deleted
```

When a user requests a new VS Code Server instance:
1. The FastAPI application receives the request with the specified base image
2. It ensures the user's workspace volume exists (or creates it)
3. It creates the necessary Kubernetes resources:
   - ConfigMap for configuration
   - PersistentVolumeClaim for instance configuration
   - PersistentVolumeClaim for user workspace (shared across instances)
   - Deployment using the specified base image with a startup script that installs VS Code
   - Service to expose the pod
   - Ingress for path-based routing
4. The user receives the URL and access token for the instance

When a user deletes an instance, the instance-specific resources are deleted but the user's workspace data remains intact.

## Configuration Options

When creating a new VS Code Server instance, you can customize:

- Base image
- VS Code Server version
- Storage size
- Memory requests and limits
- CPU requests and limits

Example:

```bash
python client.py create --user-id user1 --base-image mcr.microsoft.com/devcontainers/python:1-3.12 --vscode-version 1.97.2 --storage 5Gi --memory-limit 2Gi --cpu-limit 1000m
```

## Security Considerations

- Each VS Code Server instance requires an access token
- All traffic is encrypted using HTTPS
- Each user's data is isolated in a separate PersistentVolumeClaim
- The FastAPI application runs with minimal permissions

## Troubleshooting

### Checking Logs

FastAPI application logs:
```bash
kubectl logs -l app=vscode-manager
```

VS Code Server instance logs:
```bash
kubectl logs -l app=vscode-server,instance=<instance-id>
```

### Common Issues

1. **TLS Certificate Issues**:
   Re-run the certificate generation script and recreate the instances.

2. **Pod Not Starting**:
   Check the pod logs for errors with package installation or VS Code download.

3. **API Not Accessible**:
   Verify that the Ingress controller is running and the host entry is correctly set in `/etc/hosts`.

4. **Base Image Compatibility**:
   Not all base images will work perfectly. Check the logs for specific errors related to the image.

5. **Workspace Persistence Issues**:
   Check if the workspace PVC exists and is properly mounted:
   ```bash
   kubectl get pvc -l type=workspace
   kubectl exec -it <pod-name> -- ls -la /workspaces
   ```

## Cleanup

To delete the entire system:

```bash
kubectl delete -f fastapi-app-k8s.yaml
kubectl delete secret vscode-server-tls
# Delete any remaining VS Code Server instances
kubectl delete deployment -l app=vscode-server
kubectl delete service -l app=vscode-server
kubectl delete ingress -l app=vscode-server
kubectl delete configmap -l app=vscode-server
kubectl delete pvc -l app=vscode-server
# Delete user workspace PVCs
kubectl delete pvc -l type=workspace
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.