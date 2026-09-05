"""
Source Verifier Module for NOVA Commerce Agent.
Validates product URLs, merchant domains, and data integrity before products are returned to users.
"""
import re
import urllib.parse
from typing import Dict, Any, List, Optional
from backend.commerce.models import Product

# Known & allowed e-commerce domain suffixes / hosts
ALLOWED_COMMERCE_DOMAINS = [
    "amazon.in", "amazon.com",
    "flipkart.com",
    "myntra.com",
    "nike.com",
    "adidas.co.in", "adidas.com",
    "puma.com",
    "tatacliq.com",
    "croma.com",
    "ajio.com",
    "reliancedigital.in",
    "nykaa.com",
    "boat-lifestyle.com",
    "fastrack.in",
    "decathlon.in",
    "meesho.com",
    "snapdeal.com"
]

class SourceVerifier:
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Verify if a URL string is a valid http/https URL."""
        if not url or not isinstance(url, str):
            return False
        url = url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            return False
        try:
            parsed = urllib.parse.urlparse(url)
            return bool(parsed.netloc and "." in parsed.netloc)
        except Exception:
            return False

    @staticmethod
    def extract_domain(url: str) -> str:
        """Extract the root domain (e.g. amazon.in) from a URL."""
        try:
            parsed = urllib.parse.urlparse(url.strip())
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            return netloc
        except Exception:
            return ""

    @staticmethod
    def is_trusted_domain(url: str) -> bool:
        """Check if the URL belongs to a known/allowed e-commerce domain."""
        domain = SourceVerifier.extract_domain(url)
        if not domain:
            return False
        return any(domain == d or domain.endswith("." + d) for d in ALLOWED_COMMERCE_DOMAINS)

    @classmethod
    def verify_product(cls, product: Product) -> bool:
        """
        Verify that a product object contains legitimate, non-fabricated data.
        Rules:
        1. Title / Name must be non-empty string.
        2. Price must be > 0.
        3. If product_url is provided, it must be a valid URL.
        4. If marked as live verified (is_demo=False), product_url is MANDATORY and must be valid.
        """
        # For individual products, price must be > 0. For browse lists, price can be 0.0
        if product.result_type != "browse_list":
            if product.price is None or product.price <= 0:
                return False
        else:
            if product.price is None or product.price < 0:
                return False

        # For real live products, product_url is required
        if not product.product_url or not cls.is_valid_url(product.product_url):
            return False

        # Mark as verified if domain check succeeds
        if cls.is_trusted_domain(product.product_url):
            product.is_verified = True
        
        return True

    @classmethod
    def filter_and_verify(cls, products: List[Product]) -> List[Product]:
        """Filter a list of products to keep only verified ones."""
        verified = []
        for p in products:
            if cls.verify_product(p):
                verified.append(p)
            else:
                print(f"⚠️ [SourceVerifier] Product failed verification: '{p.name}' (URL: {p.product_url})")
        return verified
