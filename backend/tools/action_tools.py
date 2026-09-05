import json
import re
from typing import Dict, Any, Optional, List
from backend.database.db import get_connection
from backend.commerce.models import Product
from backend.tools.registry import registry
from backend.tools.cart_tools import add_to_cart

ORDINAL_MAP = {
    "first": 0, "1st": 0, "one": 0, "1": 0, "initial": 0,
    "second": 1, "2nd": 1, "two": 1, "2": 1, "other": 1,
    "third": 2, "3rd": 2, "three": 2, "3": 2,
    "fourth": 3, "4th": 3, "four": 3, "4": 3,
    "fifth": 4, "5th": 4, "five": 4, "5": 4,
    "last": -1, "final": -1
}

_CURRENT_PAGE_REFS = ("this", "this product", "this page", "this item", "buy this",
    "add this to cart", "add this", "checkout this", "checkout this product", "checkout this page",
    "current product", "current page", "current item", "this exact product", "this exact page")

_CART_CHECKOUT_REFS = ("my cart", "the cart", "our cart", "your cart", "everything in my cart",
    "all items", "everything", "the whole cart", "whole cart", "what's in my cart", "cart contents",
    "the items in my cart", "items in my cart", "my items", "checkout my items", "cart only", "my shopping cart",
    "cart")


def _is_current_page_reference(ref: str) -> bool:
    r = (ref or "").lower().strip()
    if not r:
        return False
    found_token = any(
        (token == r)
        or (r.startswith(token + " "))
        or (" " + token + " ") in (" " + r + " ")
        for token in _CURRENT_PAGE_REFS
    )
    is_ambiguous_this = (
        r in ("this",)
        and not re.search(
            r"\b(one|first|second|third|fourth|fifth|last|final|cheaper|cheapest|expensive|option|product|shoe|item|laptop|phone|result)\b",
            r,
        )
    )
    return found_token or is_ambiguous_this


def _is_cart_checkout_reference(ref: str, action_clean: str) -> bool:
    r = (ref or "").lower().strip()
    if action_clean not in ("checkout", "proceed_to_checkout", "purchase"):
        return False
    if not r:
        return True
    return any(token in r for token in _CART_CHECKOUT_REFS)


def _load_product_list(ids_list, conn):
    if not ids_list:
        return []
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids_list)
    cursor.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", ids_list)
    rows = cursor.fetchall()
    prod_map = {r["id"]: Product.from_row(r) for r in rows}
    return [prod_map[pid] for pid in ids_list if pid in prod_map]


def resolve_product_action(
    action: str,
    target_reference: Optional[str] = None,
    session_id: str = "default_session"
) -> Dict[str, Any]:
    """
    Resolve conversational references like 'the second one', 'the cheaper bottle', 'open Amazon result',
    'add this to cart', or 'proceed to checkout'.

    Distinguishes three contexts:
      A. CART checkout   → routes to create_order() (authoritative cart).
      B. CURRENT-PAGE refs ("this product") → prefer current page context over stale conversation products.
      C. CONVERSATIONAL refs ("second one", "cheapest") → use ordered conversational product list.
    """
    action_clean = (action or "open").lower().strip()
    ref_clean = (target_reference or "").lower().strip()

    # A. If the user asks to checkout their CART, delegate to authoritative create_order().
    if _is_cart_checkout_reference(ref_clean, action_clean):
        from backend.tools.order_tools import create_order
        return create_order(session_id=session_id)

    # Special global navigation actions
    if action_clean in ["back", "go_back", "previous"]:
        return {
            "status": "success",
            "action_type": "go_back",
            "message": "Navigating back to previous search results."
        }

    # Fetch both context buckets from the database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_product_ids, current_page_product_ids FROM session_states WHERE session_id = ?",
        (session_id,),
    )
    row = cursor.fetchone()

    conv_ids: List[str] = []
    current_ids: List[str] = []
    if row:
        try:
            if row["last_product_ids"]:
                conv_ids = json.loads(row["last_product_ids"])
        except Exception:
            conv_ids = []
        try:
            if row["current_page_product_ids"]:
                current_ids = json.loads(row["current_page_product_ids"])
        except Exception:
            current_ids = []

    # B. If this is a CURRENT-PAGE reference, use current_page_product_ids first,
    #    then fall back to conversation products if page context is empty.
    using_current_page = False
    source_ids = conv_ids
    if _is_current_page_reference(ref_clean):
        using_current_page = True
        source_ids = current_ids or conv_ids

    if not source_ids:
        # CART checkout fallback for empty checkout reference:
        # If action is checkout and no conversational products, try the authoritative cart.
        if action_clean in ("checkout", "proceed_to_checkout", "purchase"):
            from backend.tools.cart_tools import get_cart
            cart = get_cart(session_id=session_id)
            if cart and cart.get("items"):
                from backend.tools.order_tools import create_order
                return create_order(session_id=session_id)
            # Cart is empty → return that as the actual reason, not a "no products in context" error
            return {
                "status": "error",
                "message": "Your shopping cart is currently empty. Add products to your cart first, then checkout."
            }
        if using_current_page:
            return {
                "status": "error",
                "message": "NOVA does not have a current page product yet. Please open a valid product page in the browser with the NOVA extension active, then try again."
            }
        return {
            "status": "error",
            "message": "No active products found in conversation context. Please search for products first or add items to your cart."
        }

    ordered_products = _load_product_list(source_ids, conn)

    if not ordered_products:
        # Conversational product details missing → fall back for checkout to real cart.
        conn.close()
        if action_clean in ("checkout", "proceed_to_checkout", "purchase"):
            from backend.tools.cart_tools import get_cart
            cart = get_cart(session_id=session_id)
            if cart and cart.get("items"):
                from backend.tools.order_tools import create_order
                return create_order(session_id=session_id)
            return {
                "status": "error",
                "message": "Your shopping cart is currently empty. Add products to your cart first, then checkout."
            }
        return {
            "status": "error",
            "message": "Could not find details for recent products."
        }

    # Ensure connection is closed on every path after this point
    conn.close()

    # Filter valid individual products for cart & price selection
    valid_individual_products = [
        p for p in ordered_products
        if getattr(p, "is_individual_product", True) and p.price > 0
    ]
    if not valid_individual_products:
        valid_individual_products = [p for p in ordered_products if p.price > 0]

    # ── CHECKOUT routing: for action=checkout and EMPTY/GENERIC reference
    #    prefer the AUTHORITATIVE CART over any stale conversational product.
    if action_clean in ("checkout", "proceed_to_checkout", "purchase") and (
        not ref_clean
        or ref_clean in ("checkout", "proceed", "purchase", "pay", "buy")
    ):
        from backend.tools.cart_tools import get_cart
        cart = get_cart(session_id=session_id)
        if cart and cart.get("items"):
            from backend.tools.order_tools import create_order
            return create_order(session_id=session_id)

    selected_product: Optional[Product] = None

    # Resolution logic:
    # 1. Price relative ("cheaper", "cheapest", "expensive")
    price_candidates = valid_individual_products if valid_individual_products else ordered_products
    if any(k in ref_clean for k in ["cheaper", "cheapest", "lower price", "lowest", "least expensive"]):
        selected_product = min(price_candidates, key=lambda p: p.price)
    elif any(k in ref_clean for k in ["expensive", "priciest", "higher price", "highest"]):
        selected_product = max(price_candidates, key=lambda p: p.price)

    # 2. Ordinal resolution ("first", "second", "2nd", "last")
    if not selected_product:
        eval_list = valid_individual_products if (action_clean in ["add_to_cart", "add_cart", "buy", "checkout", "proceed_to_checkout", "purchase"] and valid_individual_products) else ordered_products
        ordinal_terms = [
            ("second", 1), ("2nd", 1), ("two", 1), ("2", 1), ("other", 1),
            ("third", 2), ("3rd", 2), ("three", 2), ("3", 2),
            ("fourth", 3), ("4th", 3), ("four", 3), ("4", 3),
            ("fifth", 4), ("5th", 4), ("five", 4), ("5", 4),
            ("last", -1), ("final", -1),
            ("first", 0), ("1st", 0), ("initial", 0),
            ("one", 0), ("1", 0)
        ]
        for term, idx in ordinal_terms:
            if re.search(r'\b' + re.escape(term) + r'\b', ref_clean):
                if -len(eval_list) <= idx < len(eval_list):
                    selected_product = eval_list[idx]
                    break

    # 3. Merchant / Source keyword matching ("amazon", "flipkart")
    if not selected_product:
        search_pool = valid_individual_products if (action_clean in ["add_to_cart", "add_cart", "buy", "checkout", "proceed_to_checkout", "purchase"] and valid_individual_products) else ordered_products
        for p in search_pool:
            m_name = (p.merchant_name or "").lower()
            b_name = (p.brand or "").lower()
            if (m_name and m_name in ref_clean) or (b_name and b_name in ref_clean):
                selected_product = p
                break

    # 4. Fallback keyword matching on title/name
    if not selected_product and ref_clean:
        ref_words = set(re.findall(r'[a-z0-9]+', ref_clean))
        best_match = None
        max_overlap = 0
        search_pool = valid_individual_products if (action_clean in ["add_to_cart", "add_cart", "buy", "checkout", "proceed_to_checkout", "purchase"] and valid_individual_products) else ordered_products
        for p in search_pool:
            title_words = set(re.findall(r'[a-z0-9]+', p.name.lower()))
            overlap = len(ref_words.intersection(title_words))
            if overlap > max_overlap:
                max_overlap = overlap
                best_match = p
        if best_match and max_overlap > 0:
            selected_product = best_match

    # Default to first product
    if not selected_product:
        if action_clean in ["add_to_cart", "add_cart", "buy", "checkout", "proceed_to_checkout", "purchase"] and valid_individual_products:
            selected_product = valid_individual_products[0]
        else:
            selected_product = ordered_products[0]

    # Perform action
    if action_clean in ["add_to_cart", "add_cart", "buy"]:
        if not getattr(selected_product, "is_individual_product", True) or selected_product.price <= 0:
            if valid_individual_products:
                selected_product = valid_individual_products[0]
            else:
                return {
                    "status": "error",
                    "message": "Cannot add generic search/browse results to cart. Only verified individual products can be added."
                }
        res = add_to_cart(selected_product.id, quantity=1, session_id=session_id)
        if "error" in res:
            return {"status": "error", "message": res["error"]}
        return {
            "status": "success",
            "action_type": "add_to_cart",
            "product": selected_product.to_dict(),
            "cart_result": res,
            "message": f"Added '{selected_product.name}' ({selected_product.currency} {selected_product.price}) to cart."
        }

    elif action_clean in ["checkout", "proceed_to_checkout", "purchase"]:
        # CHECKOUT SELECTED PRODUCT: validate individual product → stage into cart →
        # create internal order (bounds check + spending limit + Razorpay prep).
        if not getattr(selected_product, "is_individual_product", True) or selected_product.price <= 0:
            if valid_individual_products:
                selected_product = valid_individual_products[0]
            else:
                # Even without a conversation product, try authoritative cart.
                from backend.tools.cart_tools import get_cart
                cart = get_cart(session_id=session_id)
                if cart and cart.get("items"):
                    from backend.tools.order_tools import create_order
                    return create_order(session_id=session_id)
                return {
                    "status": "error",
                    "message": "Cannot checkout a generic search/listing page. Only a verified individual product or the items in your cart can be checked out."
                }

        # Stage product into the authoritative cart if not already there,
        # then build the NOVA order so expenditure limits + Razorpay apply.
        add_result = add_to_cart(selected_product.id, quantity=1, session_id=session_id)
        if "error" in add_result and "does not exist" not in str(add_result.get("error", "")):
            return {"status": "error", "message": add_result["error"]}

        from backend.tools.order_tools import create_order
        order_result = create_order(session_id=session_id)
        # Attach selected product context for UI friendliness
        if isinstance(order_result, dict) and order_result.get("success") and order_result.get("order"):
            order_result["selected_product"] = selected_product.to_dict()
            order_result["message"] = (
                f"Ready to checkout '{selected_product.name}' "
                f"({selected_product.currency} {selected_product.price}) from {selected_product.merchant_name}. "
                f"Please confirm payment in the order panel to continue."
            )
        return order_result

    else:  # "open", "navigate", "view"
        return {
            "status": "success",
            "action_type": "open_url",
            "url": selected_product.product_url,
            "product": selected_product.to_dict(),
            "is_individual_product": selected_product.is_individual_product,
            "result_type": selected_product.result_type,
            "message": f"Opening {selected_product.name} on {selected_product.merchant_name}: {selected_product.product_url}"
        }


def navigate_browser(
    action: str,
    url: Optional[str] = None,
    query: Optional[str] = None,
    merchant: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute direct browser navigation actions like opening a destination URL or going back."""
    action_clean = (action or "open").lower()
    if action_clean == "go_back" or action_clean == "back":
        return {
            "status": "success",
            "action_type": "go_back",
            "message": "Going back to previous page."
        }

    dest = url
    if not dest and query:
        from backend.agent.shop_planner import build_search_url, queue_navigation
        host = merchant or "www.flipkart.com"
        dest = build_search_url(host, query)
        if dest and session_id:
            queue_navigation(session_id, [dest])

    if dest:
        if session_id:
            from backend.agent.shop_planner import queue_navigation
            queue_navigation(session_id, [dest])
        return {
            "status": "success",
            "action_type": "navigate_tab",
            "url": dest,
            "message": f"Navigating to {dest}"
        }

    return {"status": "error", "message": "URL required for open action."}


# Schemas
resolve_product_action_schema = {
    "type": "function",
    "function": {
        "name": "resolve_product_action",
        "description": "Resolve natural language commands like 'open the second one', 'take me to the cheaper one', 'add the Amazon bottle to cart', or 'proceed to checkout' against active conversation products.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action type: 'open', 'add_to_cart', 'checkout', 'back'."
                },
                "target_reference": {
                    "type": "string",
                    "description": "Conversational reference string, e.g., 'second one', 'cheaper option', 'Amazon result', 'first shoe', 'this'."
                }
            },
            "required": ["action"]
        }
    }
}

navigate_browser_schema = {
    "type": "function",
    "function": {
        "name": "navigate_browser",
        "description": "Navigate the browser or open a destination URL explicitly.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Navigation action: 'open_url', 'go_back'."
                },
                "url": {
                    "type": "string",
                    "description": "Destination product or web page URL."
                },
                "query": {
                    "type": "string",
                    "description": "Search keywords used to construct a storefront search URL when url is omitted."
                },
                "merchant": {
                    "type": "string",
                    "description": "Storefront host or name such as flipkart.com or amazon.in."
                }
            },
            "required": ["action"]
        }
    }
}

def switch_mode(mode_name: str) -> Dict[str, Any]:
    """Switch active workspace mode (chat, discover, settings, cart, orders)."""
    m_clean = (mode_name or "chat").lower().strip()
    target_view = "view-chat"
    if "discover" in m_clean:
        target_view = "view-discover"
    elif "setting" in m_clean:
        target_view = "view-settings"
    elif "order" in m_clean:
        target_view = "view-orders"
    elif "catalog" in m_clean:
        target_view = "view-catalogue"
    elif "cart" in m_clean:
        target_view = "view-cart"

    return {
        "status": "success",
        "action_type": "switch_mode",
        "target_view": target_view,
        "mode_name": m_clean,
        "message": f"Switching to {m_clean} mode."
    }

switch_mode_schema = {
    "type": "function",
    "function": {
        "name": "switch_mode",
        "description": "Switch active workspace mode or navigate to a view (e.g. 'Switch to Discover', 'Open my orders', 'Go to home', 'Settings').",
        "parameters": {
            "type": "object",
            "properties": {
                "mode_name": {
                    "type": "string",
                    "description": "Mode name: 'discover', 'chat', 'settings', 'orders', 'cart', 'catalogue'."
                }
            },
            "required": ["mode_name"]
        }
    }
}

registry.register(resolve_product_action_schema, resolve_product_action)
registry.register(navigate_browser_schema, navigate_browser)
registry.register(switch_mode_schema, switch_mode)

