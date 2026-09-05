from typing import List, Dict, Any, Optional
from backend.commerce.location import Market, MarketResolver
from backend.discovery.sales_provider import SalesProvider
from backend.discovery.festival_provider import FestivalProvider
from backend.discovery.sports_provider import SportsProvider
from backend.discovery.movie_provider import MovieProvider

class DiscoveryEngine:
    def __init__(self):
        self.sales_provider = SalesProvider()
        self.festival_provider = FestivalProvider()
        self.sports_provider = SportsProvider()
        self.movie_provider = MovieProvider()

    def get_discovery_feed(
        self,
        category: str = "all",
        query: Optional[str] = None,
        market_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        country_code = market_override.get("country_code") if isinstance(market_override, dict) else None
        currency_code = market_override.get("currency_code") if isinstance(market_override, dict) else None
        market = MarketResolver.resolve_market(country_code=country_code, currency_code=currency_code)

        all_items: List[Dict[str, Any]] = []

        cat_clean = (category or "all").lower().strip()

        if cat_clean in ["all", "deals", "sales", "offers"]:
            all_items.extend(self.sales_provider.get_sales_events(market))

        if cat_clean in ["all", "festivals", "holidays", "cultural"]:
            all_items.extend(self.festival_provider.get_festivals(market))

        if cat_clean in ["all", "sports", "tournaments", "merch"]:
            all_items.extend(self.sports_provider.get_sports_events_and_merch(market))

        if cat_clean in ["all", "movies", "entertainment", "cinema"]:
            all_items.extend(self.movie_provider.get_movies_and_merch(market))

        # Query filter if user provided specific search term (e.g., "World Cup", "Cricket", "India")
        if query:
            q_clean = query.lower()
            filtered = []
            for item in all_items:
                text = (item.get("title", "") + " " + item.get("description", "") + " " + item.get("category", "")).lower()
                if any(w in text for w in q_clean.split()):
                    filtered.append(item)
            if filtered:
                all_items = filtered

        # Deduplicate items by URL / ID
        seen_urls = set()
        deduped = []
        for item in all_items:
            url = item.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduped.append(item)

        return {
            "status": "success",
            "market": {
                "country_name": market.country_name,
                "country_code": market.country_code,
                "currency_code": market.currency_code,
                "currency_symbol": market.currency_symbol
            },
            "category": category,
            "total_items": len(deduped),
            "feed": deduped
        }

discovery_engine = DiscoveryEngine()
