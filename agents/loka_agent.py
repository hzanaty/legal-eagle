"""
Loka Agent - Interface to Loka MCP for SAP Globalization Services data.

This agent provides a clean Python interface to Loka MCP tools with different modes:
- mode="rcm": Search RCM regulations
- mode="help": Search SAP Help Portal (future)
- mode="community": Search SAP Community (future)
- mode="analyze": Get detailed regulation info (future)

The agent handles request formatting, response parsing, and data structuring.
Actual MCP calls are executed by the orchestrator at the Cline level.
"""

import re
from typing import Dict, List, Optional, Any
from datetime import datetime


class LokaAgent:
    """
    Loka Agent for interacting with SAP Globalization Services data via Loka MCP.
    
    This agent acts as a request/response formatter and parser. It doesn't
    directly call MCP (which is Cline-only), but provides clean interfaces
    for the orchestrator to use.
    """
    
    def __init__(self):
        """Initialize Loka Agent."""
        self.server_name = "LOKA"
        self.last_request = None
        self.last_response = None
    
    def search_rcm(
        self,
        country: str,
        query: str,
        max_results: int = 10,
        loka_response: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search RCM regulations via Loka MCP.
        
        This method formats the request and parses the response.
        The actual MCP call must be made by the orchestrator.
        
        Args:
            country: Country name (e.g., "Turkey", "Spain")
            query: Search query string
            max_results: Maximum number of results (default: 10)
            loka_response: Optional Loka MCP response text to parse
        
        Returns:
            List of regulation dictionaries:
            [
                {
                    "id": "GSREQSE-14748",
                    "title": "Amendments to Social Security...",
                    "summary": "",
                    "country": "Turkey",
                    "status": "Completed"
                },
                ...
            ]
        
        Usage:
            # Step 1: Get MCP request parameters
            loka = LokaAgent()
            request = loka.get_rcm_search_request("Turkey", "social security SGK")
            
            # Step 2: Orchestrator calls Loka MCP with these params
            # response = use_mcp_tool(server_name="LOKA", tool_name="loka_search", arguments=request)
            
            # Step 3: Parse response
            regulations = loka.search_rcm("Turkey", "social security SGK", loka_response=response)
        """
        # Store request for debugging
        self.last_request = {
            "mode": "rcm",
            "country": country,
            "query": query,
            "max_results": max_results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # If no response provided, return empty list
        # (Orchestrator will provide response in production)
        if not loka_response:
            return []
        
        # Store response for debugging
        self.last_response = loka_response
        
        # Parse Loka response
        regulations = self.parse_loka_response(loka_response, mode="rcm")
        
        return regulations
    
    def get_rcm_search_request(
        self,
        country: str,
        query: str,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        Get formatted Loka MCP request parameters for RCM search.
        
        This is used by the orchestrator to make the actual MCP call.
        
        Args:
            country: Country name
            query: Search query
            max_results: Maximum results
        
        Returns:
            Dict with MCP tool arguments:
            {
                "scope": "regulations",
                "country": country,
                "query": query,
                "max_results": max_results
            }
        """
        return {
            "scope": "regulations",
            "country": country,
            "query": query,
            "max_results": max_results
        }
    
    def parse_loka_response(
        self,
        response_text: str,
        mode: str = "rcm"
    ) -> List[Dict[str, Any]]:
        """
        Parse Loka MCP text response into structured data.
        
        Args:
            response_text: Raw text response from Loka MCP
            mode: Response mode ("rcm", "help", "community")
        
        Returns:
            List of parsed items (format depends on mode)
        
        Supported formats:
            mode="rcm": Extract regulation IDs and titles from:
                "Found 3 regulations:
                 - GSREQSE-14748: Amendments to Social Security... [Turkey (TR)] - Completed"
        """
        if mode == "rcm":
            return self._parse_rcm_response(response_text)
        else:
            raise ValueError(f"Unsupported mode: {mode}")
    
    def _parse_rcm_response(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Parse RCM regulations from Loka response.
        
        Expected format:
            Found 3 regulations:
            - GSREQSE-14748: Amendments to Social Security... [Turkey (TR)] - Completed
            - GSREQSE-14473: E-invoice and e-despatch... [Turkey (TR)] - Completed
        
        Returns:
            List of regulation dicts with id, title, country, status
        """
        regulations = []
        
        # Pattern: - GSREQSE-XXXXX: Title... [Country (CODE)] - Status
        pattern = r'-\s+(GSREQ[A-Z]+-\d+):\s+([^\[]+)\s+\[([^\]]+)\]\s+-\s+(\w+)'
        
        for match in re.finditer(pattern, response_text):
            reg_id = match.group(1).strip()
            title = match.group(2).strip()
            country_info = match.group(3).strip()  # e.g., "Turkey (TR)"
            status = match.group(4).strip()
            
            # Remove trailing "..." from title
            if title.endswith('...'):
                title = title[:-3].strip()
            
            # Extract country name (before parentheses)
            country_match = re.match(r'^([^(]+)', country_info)
            country = country_match.group(1).strip() if country_match else country_info
            
            regulations.append({
                "id": reg_id,
                "title": title,
                "summary": "",  # Not available in search results
                "country": country,
                "status": status
            })
        
        return regulations
    
    def get_last_request(self) -> Optional[Dict]:
        """Get the last request made (for debugging)."""
        return self.last_request
    
    def get_last_response(self) -> Optional[str]:
        """Get the last response received (for debugging)."""
        return self.last_response


# Singleton instance for convenience
_loka_agent = None


def get_loka_agent() -> LokaAgent:
    """Get or create Loka Agent singleton."""
    global _loka_agent
    if _loka_agent is None:
        _loka_agent = LokaAgent()
    return _loka_agent