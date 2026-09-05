import os
import sys
import unittest
import uuid
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api.main import (
    ExternalAddToCartRequest,
    CreatePaymentOrderRequest,
    VerifyPaymentRequest,
    external_add_to_cart_endpoint,
    payment_create_order,
    payment_verify,
)
from backend.database.db import init_db
from backend.tools.cart_tools import clear_cart, get_cart
from backend.tools.order_tools import create_order


class TestExternalCartBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.session_id = f"test_external_{uuid.uuid4().hex[:8]}"
        clear_cart(self.session_id)

    def _external_product(self, merchant, name, price, url):
        return {
            "name": name,
            "merchant": merchant,
            "price": price,
            "currency": "INR",
            "url": url,
            "image": f"https://cdn.example.test/{uuid.uuid4().hex}.jpg",
            "availability": True,
        }

    def test_multiple_external_pages_share_authoritative_nova_cart(self):
        products = [
            self._external_product("Amazon India", "Dynamic Bottle Alpha", 499, "https://www.amazon.in/dp/B0ALPHA01"),
            self._external_product("Flipkart", "Dynamic Bottle Beta", 599, "https://www.flipkart.com/p/itmBETA02"),
            self._external_product("Demo Store", "Dynamic Bottle Gamma", 699, "https://shop.example.test/product/gamma-03"),
        ]

        for product in products:
            payload = self._call(external_add_to_cart_endpoint, ExternalAddToCartRequest(
                session_id=self.session_id,
                product=product,
                page_url=product["url"],
                source_name=product["merchant"],
            ))
            self.assertTrue(payload["success"], payload)
            self.assertEqual(payload["product"]["name"], product["name"])
            self.assertEqual(payload["product"]["product_url"], product["url"])

        cart = get_cart(self.session_id)
        self.assertEqual(len(cart["items"]), 3)
        self.assertEqual(cart["total_amount"], 1797)
        self.assertEqual(
            {item["product"]["merchant_name"] for item in cart["items"]},
            {"Amazon India", "Flipkart", "Demo Store"},
        )

    def test_external_listing_page_is_rejected_without_cart_mutation(self):
        payload = self._call(external_add_to_cart_endpoint, ExternalAddToCartRequest(
            session_id=self.session_id,
            product={
                "name": "Search results for bottles",
                "merchant": "Amazon India",
                "price": 499,
                "currency": "INR",
                "url": "https://www.amazon.in/s?k=bottles",
            },
            page_url="https://www.amazon.in/s?k=bottles",
            source_name="Amazon India",
        ))
        self.assertFalse(payload["success"])
        self.assertIn("search/listing page", payload["error"])
        self.assertEqual(get_cart(self.session_id)["items"], [])

    def test_backend_corrects_stray_numeric_price_from_money_text(self):
        product = {
            "name": "Dynamic Office Laptop 13th Gen",
            "merchant": "Example Merchant",
            "price": 3,
            "currency": "INR",
            "priceText": "Current price ₹8,490 MRP ₹79,990 EMI ₹2,425/month Bank offer ₹3,000 off",
            "priceConfidence": "high",
            "url": "https://shop.example.test/product/laptop-13th-gen",
            "availability": True,
        }
        payload = self._call(external_add_to_cart_endpoint, ExternalAddToCartRequest(
            session_id=self.session_id,
            product=product,
            page_url=product["url"],
            source_name=product["merchant"],
        ))
        self.assertTrue(payload["success"], payload)
        self.assertEqual(payload["product"]["price"], 8490.0)

        cart = get_cart(self.session_id)
        self.assertEqual(cart["items"][0]["product"]["price"], 8490.0)
        self.assertEqual(cart["total_amount"], 8490.0)

        order_res = create_order(session_id=self.session_id)
        self.assertTrue(order_res["success"], order_res)
        self.assertEqual(order_res["order"]["items"][0]["price"], 8490.0)
        self.assertEqual(order_res["order"]["total_amount"], 8490.0)

    def test_checkout_preserves_cart_until_payment_success_then_clears(self):
        product = self._external_product("Amazon India", "Dynamic Checkout Bottle", 899, "https://www.amazon.in/dp/B0CHECK01")
        self._call(external_add_to_cart_endpoint, ExternalAddToCartRequest(
            session_id=self.session_id,
            product=product,
            page_url=product["url"],
            source_name=product["merchant"],
        ))

        order_res = create_order(session_id=self.session_id)
        self.assertTrue(order_res["success"], order_res)
        self.assertEqual(len(get_cart(self.session_id)["items"]), 1)

        payment_order = self._call(payment_create_order, CreatePaymentOrderRequest(
            internal_order_id=order_res["order"]["id"]
        ))
        self.assertTrue(payment_order["demo_mode"])

        verify_payload = self._call(payment_verify, VerifyPaymentRequest(
            internal_order_id=order_res["order"]["id"],
            razorpay_order_id=payment_order["razorpay_order_id"],
            razorpay_payment_id="pay_DEMO_TEST",
            razorpay_signature="demo_signature",
        ))
        self.assertTrue(verify_payload["success"])
        self.assertEqual(get_cart(self.session_id)["items"], [])

    def _call(self, handler, request):
        response = asyncio.run(handler(request))
        return json.loads(response.body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
