"""
Market Localization Engine for NOVA Commerce Agent.
Resolves user country code, currency, and e-commerce domain scope dynamically.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

@dataclass
class Market:
    country_code: str
    country_name: str
    currency_code: str
    currency_symbol: str
    preferred_domains: List[str] = field(default_factory=list)
    search_region: str = "in"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "country_code": self.country_code,
            "country_name": self.country_name,
            "currency_code": self.currency_code,
            "currency_symbol": self.currency_symbol,
            "preferred_domains": self.preferred_domains,
            "search_region": self.search_region
        }

MARKETS: Dict[str, Market] = {
    "IN": Market(
        country_code="IN",
        country_name="India",
        currency_code="INR",
        currency_symbol="₹",
        preferred_domains=[
            "amazon.in", "flipkart.com", "myntra.com",
            "nike.com", "tatacliq.com", "croma.com", "ajio.com"
        ],
        search_region="in"
    ),
    "US": Market(
        country_code="US",
        country_name="United States",
        currency_code="USD",
        currency_symbol="$",
        preferred_domains=[
            "amazon.com", "walmart.com", "bestbuy.com",
            "nike.com", "target.com"
        ],
        search_region="us-en"
    ),
    "GB": Market(
        country_code="GB",
        country_name="United Kingdom",
        currency_code="GBP",
        currency_symbol="£",
        preferred_domains=[
            "amazon.co.uk", "argos.co.uk", "currys.co.uk",
            "johnlewis.com", "nike.com"
        ],
        search_region="uk-en"
    ),
    "GLOBAL": Market(
        country_code="GLOBAL",
        country_name="Global Market",
        currency_code="USD",
        currency_symbol="$",
        preferred_domains=["amazon.com", "ebay.com"],
        search_region="wt-wt"
    )
}

class MarketResolver:
    @staticmethod
    def resolve_from_timezone(tz: str) -> Optional[str]:
        """Infer country code from browser IANA timezone string."""
        if not tz:
            return None
        tz_lower = tz.lower()
        if "kolkata" in tz_lower or "calcutta" in tz_lower or "india" in tz_lower:
            return "IN"
        elif "america" in tz_lower or "us/" in tz_lower or "chicago" in tz_lower or "york" in tz_lower:
            return "US"
        elif "london" in tz_lower or "europe/london" in tz_lower or "gb" in tz_lower:
            return "GB"
        return None

    @classmethod
    def resolve_market(
        cls, 
        country_code: Optional[str] = None, 
        currency_code: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Market:
        """
        Resolve Market instance from explicit parameters, timezone, or default to IN.
        """
        code = (country_code or "").upper().strip()
        if code in MARKETS:
            return MARKETS[code]

        # Check timezone hint
        tz_code = cls.resolve_from_timezone(timezone)
        if tz_code in MARKETS:
            return MARKETS[tz_code]

        # Currency code hint
        curr = (currency_code or "").upper().strip()
        if curr == "INR":
            return MARKETS["IN"]
        elif curr == "USD":
            return MARKETS["US"]
        elif curr == "GBP":
            return MARKETS["GB"]

        # Default fallback is IN market
        return MARKETS["IN"]
