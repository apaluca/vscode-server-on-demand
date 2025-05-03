# VS Code Server On-Demand Management System

This system provides on-demand deployment and management of VS Code Server instances in a Minikube Kubernetes cluster. It consists of a FastAPI application that manages the lifecycle of VS Code Server pods, allowing them to be created and deleted on request.

## System Components

1. **FastAPI Management API**
   - REST API for deploying and deleting VS Code Server instances
   - Runs inside the Kubernetes cluster
   - Exposed via path-based routing at `https://vscode.local/api`

2. **VS Code Server Pods**
   - Created on demand
   - Deleted when no longer needed
   - Each instance has its own URL: `https://vscode.local/instances/<instance-id>`

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
# Create a new VS Code Server instance
python client.py create --user-id user1

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
# Create a new instance
curl -k https://vscode.local/api/instances -H "Content-Type: application/json" -d '{"user_id":"user1"}'

# List instances for a user
curl -k "https://vscode.local/api/instances?user_id=user1"

# Get instance details
curl -k https://vscode.local/api/instances/user1-abc123

# Delete an instance
curl -k -X DELETE https://vscode.local/api/instances/user1-abc123

# Check instance status
curl -k "https://vscode.local/api/status?instance_id=user1-abc123"
```

## Accessing VS Code Server

Once an instance is created, you can access it at the URL provided in the API response:

```
https://vscode.local/instances/<instance-id>?tkn=<access_token>
```

Since the system uses self-signed certificates, you'll need to accept the security warning in your browser.

## System Architecture

The system architecture follows this pattern:

```
User Request → FastAPI App → Kubernetes API → VS Code Server Pod Created/Deleted
```

When a user requests a new VS Code Server instance:
1. The FastAPI application receives the request
2. It creates the necessary Kubernetes resources:
   - ConfigMap for configuration
   - PersistentVolumeClaim for data persistence
   - Deployment for the VS Code Server pod
   - Service to expose the pod
   - Ingress for path-based routing
3. The user receives the URL and access token for the instance

When a user deletes an instance, all associated resources are deleted.

## Path-Based Routing

This system uses path-based routing instead of subdomain-based routing:

- API endpoints are accessible at `https://vscode.local/api/...`
- VS Code Server instances are accessible at `https://vscode.local/instances/<instance-id>`

The NGINX Ingress controller handles the routing to the appropriate backend services.

## Configuration Options

When creating a new VS Code Server instance, you can customize:

- Storage size
- Memory requests and limits
- CPU requests and limits

Example:

```bash
python client.py create --user-id user1 --storage 5Gi --memory-limit 2Gi --cpu-limit 1000m
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
   Check the pod logs for errors and ensure Minikube has sufficient resources.

3. **API Not Accessible**:
   Verify that the Ingress controller is running and the host entry is correctly set in `/etc/hosts`.

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
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.