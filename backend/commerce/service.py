"""
Commerce Search Service.
Orchestrates live commerce retrieval across supported sources (Live Web, SerpApi),
verifies sources/URLs, ranks results by relevance & market, caches live products in SQLite, and logs audit events.
"""
import re
import json
import sqlite3
import datetime
from typing import List, Dict, Any, Optional, Set

from backend.commerce.models import Product
from backend.commerce.connectors.base import CommerceConnector
from backend.commerce.connectors.live_web import LiveWebCommerceConnector
from backend.commerce.connectors.api_sources import SerpApiCommerceSource
from backend.commerce.connectors.demo import DemoCommerceConnector
from backend.commerce.verifier import SourceVerifier
from backend.commerce.location import Market, MarketResolver
from backend.database.db import get_connection


# ── Relevance Filtering ────────────────────────────────────────────────────────

def _extract_query_terms(query: str) -> Set[str]:
    """Extract meaningful search terms, excluding common stop words."""
    STOP_WORDS = {
        "a", "an", "the", "in", "on", "at", "for", "of", "and", "or",
        "buy", "get", "find", "me", "i", "want", "need", "best", "good",
        "cheap", "cheapest", "under", "below", "above", "price", "online",
        "india", "us", "uk", "store", "shop", "purchase", "order"
    }
    words = re.findall(r'\w+', query.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


def _is_semantically_relevant(product: Product, query: str, category: str = "") -> bool:
    """
    Check that the product's title/description is semantically relevant to the query.
    Prevents things like "bottle brush" or "water bottle cleaning tablets" appearing in "water bottle" results.
    """
    query_terms = _extract_query_terms(query)
    if not query_terms:
        return True  # Can't filter without terms

    product_text = (product.name + " " + (product.description or "")).lower()

    # Count how many significant query terms appear in the product text
    matched = sum(1 for term in query_terms if term in product_text)
    match_fraction = matched / len(query_terms)

    # Require at least 50% keyword match for relevance
    if match_fraction < 0.50:
        print(f"   🚫 Relevance filter rejected: '{product.name[:50]}' (match={match_fraction:.2f} for query='{query}')")
        return False

    # Check for accessory/utility terms in product title when NOT present in query
    ACCESSORY_TERMS = {
        "brush", "cleaning", "tablet", "cleaner", "cover", "sleeve", "bag",
        "holder", "stand", "strap", "sticker", "decal", "skin", "protector"
    }
    query_lower = query.lower()
    title_lower = product.name.lower()
    for acc in ACCESSORY_TERMS:
        if acc in title_lower and acc not in query_lower:
            print(f"   🚫 Relevance filter rejected accessory: '{product.name[:50]}' (found '{acc}' not in query)")
            return False

    return True


def _compute_service_score(product: Product, query: str, max_price: Optional[float]) -> float:
    """
    Multi-factor ranking score (0.0–1.0) for service-level ranking.
    Used after individual connector relevance scores.
    """
    score = 0.0

    # 1. Keyword coverage (40%)
    query_terms = _extract_query_terms(query)
    if query_terms:
        product_text = (product.name + " " + (product.description or "")).lower()
        text_words = set(re.findall(r'\w+', product_text))
        match_fraction = len(query_terms & text_words) / len(query_terms)
        score += match_fraction * 0.40

    # 2. Verified source (20%)
    if product.is_verified and not product.is_demo:
        score += 0.20

    # 3. Budget fit (20%) — closer to max_price (but under it) is better value
    if max_price and product.price > 0:
        if product.price <= max_price:
            # Reward products that use 50-95% of budget (best value zone)
            budget_ratio = product.price / max_price
            if 0.5 <= budget_ratio <= 0.95:
                score += 0.20
            else:
                score += 0.10
        # Over-budget products already filtered, but just in case
    elif product.price > 0:
        score += 0.10

    # 4. Has a real product image (10%)
    real_images = [img for img in product.images if img and "favicon" not in img.lower() and "s2/favicons" not in img.lower()]
    if real_images:
        score += 0.10

    # 5. Connector relevance score (from specifications metadata) (10%)
    relevance_from_connector = product.specifications.get("relevance_score", 0.5)
    score += float(relevance_from_connector) * 0.10

    return min(score, 1.0)


def _deduplicate_by_price_diversity(products: List[Product]) -> List[Product]:
    """
    Prevent filling results with products at identical or near-identical prices.
    If more than 2 products share the same price, keep only the top 2 by relevance.
    """
    from collections import defaultdict
    price_buckets: Dict[int, List[Product]] = defaultdict(list)
    for p in products:
        # Round to nearest 50 to catch near-identical prices
        bucket = int(round(p.price / 50.0) * 50)
        price_buckets[bucket].append(p)

    deduplicated = []
    for bucket, bucket_products in price_buckets.items():
        # Keep at most 2 per price bucket
        deduplicated.extend(bucket_products[:2])

    return deduplicated


class CommerceSearchService:
    def __init__(self):
        # Register active live connectors
        self.live_connectors: List[CommerceConnector] = [
            SerpApiCommerceSource(),
            LiveWebCommerceConnector()
        ]
        self.demo_connectors: List[CommerceConnector] = [
            DemoCommerceConnector("StyleStep"),
            DemoCommerceConnector("FitGear")
        ]

    def _cache_products_in_db(self, products: List[Product]):
        """Persist retrieved products into SQLite cache to allow exact ID/URL lookups in cart & orders."""
        if not products:
            return
        conn = get_connection()
        cursor = conn.cursor()

        for p in products:
            try:
                cursor.execute(
                    """INSERT INTO products (
                        id, name, brand, category, description, price, currency,
                        rating, review_count, availability, merchant, delivery_information,
                        specifications, images, product_url, merchant_name, source_name,
                        retrieved_at, is_verified, is_demo, is_individual_product, result_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        price=excluded.price,
                        rating=excluded.rating,
                        product_url=excluded.product_url,
                        retrieved_at=excluded.retrieved_at,
                        is_verified=excluded.is_verified,
                        is_demo=excluded.is_demo,
                        is_individual_product=excluded.is_individual_product,
                        result_type=excluded.result_type
                    """,
                    (
                        p.id, p.name, p.brand, p.category, p.description, p.price, p.currency,
                        p.rating, p.review_count, 1 if p.availability else 0, p.merchant,
                        p.delivery_information, json.dumps(p.specifications), json.dumps(p.images),
                        p.product_url, p.merchant_name, p.source_name, p.retrieved_at,
                        1 if p.is_verified else 0, 1 if p.is_demo else 0,
                        1 if p.is_individual_product else 0, p.result_type
                    )
                )
            except Exception as e:
                print(f"⚠️ [CommerceSearchService] Cache error for product '{p.id}': {e}")

        conn.commit()
        conn.close()

    def _log_retrieval(self, query: str, source_name: str, market_code: str, count: int, success: bool):
        """Audit log for product retrieval events."""
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        print(f"📊 [COMMERCE LOG] [{timestamp}] Market: '{market_code}' | Query: '{query}' | Source: '{source_name}' | Count: {count} | Success: {success}")

    def search_products(
        self,
        query: str,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        market: Optional[Market] = None,
        is_test_mode: bool = False
    ) -> List[Product]:
        """Search products across live commerce sources for target market."""
        query_str = (query or "").strip()
        market_obj = market or MarketResolver.resolve_market("IN")
        print(f"🔎 [CommerceSearchService] Query='{query_str}', market='{market_obj.country_code}', max_price={max_price}")

        all_products: List[Product] = []

        # 1. Query live connectors with target market
        for connector in self.live_connectors:
            if connector.is_available():
                try:
                    if isinstance(connector, LiveWebCommerceConnector):
                        results = connector.search_products(
                            query_str, category=category,
                            min_price=min_price, max_price=max_price,
                            market=market_obj
                        )
                    else:
                        results = connector.search_products(
                            query_str, category=category,
                            min_price=min_price, max_price=max_price
                        )

                    verified_results = SourceVerifier.filter_and_verify(results)
                    if verified_results:
                        all_products.extend(verified_results)
                        self._log_retrieval(query_str, connector.get_source_name(), market_obj.country_code, len(verified_results), True)
                except Exception as e:
                    print(f"❌ [CommerceSearchService] Connector error ({connector.get_source_name()}): {e}")
                    self._log_retrieval(query_str, connector.get_source_name(), market_obj.country_code, 0, False)

        # 2. Demo fallback only in test mode
        if not all_products and is_test_mode:
            print("ℹ️ [CommerceSearchService] Test Mode: Using fallback connectors.")
            for connector in self.demo_connectors:
                try:
                    results = connector.search_products(query_str, category=category, min_price=min_price, max_price=max_price)
                    all_products.extend(results)
                except Exception as e:
                    print(f"❌ [CommerceSearchService] Demo connector error: {e}")

        # 3. Separate results into Type A (individual_product) and Type B (browse_list)
        individual_candidates: List[Product] = []
        browse_candidates: List[Product] = []

        query_for_filter = f"{category or ''} {query_str}".strip()

        for p in all_products:
            if p.result_type == "browse_list":
                browse_candidates.append(p)
            else:
                if _is_semantically_relevant(p, query_for_filter):
                    individual_candidates.append(p)

        print(f"🔍 [CommerceSearchService] Candidates: {len(individual_candidates)} individual products, {len(browse_candidates)} browse lists")

        # 4. Filter individual products strictly by max_price (hard constraint)
        if max_price:
            individual_candidates = [p for p in individual_candidates if p.price <= max_price]

        # 5. Deduplicate individual products by URL or name
        seen_urls = set()
        unique_individual: List[Product] = []
        for p in individual_candidates:
            key = p.product_url or p.id
            if key not in seen_urls:
                seen_urls.add(key)
                unique_individual.append(p)

        # 6. Rank individual products by multi-factor score
        unique_individual.sort(
            key=lambda p: _compute_service_score(p, query_str, max_price),
            reverse=True
        )

        # 7. Price diversity selection (pick up to 3 genuinely distinct price options: low, mid, high within budget)
        diverse_individual: List[Product] = []
        if len(unique_individual) <= 3:
            diverse_individual = unique_individual
        else:
            # Sort by price ascending to pick low, mid, high options
            sorted_by_price = sorted(unique_individual, key=lambda p: p.price)
            low_opt = sorted_by_price[0]
            high_opt = sorted_by_price[-1]
            mid_opt = sorted_by_price[len(sorted_by_price) // 2]

            seen_ids = set()
            for opt in [low_opt, mid_opt, high_opt]:
                if opt.id not in seen_ids:
                    seen_ids.add(opt.id)
                    diverse_individual.append(opt)

        # 8. Deduplicate browse lists by merchant domain
        seen_browse_merchants = set()
        unique_browse: List[Product] = []
        for p in browse_candidates:
            if p.merchant not in seen_browse_merchants:
                seen_browse_merchants.add(p.merchant)
                unique_browse.append(p)

        # 9. Combine top 2-3 individual products + top 1-2 browse lists
        final_products = diverse_individual[:3] + unique_browse[:2]

        print(f"✅ [CommerceSearchService] Final selection: {len(diverse_individual[:3])} individual products + {len(unique_browse[:2])} browse lists")

        # 10. Persist to cache
        self._cache_products_in_db(final_products)

        return final_products

    def get_product_details(self, product_id_or_url: str) -> Optional[Product]:
        """Lookup product by ID or URL in DB cache or live connectors."""
        # 1. Try DB cache
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ? OR product_url = ?", (product_id_or_url, product_id_or_url))
        row = cursor.fetchone()
        conn.close()

        if row:
            return Product.from_row(row)

        # 2. Try live connectors
        for connector in self.live_connectors:
            p = connector.get_product_details(product_id_or_url)
            if p:
                self._cache_products_in_db([p])
                return p

        return None


# Singleton instance
search_service = CommerceSearchService()
