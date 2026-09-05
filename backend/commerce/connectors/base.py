from abc import ABC, abstractmethod
from typing import List, Optional
from backend.commerce.models import Product

class CommerceConnector(ABC):
    @abstractmethod
    def get_source_name(self) -> str:
        """Return the friendly name of this commerce source (e.g. 'Amazon India', 'Flipkart', 'Live Web Search')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this connector is currently active and configured (e.g. valid network/API credentials)."""
        pass

    @abstractmethod
    def search_products(
        self, 
        query: str, 
        category: Optional[str] = None, 
        min_price: Optional[float] = None, 
        max_price: Optional[float] = None
    ) -> List[Product]:
        """Search products from this specific commerce source."""
        pass

    @abstractmethod
    def get_product_details(self, product_id_or_url: str) -> Optional[Product]:
        """Retrieve full details for a product by ID or URL."""
        pass
