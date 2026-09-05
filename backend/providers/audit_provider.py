import json
import datetime
from typing import Dict, Any, List, Optional
from backend.database.db import get_connection

class AuditService:
    """
    Persistent Transaction Audit Trail Service (Phase 7).
    Records the sequence of events for every transaction:
    USER_REQUEST → PRODUCT_DISCOVERY → AI_RECOMMENDATION → CART_UPDATED → CHECKOUT_CREATED → USER_CONFIRMED → RAZORPAY_ORDER_CREATED → PAYMENT_SUCCESS / PAYMENT_FAILED
    """

    def record_event(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        
        json_data = json.dumps(data, default=str)
        cursor.execute(
            """
            INSERT INTO audit_logs (session_id, event_type, event_data, timestamp)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (session_id or "default_session", event_type, json_data)
        )
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return log_id

    def get_session_audit_trail(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, event_type, event_data, timestamp
            FROM audit_logs
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()

        trail = []
        for r in rows:
            try:
                parsed_data = json.loads(r["event_data"])
            except Exception:
                parsed_data = r["event_data"]
            trail.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "event_type": r["event_type"],
                "data": parsed_data,
                "timestamp": r["timestamp"]
            })
        return trail

audit_service = AuditService()
