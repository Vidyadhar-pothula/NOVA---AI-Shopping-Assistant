from typing import Dict, Any, List
from backend.database.db import get_connection

class RevenueAnalyticsService:
    """
    Lightweight Revenue Impact & Growth Measurement Service (Phase 9).
    Tracks baseline order value, AI-assisted order value, incremental value, and conversion rates.
    """

    def record_transaction(
        self,
        order_id: str,
        session_id: str,
        total_amount: float,
        has_recommendation: bool = False,
        incremental_amount: float = 0.0
    ):
        conn = get_connection()
        cursor = conn.cursor()

        baseline = total_amount - incremental_amount if has_recommendation else total_amount
        ai_assisted = total_amount if has_recommendation else 0.0

        cursor.execute(
            """
            INSERT OR REPLACE INTO revenue_analytics
            (order_id, session_id, baseline_amount, ai_assisted_amount, incremental_amount, has_recommendation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (order_id, session_id, baseline, ai_assisted, incremental_amount, 1 if has_recommendation else 0)
        )
        conn.commit()
        conn.close()

    def get_merchant_metrics(self) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*), SUM(total_amount) FROM orders WHERE status = 'paid'")
        total_orders_row = cursor.fetchone()
        total_paid_orders = total_orders_row[0] if total_orders_row else 0
        total_revenue = total_orders_row[1] if total_orders_row and total_orders_row[1] else 0.0

        cursor.execute("SELECT COUNT(*), SUM(ai_assisted_amount), SUM(incremental_amount) FROM revenue_analytics WHERE has_recommendation = 1")
        rec_row = cursor.fetchone()
        ai_assisted_count = rec_row[0] if rec_row else 0
        ai_assisted_revenue = rec_row[1] if rec_row and rec_row[1] else 0.0
        incremental_revenue = rec_row[2] if rec_row and rec_row[2] else 0.0

        conversion_rate = (ai_assisted_count / total_paid_orders * 100.0) if total_paid_orders > 0 else 0.0
        avg_order_value = (total_revenue / total_paid_orders) if total_paid_orders > 0 else 0.0

        conn.close()

        return {
            "total_paid_orders": total_paid_orders,
            "total_revenue": round(total_revenue, 2),
            "ai_assisted_orders": ai_assisted_count,
            "ai_assisted_revenue": round(ai_assisted_revenue, 2),
            "incremental_revenue": round(incremental_revenue, 2),
            "average_order_value": round(avg_order_value, 2),
            "recommendation_conversion_rate_pct": round(conversion_rate, 1),
            "currency": "INR"
        }

revenue_analytics_service = RevenueAnalyticsService()
