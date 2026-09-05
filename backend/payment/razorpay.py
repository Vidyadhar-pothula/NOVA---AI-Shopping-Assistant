"""
Razorpay Payment Integration for NOVA Commerce Agent.

Flow:
  1. Frontend calls POST /api/payment/create-order  →  we call Razorpay API to create a Razorpay Order
  2. Frontend opens Razorpay Checkout modal with the returned razorpay_order_id
  3. User pays; Razorpay returns payment_id + signature to frontend
  4. Frontend calls POST /api/payment/verify  →  we verify HMAC signature server-side
  5. On success we mark our internal order as 'paid'
"""
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
import base64
from typing import Any, Dict

from backend.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"

# ── Low-level HTTP helper ─────────────────────────────────────────────────────

def _razorpay_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Make an authenticated POST request to the Razorpay API."""
    url = f"{RAZORPAY_API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8")

    # Basic Auth: key_id:key_secret, base64-encoded
    credentials = base64.b64encode(f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {credentials}",
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise RuntimeError(f"Razorpay API error {e.code}: {error_body}")


# ── Public API ────────────────────────────────────────────────────────────────

def create_razorpay_order(amount_inr: float, internal_order_id: str, currency: str = "INR") -> Dict[str, Any]:
    """
    Create a Razorpay payment order.

    Args:
        amount_inr: The order total in INR (rupees, not paise).
        internal_order_id: Our own order ID to attach as a receipt.
        currency: Currency code (default INR).

    Returns:
        Razorpay order response dict containing `id`, `amount`, `currency`, etc.
    """
    payload = {
        "amount": int(amount_inr * 100),   # Razorpay expects paise
        "currency": currency,
        "receipt": internal_order_id[:40], # receipt max 40 chars
        "notes": {
            "nova_order_id": internal_order_id,
            "source": "NOVA AI Commerce Agent"
        }
    }
    return _razorpay_post("/orders", payload)


def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    Verify the Razorpay payment signature using HMAC-SHA256.
    This is the security-critical step that confirms the payment is authentic.

    Args:
        razorpay_order_id: The Razorpay order ID returned during order creation.
        razorpay_payment_id: The payment ID returned by Razorpay after successful payment.
        razorpay_signature: The HMAC signature sent by the Razorpay Checkout modal.

    Returns:
        True if the signature is valid, False otherwise.
    """
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, razorpay_signature)
