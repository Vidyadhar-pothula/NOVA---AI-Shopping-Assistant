from typing import Dict, Any, Optional
from backend.database.db import get_connection

_CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

def _currency_fmt(amount: float, code: str) -> str:
    code_upper = (code or "INR").upper()
    sym = _CURRENCY_SYMBOLS.get(code_upper, code_upper + " ")
    return f"{sym}{amount:,.2f}"


def get_configured_spending_limit(session_id: Optional[str] = None) -> Optional[float]:
    """Return the user-configured spending limit, or None if none was set.

    Never invents a default such as ₹10,000.
    """
    conn = get_connection()
    cursor = conn.cursor()
    keys = []
    if session_id:
        keys.append(session_id)
    keys.append("nova_settings")
    for uid in keys:
        cursor.execute(
            "SELECT pref_value FROM user_preferences WHERE user_id = ? AND pref_key = ?",
            (uid, "spending_limit"),
        )
        row = cursor.fetchone()
        if row and row["pref_value"] not in (None, "", "none", "null"):
            try:
                conn.close()
                return float(row["pref_value"])
            except (TypeError, ValueError):
                continue
    conn.close()
    return None


def set_configured_spending_limit(limit: Optional[float], user_id: str = "nova_settings") -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (id, name, email) VALUES (?, ?, ?)",
        (user_id, "NOVA Settings", f"{user_id}@nova.local"),
    )
    if limit is None:
        cursor.execute(
            "DELETE FROM user_preferences WHERE user_id = ? AND pref_key = ?",
            (user_id, "spending_limit"),
        )
    else:
        cursor.execute(
            """INSERT INTO user_preferences (user_id, pref_key, pref_value)
               VALUES (?, 'spending_limit', ?)
               ON CONFLICT(user_id, pref_key) DO UPDATE SET pref_value = excluded.pref_value""",
            (user_id, str(limit)),
        )
    conn.commit()
    conn.close()


class BoundsService:
    """Enforces only user-configured transaction limits. No invented demo thresholds."""

    def __init__(self):
        self.allowed_currencies = {"INR", "USD", "EUR", "GBP"}

    def validate_transaction_bounds(
        self,
        total_amount: float,
        quantity: int = 1,
        currency: str = "INR",
        product_name: str = "Product",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        curr = (currency or "INR").upper()
        configured_limit = get_configured_spending_limit(session_id)

        if configured_limit is not None and total_amount > configured_limit:
            return {
                "permitted": False,
                "reason": "exceeds_spending_limit",
                "limit": configured_limit,
                "attempted_amount": total_amount,
                "currency": curr,
                "message": (
                    f"This purchase total of {_currency_fmt(total_amount, curr)} exceeds your configured "
                    f"spending limit of {_currency_fmt(configured_limit, curr)}. "
                    f"I haven't placed the order."
                )
            }

        if curr not in self.allowed_currencies:
            return {
                "permitted": False,
                "reason": "unsupported_currency",
                "currency": currency,
                "message": f"Transactions in currency '{currency}' are currently restricted."
            }

        return {
            "permitted": True,
            "configured_limit": configured_limit,
            "message": "Transaction bounds verified." if configured_limit is not None else "No expenditure limit is configured; amount check skipped."
        }

bounds_service = BoundsService()
