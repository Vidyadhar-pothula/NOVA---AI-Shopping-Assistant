from typing import Dict, Any, Optional
from backend.discovery.engine import discovery_engine
from backend.tools.registry import registry

def get_discovery_feed(
    category: str = "all",
    query: Optional[str] = None,
    country_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve current live discovery items for deals, festivals, sports events/merchandise, movie releases/merchandise.
    Triggered when user asks 'What's new?', 'Any deals today?', 'What's happening for the World Cup?', etc.
    """
    market_override = {"country_code": country_code} if country_code else None
    return discovery_engine.get_discovery_feed(category=category, query=query, market_override=market_override)

get_discovery_feed_schema = {
    "type": "function",
    "function": {
        "name": "get_discovery_feed",
        "description": "Fetch live, dynamic discovery content including major shopping sales, regional festivals, sports events/merchandise, and movie releases/merchandise. Use when user asks 'What's new?', 'Any deals today?', 'What's happening in India?', 'World cup merchandise', etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category filter: 'all', 'deals', 'festivals', 'sports', 'movies'."
                },
                "query": {
                    "type": "string",
                    "description": "Specific query term, e.g., 'Cricket World Cup', 'Diwali', 'Avengers', 'India'."
                },
                "country_code": {
                    "type": "string",
                    "description": "Two-letter country code override (e.g. 'IN', 'US')."
                }
            }
        }
    }
}

registry.register(get_discovery_feed_schema, get_discovery_feed)
