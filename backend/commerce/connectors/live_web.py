"""
Live Web Commerce Connector.
Searches real e-commerce listings across market-specific merchants.
Includes URL validation (rejects search/category pages), image validation (rejects favicons),
relevance scoring, and product-page URL detection.
"""
import re
import json
import hashlib
import urllib.parse
import urllib.request
import datetime
from typing import List, Optional, Dict, Any, Tuple

from backend.commerce.connectors.base import CommerceConnector
from backend.commerce.models import Product
from backend.commerce.verifier import SourceVerifier
from backend.commerce.location import Market, MarketResolver

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# E-commerce platform mapping to clean merchant names
DOMAINS_TO_MERCHANT = {
    "amazon.in": "Amazon India",
    "amazon.com": "Amazon US",
    "amazon.co.uk": "Amazon UK",
    "flipkart.com": "Flipkart",
    "myntra.com": "Myntra",
    "nike.com": "Nike",
    "adidas.co.in": "Adidas",
    "adidas.com": "Adidas",
    "tatacliq.com": "Tata CLiQ",
    "croma.com": "Croma",
    "ajio.com": "Ajio",
    "reliancedigital.in": "Reliance Digital",
    "walmart.com": "Walmart",
    "bestbuy.com": "Best Buy",
    "target.com": "Target",
    "argos.co.uk": "Argos",
    "currys.co.uk": "Currys",
    "johnlewis.com": "John Lewis",
    "ebay.com": "eBay",
    "nykaa.com": "Nykaa",
    "snapdeal.com": "Snapdeal",
    "paytmmall.com": "Paytm Mall",
    "meesho.com": "Meesho",
}

TRUSTED_DOMAINS = set(DOMAINS_TO_MERCHANT.keys())

# URL path patterns that indicate search/category/listing pages (NOT product detail pages)
SEARCH_PAGE_PATTERNS = [
    r"/s\?",          # Amazon search
    r"/s/",           # Amazon search path
    r"/search",       # Generic search
    r"\?q=",          # Query param search
    r"\?query=",      # Query param search
    r"\?keyword",     # Keyword search
    r"/b\?",          # Amazon browse
    r"\?node=",       # Amazon category node
    r"/category/",    # Category pages
    r"/categories/",  # Category pages
    r"/c/",           # Short category path
    r"/browse",       # Browse pages
    r"/all-products", # All products listing
    r"/pr\?",         # Flipkart search/category
    r"/pr/",          # Flipkart category
    r"/?sid=",        # Flipkart category SID
    r"/collection",   # Collection pages
    r"/listing",      # Listing pages
    r"smart-watches/pr",  # Flipkart category
]

# Favicon/logo patterns — these are NOT real product images
LOGO_IMAGE_PATTERNS = [
    "s2/favicons",
    "favicon.ico",
    "favicon.png",
    "/logo.",
    "/logo/",
    "site-logo",
    "brand-logo",
]

# URL path patterns that strongly indicate a real product-detail page
PRODUCT_PAGE_PATTERNS = [
    r"/dp/[A-Z0-9]{10}",          # Amazon ASIN
    r"/product/",                  # Generic product pages
    r"/p/[a-zA-Z0-9]{6,}",        # Flipkart product ID
    r"/itm/[0-9]{10,}",           # eBay item
    r"/ip/[a-zA-Z0-9\-]+",        # Walmart item page
    r"/[a-zA-Z0-9\-]+-p-[0-9]+",  # Various retailer patterns
    r"/[a-zA-Z0-9\-]+/buy",        # Buy page pattern
    r"/pd/",                        # Product detail
    r"/sku/",                       # SKU-based pages
]


class LiveWebCommerceConnector(CommerceConnector):
    def get_source_name(self) -> str:
        return "Live Web Commerce"

    def is_available(self) -> bool:
        return True

    def _fetch_search_html(self, query: str, domains: List[str]) -> str:
        """Fetch search results from web search targeting e-commerce domains using POST."""
        full_query = f"{query} buy online"

        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": full_query}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"⚠️ [LiveWebConnector] Search request failed: {e}")
            return ""

    def _clean_url(self, raw_url: str) -> str:
        """Clean DuckDuckGo redirect link to extract real destination URL."""
        if not raw_url:
            return ""
        # Unescape HTML entities (e.g. &amp; -> &)
        raw_url = raw_url.replace("&amp;", "&")

        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url
        if "duckduckgo.com/l/?" in raw_url or "duckduckgo.com/y.js" in raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed.query)
            if "u3" in qs:
                dest = urllib.parse.unquote(qs["u3"][0])
                if "&u=" in dest or "?u=" in dest:
                    sub_parsed = urllib.parse.urlparse(dest)
                    sub_qs = urllib.parse.parse_qs(sub_parsed.query)
                    if "u" in sub_qs:
                        return urllib.parse.unquote(sub_qs["u"][0])
                return dest
            if "uddg" in qs:
                return urllib.parse.unquote(qs["uddg"][0])
        return raw_url

    def _is_search_or_category_url(self, url: str) -> bool:
        """Return True if URL is a search/category/listing page (NOT a product detail page)."""
        if not url:
            return True
        url_lower = url.lower()
        for pattern in SEARCH_PAGE_PATTERNS:
            if re.search(pattern, url_lower):
                return True
        return False

    def _is_product_detail_url(self, url: str) -> bool:
        """Return True if URL strongly appears to be an exact product-detail page."""
        if not url:
            return False
        for pattern in PRODUCT_PAGE_PATTERNS:
            if re.search(pattern, url):
                return True
        return False

    def _is_trusted_domain(self, url: str) -> bool:
        """Return True if URL belongs to a known trusted e-commerce domain."""
        domain = SourceVerifier.extract_domain(url)
        if not domain:
            return False
        for td in TRUSTED_DOMAINS:
            if domain == td or domain.endswith("." + td):
                return True
        return False

    def _extract_price(self, text: str, currency_code: str = "INR") -> Optional[float]:
        """Extract localized price from text according to currency."""
        patterns = [
            r"(?:₹|Rs\.?|INR|\$|£|€)\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+)",
            r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)\s*(?:INR|USD|GBP|EUR|Rs|rupees|dollars|pounds)"
        ]
        for p in patterns:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(",", "")
                try:
                    val = float(price_str)
                    if 1 <= val <= 10000000:
                        return val
                except ValueError:
                    continue
        return None

    def _extract_brand(self, title: str) -> str:
        """Extract common brand name from title."""
        known_brands = [
            "Nike", "Adidas", "Puma", "Reebok", "Asics", "Under Armour", "Skechers",
            "Apple", "Samsung", "Dell", "HP", "Lenovo", "Asus", "Sony", "boAt",
            "OnePlus", "Xiaomi", "Realme", "Noise", "Fire-Boltt", "Bose", "Canon",
            "Nikon", "Fujifilm", "Panasonic", "Secretlab", "Herman Miller", "Logitech",
            "Milton", "Cello", "Borosil", "Thermos", "Hydro Flask", "Nalgene", "Tupperware"
        ]
        for b in known_brands:
            if re.search(r"\b" + re.escape(b) + r"\b", title, re.IGNORECASE):
                return b
        words = title.split()
        return words[0] if words else ""

    def _extract_image_url(self, clean_url: str, html_block: str) -> Optional[str]:
        """Extract product thumbnail URL. Rejects merchant favicons and logos."""
        # Check for inline thumbnail in HTML search result block
        img_match = re.search(r'<img [^>]*src="([^"]+)"', html_block, re.IGNORECASE)
        if img_match:
            img_src = img_match.group(1)
            if img_src.startswith("//"):
                img_src = "https:" + img_src
            if img_src.startswith("http"):
                # Reject favicon/logo patterns
                is_logo = any(pat in img_src.lower() for pat in LOGO_IMAGE_PATTERNS)
                if not is_logo:
                    return img_src

        # Do NOT fall back to favicon — return None instead of a logo
        return None

    def _compute_relevance_score(
        self,
        title: str,
        snippet: str,
        query: str,
        url: str,
        merchant: str
    ) -> float:
        """
        Compute a 0.0–1.0 relevance score for a search result.
        Factors: keyword match, merchant trust, URL type.
        """
        score = 0.0

        # 1. Keyword match fraction (40% weight)
        query_words = set(re.findall(r'\w+', query.lower()))
        combined_text = (title + " " + snippet).lower()
        text_words = set(re.findall(r'\w+', combined_text))
        if query_words:
            match_fraction = len(query_words & text_words) / len(query_words)
            score += match_fraction * 0.40

        # 2. Trusted merchant (30% weight)
        if self._is_trusted_domain(url):
            score += 0.30
        else:
            score += 0.10

        # 3. URL type (30% weight)
        if self._is_product_detail_url(url):
            score += 0.30  # Real product page
        elif not self._is_search_or_category_url(url):
            score += 0.10  # Unknown but not obviously a search page

        return min(score, 1.0)

    def search_products(
        self,
        query: str,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        market: Optional[Market] = None
    ) -> List[Product]:
        """Search products on live e-commerce web listings in target market."""
        market_obj = market or MarketResolver.resolve_market("IN")
        search_term = f"{category or ''} {query}".strip()
        print(f"🔍 [LiveWebConnector] Market '{market_obj.country_code}' ({market_obj.currency_code}) search for: '{search_term}'")

        html = self._fetch_search_html(search_term, market_obj.preferred_domains)
        if not html:
            return []

        products: List[Product] = []
        # Parse DuckDuckGo Lite search result links
        results_blocks = re.findall(
            r'<a [^>]*rel="nofollow"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL
        )

        seen_urls = set()
        candidates: List[Dict] = []

        for item in results_blocks:
            clean_url = self._clean_url(item[0])
            raw_title = item[1]
            clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
            clean_snippet = clean_title

            # Skip empty, duplicate, or DuckDuckGo ad URLs
            if not clean_url or clean_url in seen_urls:
                continue

            seen_urls.add(clean_url)

            # Determine merchant
            domain = SourceVerifier.extract_domain(clean_url)
            merchant = "Unknown"
            for d, m in DOMAINS_TO_MERCHANT.items():
                if domain == d or domain.endswith("." + d):
                    merchant = m
                    break
            if merchant == "Unknown" and domain:
                merchant = domain.split(".")[0].capitalize()

            is_listing_url = self._is_search_or_category_url(clean_url)
            is_product_page = self._is_product_detail_url(clean_url)

            # Extract price from title or snippet
            price = self._extract_price(clean_title, market_obj.currency_code)

            # Apply strict price filters for individual products
            if not is_listing_url:
                if min_price and price and price < min_price:
                    continue
                if max_price and price and price > max_price:
                    continue

            # Classify result_type:
            # If URL is a product page (/dp/ASIN, /p/ID) or has verified price -> Type A (individual_product)
            # If URL is a search/category listing page -> Type B (browse_list)
            if is_product_page or (not is_listing_url and price):
                result_type = "individual_product"
                # If price is missing from snippet for an exact product page, assign estimated market price
                if not price:
                    price_val = max_price * 0.85 if max_price else 799.0
                    price_estimated = True
                else:
                    price_val = price
                    price_estimated = False
                title_for_prod = clean_title
            else:
                result_type = "browse_list"
                price_val = price or 0.0
                price_estimated = True
                title_for_prod = f"Browse {search_term.title()} on {merchant}"

            # Compute relevance score
            relevance = self._compute_relevance_score(
                clean_title, clean_snippet, search_term, clean_url, merchant
            )

            is_trusted = self._is_trusted_domain(clean_url)
            img_url = self._extract_image_url(clean_url, clean_snippet)
            brand = self._extract_brand(clean_title)
            prod_id = f"live_{market_obj.country_code.lower()}_{hashlib.md5(clean_url.encode()).hexdigest()[:8]}"

            candidates.append({
                "id": prod_id,
                "title": title_for_prod[:100],
                "snippet": clean_snippet[:200],
                "url": clean_url,
                "merchant": merchant,
                "price": round(float(price_val), 2),
                "price_estimated": price_estimated,
                "currency": market_obj.currency_code,
                "brand": brand,
                "img_url": img_url,
                "relevance": relevance,
                "is_product_page": is_product_page,
                "is_trusted": is_trusted,
                "domain": domain,
                "result_type": result_type
            })

        # Sort candidates by relevance score descending
        candidates.sort(key=lambda c: c["relevance"], reverse=True)

        # Build Product objects from candidates
        for c in candidates[:10]:
            product = Product(
                id=c["id"],
                name=c["title"],
                brand=c["brand"],
                category=category or "General",
                description=c["snippet"] or c["title"],
                price=c["price"],
                currency=c["currency"],
                rating=None,
                review_count=None,
                availability=True,
                merchant=c["merchant"],
                merchant_name=c["merchant"],
                source_name=f"{c['merchant']} ({market_obj.country_code})",
                product_url=c["url"],
                delivery_information=f"Available in {market_obj.country_name}",
                images=[c["img_url"]] if c["img_url"] else [],
                retrieved_at=datetime.datetime.utcnow().isoformat() + "Z",
                is_verified=c["is_trusted"],
                is_demo=False,
                is_individual_product=c["is_product_page"],
                result_type=c["result_type"],
                specifications={
                    "is_product_page": c["is_product_page"],
                    "relevance_score": round(c["relevance"], 3),
                    "price_estimated": c["price_estimated"],
                }
            )

            if SourceVerifier.verify_product(product):
                products.append(product)

        print(f"✅ [LiveWebConnector] Found {len(products)} candidates for '{search_term}' in {market_obj.country_code}.")
        return products

    def get_product_details(self, product_id_or_url: str) -> Optional[Product]:
        """Live details retrieval by URL."""
        if SourceVerifier.is_valid_url(product_id_or_url):
            domain = SourceVerifier.extract_domain(product_id_or_url)
            merchant = "Commerce Source"
            for d, m in DOMAINS_TO_MERCHANT.items():
                if domain == d or domain.endswith("." + d):
                    merchant = m
                    break
            prod_id = f"live_{hashlib.md5(product_id_or_url.encode()).hexdigest()[:8]}"
            return Product(
                id=prod_id,
                name=f"Product from {merchant}",
                brand=merchant,
                category="General",
                description="Live product retrieved from official merchant.",
                price=0.0,
                currency="INR",
                merchant=merchant,
                merchant_name=merchant,
                source_name=f"{merchant} Store",
                product_url=product_id_or_url,
                retrieved_at=datetime.datetime.utcnow().isoformat() + "Z",
                is_verified=True,
                is_demo=False
            )
        return None
