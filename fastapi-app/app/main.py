from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config
from pydantic import BaseModel
import uuid
import os
import logging
from typing import Optional, Dict, Any, List

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
    allow_origins=["*"],  # Vulnerable to CORS attacks, use with caution
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
    
class VSCodeServerResponse(BaseModel):
    """Response model for VS Code Server instance details"""
    instance_id: str
    url: str
    access_token: str
    status: str

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

def create_configmap(instance_id: str, access_token: str) -> None:
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
            "EXTENSIONS_DIR": "/root/.vscode/extensions"
        }
    )
    
    try:
        core_v1_api.create_namespaced_config_map(
            namespace=NAMESPACE,
            body=configmap
        )
        logger.info(f"Created ConfigMap for instance {instance_id}")
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
    memory_request: str, 
    memory_limit: str,
    cpu_request: str,
    cpu_limit: str
) -> None:
    """Create a Deployment for the VS Code Server instance"""

    # Generate the base path for this instance
    instance_path = f"{INSTANCES_PATH_PREFIX}/{instance_id}"

    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(
            name=instance_id,
            labels={"app": BASE_NAME, "instance": instance_id}
        ),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(
                match_labels={"app": BASE_NAME, "instance": instance_id}
            ),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"app": BASE_NAME, "instance": instance_id}
                ),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name=BASE_NAME,
                            image=f"{BASE_NAME}:latest",
                            image_pull_policy="Never",
                            ports=[client.V1ContainerPort(container_port=8000)],
                            env_from=[
                                client.V1EnvFromSource(
                                    config_map_ref=client.V1ConfigMapEnvSource(
                                        name=f"{instance_id}-config"
                                    )
                                )
                            ],
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="vscode-data",
                                    mount_path="/root/.vscode"
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
                            command=["code"],
                            args=[
                                "serve-web",
                                "--accept-server-license-terms",
                                "--host", "0.0.0.0",
                                "--port", "8000",
                                "--connection-token", "$(TOKEN)",
                                "--server-base-path", instance_path,
                                "--cli-data-dir", "/root/.vscode/cli-data",
                                "--user-data-dir", "/root/.vscode/user-data",
                                "--server-data-dir", "/root/.vscode/server-data",
                                "--extensions-dir", "/root/.vscode/extensions"
                            ]
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="vscode-data",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=f"{instance_id}-data"
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
        logger.info(f"Created Deployment for instance {instance_id}")
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
        
        # Delete ConfigMap
        core_v1_api.delete_namespaced_config_map(
            name=f"{instance_id}-config",
            namespace=NAMESPACE
        )
        logger.info(f"Deleted ConfigMap for instance {instance_id}")
        
        # Delete PVC (data will be lost!)
        core_v1_api.delete_namespaced_persistent_volume_claim(
            name=f"{instance_id}-data",
            namespace=NAMESPACE
        )
        logger.info(f"Deleted PVC for instance {instance_id}")
        
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
            label_selector=f"app={BASE_NAME}"
        )
        
        for deployment in deployments.items:
            instance_id = deployment.metadata.name
            if instance_id.startswith(f"{user_id}-"):
                # Get the ConfigMap to retrieve the access token
                config_map = core_v1_api.read_namespaced_config_map(
                    name=f"{instance_id}-config",
                    namespace=NAMESPACE
                )
                
                access_token = config_map.data.get("TOKEN", "")
                path = generate_instance_path(instance_id)
                url = f"https://{BASE_DOMAIN}{path}?tkn={access_token}"
                status_str = get_instance_status(instance_id)
                
                instances.append(
                    VSCodeServerResponse(
                        instance_id=instance_id,
                        url=url,
                        access_token=access_token,
                        status=status_str
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
    """Create a new VS Code Server instance"""
    instance_id = generate_instance_id(request.user_id)
    access_token = generate_access_token()
    path = generate_instance_path(instance_id)
    
    # Create all necessary resources
    create_configmap(instance_id, access_token)
    create_pvc(instance_id, request.storage_size)
    create_deployment(
        instance_id, 
        request.memory_request, 
        request.memory_limit,
        request.cpu_request,
        request.cpu_limit
    )
    create_service(instance_id)
    create_ingress_for_instance(instance_id, INSTANCES_PATH_PREFIX)
    
    # Generate the access URL
    url = f"https://{BASE_DOMAIN}{path}?tkn={access_token}"
    
    return VSCodeServerResponse(
        instance_id=instance_id,
        url=url,
        access_token=access_token,
        status="Creating"
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
        path = generate_instance_path(instance_id)
        url = f"https://{BASE_DOMAIN}{path}?tkn={access_token}"
        status_str = get_instance_status(instance_id)
        
        return VSCodeServerResponse(
            instance_id=instance_id,
            url=url,
            access_token=access_token,
            status=status_str
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

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}