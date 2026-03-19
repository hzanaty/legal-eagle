"""
SAP AI Core client with OpenAI-compatible interface.
Handles OAuth2 authentication and provides chat completion and embeddings functionality.
"""

import os
import time
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import httpx


class SAPAICoreClient:
    """
    SAP AI Core client with OpenAI-compatible interface.
    
    Automatically handles:
    - OAuth2 token authentication (client credentials flow)
    - Token caching and refresh
    - OpenAI-compatible chat completions and embeddings
    """
    
    def __init__(
        self,
        base_url: str,
        auth_url: str,
        client_id: str,
        client_secret: str,
        chat_deployment_id: str,
        embeddings_deployment_id: str,
        resource_group: str = "default"
    ):
        """
        Initialize SAP AI Core client.
        
        Args:
            base_url: SAP AI Core API base URL
            auth_url: SAP AI Core OAuth2 auth URL
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            chat_deployment_id: Deployment ID for chat completions model
            embeddings_deployment_id: Deployment ID for embeddings model
            resource_group: AI resource group (default: "default")
        """
        self.base_url = base_url.rstrip('/')
        self.auth_url = auth_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.chat_deployment_id = chat_deployment_id
        self.embeddings_deployment_id = embeddings_deployment_id
        self.resource_group = resource_group
        
        # Token caching
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    def _get_access_token(self) -> str:
        """
        Get OAuth2 access token (with caching).
        Automatically refreshes if expired.
        """
        # Return cached token if still valid
        if self._access_token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at - timedelta(minutes=5):
                return self._access_token
        
        # Request new token
        token_url = f"{self.auth_url}/oauth/token"
        
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()
            token_data = response.json()
            
            self._access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            return self._access_token
        except Exception as e:
            raise RuntimeError(f"Failed to obtain SAP AI Core access token: {e}")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with fresh access token."""
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "AI-Resource-Group": self.resource_group
        }
    
    # OpenAI-compatible interface
    
    class ChatCompletions:
        """Chat completions endpoint (OpenAI-compatible)."""
        
        def __init__(self, client: 'SAPAICoreClient'):
            self.client = client
        
        def create(
            self,
            model: str,
            messages: List[Dict[str, str]],
            temperature: float = 1.0,
            max_tokens: Optional[int] = None,
            timeout: Optional[float] = None,
            response_format: Optional[Dict[str, str]] = None,
            **kwargs
        ) -> Any:
            """
            Create chat completion (OpenAI-compatible).
            
            Args:
                model: Model name (ignored, uses configured deployment)
                messages: List of message dicts with 'role' and 'content'
                temperature: Sampling temperature
                max_tokens: Maximum tokens to generate
                timeout: Request timeout in seconds
                response_format: Response format (e.g., {"type": "json_object"})
                **kwargs: Other OpenAI parameters (ignored)
            
            Returns:
                Response object with OpenAI-compatible structure
            """
            url = f"{self.client.base_url}/v2/inference/deployments/{self.client.chat_deployment_id}/chat/completions?api-version=2023-05-15"
            
            payload = {
                "messages": messages,
                "temperature": temperature
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            if response_format:
                payload["response_format"] = response_format
            
            timeout_val = timeout or 60.0
            
            try:
                response = requests.post(
                    url,
                    headers=self.client._get_headers(),
                    json=payload,
                    timeout=timeout_val
                )
                response.raise_for_status()
                
                # Return response in OpenAI-compatible format
                result = response.json()
                return ChatCompletionResponse(result)
            except Exception as e:
                raise RuntimeError(f"SAP AI Core chat completion failed: {e}")
    
    class Embeddings:
        """Embeddings endpoint (OpenAI-compatible)."""
        
        def __init__(self, client: 'SAPAICoreClient'):
            self.client = client
        
        def create(
            self,
            model: str,
            input: Any,
            timeout: Optional[float] = None,
            **kwargs
        ) -> Any:
            """
            Create embeddings (OpenAI-compatible).
            
            Args:
                model: Model name (ignored, uses configured deployment)
                input: Text or list of texts to embed
                timeout: Request timeout in seconds
                **kwargs: Other OpenAI parameters (ignored)
            
            Returns:
                Response object with OpenAI-compatible structure
            """
            url = f"{self.client.base_url}/v2/inference/deployments/{self.client.embeddings_deployment_id}/embeddings?api-version=2023-05-15"
            
            payload = {"input": input}
            timeout_val = timeout or 60.0
            
            try:
                response = requests.post(
                    url,
                    headers=self.client._get_headers(),
                    json=payload,
                    timeout=timeout_val
                )
                response.raise_for_status()
                
                # Return response in OpenAI-compatible format
                result = response.json()
                return EmbeddingsResponse(result)
            except Exception as e:
                raise RuntimeError(f"SAP AI Core embeddings failed: {e}")
    
    @property
    def chat(self):
        """Access chat endpoint."""
        return type('Chat', (), {'completions': self.ChatCompletions(self)})()
    
    @property
    def embeddings(self):
        """Access embeddings endpoint."""
        return self.Embeddings(self)


# Response wrapper classes (OpenAI-compatible)

class ChatCompletionResponse:
    """Wrapper for chat completion response."""
    
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.choices = [
            type('Choice', (), {
                'message': type('Message', (), {
                    'content': choice.get('message', {}).get('content', ''),
                    'role': choice.get('message', {}).get('role', 'assistant')
                })()
            })()
            for choice in data.get('choices', [])
        ]


class EmbeddingsResponse:
    """Wrapper for embeddings response."""
    
    def __init__(self, raw_data: Dict[str, Any]):
        self._raw_data = raw_data
        self.data = [
            type('EmbeddingData', (), {
                'embedding': item.get('embedding', [])
            })()
            for item in raw_data.get('data', [])
        ]


# Factory function to create client from environment variables

def create_sap_aicore_client() -> SAPAICoreClient:
    """
    Create SAP AI Core client from environment variables.
    
    Required environment variables:
    - LEGAL_EAGLE_SAP_AICORE_BASE_URL
    - LEGAL_EAGLE_SAP_AICORE_AUTH_URL
    - LEGAL_EAGLE_SAP_AICORE_CLIENT_ID
    - LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET
    - LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID
    - LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID
    
    Returns:
        Configured SAPAICoreClient instance
    """
    base_url = os.getenv("LEGAL_EAGLE_SAP_AICORE_BASE_URL")
    auth_url = os.getenv("LEGAL_EAGLE_SAP_AICORE_AUTH_URL")
    client_id = os.getenv("LEGAL_EAGLE_SAP_AICORE_CLIENT_ID")
    client_secret = os.getenv("LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET")
    chat_deployment = os.getenv("LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID")
    embeddings_deployment = os.getenv("LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID")
    
    if not all([base_url, auth_url, client_id, client_secret, chat_deployment, embeddings_deployment]):
        raise RuntimeError(
            "Missing required SAP AI Core environment variables. "
            "Required: LEGAL_EAGLE_SAP_AICORE_* (BASE_URL, AUTH_URL, CLIENT_ID, CLIENT_SECRET, "
            "CHAT_DEPLOYMENT_ID, EMBEDDINGS_DEPLOYMENT_ID)"
        )
    
    return SAPAICoreClient(
        base_url=base_url,
        auth_url=auth_url,
        client_id=client_id,
        client_secret=client_secret,
        chat_deployment_id=chat_deployment,
        embeddings_deployment_id=embeddings_deployment
    )