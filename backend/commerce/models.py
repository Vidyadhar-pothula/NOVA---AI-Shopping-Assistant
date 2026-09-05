import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Product:
    id: str
    name: str
    brand: str
    category: str
    description: str
    price: float
    currency: str = "INR"
    rating: Optional[float] = None
    review_count: Optional[int] = None
    availability: bool = True
    merchant: str = "Unknown"
    merchant_name: str = "Unknown"
    source_name: str = "Commerce Source"
    product_url: str = ""
    delivery_information: Optional[str] = None
    specifications: Dict[str, Any] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)
    retrieved_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")
    is_verified: bool = True
    is_demo: bool = False
    is_individual_product: bool = True
    result_type: str = "individual_product"  # "individual_product" (Type A) or "browse_list" (Type B)

    def __post_init__(self):
        # Synchronize merchant and merchant_name if one is set
        if self.merchant_name == "Unknown" and self.merchant != "Unknown":
            self.merchant_name = self.merchant
        elif self.merchant == "Unknown" and self.merchant_name != "Unknown":
            self.merchant = self.merchant_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "title": self.name,  # Alias for standard schema compliance
            "brand": self.brand,
            "category": self.category,
            "description": self.description,
            "price": self.price,
            "currency": self.currency,
            "rating": self.rating,
            "review_count": self.review_count,
            "availability": self.availability,
            "merchant": self.merchant,
            "merchant_name": self.merchant_name,
            "source_name": self.source_name,
            "product_url": self.product_url,
            "delivery_information": self.delivery_information,
            "specifications": self.specifications,
            "images": self.images,
            "retrieved_at": self.retrieved_at,
            "is_verified": self.is_verified,
            "is_demo": self.is_demo,
            "is_individual_product": self.is_individual_product,
            "result_type": self.result_type
        }

    @classmethod
    def from_row(cls, row) -> 'Product':
        import json
        row_dict = dict(row)
        
        # Parse specifications JSON
        spec_val = row_dict.get("specifications")
        specs = {}
        if spec_val:
            try:
                specs = json.loads(spec_val)
            except Exception:
                specs = {}
                
        # Parse images JSON
        img_val = row_dict.get("images")
        images = []
        if img_val:
            try:
                images = json.loads(img_val)
            except Exception:
                images = []
                
        merchant = row_dict.get("merchant_name") or row_dict.get("merchant", "Unknown")
        return cls(
            id=row_dict["id"],
            name=row_dict.get("name") or row_dict.get("title", ""),
            brand=row_dict.get("brand", ""),
            category=row_dict.get("category", ""),
            description=row_dict.get("description", ""),
            price=float(row_dict["price"]),
            currency=row_dict.get("currency", "INR"),
            rating=row_dict.get("rating"),
            review_count=row_dict.get("review_count"),
            availability=bool(row_dict.get("availability", 1)),
            merchant=merchant,
            merchant_name=merchant,
            source_name=row_dict.get("source_name", "Commerce Source"),
            product_url=row_dict.get("product_url", ""),
            delivery_information=row_dict.get("delivery_information"),
            specifications=specs,
            images=images,
            retrieved_at=row_dict.get("retrieved_at", datetime.datetime.utcnow().isoformat() + "Z"),
            is_verified=bool(row_dict.get("is_verified", 1)),
            is_demo=bool(row_dict.get("is_demo", 0)),
            is_individual_product=bool(row_dict.get("is_individual_product", 1)),
            result_type=row_dict.get("result_type", "individual_product")
        )


@dataclass
class CartItem:
    product: Product
    quantity: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product": self.product.to_dict(),
            "quantity": self.quantity,
            "subtotal": self.product.price * self.quantity
        }

@dataclass
class Cart:
    cart_id: str
    items: List[CartItem] = field(default_factory=list)

    @property
    def total_amount(self) -> float:
        return sum(item.product.price * item.quantity for item in self.items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cart_id": self.cart_id,
            "items": [item.to_dict() for item in self.items],
            "total_amount": self.total_amount,
            "currency": "INR" if not self.items else self.items[0].product.currency
        }

@dataclass
class Order:
    id: str
    session_id: str
    status: str # 'prepared', 'paid', 'cancelled'
    total_amount: float
    currency: str
    items: List[Dict[str, Any]] = field(default_factory=list)
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "status": self.status,
            "total_amount": self.total_amount,
            "currency": self.currency,
            "items": self.items,
            "created_at": self.created_at
        }
