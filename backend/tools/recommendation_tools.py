from typing import Dict, Any, Optional, List
from backend.personalization.recommendation_engine import recommendation_engine
from backend.personalization.history_analyzer import history_analyzer
from backend.tools.registry import registry
from backend.database.db import get_connection
from backend.commerce.models import Product


def _get_current_page_product_id(session_id: str) -> Optional[str]:
    """Return the first current-page product id for a session, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT current_page_product_ids, last_product_ids FROM session_states WHERE session_id = ?",
        (session_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    import json
    for field in ("current_page_product_ids", "last_product_ids"):
        raw = row[field]
        if raw:
            try:
                ids = json.loads(raw)
                if ids:
                    return ids[0]
            except Exception:
                continue
    return None


def get_pairing_suggestions(
    session_id: str = "default_session",
    current_product_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Contextual pairing / upsell suggestions after the user adds a single product
    (especially from a browser extension "add this to cart" action).

    * Returns 2–3 DYNAMIC, individually-classified, addable products from the
      shared recommendation engine — never hardcoded.
    * Uses (in priority order):
        1. Explicit current_product_id argument.
        2. CURRENT BROWSER PAGE PRODUCT context for the session (extension use case).
        3. Active / last displayed conversation products.
        4. Cart contents (anchor = most recently added product).
    * Each returned suggestion has: product_id, name, brand, price, currency,
      merchant/source, exact product URL, image, is_individual_product=True,
      availability, and a dynamic recommendation_reason with evidence.
    * The tool also returns whether personalized purchase history evidence
      actually exists (so the LLM can avoid falsely claiming "Based on your
      previous purchases...").
    * The tool does NOT modify the cart. Only the user (via explicit add_to_cart
      calls from the LLM) adds suggestions to the authoritative cart.
    """
    # Pick best anchor product id
    anchor_pid = current_product_id or _get_current_page_product_id(session_id)

    if not anchor_pid:
        # Fallback: last product added to the cart
        from backend.tools.cart_tools import get_cart as _get_cart
        c = _get_cart(session_id)
        if c and c.get("items"):
            last_item = c["items"][-1]
            anchor_pid = last_item["product"]["id"]

    # Fetch personalized recommendations from the shared engine
    recs = recommendation_engine.get_recommendations(
        session_id=session_id,
        current_product_id=anchor_pid,
        limit=3,
    )

    has_personalized_evidence = bool(recs.get("has_personalized_history"))
    items = recs.get("recommendations") or []

    # Filter: only individually-classified products (never listings / browse pages)
    valid_suggestions: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("is_individual_product") is False:
            continue
        if not it.get("id") or not it.get("name"):
            continue
        valid_suggestions.append({
            "product_id": it["id"],
            "name": it["name"],
            "brand": it.get("brand", ""),
            "price": float(it.get("price", 0.0)),
            "currency": it.get("currency", "INR"),
            "merchant": it.get("merchant_name") or it.get("merchant") or it.get("source_name") or "",
            "source": it.get("source_name") or "",
            "product_url": it.get("product_url") or it.get("url") or "",
            "image": (it.get("images") or [None])[0] if isinstance(it.get("images"), list) else it.get("image"),
            "availability": it.get("availability", True) is not False,
            "is_individual_product": True,
            "recommendation_reason": it.get("recommendation_reason") or "Complementary product suggestion",
        })
        if len(valid_suggestions) >= 3:
            break

    # Build an honest evidence header for the LLM
    if has_personalized_evidence:
        evidence_statement = "Based on the user's authorized NOVA purchase history and current product context."
    else:
        evidence_statement = "Based on current product context (no authorized purchase history is available yet)."

    return {
        "success": True,
        "anchor_product_id": anchor_pid,
        "count": len(valid_suggestions),
        "evidence_statement": evidence_statement,
        "has_personalized_history": has_personalized_evidence,
        "suggestions": valid_suggestions,
        "next_action_guidance": (
            "Present the suggestions naturally. Ask whether the user wants to pair the "
            "anchor product with any of them, or continue with the anchor product alone. "
            "Do not fabricate personal history evidence."
        ),
    }


def get_recommendations(
    session_id: str = "default_session",
    current_product_id: Optional[str] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    country_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get 2-3 personalized product recommendations combining customer order history, purchase frequency,
    co-purchase patterns, and current product context.
    """
    return recommendation_engine.get_recommendations(
        session_id=session_id,
        current_product_id=current_product_id,
        category=category,
        query=query,
        country_code=country_code,
        limit=3
    )

def get_purchase_history_summary(session_id: str = "default_session") -> Dict[str, Any]:
    """
    Analyze customer's order history to return frequently purchased products, top categories, top brands, and purchase patterns.
    """
    return history_analyzer.analyze_frequent_purchases(session_id=session_id)

def get_copurchase_recommendations(
    session_id: str = "default_session",
    anchor_product_id: Optional[str] = None,
    anchor_category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Identify products or categories frequently bought together with the specified item or category based on historical order baskets.
    """
    return history_analyzer.analyze_copurchase_pairs(
        session_id=session_id,
        anchor_product_id=anchor_product_id,
        anchor_category=anchor_category
    )

# Schemas
get_recommendations_schema = {
    "type": "function",
    "function": {
        "name": "get_recommendations",
        "description": "Get 2-3 personalized product recommendations using the customer's authorized purchase history, frequency, recency, and co-purchase patterns. Trigger when user asks 'What do you recommend?', 'What do I usually buy with this?', 'Suggest complementary products'.",
        "parameters": {
            "type": "object",
            "properties": {
                "current_product_id": {
                    "type": "string",
                    "description": "Optional active/current product ID being viewed or purchased."
                },
                "category": {
                    "type": "string",
                    "description": "Optional product category filter."
                },
                "query": {
                    "type": "string",
                    "description": "Optional specific recommendation keyword."
                }
            }
        }
    }
}

get_purchase_history_summary_schema = {
    "type": "function",
    "function": {
        "name": "get_purchase_history_summary",
        "description": "Retrieve customer's purchase history summary including frequently purchased items, top categories, and top brands. Trigger when user asks 'What do I buy frequently?', 'Show my top categories', 'What have I ordered before?'.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

get_copurchase_recommendations_schema = {
    "type": "function",
    "function": {
        "name": "get_copurchase_recommendations",
        "description": "Find items frequently bought together with the current product or category based on past orders. Trigger when user asks 'What do people buy together with this?', 'What pairs with this?'.",
        "parameters": {
            "type": "object",
            "properties": {
                "anchor_product_id": {
                    "type": "string",
                    "description": "ID of the target product."
                },
                "anchor_category": {
                    "type": "string",
                    "description": "Category of the target product."
                }
            }
        }
    }
}

get_pairing_suggestions_schema = {
    "type": "function",
    "function": {
        "name": "get_pairing_suggestions",
        "description": (
            "Contextual pairing / upsell suggestions to offer IMMEDIATELY after the user says "
            "'add this to cart' (especially on an external browser product page via the extension). "
            "Returns 2–3 DYNAMIC complementary products using the shared recommendation engine "
            "(never hardcoded pairings). Each returned suggestion is a canonically-valid individual "
            "product with price, merchant, URL, availability, and an honest recommendation reason. "
            "The response also tells you whether the user has authorized personalized history, "
            "so you can avoid falsely claiming 'Based on your previous purchases...' when none exists. "
            "Call this RIGHT AFTER an add-to-cart action on a single product, then ask the user "
            "whether they want to pair it with any suggestion, or continue with just the main product."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "current_product_id": {
                    "type": "string",
                    "description": "Optional explicit anchor product ID. If omitted, the current browser page product or most recently added cart item is used automatically."
                },
            },
        },
    },
}

registry.register(get_recommendations_schema, get_recommendations)
registry.register(get_purchase_history_summary_schema, get_purchase_history_summary)
registry.register(get_copurchase_recommendations_schema, get_copurchase_recommendations)
registry.register(get_pairing_suggestions_schema, get_pairing_suggestions)
