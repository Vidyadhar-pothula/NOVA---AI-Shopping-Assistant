"""Verify registry wrapper fix resolves the tool call argument issue without loop 2 fallback."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from backend.api.main import app
from backend.database.db import init_db, get_connection

init_db()
client = TestClient(app)

sid = "wrapper_fix_test"
# Cleanup
conn = get_connection()
cur = conn.cursor()
cur.execute("DELETE FROM cart_items WHERE cart_id = ?", (sid,))
cur.execute("DELETE FROM session_states WHERE session_id = ?", (sid,))
cur.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE session_id = ?)", (sid,))
cur.execute("DELETE FROM orders WHERE session_id = ?", (sid,))
conn.commit()
conn.close()

# Seed product
pid = "wr_earbuds_001"
import datetime
now = datetime.datetime.utcnow().isoformat() + "Z"
conn = get_connection()
cur = conn.cursor()
cur.execute("""INSERT OR REPLACE INTO products (
    id, name, brand, category, description, price, currency,
    rating, review_count, availability, merchant, merchant_name,
    source_name, product_url, specifications, images,
    retrieved_at, is_verified, is_demo, is_individual_product, result_type
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    (pid, "Wrapper Fix Earbuds", "BoAt", "Audio", "Test", 2999.0, "INR",
     4.2, 50, 1, "Amazon.in", "Amazon.in", "Amazon",
     f"https://amazon.in/dp/{pid}", json.dumps({}), json.dumps([]),
     now, 1, 0, 1, "individual_product"))
conn.commit()
conn.close()

# Add via cart tool
from backend.tools.cart_tools import add_to_cart
res = add_to_cart(pid, session_id=sid)
print(f"Add to cart: {res.get('success')}")

# Now call the chat endpoint — the wrapper fix should prevent loop 2
print("\n=== Calling /api/chat 'checkout my cart' ===")
r = client.post("/api/chat", json={
    "session_id": sid,
    "message": "checkout my cart",
})
chat = r.json()
print(f"status={r.status_code}")
print(f"tool executions: {len(chat.get('executed_tools', []))}")
for t in chat.get("executed_tools", []):
    print(f"  tool: {t.get('name')}")
    res = t.get("result") or {}
    if isinstance(res, dict):
        print(f"    result keys: {list(res.keys())[:8]}")
        print(f"    success: {res.get('success')} stage: {res.get('stage')}")
    elif isinstance(res, str) and "Error executing" in res:
        print(f"    ❌ STILL BROKEN: {res[:200]}")
    else:
        print(f"    result snippet: {str(res)[:150]}")
print(f"\nresponse snippet: {str(chat.get('response',''))[:300]}")
print(f"\npayment_handoff present: {'payment_handoff' in chat}")
if "payment_handoff" in chat:
    ph = chat["payment_handoff"]
    print(f"  -> razorpay_order_id: {ph.get('razorpay_order_id')}")
    print(f"  -> amount_paise: {ph.get('amount_paise')}")
    print(f"  -> currency: {ph.get('currency')}")
    print(f"  -> demo_mode: {ph.get('demo_mode')}")

# Confirm no 'got an unexpected keyword argument' errors
resp_text = str(chat.get("response", ""))
has_wrap_error = "unexpected keyword argument" in resp_text or "syntax error" in resp_text
print(f"\nWrapper fix result: {'❌ FAIL - still hitting errors' if has_wrap_error else '✅ PASS - clean execution'}")
sys.exit(1 if has_wrap_error else 0)
