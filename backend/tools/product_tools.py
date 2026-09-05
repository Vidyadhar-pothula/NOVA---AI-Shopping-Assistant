from typing import List, Dict, Any, Optional
from backend.commerce.service import search_service
from backend.tools.registry import registry

from backend.commerce.location import MarketResolver

def search_products(
    query: str, 
    min_price: Optional[float] = None, 
    max_price: Optional[float] = None, 
    category: Optional[str] = None,
    country_code: Optional[str] = None,
    result_count: Optional[int] = None,
    session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search live sources, preferring products already extracted from the current browser page."""
    count = min(result_count, 8) if result_count else 5
    page_hits: List[Dict[str, Any]] = []
    if session_id:
        from backend.providers.catalog_provider import catalog_service
        cat = catalog_service.inspect_session_catalog(session_id)
        qwords = [w for w in (query or "").lower().split() if len(w) > 2]
        for item in cat.get("products") or []:
            name = (item.get("name") or "").lower()
            price = item.get("price")
            try:
                price_val = float(price) if price is not None else None
            except (TypeError, ValueError):
                price_val = None
            if max_price is not None and price_val is not None and price_val > float(max_price):
                continue
            if min_price is not None and price_val is not None and price_val < float(min_price):
                continue
            if qwords and not any(w in name for w in qwords):
                continue
            page_hits.append(item)
        if page_hits:
            return page_hits[:count]

    market_obj = MarketResolver.resolve_market(country_code=country_code)
    prods = search_service.search_products(query, category=category, min_price=min_price, max_price=max_price, market=market_obj)
    return [p.to_dict() for p in prods[:count]]


def get_product_details(product_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve detailed information about a single product by ID or URL."""
    prod = search_service.get_product_details(product_id)
    if prod:
        return prod.to_dict()
    return None

def compare_products(product_ids: List[str]) -> Dict[str, Any]:
    """Compare features, price, source, and exact URLs of multiple products side-by-side."""
    comparison = {}
    for pid in product_ids:
        prod = search_service.get_product_details(pid)
        if prod:
            comparison[pid] = {
                "name": prod.name,
                "brand": prod.brand,
                "price": prod.price,
                "currency": prod.currency,
                "rating": prod.rating,
                "merchant": prod.merchant_name,
                "source_name": prod.source_name,
                "product_url": prod.product_url,
                "availability": "In Stock" if prod.availability else "Out of Stock",
                "retrieved_at": prod.retrieved_at,
                "is_verified": prod.is_verified,
                "specifications": prod.specifications
            }
    return comparison

def compare_prices(product_name: str) -> List[Dict[str, Any]]:
    """Compare live prices for the same product across different commerce platforms (Amazon, Flipkart, Nike, etc.)."""
    prods = search_service.search_products(product_name)
    comparison = []
    for prod in prods:
        comparison.append({
            "product_id": prod.id,
            "name": prod.name,
            "brand": prod.brand,
            "merchant": prod.merchant_name,
            "source_name": prod.source_name,
            "price": prod.price,
            "currency": prod.currency,
            "product_url": prod.product_url,
            "availability": prod.availability,
            "retrieved_at": prod.retrieved_at,
            "is_verified": prod.is_verified
        })
    return comparison

def check_inventory(product_id: str) -> Dict[str, Any]:
    """Check stock level and delivery availability for a specific product."""
    prod = search_service.get_product_details(product_id)
    if prod:
        return {
            "product_id": product_id,
            "name": prod.name,
            "merchant": prod.merchant_name,
            "availability": prod.availability,
            "delivery_information": prod.delivery_information or "Standard Delivery Available",
            "product_url": prod.product_url,
            "retrieved_at": prod.retrieved_at
        }
    return {"error": "Product not found."}


# Register the tools with their JSON schemas

search_products_schema = {
    "type": "function",
    "function": {
        "name": "search_products",
        "description": "Search for live verified products based on category, query keywords, and price limits. Returns candidate products for evaluation.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "User-grounded keywords or search term."
                },
                "min_price": {
                    "type": "number",
                    "description": "Minimum price filter in user's currency."
                },
                "max_price": {
                    "type": "number",
                    "description": "Maximum price filter (hard constraint) in user's currency."
                },
                "category": {
                    "type": "string",
                    "description": "Product category only when the user clearly provided one."
                },
                "result_count": {
                    "type": "integer",
                    "description": "Number of candidate products to retrieve. Only set if the user explicitly requested a specific count."
                }
            },
            "required": ["query"]
        }
    }
}

get_product_details_schema = {
    "type": "function",
    "function": {
        "name": "get_product_details",
        "description": "Retrieve extensive details of a specific product by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The unique product identifier."
                }
            },
            "required": ["product_id"]
        }
    }
}

compare_products_schema = {
    "type": "function",
    "function": {
        "name": "compare_products",
        "description": "Compare features, price, and specs of multiple products side-by-side by providing their product IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of product IDs to compare."
                }
            },
            "required": ["product_ids"]
        }
    }
}

compare_prices_schema = {
    "type": "function",
    "function": {
        "name": "compare_prices",
        "description": "Compare prices for a specific product brand or name across all merchants in the system to find the best deal.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "The product name, brand, or model the user asked to compare."
                }
            },
            "required": ["product_name"]
        }
    }
}

check_inventory_schema = {
    "type": "function",
    "function": {
        "name": "check_inventory",
        "description": "Check if a product is in stock and get its delivery information.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The product ID to verify inventory for."
                }
            },
            "required": ["product_id"]
        }
    }
}

registry.register(search_products_schema, search_products)
registry.register(get_product_details_schema, get_product_details)
registry.register(compare_products_schema, compare_products)
registry.register(compare_prices_schema, compare_prices)
registry.register(check_inventory_schema, check_inventory)
