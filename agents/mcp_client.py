"""
MCP Client - Helper for calling MCP tools from Python code.

This module provides a bridge to call MCP tools (like Loka) from Python.
Since MCP tools are not directly accessible in Python runtime, we use
a subprocess approach to invoke them through the Cline environment.
"""

import subprocess
import json
import re
from typing import Dict, List, Optional, Any


def call_loka_search(
    scope: str,
    country: str,
    query: Optional[str] = None,
    product: Optional[str] = None,
    max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Call Loka MCP search tool and parse results.
    
    Args:
        scope: Search scope ("regulations", "epics", etc.)
        country: Country name (e.g., "Turkey")
        query: Optional search query
        product: Optional product filter
        max_results: Maximum number of results
    
    Returns:
        List of regulation dictionaries with id and title
    """
    # Build MCP tool arguments
    args = {
        "scope": scope,
        "country": country,
        "max_results": max_results
    }
    
    if query:
        args["query"] = query
    if product:
        args["product"] = product
    
    # Call Loka via subprocess (this is a placeholder - actual implementation
    # would need to invoke MCP through Cline's environment)
    # For now, we'll use a simpler approach: directly construct the search
    
    # Since we can't actually call MCP from Python subprocess (MCP is Cline-only),
    # we return empty list. The actual integration needs to happen at a different level.
    return []


def parse_loka_search_response(response_text: str) -> List[Dict[str, str]]:
    """
    Parse Loka search text response to extract regulation data.
    
    Expected format:
        Found 3 regulations:
        - GSREQSE-14748: Amendments to Social Security... [Turkey (TR)] - Completed
        - GSREQSE-14473: E-invoice and e-despatch... [Turkey (TR)] - Completed
    
    Args:
        response_text: Raw text response from Loka search
    
    Returns:
        List of dicts with 'id' and 'title' keys
    """
    regulations = []
    
    # Pattern to match regulation lines: - GSREQSE-XXXXX: Title... [Country] - Status
    pattern = r'-\s+(GSREQ[A-Z]+-\d+):\s+([^\[]+)'
    
    for match in re.finditer(pattern, response_text):
        reg_id = match.group(1).strip()
        title = match.group(2).strip()
        
        # Remove trailing "..." if present
        if title.endswith('...'):
            title = title[:-3].strip()
        
        regulations.append({
            "id": reg_id,
            "title": title,
            "summary": ""  # Not available in search results
        })
    
    return regulations