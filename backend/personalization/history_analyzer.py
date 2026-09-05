import json
from collections import defaultdict, Counter
from typing import Dict, Any, List, Optional
from backend.database.db import get_connection

class HistoryAnalyzer:
    """Analyzes customer order history to extract frequent purchases, brand/category preferences, and co-purchase pairs."""

    def get_user_order_history(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all orders and item details for the session or user."""
        conn = get_connection()
        cursor = conn.cursor()

        query = """
            SELECT o.id as order_id, o.created_at, oi.product_id, oi.quantity, oi.price as item_price,
                   p.name, p.brand, p.category, p.merchant_name, p.product_url
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.session_id = ? OR (? IS NOT NULL AND o.session_id = ?)
            ORDER BY o.created_at DESC
        """
        cursor.execute(query, (session_id, user_id, user_id))
        rows = cursor.fetchall()

        if not rows:
            # Fallback check shopping_history table
            sh_query = """
                SELECT sh.id as order_id, sh.purchase_date as created_at, sh.product_id, 1 as quantity, p.price as item_price,
                       p.name, p.brand, p.category, p.merchant_name, p.product_url
                FROM shopping_history sh
                JOIN products p ON sh.product_id = p.id
                WHERE sh.user_id = ? OR ? IS NULL
                ORDER BY sh.purchase_date DESC
            """
            cursor.execute(sh_query, (session_id, session_id))
            rows = cursor.fetchall()

        conn.close()
        return [dict(r) for r in rows]

    def analyze_frequent_purchases(self, session_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Analyze order history to determine purchase frequencies, category weights, and brand preferences."""
        history = self.get_user_order_history(session_id, user_id)
        if not history:
            return {
                "has_history": False,
                "top_products": [],
                "top_categories": {},
                "top_brands": {},
                "recent_purchases": [],
                "total_orders_count": 0
            }

        product_counts = defaultdict(lambda: {"count": 0, "quantity": 0, "details": None, "last_date": None})
        category_counts = Counter()
        brand_counts = Counter()
        distinct_order_ids = set()

        for row in history:
            pid = row["product_id"]
            distinct_order_ids.add(row["order_id"])
            qty = row.get("quantity", 1)

            product_counts[pid]["count"] += 1
            product_counts[pid]["quantity"] += qty
            product_counts[pid]["last_date"] = row.get("created_at")
            product_counts[pid]["details"] = {
                "id": pid,
                "name": row["name"],
                "brand": row["brand"],
                "category": row["category"],
                "price": row["item_price"],
                "merchant": row.get("merchant_name", "Store"),
                "product_url": row.get("product_url", "")
            }

            if row["category"]:
                category_counts[row["category"]] += qty
            if row["brand"]:
                brand_counts[row["brand"]] += qty

        # Sort products by total quantity / purchase frequency
        sorted_prods = sorted(
            product_counts.values(),
            key=lambda x: (x["quantity"], x["count"]),
            reverse=True
        )

        top_products = [
            {
                **item["details"],
                "purchase_count": item["count"],
                "total_quantity": item["quantity"],
                "last_purchased_at": item["last_date"]
            }
            for item in sorted_prods
        ]

        recent_purchases = history[:5]

        return {
            "has_history": True,
            "total_orders_count": len(distinct_order_ids),
            "top_products": top_products,
            "top_categories": dict(category_counts.most_common(5)),
            "top_brands": dict(brand_counts.most_common(5)),
            "recent_purchases": recent_purchases
        }

    def analyze_copurchase_pairs(
        self,
        session_id: str,
        anchor_product_id: Optional[str] = None,
        anchor_category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dynamically identify product and category pairs commonly ordered together in the same basket."""
        conn = get_connection()
        cursor = conn.cursor()

        # Group items by order
        cursor.execute("""
            SELECT oi.order_id, oi.product_id, p.category, p.name, p.brand
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "copurchased_categories": [],
                "copurchased_products": [],
                "has_copurchase_data": False
            }

        order_baskets = defaultdict(list)
        for r in rows:
            order_baskets[r["order_id"]].append(dict(r))

        category_co_occurrence = Counter()
        product_co_occurrence = Counter()

        for order_id, items in order_baskets.items():
            if len(items) < 2:
                continue

            categories_in_order = [item["category"] for item in items if item["category"]]
            product_ids_in_order = [item["product_id"] for item in items if item["product_id"]]

            # Pairwise category co-occurrence
            for i in range(len(categories_in_order)):
                for j in range(i + 1, len(categories_in_order)):
                    cat1, cat2 = sorted([categories_in_order[i], categories_in_order[j]])
                    if cat1 != cat2:
                        category_co_occurrence[(cat1, cat2)] += 1

            # Pairwise product co-occurrence
            for i in range(len(product_ids_in_order)):
                for j in range(i + 1, len(product_ids_in_order)):
                    p1, p2 = sorted([product_ids_in_order[i], product_ids_in_order[j]])
                    product_co_occurrence[(p1, p2)] += 1

        rel_categories = []
        if anchor_category:
            ac_lower = anchor_category.lower()
            for (c1, c2), count in category_co_occurrence.items():
                if c1.lower() == ac_lower:
                    rel_categories.append({"category": c2, "co_count": count})
                elif c2.lower() == ac_lower:
                    rel_categories.append({"category": c1, "co_count": count})

        rel_categories.sort(key=lambda x: x["co_count"], reverse=True)

        return {
            "has_copurchase_data": len(category_co_occurrence) > 0,
            "copurchased_categories": rel_categories[:5],
            "top_global_pairs": [
                {"pair": list(pair), "count": count}
                for pair, count in category_co_occurrence.most_common(5)
            ]
        }

history_analyzer = HistoryAnalyzer()
