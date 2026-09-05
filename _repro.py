"""Reproduction test for the CRITICAL bugs described."""
import json
import sys
sys.path.insert(0, "/Users/vidyadhar/razorpay hackathon")

from backend.database.db import init_db, get_connection
from backend.commerce.models import Product

print("=" * 60)
print("CRITICAL BUG REPRODUCTION TEST")
print("=" * 60)

init_db()

sid = "bug_repro_session"

# Clean up
conn = get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM products WHERE id IN ('bug_laptop_001')")
cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (sid,))
cursor.execute("DELETE FROM session_states WHERE session_id = ?", (sid,))
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE session_id = ?)", (sid,))
cursor.execute("DELETE FROM orders WHERE session_id = ?", (sid,))
conn.commit()

# Step 1: Insert a test product (like the Samsung Galaxy Book4 at Rs 79,990)
p = Product(
    id="bug_laptop_001",
    name="Samsung Galaxy Book4 Metal Business Laptop",
    brand="Samsung",
    category="Electronics > Computers > Laptops",
    description="Intel Core 7, 16GB, 512GB SSD",
    price=79990.0,
    currency="INR",
    rating=4.5,
    review_count=200,
    availability=True,
    merchant="Flipkart",
    merchant_name="Flipkart",
    source_name="Flipkart",
    product_url="https://flipkart.com/laptop-page",
    images=[],
    is_verified=True,
    is_individual_product=True,
    result_type="individual_product"
)

spec_json = json.dumps(p.specifications)
img_json = json.dumps(p.images)
cursor.execute("""
    INSERT INTO products (id, name, brand, category, description, price, currency,
        rating, review_count, availability, merchant, specifications, images,
        product_url, merchant_name, source_name, retrieved_at, is_verified,
        is_demo, is_individual_product, result_type)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    p.id, p.name, p.brand, p.category, p.description, p.price, p.currency,
    p.rating, p.review_count, 1, p.merchant, spec_json, img_json,
    p.product_url, p.merchant_name, p.source_name, p.retrieved_at,
    1, 0, 1, p.result_type
))
conn.commit()
conn.close()

print("\n=== Step 1: Product added. Add to cart. ===")
from backend.tools.cart_tools import add_to_cart, get_cart
res = add_to_cart(product_id="bug_laptop_001", quantity=1, session_id=sid)
print(f"Add to cart: {res.get('message', res.get('error', '?'))}")
cart = get_cart(session_id=sid)
print(f"Cart items: {len(cart['items'])}, total: {cart['total_amount']}")

print("\n=== Step 2: Agent says 'checkout my cart' → should route via CART, NOT recent products ===")
# NOTE: intentionally NOT setting last_product_ids / conversation products
# This simulates products being added via extension without conversation context
from backend.tools.action_tools import resolve_product_action

# BUG 3 reproduction: action=checkout, target_ref="my cart" when session has no recent products
rpa = resolve_product_action(action="checkout", target_reference="my cart", session_id=sid)
print(f"resolve_product_action(checkout, my cart): status={rpa.get('status')} success={rpa.get('success')}")
if rpa.get('status') == 'error':
    print(f"  ERROR MESSAGE: {rpa.get('message')}")
    print("  >>> BUG 3 CONFIRMED: CART CHECKOUT FAILED due to missing recent products!")
elif rpa.get('success'):
    print(f"  >>> OK: order prepared: id={rpa.get('order', {}).get('id')}, requires_confirmation={rpa.get('order', {}).get('requires_confirmation')}")
else:
    print(f"  Full result: {json.dumps(rpa, indent=2)[:500]}")

# Now let's test: what if conversation has a prepared order, and user says "yes"?
# We need to trace: does "yes" trigger actual payment flow?
print("\n=== Step 3: Simulate agent handling 'yes' confirmation after order prepared ===")
# Let's re-create an order first
order_res = resolve_product_action(action="checkout", target_reference="my cart", session_id=sid)
order_id = None
if order_res.get('success'):
    order_id = order_res['order']['id']
    print(f"Order prepared: {order_id}, status: {order_res['order']['status']}")
    print(f"Cart still has items: {len(get_cart(session_id=sid)['items'])} (expected 1)")

print("\n=== Step 4: Check main.py for payment verification flow ===")
# The problem: when user says "yes", does the agent:
# 1. Call create_payment_order? (call backend endpoint /api/payment/create-order)
# 2. Actually wait for payment verification?
# 3. Clear cart only AFTER verification?
# Currently, the agent just calls create_order which prepares an order but doesn't actually go to payment.
# The agent then says "order placed successfully" on its own.

print("\nBUG 1 ANALYSIS:")
print(" create_order() returns an order in status 'prepared' with requires_confirmation=True.")
print(" But there is NO TOOL defined for: proceed_to_payment / confirm_checkout / verify_payment!")
print(" Agent has: create_order tool, but NO 'confirm_order' tool.")
print(" So when user says 'yes', LLM has NO tool to trigger payment flow.")
print(" Therefore LLM just generates: 'order placed' text based on create_order message.")
print()
print("BUG 2 ANALYSIS:")
print(" clear_cart() is called in main.py payment_verify() only AFTER verification.")
print(" But the agent never reaches payment_verify() because there's no confirm tool!")
print()
print("BUG 3 ANALYSIS:")
print(" resolve_product_action() has fallback for cart checkout in multiple places,")
print(" but _is_cart_checkout_reference() gate may not match 'checkout my cart' correctly OR")
print(" fallthrough paths may not catch all cases.")

print("\n=== Step 5: Detailed test of _is_cart_checkout_reference ===")
from backend.tools.action_tools import _is_cart_checkout_reference
tests = [
    ("my cart", "checkout"),
    ("the cart", "checkout"),
    ("cart", "checkout"),
    ("everything in my cart", "purchase"),
    ("my items", "checkout"),
    ("", "checkout"),
    ("checkout", "checkout"),
    ("second one", "checkout"),
    ("this product", "checkout"),
]
print("_is_cart_checkout_reference tests:")
for ref, action in tests:
    result = _is_cart_checkout_reference(ref, action)
    print(f"  ref={repr(ref)}, action={repr(action)} -> {result}")

# Cleanup
print("\nCleanup...")
conn = get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM products WHERE id = 'bug_laptop_001'")
cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (sid,))
cursor.execute("DELETE FROM session_states WHERE session_id = ?", (sid,))
cursor.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE session_id = ?)", (sid,))
cursor.execute("DELETE FROM orders WHERE session_id = ?", (sid,))
conn.commit()
conn.close()

print("\n=== REPRODUCTION COMPLETE ===")
