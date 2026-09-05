"""Deterministic commerce routing that does not depend on the LLM.

Cart queries, cart checkout, payment confirmation, and catalogue mode
must hit the authoritative backend services — never recent-product context.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.database.db import get_connection
from backend.commerce.models import Product


def extract_user_intent(message: str) -> str:
    match = re.search(
        r"^\s*User message:\s*(.+?)\s*$",
        message or "",
        re.IGNORECASE | re.MULTILINE,
    )
    if match:
        return match.group(1).strip()
    return (message or "").strip()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_commerce_intent(message: str) -> str:
    raw = extract_user_intent(message)
    t = _norm(raw)
    t = re.sub(r"[.!?]+$", "", t)
    if not t:
        return "none"

    if re.search(r"\b(checkout|buy|purchase|pay for)\b.{0,40}\bthis\b", t) or re.search(
        r"\b(this product|this page|this item|the (first|second|third|cheaper|cheapest) one)\b",
        t,
    ) and re.search(r"\b(checkout|buy|purchase)\b", t):
        if re.search(r"\b(my cart|the cart|shopping cart)\b", t):
            return "checkout_cart"
        return "checkout_product"

    if re.search(
        r"\b(checkout(\s+my)?\s+cart|checkout the cart|buy (what'?s|everything) in my cart|"
        r"pay for my cart|proceed to checkout|checkout my items)\b",
        t,
    ) or t in {
        "checkout",
        "checkout cart",
        "checkout my cart",
        "proceed to checkout",
        "buy my cart",
    }:
        return "checkout_cart"

    if re.search(
        r"\b(what'?s in my cart|show( me)?( my)? cart|view( my)? cart|my cart|"
        r"cart contents|shopping cart)\b",
        t,
    ) and not re.search(r"\b(add|put|place|checkout|buy|clear|empty|remove)\b", t):
        return "cart_query"

    if t in {"cart", "show cart", "view cart", "my cart?", "what's in my cart?"}:
        return "cart_query"

    if re.search(
        r"\b(catalogue mode|catalog mode|enter catalogue|enter catalog|"
        r"open catalogue|open catalog|analyse this page|analyze this page|"
        r"what products (are )?(available|on this page)|show( me)? (the )?catalogue|"
        r"show( me)? (the )?catalog)\b",
        t,
    ):
        return "catalogue"

    if re.fullmatch(
        r"(yes|yep|yeah|y|confirm|confirmed|proceed|proceed to payment|"
        r"yes,? proceed|yes proceed to payment|pay|let'?s pay|okay go|"
        r"ok proceed|go ahead|yes i want to pay|yes,? pay)",
        t,
    ):
        return "confirm_payment"

    if re.fullmatch(r"(no|nope|cancel|wait|hold on|not now|stop)", t):
        return "decline_payment"

    if re.search(r"\b(add|put|place)\b.{0,30}\bthis\b.{0,20}\bcart\b", t) or t in {
        "add this",
        "add this to cart",
        "add this to my cart",
        "buy this",
    }:
        return "add_this"

    if re.search(r"\badd (this|the)?\s*(page|listing|search)\b.{0,20}\bcart\b", t):
        return "add_this_page"

    return "none"


def get_session_flag(session_id: str, column: str) -> Optional[str]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT {column} FROM session_states WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
    except Exception:
        conn.close()
        return None
    conn.close()
    if not row:
        return None
    return row[0]


def set_session_flag(session_id: str, column: str, value: Optional[str]) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO session_states (session_id, updated_at)
        VALUES (?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """,
        (session_id,),
    )
    cursor.execute(
        f"UPDATE session_states SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
        (value, session_id),
    )
    conn.commit()
    conn.close()


def get_pending_order_id(session_id: str) -> Optional[str]:
    return get_session_flag(session_id, "pending_order_id")


def set_pending_order_id(session_id: str, order_id: Optional[str]) -> None:
    set_session_flag(session_id, "pending_order_id", order_id)


def load_products_by_ids(ids_list: List[str]) -> List[Product]:
    if not ids_list:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids_list)
    cursor.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", ids_list)
    rows = cursor.fetchall()
    conn.close()
    prod_map = {r["id"]: Product.from_row(r) for r in rows}
    return [prod_map[pid] for pid in ids_list if pid in prod_map]


def get_current_page_product_ids(session_id: str) -> List[str]:
    raw = get_session_flag(session_id, "current_page_product_ids")
    if not raw:
        return []
    try:
        ids = json.loads(raw)
        return ids if isinstance(ids, list) else []
    except Exception:
        return []


def format_cart_reply(cart: Dict[str, Any]) -> str:
    items = cart.get("items") or []
    currency = cart.get("currency") or "INR"
    if not items:
        return "Your shopping cart is empty."

    lines = [f"Here is what is currently in your cart ({len(items)} item(s)):"]
    for idx, item in enumerate(items, start=1):
        prod = item.get("product") or {}
        name = prod.get("name") or "Unnamed item"
        qty = item.get("quantity") or 1
        price = prod.get("price")
        subtotal = item.get("subtotal")
        merchant = prod.get("merchant_name") or prod.get("merchant") or ""
        url = prod.get("product_url") or ""
        curr = prod.get("currency") or currency
        parts = [f"{idx}. {name} × {qty}"]
        if merchant:
            parts.append(f"from {merchant}")
        if price is not None:
            parts.append(f"at {curr} {price}")
        if subtotal is not None:
            parts.append(f"(subtotal {curr} {subtotal})")
        line = " ".join(parts)
        if url:
            line += f"\n   URL: {url}"
        lines.append(line)
    total = cart.get("total_amount")
    lines.append(f"\nCart total: {currency} {total}")
    return "\n".join(lines)


def format_order_review(order_result: Dict[str, Any]) -> str:
    if order_result.get("error"):
        return order_result["error"]
    order = order_result.get("order") or {}
    items = order.get("items") or []
    currency = order.get("currency") or "INR"
    total = order.get("total_amount")
    lines = [
        "I've prepared your order for review. No payment has been taken and your cart is unchanged.",
        "",
    ]
    for item in items:
        lines.append(
            f"- {item.get('quantity')}× {item.get('name')} "
            f"({currency} {item.get('subtotal')})"
        )
    lines.append(f"\nOrder total: {currency} {total}")
    lines.append(
        "Shall I proceed to Razorpay TEST payment? Reply with 'yes' / 'confirm' / 'proceed to payment' to continue, or 'no' to cancel."
    )
    return "\n".join(lines)


def format_catalogue_reply(payload: Dict[str, Any]) -> str:
    source = payload.get("source") or {}
    summary = payload.get("summary") or {}
    products = payload.get("products") or []
    merchant = source.get("merchant_name")
    page_url = source.get("page_url")
    lines = ["Catalogue Mode"]
    if merchant:
        lines.append(f"Source: {merchant}")
    if page_url:
        lines.append(f"Page: {page_url}")
    lines.append(f"Products detected: {summary.get('total_detected', len(products))}")
    lines.append(f"Valid products: {summary.get('total_valid', 0)}")
    if not products:
        lines.append(
            "\nNo purchasable products are available from the current page context. "
            "Open a supported ecommerce product or listing page with the NOVA extension active."
        )
        return "\n".join(lines)

    lines.append("\nProducts")
    lines.append("────────────────────")
    for idx, p in enumerate(products, start=1):
        lines.append(f"{idx}. {p.get('name') or 'Product'}")
        if p.get("brand"):
            lines.append(f"   Brand: {p['brand']}")
        if p.get("category"):
            lines.append(f"   Category: {p['category']}")
        if p.get("price") is not None:
            curr = p.get("currency") or ""
            lines.append(f"   Price: {curr} {p['price']}".strip())
        if p.get("availability") is not None:
            lines.append(f"   Availability: {'in stock' if p.get('availability') else 'unavailable'}")
        if p.get("rating") is not None:
            lines.append(f"   Rating: {p['rating']}")
        if p.get("image_url") or (p.get("images") or [None])[0]:
            img = p.get("image_url") or (p.get("images") or [None])[0]
            if img:
                lines.append(f"   Image: {img}")
        if p.get("product_url"):
            lines.append(f"   URL: {p['product_url']}")
        if p.get("id"):
            lines.append(f"   Product ID: {p['id']}")
        lines.append("────────────────────")
    return "\n".join(lines)


def _tool_record(name: str, arguments: Dict[str, Any], result: Any) -> Dict[str, Any]:
    return {
        "name": name,
        "arguments": arguments,
        "result": result,
    }


def try_deterministic_commerce(session_id: str, user_message: str) -> Optional[Dict[str, Any]]:
    """Return a completed agent payload when the intent must not go through the LLM."""
    intent = classify_commerce_intent(user_message)

    if intent == "cart_query":
        from backend.tools.cart_tools import get_cart
        from backend.providers.audit_provider import audit_service

        cart = get_cart(session_id)
        audit_service.record_event(
            session_id=session_id,
            event_type="CART_QUERY",
            data={
                "item_count": len(cart.get("items") or []),
                "total_amount": cart.get("total_amount"),
                "currency": cart.get("currency"),
            },
        )
        return {
            "response": format_cart_reply(cart),
            "executed_tools": [_tool_record("get_cart", {}, cart)],
        }

    if intent == "checkout_cart":
        from backend.tools.order_tools import create_order
        from backend.providers.audit_provider import audit_service

        audit_service.record_event(
            session_id=session_id,
            event_type="USER_CHECKOUT_REQUEST",
            data={"intent": "checkout_cart", "message": extract_user_intent(user_message)},
        )
        result = create_order(session_id=session_id)
        if result.get("success") and result.get("order"):
            set_pending_order_id(session_id, result["order"]["id"])
            audit_service.record_event(
                session_id=session_id,
                event_type="CONFIRMATION_REQUESTED",
                data={"order_id": result["order"]["id"], "total_amount": result["order"].get("total_amount")},
            )
            return {
                "response": format_order_review(result),
                "executed_tools": [_tool_record("create_order", {}, result)],
            }
        return {
            "response": result.get("error") or "Checkout could not be prepared from the cart.",
            "executed_tools": [_tool_record("create_order", {}, result)],
        }

    if intent == "confirm_payment":
        pending = get_pending_order_id(session_id)
        if not pending:
            return None
        from backend.tools.order_tools import proceed_to_payment
        from backend.providers.audit_provider import audit_service

        audit_service.record_event(
            session_id=session_id,
            event_type="USER_CONFIRMED",
            data={"order_id": pending},
        )
        result = proceed_to_payment(order_id=pending, session_id=session_id)
        if result.get("error"):
            return {
                "response": result["error"],
                "executed_tools": [_tool_record("proceed_to_payment", {"order_id": pending}, result)],
            }
        return {
            "response": (
                "Please complete the Razorpay TEST Checkout panel that has just appeared. "
                "I will confirm your order only after payment is successfully verified."
            ),
            "executed_tools": [_tool_record("proceed_to_payment", {"order_id": pending}, result)],
        }

    if intent == "decline_payment":
        pending = get_pending_order_id(session_id)
        if not pending:
            return None
        set_pending_order_id(session_id, None)
        return {
            "response": "Payment cancelled. Your cart is unchanged.",
            "executed_tools": [],
        }

    if intent == "catalogue":
        from backend.providers.catalog_provider import catalog_service
        from backend.tools.action_tools import switch_mode

        mode = switch_mode("catalogue")
        payload = catalog_service.inspect_session_catalog(session_id)
        products = payload.get("products") or []
        valid_ids = [p["id"] for p in products if p.get("id") and p.get("is_individual_product", True)]
        if valid_ids:
            from backend.agent.agent import update_active_products
            update_active_products(session_id, valid_ids)
        return {
            "response": format_catalogue_reply(payload),
            "executed_tools": [
                _tool_record("switch_mode", {"mode_name": "catalogue"}, mode),
                _tool_record("inspect_catalog", {"session_id": session_id}, payload),
            ],
        }

    from backend.agent.shop_planner import looks_like_accessory_request, looks_like_shop_search, try_shop_turn
    if looks_like_accessory_request(user_message) or looks_like_shop_search(user_message):
        shop_payload = try_shop_turn(session_id, user_message)
        if shop_payload:
            return shop_payload

    if intent in {"add_this", "add_this_page"}:
        from backend.tools.action_tools import resolve_product_action

        result = resolve_product_action(
            action="add_to_cart",
            target_reference="this",
            session_id=session_id,
        )
        return {
            "response": result.get("message") or result.get("error") or "Could not add this page item to the cart.",
            "executed_tools": [_tool_record("resolve_product_action", {"action": "add_to_cart", "target_reference": "this"}, result)],
        }

    return None


def rewrite_tool_calls(
    tool_calls: List[Dict[str, Any]],
    user_message: str,
) -> List[Dict[str, Any]]:
    """Correct unsafe LLM routing before tools execute."""
    intent = classify_commerce_intent(user_message)
    rewritten: List[Dict[str, Any]] = []
    for tc in tool_calls:
        name = tc.get("name")
        args = dict(tc.get("arguments") or {})

        if name == "check_inventory":
            pid = str(args.get("product_id") or "").strip()
            if not pid or intent in {"cart_query", "checkout_cart", "confirm_payment"}:
                continue

        if intent == "cart_query":
            if name != "get_cart":
                continue
        if intent == "checkout_cart":
            if name in {"resolve_product_action", "check_inventory", "get_product_details"}:
                rewritten.append({"name": "create_order", "arguments": {}})
                continue
        if intent == "confirm_payment" and name != "proceed_to_payment":
            continue

        if name == "add_to_cart":
            pid = str(args.get("product_id") or "").strip()
            looks_like_phrase = (
                not pid
                or " " in pid
                or pid.lower() in {"this", "that", "it", "second", "first", "headphones", "product"}
            )
            if looks_like_phrase:
                rewritten.append({
                    "name": "resolve_product_action",
                    "arguments": {"action": "add_to_cart", "target_reference": pid or "this"},
                })
                continue

        rewritten.append({"name": name, "arguments": args})

    if intent == "cart_query" and not any(t["name"] == "get_cart" for t in rewritten):
        rewritten = [{"name": "get_cart", "arguments": {}}]
    if intent == "checkout_cart" and not any(t["name"] == "create_order" for t in rewritten):
        rewritten = [{"name": "create_order", "arguments": {}}]
    return rewritten
