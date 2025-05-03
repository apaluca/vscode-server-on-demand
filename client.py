#!/usr/bin/env python3
"""
VS Code Server Manager Client Script

This script provides command-line interaction with the VS Code Server Manager API.
"""

import argparse
import json
import os
import sys
import requests
from typing import Dict, Any, Optional
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Default API endpoint
DEFAULT_API_URL = "https://api.vscode.local"

def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description="VS Code Server Manager Client")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create instance command
    create_parser = subparsers.add_parser("create", help="Create a new VS Code Server instance")
    create_parser.add_argument("--user-id", required=True, help="User ID")
    create_parser.add_argument("--storage", default="2Gi", help="Storage size (default: 2Gi)")
    create_parser.add_argument("--memory-request", default="256Mi", help="Memory request (default: 256Mi)")
    create_parser.add_argument("--memory-limit", default="1Gi", help="Memory limit (default: 1Gi)")
    create_parser.add_argument("--cpu-request", default="100m", help="CPU request (default: 100m)")
    create_parser.add_argument("--cpu-limit", default="500m", help="CPU limit (default: 500m)")
    
    # List instances command
    list_parser = subparsers.add_parser("list", help="List VS Code Server instances")
    list_parser.add_argument("--user-id", required=True, help="User ID")
    
    # Get instance command
    get_parser = subparsers.add_parser("get", help="Get details of a VS Code Server instance")
    get_parser.add_argument("--instance-id", required=True, help="Instance ID")
    
    # Delete instance command
    delete_parser = subparsers.add_parser("delete", help="Delete a VS Code Server instance")
    delete_parser.add_argument("--instance-id", required=True, help="Instance ID")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check the status of a VS Code Server instance")
    status_parser.add_argument("--instance-id", required=True, help="Instance ID")
    
    # Global options
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help=f"API URL (default: {DEFAULT_API_URL})")
    
    return parser.parse_args()

def make_api_request(method: str, url: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make an API request to the VS Code Server Manager"""
    try:
        if method.upper() == "GET":
            response = requests.get(url, params=data, verify=False)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, verify=False)
        elif method.upper() == "DELETE":
            response = requests.delete(url, verify=False)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"Error making API request: {e}")
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"API Error: {error_data.get('detail', 'Unknown error')}")
            except ValueError:
                print(f"API Error: {e.response.text}")
        sys.exit(1)

def create_instance(args):
    """Create a new VS Code Server instance"""
    data = {
        "user_id": args.user_id,
        "storage_size": args.storage,
        "memory_request": args.memory_request,
        "memory_limit": args.memory_limit,
        "cpu_request": args.cpu_request,
        "cpu_limit": args.cpu_limit
    }
    
    response = make_api_request("POST", f"{args.api_url}/instances", data)
    
    print("VS Code Server instance created successfully!")
    print(f"Instance ID: {response['instance_id']}")
    print(f"Access URL: {response['url']}")
    print(f"Access Token: {response['access_token']}")
    print(f"Status: {response['status']}")
    
    return response

def list_instances(args):
    """List VS Code Server instances"""
    params = {"user_id": args.user_id}
    response = make_api_request("GET", f"{args.api_url}/instances", params)
    
    instances = response.get("instances", [])
    if not instances:
        print(f"No VS Code Server instances found for user {args.user_id}")
        return
    
    print(f"Found {len(instances)} VS Code Server instance(s) for user {args.user_id}:")
    for instance in instances:
        print(f"  • Instance ID: {instance['instance_id']}")
        print(f"    Access URL: {instance['url']}")
        print(f"    Status: {instance['status']}")
        print()
    
    return response

def get_instance(args):
    """Get details of a VS Code Server instance"""
    response = make_api_request("GET", f"{args.api_url}/instances/{args.instance_id}")
    
    print(f"VS Code Server instance details:")
    print(f"Instance ID: {response['instance_id']}")
    print(f"Access URL: {response['url']}")
    print(f"Access Token: {response['access_token']}")
    print(f"Status: {response['status']}")
    
    return response

def delete_instance(args):
    """Delete a VS Code Server instance"""
    response = make_api_request("DELETE", f"{args.api_url}/instances/{args.instance_id}")
    
    print(f"VS Code Server instance {args.instance_id} has been deleted")
    
    return response

def check_status(args):
    """Check the status of a VS Code Server instance"""
    params = {"instance_id": args.instance_id}
    response = make_api_request("GET", f"{args.api_url}/status", params)
    
    print(f"VS Code Server instance {response['instance_id']} status: {response['status']}")
    
    return response

def main():
    """Main function"""
    args = parse_args()
    
    if args.command == "create":
        create_instance(args)
    elif args.command == "list":
        list_instances(args)
    elif args.command == "get":
        get_instance(args)
    elif args.command == "delete":
        delete_instance(args)
    elif args.command == "status":
        check_status(args)
    else:
        print("Please specify a command. Use --help for more information.")
        sys.exit(1)

if __name__ == "__main__":
    main()