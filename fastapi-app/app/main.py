from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config
from pydantic import BaseModel, validator
import uuid
import os
import logging
import re
from typing import Optional, List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="VS Code Server Manager",
    description="API for on-demand deployment of VS Code Server instances in Kubernetes",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the Kubernetes client
try:
    # Try to load in-cluster config first
    config.load_incluster_config()
    logger.info("Loaded in-cluster Kubernetes configuration")
except config.ConfigException:
    # Fall back to kubeconfig if not in a cluster
    config.load_kube_config()
    logger.info("Loaded kubeconfig Kubernetes configuration")

# Create API clients
core_v1_api = client.CoreV1Api()
apps_v1_api = client.AppsV1Api()
networking_v1_api = client.NetworkingV1Api()

# Configuration
NAMESPACE = os.environ.get("KUBERNETES_NAMESPACE", "default")
BASE_NAME = "vscode-server"
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "vscode.local")
TLS_SECRET_NAME = "vscode-server-tls"
DEFAULT_STORAGE_SIZE = "2Gi"
DEFAULT_MEMORY_REQUEST = "256Mi"
DEFAULT_MEMORY_LIMIT = "1Gi"
DEFAULT_CPU_REQUEST = "100m"
DEFAULT_CPU_LIMIT = "500m"
DEFAULT_BASE_IMAGE = "ubuntu:24.04"

# Path configuration for path-based routing
API_PATH_PREFIX = "/api"
INSTANCES_PATH_PREFIX = "/instances"

# Data Models
class VSCodeServerRequest(BaseModel):
    """Request model for creating a VS Code Server instance"""
    user_id: str
    storage_size: Optional[str] = DEFAULT_STORAGE_SIZE
    memory_request: Optional[str] = DEFAULT_MEMORY_REQUEST
    memory_limit: Optional[str] = DEFAULT_MEMORY_LIMIT
    cpu_request: Optional[str] = DEFAULT_CPU_REQUEST
    cpu_limit: Optional[str] = DEFAULT_CPU_LIMIT
    base_image: Optional[str] = DEFAULT_BASE_IMAGE
    vscode_version: Optional[str] = "1.97.2"
    
    @validator('base_image')
    def validate_base_image(cls, v):
        # Basic validation to ensure the base image format is valid
        if not re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9_./:]*$', v):
            raise ValueError("Invalid base image format")
        return v

class VSCodeServerResponse(BaseModel):
    """Response model for VS Code Server instance details"""
    instance_id: str
    url: str
    access_token: str
    status: str
    base_image: str

class VSCodeServerList(BaseModel):
    """Response model for listing VS Code Server instances"""
    instances: List[VSCodeServerResponse]

class VSCodeServerStatus(BaseModel):
    """Response model for getting VS Code Server instance status"""
    instance_id: str
    status: str
    
# Helper Functions
def generate_instance_id(user_id: str) -> str:
    """Generate a unique instance ID based on user ID and random suffix"""
    random_suffix = uuid.uuid4().hex[:8]
    return f"{user_id}-{random_suffix}"

def generate_access_token() -> str:
    """Generate a UUID-like access token for VS Code Server"""
    return str(uuid.uuid4())

def generate_instance_path(instance_id: str) -> str:
    """Generate a path for the VS Code Server instance"""
    return f"{INSTANCES_PATH_PREFIX}/{instance_id}"

def ensure_user_workspace_pvc(user_id: str, storage_size: str) -> None:
    """Create a PersistentVolumeClaim for the user's workspace if it doesn't exist"""
    pvc_name = f"{user_id}-workspace"
    
    try:
        # Try to get the PVC first to check if it exists
        core_v1_api.read_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=NAMESPACE
        )
        logger.info(f"Using existing workspace PVC for user {user_id}")
        return
    except client.exceptions.ApiException as e:
        if e.status != 404:
            # If error is not "Not Found", raise it
            logger.error(f"Error checking workspace PVC: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to check workspace PVC: {str(e)}"
            )
    
    # Create the PVC if it doesn't exist
    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=pvc_name,
            labels={"app": BASE_NAME, "user": user_id, "type": "workspace"}
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=client.V1ResourceRequirements(
                requests={"storage": storage_size}
            )
        )
    )
    
    try:
        core_v1_api.create_namespaced_persistent_volume_claim(
            namespace=NAMESPACE,
            body=pvc
        )
        logger.info(f"Created workspace PVC for user {user_id}")
    except client.exceptions.ApiException as e:
        logger.error(f"Error creating workspace PVC: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create workspace PVC: {str(e)}"
        )

def create_configmap(instance_id: str, access_token: str, base_image: str, vscode_version: str) -> None:
    """Create a ConfigMap for the VS Code Server instance"""
    configmap = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=f"{instance_id}-config",
            labels={"app": BASE_NAME, "instance": instance_id}
        ),
        data={
            "PORT": "8000",
            "HOST": "0.0.0.0",
            "TOKEN": access_token,
            "CLI_DATA_DIR": "/root/.vscode/cli-data",
            "USER_DATA_DIR": "/root/.vscode/user-data",
            "SERVER_DATA_DIR": "/root/.vscode/server-data",
            "EXTENSIONS_DIR": "/root/.vscode/extensions",
            "BASE_IMAGE": base_image,
            "VSCODE_VERSION": vscode_version
        }
    )
    
    try:
        core_v1_api.create_namespaced_config_map(
            namespace=NAMESPACE,
            body=configmap
        )
        logger.info(f"Created ConfigMap for instance {instance_id} with base image {base_image}")
    except client.exceptions.ApiException as e:
        logger.error(f"Error creating ConfigMap: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create ConfigMap: {str(e)}"
        )

def create_pvc(instance_id: str, storage_size: str) -> None:
    """Create a PersistentVolumeClaim for the VS Code Server instance"""
    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=f"{instance_id}-data",
            labels={"app": BASE_NAME, "instance": instance_id}
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=client.V1ResourceRequirements(
                requests={"storage": storage_size}
            )
        )
    )
    
    try:
        core_v1_api.create_namespaced_persistent_volume_claim(
            namespace=NAMESPACE,
            body=pvc
        )
        logger.info(f"Created PVC for instance {instance_id}")
    except client.exceptions.ApiException as e:
        logger.error(f"Error creating PVC: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create PVC: {str(e)}"
        )

def create_deployment(
    instance_id: str,
    user_id: str,
    memory_request: str, 
    memory_limit: str,
    cpu_request: str,
    cpu_limit: str,
    base_image: str,
    vscode_version: str
) -> None:
    """Create a Deployment for the VS Code Server instance with custom base image"""

    # Generate the base path for this instance
    instance_path = f"{INSTANCES_PATH_PREFIX}/{instance_id}"
    
    # Get the workspace PVC name
    workspace_pvc_name = f"{user_id}-workspace"
    
    # Install script as command to install VS Code in the container at runtime
    install_script = f"""
    # Install dependencies
    if ! command -v wget >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
        if command -v apt-get >/dev/null 2>&1; then
            apt-get update && apt-get install -y curl wget ca-certificates git
        elif command -v yum >/dev/null 2>&1; then
            yum install -y curl wget ca-certificates git
        elif command -v apk >/dev/null 2>&1; then
            apk add --no-cache curl wget ca-certificates git
        fi
    fi
    
    # Determine architecture
    if [ "$(uname -m)" = "x86_64" ]; then
        export TARGET='cli-linux-x64'
    elif [ "$(uname -m)" = "aarch64" ] || [ "$(uname -m)" = "arm64" ]; then
        export TARGET='cli-linux-arm64'
    else
        echo "Unsupported architecture: $(uname -m)"
        exit 1
    fi
    
    # Install VS Code
    wget -qO- "https://update.code.visualstudio.com/{vscode_version}/${{TARGET}}/stable" | tar xvz -C /usr/bin/
    chmod +x /usr/bin/code
    
    # Run VS Code Server
    exec code serve-web --accept-server-license-terms --host 0.0.0.0 --port 8000 \
        --connection-token "$TOKEN" --server-base-path {instance_path} \
        --cli-data-dir "$CLI_DATA_DIR" --user-data-dir "$USER_DATA_DIR" \
        --server-data-dir "$SERVER_DATA_DIR" --extensions-dir "$EXTENSIONS_DIR"
    """
    
    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(
            name=instance_id,
            labels={"app": BASE_NAME, "instance": instance_id, "user": user_id}
        ),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(
                match_labels={"app": BASE_NAME, "instance": instance_id}
            ),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"app": BASE_NAME, "instance": instance_id, "user": user_id}
                ),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name=BASE_NAME,
                            image=base_image,
                            image_pull_policy="IfNotPresent",
                            ports=[client.V1ContainerPort(container_port=8000)],
                            env_from=[
                                client.V1EnvFromSource(
                                    config_map_ref=client.V1ConfigMapEnvSource(
                                        name=f"{instance_id}-config"
                                    )
                                )
                            ],
                            volume_mounts=[
                                # VS Code Server configuration (instance-specific)
                                client.V1VolumeMount(
                                    name="vscode-data",
                                    mount_path="/root/.vscode"
                                ),
                                # User workspace (shared across instances)
                                client.V1VolumeMount(
                                    name="workspace-data",
                                    mount_path="/workspaces"
                                )
                            ],
                            resources=client.V1ResourceRequirements(
                                requests={
                                    "memory": memory_request,
                                    "cpu": cpu_request
                                },
                                limits={
                                    "memory": memory_limit,
                                    "cpu": cpu_limit
                                }
                            ),
                            command=["/bin/sh", "-c"],
                            args=[install_script]
                        )
                    ],
                    volumes=[
                        # VS Code Server configuration (instance-specific)
                        client.V1Volume(
                            name="vscode-data",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=f"{instance_id}-data"
                            )
                        ),
                        # User workspace (shared across instances)
                        client.V1Volume(
                            name="workspace-data",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=workspace_pvc_name
                            )
                        )
                    ]
                )
            )
        )
    )
    
    try:
        apps_v1_api.create_namespaced_deployment(
            namespace=NAMESPACE,
            body=deployment
        )
        logger.info(f"Created Deployment for instance {instance_id} with base image {base_image}")
    except client.exceptions.ApiException as e:
        logger.error(f"Error creating Deployment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Deployment: {str(e)}"
        )

def create_service(instance_id: str) -> None:
    """Create a Service for the VS Code Server instance"""
    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=f"{instance_id}-service",
            labels={"app": BASE_NAME, "instance": instance_id}
        ),
        spec=client.V1ServiceSpec(
            selector={"app": BASE_NAME, "instance": instance_id},
            ports=[
                client.V1ServicePort(
                    port=8000,
                    target_port=8000
                )
            ],
            type="ClusterIP"
        )
    )
    
    try:
        core_v1_api.create_namespaced_service(
            namespace=NAMESPACE,
            body=service
        )
        logger.info(f"Created Service for instance {instance_id}")
    except client.exceptions.ApiException as e:
        logger.error(f"Error creating Service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Service: {str(e)}"
        )

def create_ingress_for_instance(instance_id: str, path_prefix: str) -> None:
    """Create an Ingress for the VS Code Server instance using path-based routing"""

    # Generate the full path for this instance
    instance_path = f"{path_prefix}/{instance_id}"

    ingress = client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=f"{instance_id}-ingress",
            labels={"app": BASE_NAME, "instance": instance_id},
            annotations={
                "nginx.ingress.kubernetes.io/backend-protocol": "HTTP",
                "nginx.ingress.kubernetes.io/proxy-read-timeout": "3600",
                "nginx.ingress.kubernetes.io/proxy-send-timeout": "3600",
                "nginx.ingress.kubernetes.io/proxy-body-size": "0",
                "nginx.ingress.kubernetes.io/proxy-buffer-size": "128k",
                "nginx.ingress.kubernetes.io/proxy-http-version": "1.1",
                "nginx.ingress.kubernetes.io/websocket-services": f"{instance_id}-service",
                "nginx.ingress.kubernetes.io/use-regex": "true"
            }
        ),
        spec=client.V1IngressSpec(
            tls=[
                client.V1IngressTLS(
                    hosts=[BASE_DOMAIN],
                    secret_name=TLS_SECRET_NAME
                )
            ],
            rules=[
                client.V1IngressRule(
                    host=BASE_DOMAIN,
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path=f"{instance_path}(/.*)?",
                                path_type="ImplementationSpecific",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=f"{instance_id}-service",
                                        port=client.V1ServiceBackendPort(
                                            number=8000
                                        )
                                    )
                                )
                            )
                        ]
                    )
                )
            ]
        )
    )
    
    try:
        networking_v1_api.create_namespaced_ingress(
            namespace=NAMESPACE,
            body=ingress
        )
        logger.info(f"Created Ingress for instance {instance_id}")
    except client.exceptions.ApiException as e:
        logger.error(f"Error creating Ingress: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Ingress: {str(e)}"
        )

def get_instance_status(instance_id: str) -> str:
    """Get the status of a VS Code Server instance"""
    try:
        deployment = apps_v1_api.read_namespaced_deployment_status(
            name=instance_id,
            namespace=NAMESPACE
        )
        
        available_replicas = deployment.status.available_replicas
        if available_replicas is not None and available_replicas > 0:
            return "Running"
        return "Pending"
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return "NotFound"
        logger.error(f"Error getting deployment status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get deployment status: {str(e)}"
        )

def delete_instance_resources(instance_id: str) -> None:
    """Delete all resources associated with a VS Code Server instance"""
    try:
        # Delete Ingress
        networking_v1_api.delete_namespaced_ingress(
            name=f"{instance_id}-ingress",
            namespace=NAMESPACE
        )
        logger.info(f"Deleted Ingress for instance {instance_id}")
        
        # Delete Service
        core_v1_api.delete_namespaced_service(
            name=f"{instance_id}-service",
            namespace=NAMESPACE
        )
        logger.info(f"Deleted Service for instance {instance_id}")
        
        # Delete Deployment
        apps_v1_api.delete_namespaced_deployment(
            name=instance_id,
            namespace=NAMESPACE
        )
        logger.info(f"Deleted Deployment for instance {instance_id}")
        
        # Delete ConfigMaps
        core_v1_api.delete_namespaced_config_map(
            name=f"{instance_id}-config",
            namespace=NAMESPACE
        )
        logger.info(f"Deleted ConfigMap for instance {instance_id}")
        
        # Delete instance-specific PVC (VS Code configuration)
        # Note: We DO NOT delete the user's workspace PVC here
        core_v1_api.delete_namespaced_persistent_volume_claim(
            name=f"{instance_id}-data",
            namespace=NAMESPACE
        )
        logger.info(f"Deleted instance PVC for instance {instance_id}")
        
    except client.exceptions.ApiException as e:
        if e.status == 404:
            # Resource not found, continue with deletion
            logger.warning(f"Resource not found during deletion: {e}")
        else:
            logger.error(f"Error deleting resources: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete resources: {str(e)}"
            )

def list_user_instances(user_id: str) -> List[VSCodeServerResponse]:
    """List all VS Code Server instances for a user"""
    instances = []
    
    try:
        # Get all deployments with the user's ID in the name
        deployments = apps_v1_api.list_namespaced_deployment(
            namespace=NAMESPACE,
            label_selector=f"app={BASE_NAME},user={user_id}"
        )
        
        for deployment in deployments.items:
            instance_id = deployment.metadata.name
            # Get the ConfigMap to retrieve the access token
            config_map = core_v1_api.read_namespaced_config_map(
                name=f"{instance_id}-config",
                namespace=NAMESPACE
            )
            
            access_token = config_map.data.get("TOKEN", "")
            base_image = config_map.data.get("BASE_IMAGE", DEFAULT_BASE_IMAGE)
            path = generate_instance_path(instance_id)
            url = f"https://{BASE_DOMAIN}{path}?tkn={access_token}"
            status_str = get_instance_status(instance_id)
            
            instances.append(
                VSCodeServerResponse(
                    instance_id=instance_id,
                    url=url,
                    access_token=access_token,
                    status=status_str,
                    base_image=base_image
                )
            )
    
    except client.exceptions.ApiException as e:
        logger.error(f"Error listing instances: {e}")
        # Continue with empty list in case of error
    
    return instances

# API Endpoints
@app.get("/", status_code=status.HTTP_200_OK)
def root():
    """Root endpoint to check if the API is running"""
    return {"status": "ok", "service": "VS Code Server Manager API"}

@app.post("/instances", response_model=VSCodeServerResponse, status_code=status.HTTP_201_CREATED)
def create_instance(request: VSCodeServerRequest):
    """Create a new VS Code Server instance with custom base image"""
    instance_id = generate_instance_id(request.user_id)
    access_token = generate_access_token()
    path = generate_instance_path(instance_id)
    
    # Ensure the user's workspace PVC exists
    ensure_user_workspace_pvc(request.user_id, request.storage_size)
    
    # Create all necessary resources
    create_configmap(instance_id, access_token, request.base_image, request.vscode_version)
    create_pvc(instance_id, request.storage_size)  # Instance-specific PVC for VS Code configuration
    create_deployment(
        instance_id,
        request.user_id,
        request.memory_request, 
        request.memory_limit,
        request.cpu_request,
        request.cpu_limit,
        request.base_image,
        request.vscode_version
    )
    create_service(instance_id)
    create_ingress_for_instance(instance_id, INSTANCES_PATH_PREFIX)
    
    # Generate the access URL
    url = f"https://{BASE_DOMAIN}{path}?tkn={access_token}"
    
    return VSCodeServerResponse(
        instance_id=instance_id,
        url=url,
        access_token=access_token,
        status="Creating",
        base_image=request.base_image
    )

@app.get("/instances/{instance_id}", response_model=VSCodeServerResponse)
def get_instance(instance_id: str):
    """Get details of a specific VS Code Server instance"""
    try:
        # Get the ConfigMap to retrieve the access token
        config_map = core_v1_api.read_namespaced_config_map(
            name=f"{instance_id}-config",
            namespace=NAMESPACE
        )
        
        access_token = config_map.data.get("TOKEN", "")
        base_image = config_map.data.get("BASE_IMAGE", DEFAULT_BASE_IMAGE)
        path = generate_instance_path(instance_id)
        url = f"https://{BASE_DOMAIN}{path}?tkn={access_token}"
        status_str = get_instance_status(instance_id)
        
        return VSCodeServerResponse(
            instance_id=instance_id,
            url=url,
            access_token=access_token,
            status=status_str,
            base_image=base_image
        )
    
    except client.exceptions.ApiException as e:
        if e.status == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Instance {instance_id} not found"
            )
        logger.error(f"Error getting instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get instance details: {str(e)}"
        )

@app.get("/instances", response_model=VSCodeServerList)
def list_instances(user_id: str):
    """List all VS Code Server instances for a user"""
    instances = list_user_instances(user_id)
    return VSCodeServerList(instances=instances)

@app.delete("/instances/{instance_id}", response_model=VSCodeServerStatus)
def delete_instance(instance_id: str):
    """Delete a VS Code Server instance"""
    # Check if the instance exists
    status_str = get_instance_status(instance_id)
    if status_str == "NotFound":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )
    
    # Delete all resources
    delete_instance_resources(instance_id)
    
    return VSCodeServerStatus(
        instance_id=instance_id,
        status="Deleted"
    )

@app.get("/status", response_model=VSCodeServerStatus)
def check_instance_status(instance_id: str):
    """Check the status of a VS Code Server instance"""
    status_str = get_instance_status(instance_id)
    if status_str == "NotFound":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )
    
    return VSCodeServerStatus(
        instance_id=instance_id,
        status=status_str
    )

@app.get("/workspaces/{user_id}", response_model=dict)
def get_user_workspace_status(user_id: str):
    """Get details about a user's workspace"""
    pvc_name = f"{user_id}-workspace"
    
    try:
        # Try to get the PVC
        pvc = core_v1_api.read_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=NAMESPACE
        )
        
        # Get all instances for this user
        instances = list_user_instances(user_id)
        
        return {
            "user_id": user_id,
            "workspace_exists": True,
            "storage_size": pvc.spec.resources.requests.get("storage", "Unknown"),
            "status": pvc.status.phase,
            "creation_time": pvc.metadata.creation_timestamp,
            "active_instances": len(instances),
            "instances": [{"instance_id": i.instance_id, "base_image": i.base_image} for i in instances]
        }
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return {
                "user_id": user_id,
                "workspace_exists": False,
                "active_instances": 0,
                "instances": []
            }
        else:
            logger.error(f"Error checking workspace: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to check workspace: {str(e)}"
            )

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}