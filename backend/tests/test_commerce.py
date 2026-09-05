"""
Test Suite for Fully Dynamic Real-World Commerce Discovery & Market Localization.
"""
import unittest
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.commerce.models import Product
from backend.commerce.verifier import SourceVerifier
from backend.commerce.location import MarketResolver, Market
from backend.commerce.connectors.live_web import LiveWebCommerceConnector
from backend.commerce.service import search_service
from backend.tools.product_tools import search_products
from backend.database.db import init_db

class TestCommerceDiscovery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_url_verifier(self):
        """Test URL syntax and domain verification."""
        self.assertTrue(SourceVerifier.is_valid_url("https://www.amazon.in/dp/B0C1D2E3F4"))
        self.assertTrue(SourceVerifier.is_valid_url("https://www.flipkart.com/nike-running-shoes/p/itm12345"))
        self.assertFalse(SourceVerifier.is_valid_url("not_a_url"))
        self.assertFalse(SourceVerifier.is_valid_url("http://invalid"))

        # Test trusted domain extraction
        self.assertEqual(SourceVerifier.extract_domain("https://www.amazon.in/dp/B0C1D2E3F4"), "amazon.in")
        self.assertEqual(SourceVerifier.extract_domain("https://www.flipkart.com/item"), "flipkart.com")
        self.assertTrue(SourceVerifier.is_trusted_domain("https://www.myntra.com/shoes"))

    def test_02_market_resolver(self):
        """Test MarketResolver location, currency, and timezone resolution."""
        m_in = MarketResolver.resolve_market("IN")
        self.assertEqual(m_in.country_code, "IN")
        self.assertEqual(m_in.currency_code, "INR")
        self.assertIn("amazon.in", m_in.preferred_domains)

        m_us = MarketResolver.resolve_market("US")
        self.assertEqual(m_us.country_code, "US")
        self.assertEqual(m_us.currency_code, "USD")
        self.assertIn("amazon.com", m_us.preferred_domains)

        m_tz = MarketResolver.resolve_market(timezone="Asia/Kolkata")
        self.assertEqual(m_tz.country_code, "IN")

    def test_03_product_model_serialization(self):
        """Test Product model initialization and dictionary serialization."""
        p = Product(
            id="prod_test_123",
            name="ASICS Gel Kayano 30",
            brand="ASICS",
            category="running shoes",
            description="Premium stability running shoe.",
            price=13999.0,
            currency="INR",
            merchant="Amazon",
            merchant_name="Amazon",
            source_name="Amazon India",
            product_url="https://www.amazon.in/dp/B0C9876543",
            images=["https://images.example.com/shoe.jpg"],
            is_verified=True,
            is_demo=False
        )
        d = p.to_dict()
        self.assertEqual(d["id"], "prod_test_123")
        self.assertEqual(d["price"], 13999.0)
        self.assertEqual(d["merchant_name"], "Amazon")
        self.assertEqual(d["product_url"], "https://www.amazon.in/dp/B0C9876543")
        self.assertTrue(d["is_verified"])
        self.assertFalse(d["is_demo"])

        self.assertTrue(SourceVerifier.verify_product(p))

    def test_04_live_web_connector_multimarket(self):
        """Test LiveWebCommerceConnector across different markets (IN, US)."""
        connector = LiveWebCommerceConnector()
        self.assertTrue(connector.is_available())
        
        # Test India Market Search
        m_in = MarketResolver.resolve_market("IN")
        products_in = connector.search_products("running shoes", max_price=5000, market=m_in)
        self.assertIsInstance(products_in, list)
        
        if products_in:
            first = products_in[0]
            self.assertTrue(first.product_url.startswith("http"))
            self.assertEqual(first.currency, "INR")
            print(f"\n✅ Live IN Product Found: {first.name} | ₹{first.price} | Merchant: {first.merchant_name} | Link: {first.product_url}")

    def test_06_url_and_image_validation(self):
        """Test that search/category URLs and favicon image URLs are properly rejected."""
        connector = LiveWebCommerceConnector()

        # Test search/category URL rejection
        self.assertTrue(connector._is_search_or_category_url("https://www.amazon.in/s?k=water+bottle"))
        self.assertTrue(connector._is_search_or_category_url("https://www.flipkart.com/search?q=phone"))
        self.assertTrue(connector._is_search_or_category_url("https://www.amazon.in/b?node=12345"))
        self.assertFalse(connector._is_search_or_category_url("https://www.amazon.in/dp/B0C1D2E3F4"))
        self.assertFalse(connector._is_search_or_category_url("https://www.flipkart.com/nike-running-shoes/p/itm12345"))

        # Test favicon image rejection
        img = connector._extract_image_url("https://www.amazon.in/dp/B0C1D2E3F4", '<img src="https://www.google.com/s2/favicons?domain=amazon.in">')
        self.assertIsNone(img)

    def test_07_semantic_relevance_filter(self):
        """Test semantic relevance filtering."""
        from backend.commerce.service import _is_semantically_relevant
        p_good = Product(id="1", name="Milton Stainless Steel Water Bottle 1L", brand="Milton", category="Water Bottles", description="1 Litre Insulated Water Bottle", price=799.0, product_url="https://amazon.in/dp/B1")
        p_bad = Product(id="2", name="Cleaning Brush Set for Water Bottles", brand="Generic", category="Accessories", description="Bottle cleaning brush set", price=199.0, product_url="https://amazon.in/dp/B2")

        # "water bottle" query should accept the water bottle and reject the brush set
        self.assertTrue(_is_semantically_relevant(p_good, "water bottle"))
        self.assertFalse(_is_semantically_relevant(p_bad, "water bottle"))

if __name__ == "__main__":
    unittest.main()
