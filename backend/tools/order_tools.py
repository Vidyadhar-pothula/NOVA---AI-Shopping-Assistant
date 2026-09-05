import uuid
from typing import Dict, Any
from backend.database.db import get_connection
from backend.tools.cart_tools import get_cart
from backend.tools.registry import registry

def create_order(session_id: str = "default_session", **kwargs) -> Dict[str, Any]:
    """Prepare and create a new ORDER-PREPARED record from the items currently in the active cart.

    IMPORTANT SAFETY NOTES (enforced both here and in the agent system prompt):
    * This function ONLY prepares an order (status = "prepared") with
      requires_confirmation=True. It does NOT perform any payment, does NOT
      clear the cart, does NOT send a success email, and does NOT record a
      successful order outcome.
    * The shopping cart remains completely unchanged until payment has been
      VERIFIED through the Razorpay payment flow.
    * The agent must NEVER tell the user that their order was placed based on
      the output of this function alone.
    * After calling this, the agent MUST ask the user for explicit confirmation
      AND (once confirmed) call proceed_to_payment to generate the
      Razorpay order + handoff to the payment UI.
    """
    cart = get_cart(session_id)
    
    if not cart or not cart.get("items"):
        return {"error": "Your shopping cart is empty. Please add items to your cart before ordering."}
        
    conn = get_connection()
    cursor = conn.cursor()
    
    order_id = f"ord_{uuid.uuid4().hex[:10]}"
    total_amount = cart["total_amount"]
    currency = cart.get("currency", "INR")
    total_quantity = sum(item.get("quantity", 1) for item in cart["items"])

    # Phase 5: Bounded Money Actions validation
    from backend.providers.bounds_provider import bounds_service
    from backend.providers.audit_provider import audit_service

    audit_service.record_event(
        session_id=session_id,
        event_type="CART_RETRIEVED",
        data={
            "item_count": len(cart["items"]),
            "total_amount": total_amount,
            "currency": currency,
        },
    )
    audit_service.record_event(
        session_id=session_id,
        event_type="CART_VALIDATED",
        data={"items": [{"id": i["product"]["id"], "qty": i["quantity"]} for i in cart["items"]]},
    )

    bounds_check = bounds_service.validate_transaction_bounds(
        total_amount=total_amount,
        quantity=total_quantity,
        currency=currency,
        session_id=session_id,
    )

    if not bounds_check["permitted"]:
        audit_service.record_event(
            session_id=session_id,
            event_type="TRANSACTION_BOUNDS_EXCEEDED",
            data=bounds_check
        )
        conn.close()
        return {
            "error": bounds_check["message"],
            "bounds_exceeded": True,
            "blocks_payment": True
        }

    audit_service.record_event(
        session_id=session_id,
        event_type="EXPENDITURE_VALIDATION",
        data=bounds_check,
    )
    
    try:
        cursor.execute("""
            INSERT INTO orders (id, session_id, status, total_amount, currency) 
            VALUES (?, ?, ?, ?, ?)
        """, (order_id, session_id, "prepared", total_amount, currency))
        
        order_items_list = []
        for item in cart["items"]:
            prod = item["product"]
            qty = item["quantity"]
            price = prod["price"]
            
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price) 
                VALUES (?, ?, ?, ?)
            """, (order_id, prod["id"], qty, price))
            
            order_items_list.append({
                "product_id": prod["id"],
                "name": prod["name"],
                "quantity": qty,
                "price": price,
                "subtotal": qty * price,
                "merchant": prod.get("merchant_name") or prod.get("merchant"),
                "product_url": prod.get("product_url"),
            })
            
        conn.commit()
        
        audit_service.record_event(
            session_id=session_id,
            event_type="ORDER_PREPARED",
            data={
                "order_id": order_id,
                "total_amount": total_amount,
                "currency": currency,
                "items_count": len(order_items_list),
                "requires_explicit_payment_confirmation": True,
                "cart_not_cleared_yet": True
            }
        )
        
        items_str = "; ".join(
            f"{i['quantity']}x {i['name']} ({currency} {i['subtotal']:.2f})"
            for i in order_items_list
        )
        
        return {
            "success": True,
            "stage": "order_prepared_payment_required",
            "next_action_required": "CALL proceed_to_payment AFTER user explicitly confirms these items and amount",
            "message": (
                f"Order {order_id} has been PREPARED for your review. It contains: {items_str}. "
                f"Order total: {currency} {total_amount:.2f}. "
                f"NO PAYMENT HAS BEEN TAKEN AND YOUR CART IS UNCHANGED. "
                f"Ask the user to confirm explicitly ('yes', 'confirm', 'proceed') that they want to proceed to "
                f"Razorpay payment. Once confirmed, call proceed_to_payment(order_id='{order_id}') to create "
                f"the Razorpay test-mode order and open the payment panel."
            ),
            "order": {
                "id": order_id,
                "status": "prepared",
                "total_amount": total_amount,
                "currency": currency,
                "items": order_items_list,
                "payment_gateway": "Razorpay",
                "requires_confirmation": True,
                "cart_unchanged": True,
                "claiming_success_is_forbidden": True
            }
        }
    except Exception as e:
        conn.rollback()
        print(f"Error creating order: {e}")
        return {"error": f"Failed to prepare order: {str(e)}"}
    finally:
        conn.close()


def proceed_to_payment(order_id: str, session_id: str = "default_session", **kwargs) -> Dict[str, Any]:
    """Create the Razorpay test-mode order for an already-prepared internal order.

    This is the ONLY bridge between the conversation agent and the real
    Razorpay payment flow.

    * The expenditure-limit check was already enforced in create_order, but
      we re-check here defensively so callers cannot skip that step.
    * Only prepared (status='prepared') orders may advance. Paid, cancelled
      or missing orders return a hard error.
    * When RAZORPAY_KEY_ID is set to the real test key, we call Razorpay's
      Orders API and return the real Razorpay order id + amount + currency
      so the frontend can open the Razorpay Checkout UI.
    * When no real key is set (demo mode), we return a deterministic
      order_DEMO_... id so the frontend flow still works end-to-end against
      the verify endpoint. No money is ever charged.
    * The cart is NOT cleared here. Clearing the cart ONLY happens inside
      /api/payment/verify AFTER the Razorpay HMAC signature is verified.
    * After this call, the agent MUST tell the user to complete the Razorpay
      Checkout panel that appears on screen. It must NOT say "order placed".
      The success path is: Razorpay UI → /api/payment/verify → order status
      'paid', cart cleared, confirmation email sent.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order_row = cursor.fetchone()
    if not order_row:
        conn.close()
        return {"error": f"Order '{order_id}' was not found. Prepare the order first with create_order."}

    oid = order_row["id"]
    session_match = order_row["session_id"]
    status = order_row["status"]
    total_amount = float(order_row["total_amount"])
    currency = order_row["currency"]

    if status == "paid":
        conn.close()
        return {"error": f"Order {oid} has already been paid. A new payment is not required."}
    if status != "prepared":
        conn.close()
        return {"error": f"Order {oid} is in status '{status}' and cannot proceed to payment."}

    if session_match and session_id and session_match != session_id:
        conn.close()
        return {"error": "Order does not belong to this session."}

    # Re-apply bounds defensively
    from backend.providers.bounds_provider import bounds_service
    from backend.providers.audit_provider import audit_service
    cursor.execute("SELECT quantity FROM order_items WHERE order_id = ?", (oid,))
    oq_rows = cursor.fetchall()
    total_qty = sum(r["quantity"] for r in oq_rows) or 1
    conn.close()

    bounds_check = bounds_service.validate_transaction_bounds(
        total_amount=total_amount,
        quantity=total_qty,
        currency=currency,
        session_id=session_id,
    )
    if not bounds_check["permitted"]:
        audit_service.record_event(
            session_id=session_id,
            event_type="PROCEED_TO_PAYMENT_BLOCKED_BY_BOUNDS",
            data={"order_id": oid, **bounds_check}
        )
        return {
            "error": bounds_check["message"],
            "bounds_exceeded": True,
            "blocks_payment": True
        }

    from backend.config import RAZORPAY_KEY_ID
    if not RAZORPAY_KEY_ID or RAZORPAY_KEY_ID == "rzp_test_placeholder":
        audit_service.record_event(
            session_id=session_id,
            event_type="RAZORPAY_ORDER_CREATE_FAILED",
            data={"order_id": oid, "error": "Razorpay TEST key is not configured"}
        )
        return {
            "error": (
                "Razorpay TEST credentials are not configured, so the payment window cannot open. "
                "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET. The cart is unchanged."
            ),
            "blocks_payment": True,
            "cart_unchanged": True,
            "success": False,
        }

    try:
        from backend.payment.razorpay import create_razorpay_order
        rzp = create_razorpay_order(
            amount_inr=total_amount,
            internal_order_id=oid,
            currency=currency
        )
        conn2 = get_connection()
        c2 = conn2.cursor()
        c2.execute("UPDATE orders SET razorpay_order_id = ? WHERE id = ?", (rzp["id"], oid))
        conn2.commit()
        conn2.close()

        audit_service.record_event(
            session_id=session_id,
            event_type="RAZORPAY_ORDER_CREATED",
            data={
                "internal_order_id": oid,
                "razorpay_order_id": rzp["id"],
                "amount": total_amount,
                "currency": currency,
                "demo_mode": False,
                "origin": "conversational_proceed_to_payment"
            }
        )

        return {
            "success": True,
            "stage": "razorpay_order_ready",
            "demo_mode": False,
            "internal_order_id": oid,
            "razorpay_order_id": rzp["id"],
            "amount_paise": rzp["amount"],
            "amount": total_amount,
            "currency": currency,
            "next_action_user": "Complete the Razorpay Checkout panel now shown on screen.",
            "agent_must_not_claim_success": True,
            "message": (
                f"Razorpay order {rzp['id']} is ready. "
                f"Instruct the user to finish the Razorpay Checkout panel. "
                f"Do NOT claim order success yet. Cart remains unchanged until payment is verified."
            )
        }
    except Exception as exc:
        audit_service.record_event(
            session_id=session_id,
            event_type="RAZORPAY_ORDER_CREATE_FAILED",
            data={"order_id": oid, "error": str(exc)}
        )
        return {
            "error": (
                f"Razorpay could not create a test order for order {oid} ({str(exc)}). "
                f"The payment step has been BLOCKED. No order was placed, no cart changes occurred."
            ),
            "blocks_payment": True,
            "cart_unchanged": True
        }


# Register the create_order tool schema (excluding session_id parameter)

create_order_schema = {
    "type": "function",
    "function": {
        "name": "create_order",
        "description": (
            "PREPARE a checkout order from the authoritative cart. Returns an order in status='prepared' "
            "WITH requires_confirmation=True. DOES NOT perform payment, DOES NOT clear the cart, DOES NOT "
            "send a confirmation email. After the user EXPLICITLY confirms the items/total, call "
            "proceed_to_payment with the returned order_id to create the Razorpay order and open the "
            "real payment panel. Never tell the user their order was placed based only on this call."
        ),
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

proceed_to_payment_schema = {
    "type": "function",
    "function": {
        "name": "proceed_to_payment",
        "description": (
            "Move an already-prepared order to the Razorpay payment step. "
            "Call ONLY AFTER the user explicitly confirms the prepared order items and total "
            "(for example, by saying 'yes' to the order review). "
            "This triggers the real Razorpay test checkout UI. On failure, payment is BLOCKED and "
            "the cart remains UNCHANGED. On success, the frontend displays Razorpay Checkout and you "
            "must wait for the user to complete it. Never claim order success after this call — "
            "payment verification occurs separately in the UI and only then clears the cart + sends email."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The internal order id (ord_xxx) returned by create_order()."
                }
            },
            "required": ["order_id"]
        }
    }
}

registry.register(create_order_schema, create_order)
registry.register(proceed_to_payment_schema, proceed_to_payment)
