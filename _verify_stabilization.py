"""Stabilization verification: cart intercept, checkout-without-recent, bounds, catalogue."""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database.db import init_db, get_connection
from backend.tools.cart_tools import add_to_cart, get_cart, clear_cart
from backend.tools.order_tools import create_order
from backend.agent.agent import run_agent, update_current_page_products, update_active_products
from backend.agent.commerce_router import classify_commerce_intent, rewrite_tool_calls
from backend.providers.bounds_provider import bounds_service, set_configured_spending_limit
from backend.providers.catalog_provider import catalog_service

SID = "verify_stabilization_session"
PASSES = []
FAILS = []


def check(name, cond, detail=""):
    if cond:
        PASSES.append(name)
        print(f"PASS  {name}")
    else:
        FAILS.append(name)
        print(f"FAIL  {name}  {detail}")


def seed_product(pid, name, price, url, individual=True):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO products (
            id, name, brand, category, description, price, currency, availability,
            merchant, merchant_name, source_name, product_url, is_verified, is_demo,
            is_individual_product, result_type
        ) VALUES (?, ?, ?, ?, ?, ?, 'INR', 1, ?, ?, ?, ?, 1, 0, ?, ?)""",
        (
            pid, name, "BrandX", "electronics", "seed", price, "Seed Store", "Seed Store",
            "seed", url, 1 if individual else 0,
            "individual_product" if individual else "browse_list",
        ),
    )
    conn.commit()
    conn.close()


def main():
    init_db()
    clear_cart(SID)
    set_configured_spending_limit(None)

    p1 = "seed_" + uuid.uuid4().hex[:8]
    p2 = "seed_" + uuid.uuid4().hex[:8]
    seed_product(p1, "Dynamic Seed Speaker", 1799, "https://merchant.example/p/speaker-1")
    seed_product(p2, "Dynamic Seed Mouse", 499, "https://merchant.example/p/mouse-1")

    add_to_cart(p1, 1, SID)
    add_to_cart(p2, 2, SID)
    cart = get_cart(SID)
    check("authoritative cart has two items", len(cart["items"]) == 2, cart)
    check("cart total is 1799+998", abs(cart["total_amount"] - (1799 + 998)) < 0.01, cart["total_amount"])

    check("intent cart_query", classify_commerce_intent("What's in my cart?") == "cart_query")
    check("intent checkout_cart", classify_commerce_intent("checkout my cart") == "checkout_cart")
    check("intent confirm", classify_commerce_intent("Yes, proceed") == "confirm_payment")

    wrapped = "User message: show me my cart\n\nUse this current shopping page as context."
    nova = run_agent(SID, wrapped)
    tools = [t["name"] for t in nova.get("executed_tools") or []]
    check("NOVA cart query uses get_cart", tools == ["get_cart"], tools)
    check("NOVA cart query names speaker", "Dynamic Seed Speaker" in (nova.get("response") or ""), nova.get("response"))
    check("NOVA cart query names mouse", "Dynamic Seed Mouse" in (nova.get("response") or ""), nova.get("response"))
    check("NOVA does not say recent products", "recent products" not in (nova.get("response") or "").lower())

    rewritten = rewrite_tool_calls(
        [{"name": "resolve_product_action", "arguments": {"action": "checkout", "target_reference": "my cart"}},
         {"name": "check_inventory", "arguments": {"product_id": ""}}],
        "checkout my cart",
    )
    check("rewrite checkout my cart -> create_order", any(t["name"] == "create_order" for t in rewritten), rewritten)
    check("rewrite drops empty check_inventory", not any(t["name"] == "check_inventory" for t in rewritten), rewritten)

    update_active_products(SID, [])
    update_current_page_products(SID, [])
    checkout = run_agent(SID, "Checkout my cart.")
    checkout_tools = [t["name"] for t in checkout.get("executed_tools") or []]
    check("checkout without recent context uses create_order", "create_order" in checkout_tools, checkout_tools)
    check("checkout does not mention recent products", "recent products" not in (checkout.get("response") or "").lower())
    check("checkout asks confirmation", "confirm" in (checkout.get("response") or "").lower() or "yes" in (checkout.get("response") or "").lower(), checkout.get("response"))
    check("checkout does not claim paid", "successfully placed" not in (checkout.get("response") or "").lower())

    bounds = bounds_service.validate_transaction_bounds(999999, session_id=SID)
    check("no invented expenditure limit", bounds["permitted"] is True, bounds)

    set_configured_spending_limit(100)
    bounds2 = bounds_service.validate_transaction_bounds(1799, session_id=SID)
    check("configured limit blocks over-limit cart", bounds2["permitted"] is False, bounds2)
    set_configured_spending_limit(None)

    cat = catalog_service.inspect_session_catalog(SID)
    check("empty catalogue is empty not hardcoded", cat["summary"]["total_valid"] == 0, cat)

    update_current_page_products(SID, [p1, p2], page_url="https://merchant.example/search?q=audio", source_name="merchant.example")
    cat2 = catalog_service.inspect_session_catalog(SID)
    check("session catalogue uses canonical products", cat2["summary"]["total_valid"] == 2, cat2)
    names = [p["name"] for p in cat2["products"]]
    check("catalogue has no fake demo names", "Acer" not in str(names) and "headphones" not in str(names).lower(), names)
    check("catalogue includes exact URLs", all(p.get("product_url", "").startswith("http") for p in cat2["products"]))

    listing = seed_product("list_" + uuid.uuid4().hex[:6], "Headphones Search", 0, "https://merchant.example/search?q=headphones", individual=False)
    # listing helper returns None; product already inserted
    from backend.tools.cart_tools import add_to_cart as _add
    # find listing id
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM products WHERE product_url LIKE '%search?q=headphones%' AND is_individual_product = 0")
    row = c.fetchone()
    conn.close()
    if row:
        res = _add(row["id"], 1, SID)
        check("listing page cannot enter cart", "error" in res, res)

    after = get_cart(SID)
    check("cart preserved after listing reject", any(i["product"]["id"] in {p1, p2} for i in after["items"]))

    print("\n==== SUMMARY ====")
    print(f"PASS {len(PASSES)}  FAIL {len(FAILS)}")
    if FAILS:
        print("Failed:", FAILS)
        sys.exit(1)


if __name__ == "__main__":
    main()
