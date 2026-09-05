"""
API-based Commerce Connectors for NOVA Commerce Agent.
Supports SerpApi (Google Shopping) and RapidAPI (Amazon/Flipkart) when API keys are configured.
"""
import os
import json
import hashlib
import datetime
import urllib.parse
import urllib.request
from typing import List, Optional, Dict, Any

from backend.commerce.connectors.base import CommerceConnector
from backend.commerce.models import Product
from backend.commerce.verifier import SourceVerifier
from backend.config import SERP_API_KEY, COMMERCE_API_KEY, RAPIDAPI_KEY

class SerpApiCommerceSource(CommerceConnector):
    """Google Shopping API adapter using SerpApi."""
    
    def get_source_name(self) -> str:
        return "SerpApi Google Shopping"

    def is_available(self) -> bool:
        return bool(SERP_API_KEY and SERP_API_KEY != "placeholder")

    def search_products(
        self, 
        query: str, 
        category: Optional[str] = None, 
        min_price: Optional[float] = None, 
        max_price: Optional[float] = None,
        market: Optional[Any] = None
    ) -> List[Product]:
        if not self.is_available():
            return []

        market_code = market.country_code.lower() if market and hasattr(market, 'country_code') else "in"
        country_name = market.country_name if market and hasattr(market, 'country_name') else "India"
        currency = market.currency_code if market and hasattr(market, 'currency_code') else "INR"

        search_term = f"{category or ''} {query}".strip()
        params = {
            "engine": "google_shopping",
            "q": search_term,
            "location": country_name,
            "gl": market_code,
            "hl": "en",
            "api_key": SERP_API_KEY
        }

        url = f"https://serpapi.com/search.json?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "NOVA-Commerce-Agent/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"⚠️ [SerpApiCommerceSource] API request failed: {e}")
            return []

        shopping_results = data.get("shopping_results", [])
        products: List[Product] = []

        for item in shopping_results:
            title = item.get("title")
            raw_link = item.get("link") or item.get("product_link") or ""
            extracted_price = item.get("extracted_price") or item.get("price")
            merchant = item.get("source") or "Google Shopping Merchant"
            rating = item.get("rating")
            reviews = item.get("reviews")
            thumbnail = item.get("thumbnail")

            if not title or not raw_link or not extracted_price:
                continue

            try:
                price = float(extracted_price)
            except (ValueError, TypeError):
                continue

            if min_price and price < min_price:
                continue
            if max_price and price > max_price:
                continue

            prod_id = f"serp_{hashlib.md5(raw_link.encode()).hexdigest()[:8]}"
            product = Product(
                id=prod_id,
                name=title,
                brand=merchant,
                category=category or "General",
                description=f"Available on {merchant}",
                price=price,
                currency="INR",
                rating=float(rating) if rating else None,
                review_count=int(reviews) if reviews else None,
                availability=True,
                merchant=merchant,
                merchant_name=merchant,
                source_name="Google Shopping",
                product_url=raw_link,
                images=[thumbnail] if thumbnail else [],
                retrieved_at=datetime.datetime.utcnow().isoformat() + "Z",
                is_verified=True,
                is_demo=False
            )

            if SourceVerifier.verify_product(product):
                products.append(product)

        return products

    def get_product_details(self, product_id_or_url: str) -> Optional[Product]:
        return None
