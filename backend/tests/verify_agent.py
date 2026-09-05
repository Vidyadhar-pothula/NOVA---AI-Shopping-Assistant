import os
import sys
import json

# Add parent directory to path so backend imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database.db import init_db, get_connection
from backend.agent.agent import run_agent, clear_session

def run_test():
    session_id = "test_verification_session"
    
    print("\n=== STEP 1: INITIALIZE DATABASE ===")
    init_db()
    
    print("\n=== STEP 2: CLEAR SESSION ===")
    clear_session(session_id)
    
    # Check that database starts fresh for the test
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cart_items WHERE cart_id = ?", (session_id,))
    assert cursor.fetchone()[0] == 0, "Cart should be empty at start"
    conn.close()

    print("\n=== STEP 3: RUN FLOW ===")
    
    # 1. Search products
    q1 = "Find me running shoes under ₹5000."
    print(f"\nUser: {q1}")
    res1 = run_agent(session_id, q1)
    print(f"NOVA: {res1['response']}")
    print(f"Executed tools: {[t['name'] for t in res1['executed_tools']]}")
    
    # 2. Compare products
    q2 = "Compare the first two."
    print(f"\nUser: {q2}")
    res2 = run_agent(session_id, q2)
    print(f"NOVA: {res2['response']}")
    print(f"Executed tools: {[t['name'] for t in res2['executed_tools']]}")
    
    # 3. Add to cart
    q3 = "Add the first one to my cart."
    print(f"\nUser: {q3}")
    res3 = run_agent(session_id, q3)
    print(f"NOVA: {res3['response']}")
    print(f"Executed tools: {[t['name'] for t in res3['executed_tools']]}")
    
    # Check cart state in DB
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), product_id FROM cart_items WHERE cart_id = ?", (session_id,))
    count, prod_id = cursor.fetchone()
    print(f"DB Check: Cart has {count} item(s) (Product ID: {prod_id})")
    assert count == 1, "Cart should contain exactly 1 item"
    conn.close()

    # 4. Check total
    q4 = "What's my total?"
    print(f"\nUser: {q4}")
    res4 = run_agent(session_id, q4)
    print(f"NOVA: {res4['response']}")
    print(f"Executed tools: {[t['name'] for t in res4['executed_tools']]}")
    
    # 5. Create order
    q5 = "Create the order."
    print(f"\nUser: {q5}")
    res5 = run_agent(session_id, q5)
    print(f"NOVA: {res5['response']}")
    print(f"Executed tools: {[t['name'] for t in res5['executed_tools']]}")
    
    # Check order state in DB
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, total_amount FROM orders WHERE session_id = ? ORDER BY created_at DESC LIMIT 1", (session_id,))
    order_row = cursor.fetchone()
    assert order_row is not None, "An order should have been created in the database"
    print(f"DB Check: Created order with status '{order_row['status']}' and total amount ₹{order_row['total_amount']}")
    assert order_row["status"] == "prepared", "Order status should be 'prepared'"
    
    # Check cart is cleared
    cursor.execute("SELECT COUNT(*) FROM cart_items WHERE cart_id = ?", (session_id,))
    assert cursor.fetchone()[0] == 0, "Cart should be cleared after order creation"
    print("DB Check: Cart has been successfully cleared.")
    
    conn.close()
    
    print("\n=== INTEGRATION TEST COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_test()
