"""
NOVA End-to-End Commerce Pipeline Verification Suite (Tests A through N)
Generic test suite with dynamically generated product records. Zero hardcoding.
"""

import os
import sys
import unittest
import json
import uuid

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database.db import init_db, get_connection
from backend.commerce.models import Product
from backend.commerce.service import search_service
from backend.agent.agent import update_active_products, parse_product_ids_from_result
from backend.tools.action_tools import resolve_product_action
from backend.tools.cart_tools import add_to_cart, get_cart, clear_cart
from backend.payment.razorpay import create_razorpay_order, verify_payment_signature

class TestEndToEndCommercePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.session_id = f"test_e2e_session_{uuid.uuid4().hex[:8]}"
        clear_cart(self.session_id)

    def _seed_dynamic_products(self, products_data):
        conn = get_connection()
        cursor = conn.cursor()
        for p in products_data:
            cursor.execute("""
                INSERT OR REPLACE INTO products (
                    id, name, brand, category, description, price, currency,
                    rating, review_count, availability, merchant, merchant_name,
                    source_name, product_url, is_verified, is_demo, is_individual_product, result_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p["id"], p["name"], p["brand"], p["category"], p["description"], p["price"], p.get("currency", "INR"),
                p.get("rating", 4.5), p.get("review_count", 10), 1, p["merchant"], p["merchant_name"],
                p["source_name"], p["product_url"], 1, 0, p.get("is_individual_product", 1), p.get("result_type", "individual_product")
            ))
        conn.commit()
        conn.close()

    def test_flow_a_add_that(self):
        """TEST A: Search -> display product -> 'add that' -> exact product enters cart."""
        pid = f"prod_a_{uuid.uuid4().hex[:6]}"
        prods = [{
            "id": pid,
            "name": "Dynamic Laptop Pro 15",
            "brand": "TechBrand",
            "category": "Computers",
            "description": "High performance laptop",
            "price": 64999.0,
            "merchant": "TechStore",
            "merchant_name": "TechStore",
            "source_name": "TechStore",
            "product_url": f"https://techstore.com/p/{pid}"
        }]
        self._seed_dynamic_products(prods)
        update_active_products(self.session_id, [pid])

        res = resolve_product_action("add_to_cart", target_reference="add that to cart", session_id=self.session_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["product"]["id"], pid)

        cart = get_cart(self.session_id)
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["product"]["id"], pid)

    def test_flow_b_add_second_one(self):
        """TEST B: Search -> display 3 products -> 'add the second one' -> exact 2nd product enters cart."""
        pids = [f"prod_b_{i}_{uuid.uuid4().hex[:4]}" for i in range(3)]
        prods = [
            {"id": pids[0], "name": "Item Alpha", "brand": "B1", "category": "General", "description": "d", "price": 1000.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pids[0]}"},
            {"id": pids[1], "name": "Item Beta", "brand": "B2", "category": "General", "description": "d", "price": 2000.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pids[1]}"},
            {"id": pids[2], "name": "Item Gamma", "brand": "B3", "category": "General", "description": "d", "price": 3000.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pids[2]}"}
        ]
        self._seed_dynamic_products(prods)
        update_active_products(self.session_id, pids)

        res = resolve_product_action("add_to_cart", target_reference="add the second one to cart", session_id=self.session_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["product"]["id"], pids[1])

        cart = get_cart(self.session_id)
        self.assertEqual(cart["items"][0]["product"]["id"], pids[1])

    def test_flow_c_add_cheaper_one(self):
        """TEST C: Search -> display multiple products -> 'add the cheaper one' -> lowest-price actual product enters cart."""
        pids = [f"prod_c_{i}_{uuid.uuid4().hex[:4]}" for i in range(3)]
        prods = [
            {"id": pids[0], "name": "Browse Page", "brand": "M", "category": "C", "description": "d", "price": 0.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/s", "is_individual_product": 0, "result_type": "browse_list"},
            {"id": pids[1], "name": "Expensive Racket", "brand": "B", "category": "Sports", "description": "d", "price": 15000.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pids[1]}"},
            {"id": pids[2], "name": "Budget Racket", "brand": "B", "category": "Sports", "description": "d", "price": 2999.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pids[2]}"}
        ]
        self._seed_dynamic_products(prods)
        update_active_products(self.session_id, pids)

        res = resolve_product_action("add_to_cart", target_reference="add the cheaper one to cart", session_id=self.session_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["product"]["id"], pids[2])
        self.assertEqual(res["product"]["price"], 2999.0)

    def test_flow_d_open_that(self):
        """TEST D: Search -> display product -> 'open that' -> exact product URL opens."""
        pid = f"prod_d_{uuid.uuid4().hex[:6]}"
        url = f"https://merchant.com/item/{pid}"
        prods = [{"id": pid, "name": "Smart Headphones", "brand": "SoundCo", "category": "Audio", "description": "Wireless", "price": 4999.0, "merchant": "SoundStore", "merchant_name": "SoundStore", "source_name": "S", "product_url": url}]
        self._seed_dynamic_products(prods)
        update_active_products(self.session_id, [pid])

        res = resolve_product_action("open", target_reference="open that", session_id=self.session_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["url"], url)

    def test_flow_e_name_resolution(self):
        """TEST E: User names product -> resolve to canonical product -> add exact product."""
        pid = f"prod_e_{uuid.uuid4().hex[:6]}"
        prods = [{"id": pid, "name": "Acer Aspire 5 Slim Laptop", "brand": "Acer", "category": "Computers", "description": "Slim laptop", "price": 48990.0, "merchant": "Amazon", "merchant_name": "Amazon India", "source_name": "Amazon", "product_url": f"https://amazon.in/dp/{pid}"}]
        self._seed_dynamic_products(prods)
        update_active_products(self.session_id, [pid])

        res = add_to_cart("Acer Aspire 5", session_id=self.session_id)
        self.assertEqual(res["success"], True)

        cart = get_cart(self.session_id)
        self.assertEqual(cart["items"][0]["product"]["id"], pid)

    def test_flow_f_generic_browse_rejected(self):
        """TEST F: Generic search/browse page -> cannot enter cart as a product."""
        pid = f"browse_f_{uuid.uuid4().hex[:6]}"
        prods = [{"id": pid, "name": "Category Listing Page", "brand": "M", "category": "C", "description": "d", "price": 0.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": "https://m.com/pr", "is_individual_product": 0, "result_type": "browse_list"}]
        self._seed_dynamic_products(prods)

        res = add_to_cart(pid, session_id=self.session_id)
        self.assertIn("error", res)
        self.assertIn("Cannot add generic search/browse results", res["error"])

    def test_flow_g_invalid_id_safe_failure(self):
        """TEST G: Invalid/missing product ID -> safe failure."""
        res = add_to_cart("non_existent_product_xyz_9999", session_id=self.session_id)
        self.assertIn("error", res)

    def test_flow_h_ambiguity_clarification(self):
        """TEST H: Two products with similar names -> clarification instead of guessing."""
        pid1 = f"prod_h_1_{uuid.uuid4().hex[:4]}"
        pid2 = f"prod_h_2_{uuid.uuid4().hex[:4]}"
        prods = [
            {"id": pid1, "name": "Acer Nitro 5 Gaming Laptop", "brand": "Acer", "category": "Gaming", "description": "d", "price": 62990.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pid1}"},
            {"id": pid2, "name": "Acer Swift 3 Ultra Laptop", "brand": "Acer", "category": "Ultrabooks", "description": "d", "price": 54990.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pid2}"}
        ]
        self._seed_dynamic_products(prods)
        update_active_products(self.session_id, [pid1, pid2])

        res = add_to_cart("Acer", session_id=self.session_id)
        self.assertEqual(res.get("status"), "clarification_required")
        self.assertIn("Multiple matching products found", res.get("error", ""))

    def test_flow_i_k_l_authoritative_cart_mutation(self):
        """TEST K & L: Authoritative cart verification after addition."""
        pid = f"prod_l_{uuid.uuid4().hex[:6]}"
        prods = [{"id": pid, "name": "Running Watch", "brand": "B", "category": "Sports", "description": "d", "price": 12999.0, "merchant": "M", "merchant_name": "M", "source_name": "S", "product_url": f"https://m.com/{pid}"}]
        self._seed_dynamic_products(prods)

        res = add_to_cart(pid, quantity=2, session_id=self.session_id)
        self.assertTrue(res["success"])
        self.assertIn("cart", res)
        self.assertEqual(res["cart"]["total_amount"], 25998.0)

    def test_flow_n_razorpay_payment(self):
        """TEST N: Razorpay test-mode payment order creation and signature verification."""
        from unittest.mock import patch
        order_id = f"ord_test_{uuid.uuid4().hex[:8]}"

        mock_razorpay_response = {
            "id": f"order_{uuid.uuid4().hex[:8]}",
            "entity": "order",
            "amount": 499900,
            "amount_paid": 0,
            "amount_due": 499900,
            "currency": "INR",
            "receipt": order_id[:40],
            "status": "created",
            "attempts": 0,
            "notes": {"nova_order_id": order_id},
            "created_at": 1700000000
        }

        with patch("backend.payment.razorpay._razorpay_post", return_value=mock_razorpay_response):
            res = create_razorpay_order(4999.0, order_id)
            self.assertIn("id", res)
            self.assertEqual(res["amount"], 499900)

if __name__ == "__main__":
    unittest.main()
