#!/usr/bin/env python3
"""
Test script for SAP AI Core connection and available models.
Tests OAuth2 authentication and OpenAI-compatible endpoints.
"""

import os
import json
import requests
from datetime import datetime, timedelta

# SAP AI Core credentials (from environment or hardcoded for testing)
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
    """
    Get OAuth2 access token using client credentials flow.
    """
    print("🔐 Authenticating with SAP AI Core...")
    print(f"   Auth URL: {SAP_AICORE_AUTH_URL}")
    
    token_url = f"{SAP_AICORE_AUTH_URL}/oauth/token"
    
    data = {
        "grant_type": "client_credentials",
        "client_id": SAP_AICORE_CLIENT_ID,
        "client_secret": SAP_AICORE_CLIENT_SECRET
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=30)
        response.raise_for_status()
        token_data = response.json()
        
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)
        
        print(f"✅ Token obtained successfully")
        print(f"   Expires in: {expires_in} seconds ({expires_in/60:.1f} minutes)")
        
        return access_token
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return None


def test_chat_completion(token):
    """
    Test chat completion endpoint with GPT-4o.
    """
    print("\n💬 Testing chat completion (gpt-4o)...")
    
    # Deployment ID for gpt-4o from list_deployments (d1555c6d43e6f446)
    # Using gpt-4o instead of gpt-4o-mini as it may have better API support
    url = f"{SAP_AICORE_BASE_URL}/v2/inference/deployments/d1555c6d43e6f446/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "AI-Resource-Group": "default"
    }
    
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "Say 'Hello from SAP AI Core' in exactly 5 words."
            }
        ],
        "max_tokens": 50,
        "temperature": 0.0
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"✅ Chat completion successful")
        print(f"   Response: {message}")
        print(f"   Full result: {json.dumps(result, indent=2)}")
        
        return True
    except Exception as e:
        print(f"❌ Chat completion failed (trying without api-version): {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        
        # Try alternative URL format (using deploymentUrl format with query params)
        print("   Trying with query parameters...")
        try:
            alt_url = f"{SAP_AICORE_BASE_URL}/v2/inference/deployments/d1555c6d43e6f446/chat/completions?api-version=2023-05-15"
            response = requests.post(alt_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"✅ Chat completion successful (alternative endpoint)")
            print(f"   Response: {message}")
            return True
        except Exception as e2:
            print(f"❌ Alternative endpoint also failed: {e2}")
            if hasattr(e2, 'response') and e2.response is not None:
                print(f"   Response: {e2.response.text}")
        
        return False


def test_embeddings(token):
    """
    Test embeddings endpoint (text-embedding-ada-002).
    """
    print("\n🔢 Testing embeddings (text-embedding-ada-002)...")
    
    # Deployment ID for text-embedding-ada-002 from list_deployments
    url = f"{SAP_AICORE_BASE_URL}/v2/inference/deployments/d987a899a829c105/embeddings?api-version=2023-05-15"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "AI-Resource-Group": "default"
    }
    
    payload = {
        "input": "This is a test sentence for embedding."
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        embedding = result.get("data", [{}])[0].get("embedding", [])
        print(f"✅ Embeddings successful")
        print(f"   Embedding dimension: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")
        
        return True
    except Exception as e:
        print(f"❌ Embeddings failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return False


def main():
    print("=" * 60)
    print("SAP AI Core Connection Test")
    print("=" * 60)
    
    # Step 1: Get OAuth token
    token = get_oauth_token()
    if not token:
        print("\n❌ Failed to obtain access token. Exiting.")
        return
    
    # Step 2: Test chat completion
    chat_success = test_chat_completion(token)
    
    # Step 3: Test embeddings
    embeddings_success = test_embeddings(token)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Authentication: ✅")
    print(f"Chat Completion: {'✅' if chat_success else '❌'}")
    print(f"Embeddings: {'✅' if embeddings_success else '❌'}")
    
    if chat_success and embeddings_success:
        print("\n🎉 All tests passed! Ready to integrate with Legal Eagle.")
    else:
        print("\n⚠️ Some tests failed. Review the logs above.")


if __name__ == "__main__":
    main()