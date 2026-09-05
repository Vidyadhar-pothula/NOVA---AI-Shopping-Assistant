"""
NOVA Product Identity & Reference Resolution Verification Suite
Verifies:
1. Product identity preservation across search -> context -> action -> cart.
2. Relative price resolution ('cheaper one') ignoring ₹0 browse/search listings.
3. Pronoun ('that', 'it') and ordinal ('second one') reference resolution.
4. Strict rejection of generic browse / ₹0 items from entering cart.
5. Dynamic functionality across multiple categories and merchants without hardcoded values.
"""

import os
import sys
import unittest
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database.db import init_db, get_connection
from backend.commerce.models import Product
from backend.agent.agent import update_active_products, parse_product_ids_from_result
from backend.tools.action_tools import resolve_product_action
from backend.tools.cart_tools import add_to_cart, get_cart, clear_cart

class TestProductIdentityResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.session_id = "test_identity_session_123"
        clear_cart(self.session_id)
        # Clear session state
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM session_states WHERE session_id = ?", (self.session_id,))
        conn.commit()
        conn.close()

    def _seed_products(self, products_data):
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
                p["id"], p["name"], p["brand"], p["category"], p["description"], p["price"], p["currency"],
                p.get("rating", 4.5), p.get("review_count", 10), 1, p["merchant"], p["merchant_name"],
                p["source_name"], p["product_url"], 1, 0, p.get("is_individual_product", 1), p.get("result_type", "product")
            ))
        conn.commit()
        conn.close()

    def test_parse_product_ids_from_various_tool_formats(self):
        """Verify parse_product_ids_from_result extracts IDs from dicts with recommendations, feed, products, etc."""
        dict_rec = {"status": "success", "recommendations": [{"id": "prod_rec_1"}, {"id": "prod_rec_2"}]}
        parsed_rec = parse_product_ids_from_result("get_recommendations", dict_rec)
        self.assertEqual(parsed_rec, ["prod_rec_1", "prod_rec_2"])

        dict_feed = {"status": "success", "feed": [{"id": "prod_feed_1"}]}
        parsed_feed = parse_product_ids_from_result("get_discovery_feed", dict_feed)
        self.assertEqual(parsed_feed, ["prod_feed_1"])

    def test_cheaper_one_ignores_zero_price_browse_page(self):
        """
        Observed bug fix: When a search returns individual products AND a ₹0 browse page,
        asking for 'the cheaper one' must pick the individual product with lowest price > 0, NOT the ₹0 browse page.
        """
        prods = [
            {
                "id": "browse_racket_01",
                "name": "Amazon Search Results for Tennis Rackets",
                "brand": "Amazon",
                "category": "Sports",
                "description": "Search listing",
                "price": 0.0,
                "currency": "INR",
                "merchant": "Amazon",
                "merchant_name": "Amazon India",
                "source_name": "Amazon",
                "product_url": "https://www.amazon.in/s?k=tennis+racket",
                "is_individual_product": 0,
                "result_type": "search_results_page"
            },
            {
                "id": "racket_expensive_02",
                "name": "Wilson Pro Staff 97 v13 Tennis Racket",
                "brand": "Wilson",
                "category": "Sports",
                "description": "Pro tennis racket",
                "price": 18999.0,
                "currency": "INR",
                "merchant": "Amazon",
                "merchant_name": "Amazon India",
                "source_name": "Amazon",
                "product_url": "https://www.amazon.in/dp/B08H8XYZ12",
                "is_individual_product": 1,
                "result_type": "product"
            },
            {
                "id": "racket_cheaper_03",
                "name": "Head Titanium Tennis Racket",
                "brand": "Head",
                "category": "Sports",
                "description": "Beginner tennis racket",
                "price": 3499.0,
                "currency": "INR",
                "merchant": "Flipkart",
                "merchant_name": "Flipkart",
                "source_name": "Flipkart",
                "product_url": "https://www.flipkart.com/p/itm12345678",
                "is_individual_product": 1,
                "result_type": "product"
            }
        ]
        self._seed_products(prods)
        update_active_products(self.session_id, [p["id"] for p in prods])

        res = resolve_product_action("add_to_cart", target_reference="add the cheaper one to cart", session_id=self.session_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["product"]["id"], "racket_cheaper_03")
        self.assertEqual(res["product"]["price"], 3499.0)

        # Check cart items
        cart = get_cart(self.session_id)
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["product"]["id"], "racket_cheaper_03")
        self.assertEqual(cart["items"][0]["product"]["price"], 3499.0)

    def test_add_that_to_cart_preserves_recommended_identity(self):
        """Verify 'add that to cart' adds the exact product currently in active session context."""
        prods = [
            {
                "id": "shoe_nike_99",
                "name": "Nike Pegasus 40 Running Shoes",
                "brand": "Nike",
                "category": "Footwear",
                "description": "Running shoes",
                "price": 11895.0,
                "currency": "INR",
                "merchant": "Nike",
                "merchant_name": "Nike Store",
                "source_name": "Nike",
                "product_url": "https://www.nike.com/in/t/pegasus-40",
                "is_individual_product": 1,
                "result_type": "product"
            }
        ]
        self._seed_products(prods)
        update_active_products(self.session_id, ["shoe_nike_99"])

        res = resolve_product_action("add_to_cart", target_reference="add that to cart", session_id=self.session_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["product"]["id"], "shoe_nike_99")
        self.assertEqual(res["product"]["name"], "Nike Pegasus 40 Running Shoes")

    def test_ordinal_reference_resolution(self):
        """Verify 'the second one' selects the 2nd valid item from active context."""
        prods = [
            {
                "id": "watch_01",
                "name": "Apple Watch Series 9",
                "brand": "Apple",
                "category": "Electronics",
                "description": "Smartwatch",
                "price": 41900.0,
                "currency": "INR",
                "merchant": "Croma",
                "merchant_name": "Croma",
                "source_name": "Croma",
                "product_url": "https://www.croma.com/p/1",
                "is_individual_product": 1,
                "result_type": "product"
            },
            {
                "id": "watch_02",
                "name": "Samsung Galaxy Watch 6",
                "brand": "Samsung",
                "category": "Electronics",
                "description": "Android Smartwatch",
                "price": 29999.0,
                "currency": "INR",
                "merchant": "Amazon",
                "merchant_name": "Amazon India",
                "source_name": "Amazon",
                "product_url": "https://www.amazon.in/dp/B09999",
                "is_individual_product": 1,
                "result_type": "product"
            }
        ]
        self._seed_products(prods)
        update_active_products(self.session_id, ["watch_01", "watch_02"])

        res = resolve_product_action("open", target_reference="open the second one", session_id=self.session_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["product"]["id"], "watch_02")
        self.assertEqual(res["url"], "https://www.amazon.in/dp/B09999")

    def test_direct_add_to_cart_rejects_browse_listing(self):
        """Verify add_to_cart direct tool invocation rejects non-individual or ₹0 items."""
        browse_prod = {
            "id": "browse_direct_00",
            "name": "Flipkart Category Browse",
            "brand": "Flipkart",
            "category": "All",
            "description": "Category page",
            "price": 0.0,
            "currency": "INR",
            "merchant": "Flipkart",
            "merchant_name": "Flipkart",
            "source_name": "Flipkart",
            "product_url": "https://www.flipkart.com/pr/all",
            "is_individual_product": 0,
            "result_type": "category_page"
        }
        self._seed_products([browse_prod])

        res = add_to_cart("browse_direct_00", session_id=self.session_id)
        self.assertIn("error", res)
        self.assertIn("Cannot add generic search/browse results", res["error"])

if __name__ == "__main__":
    unittest.main()
