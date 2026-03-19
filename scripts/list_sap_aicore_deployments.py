#!/usr/bin/env python3
"""
List all available deployments on SAP AI Core instance.
"""

import os
import json
import requests

# SAP AI Core credentials
SAP_AICORE_BASE_URL = os.getenv(
    "LEGAL_EAGLE_SAP_AICORE_BASE_URL",
    "https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com"
)
SAP_AICORE_AUTH_URL = os.getenv(
    "LEGAL_EAGLE_SAP_AICORE_AUTH_URL",
    "https://sapaicore-vkibf89l.authentication.sap.hana.ondemand.com"
)
SAP_AICORE_CLIENT_ID = os.getenv(
    "LEGAL_EAGLE_SAP_AICORE_CLIENT_ID",
    "sb-0258b940-0094-4fa5-9d5c-6c8c95eaae77!b99964|xsuaa_std!b77089"
)
SAP_AICORE_CLIENT_SECRET = os.getenv(
    "LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET",
    "45974a61-eed6-4daa-b0a7-3ab5ac4436cb$HAplSj6NcoXaCo_NmPN5SOmOZ-Ik-hKjdckXeyfbvF0="
)


def get_oauth_token():
    """Get OAuth2 access token."""
    token_url = f"{SAP_AICORE_AUTH_URL}/oauth/token"
    
    data = {
        "grant_type": "client_credentials",
        "client_id": SAP_AICORE_CLIENT_ID,
        "client_secret": SAP_AICORE_CLIENT_SECRET
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return None


def list_deployments(token):
    """List all deployments."""
    print("📋 Listing SAP AI Core deployments...\n")
    
    # Try different API versions and endpoints
    endpoints = [
        "/v2/lm/deployments",
        "/lm/deployments",
        "/v2/inference/deployments",
        "/inference/deployments"
    ]
    
    headers = {
        "Authorization": f"Bearer {token}",
        "AI-Resource-Group": "default"
    }
    
    for endpoint in endpoints:
        url = f"{SAP_AICORE_BASE_URL}{endpoint}"
        print(f"Trying: {endpoint}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Success! Found deployments at {endpoint}\n")
                print(json.dumps(result, indent=2))
                
                # Parse and display deployments
                if "resources" in result:
                    print("\n" + "="*60)
                    print("Available Deployments:")
                    print("="*60)
                    for deployment in result["resources"]:
                        dep_id = deployment.get("id")
                        scenario_id = deployment.get("scenarioId")
                        status = deployment.get("status")
                        config_id = deployment.get("configurationId")
                        print(f"\n📦 Deployment ID: {dep_id}")
                        print(f"   Scenario: {scenario_id}")
                        print(f"   Status: {status}")
                        print(f"   Config: {config_id}")
                
                return
            else:
                print(f"   Status {response.status_code}: {response.text[:200]}\n")
        
        except Exception as e:
            print(f"   Error: {e}\n")
    
    print("❌ Could not find deployments endpoint.")


def main():
    print("=" * 60)
    print("SAP AI Core - List Deployments")
    print("=" * 60 + "\n")
    
    token = get_oauth_token()
    if not token:
        print("Failed to get token")
        return
    
    print("✅ Authentication successful\n")
    list_deployments(token)


if __name__ == "__main__":
    main()