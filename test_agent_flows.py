import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.agent.agent import run_agent, clear_session

def test_flows():
    session_id = "test_verification_session"
    clear_session(session_id)

    print("--- TEST 1: Product Search ---")
    res1 = run_agent(session_id, "Find me a steel water bottle under ₹1000.")
    print("Response 1:", res1.get("response"))
    print("Executed tools 1:", [t["name"] for t in res1.get("executed_tools", [])])

    print("\n--- TEST 2: Ordinal Reference 'Open the second one' ---")
    res2 = run_agent(session_id, "Open the second one.")
    print("Response 2:", res2.get("response"))
    print("Executed tools 2:", [t["name"] for t in res2.get("executed_tools", [])])

    print("\n--- TEST 3: Navigation 'Go back' ---")
    res3 = run_agent(session_id, "Go back.")
    print("Response 3:", res3.get("response"))
    print("Executed tools 3:", [t["name"] for t in res3.get("executed_tools", [])])

    print("\n--- TEST 4: Cart 'Add the first one to cart' ---")
    res4 = run_agent(session_id, "Add the first one to cart.")
    print("Response 4:", res4.get("response"))
    print("Executed tools 4:", [t["name"] for t in res4.get("executed_tools", [])])

    print("\n--- TEST 5: Checkout 'Proceed to checkout' ---")
    res5 = run_agent(session_id, "Proceed to checkout.")
    print("Response 5:", res5.get("response"))
    print("Executed tools 5:", [t["name"] for t in res5.get("executed_tools", [])])

    print("\n--- TEST 6: Discover 'What's new?' ---")
    res6 = run_agent(session_id, "What's new?")
    print("Response 6:", res6.get("response"))
    print("Executed tools 6:", [t["name"] for t in res6.get("executed_tools", [])])

    print("\n--- TEST 7 & 8: Sports & Merchandise ---")
    res7 = run_agent(session_id, "Any major sports events coming up? Show me merchandise.")
    print("Response 7:", res7.get("response"))
    print("Executed tools 7:", [t["name"] for t in res7.get("executed_tools", [])])

    print("\n--- TEST 9: Region-aware discovery 'What's happening in India this month?' ---")
    res9 = run_agent(session_id, "What's happening in India this month?")
    print("Response 9:", res9.get("response"))
    print("Executed tools 9:", [t["name"] for t in res9.get("executed_tools", [])])

    print("\n--- TEST 10: Calendar 'Add the World Cup final to my calendar' ---")
    res10 = run_agent(session_id, "Add the World Cup final to my calendar.")
    print("Response 10:", res10.get("response"))
    print("Executed tools 10:", [t["name"] for t in res10.get("executed_tools", [])])

    print("\n--- TEST 11: Email 'Email me today's best deals' ---")
    res11 = run_agent(session_id, "Email me today's best deals.")
    print("Response 11:", res11.get("response"))
    print("Executed tools 11:", [t["name"] for t in res11.get("executed_tools", [])])

    print("\n--- TEST 12: Price-relative reference 'Open the cheaper one' ---")
    res12 = run_agent(session_id, "Open the cheaper one.")
    print("Response 12:", res12.get("response"))
    print("Executed tools 12:", [t["name"] for t in res12.get("executed_tools", [])])

if __name__ == "__main__":
    test_flows()
