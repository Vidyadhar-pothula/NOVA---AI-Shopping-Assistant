from typing import List, Dict, Any, Optional
import datetime
import json
from backend.database.db import get_connection
from backend.commerce.models import Product


class CatalogService:
    """Build a structured catalogue from the current page / session products only."""

    def calculate_ai_readability(self, prod: Dict[str, Any]) -> Dict[str, Any]:
        has_id = bool(prod.get("id"))
        has_name = bool(prod.get("name") or prod.get("title"))
        has_price = prod.get("price") is not None and str(prod.get("price")) != "0" and float(prod.get("price") or 0) > 0
        has_availability = prod.get("availability") is not None or prod.get("in_stock") is not None
        url = prod.get("product_url") or prod.get("url") or ""
        has_exact_url = bool(url) and str(url).startswith("http")

        checks = {
            "Product identity": has_id,
            "Product name": has_name,
            "Price": has_price,
            "Availability": has_availability,
            "Exact product URL": has_exact_url,
            "Brand": bool(prod.get("brand")),
            "Category": bool(prod.get("category")),
            "Image": bool(prod.get("image_url") or prod.get("image") or (prod.get("images") or [None])[0])
        }

        required_passed = sum([has_id, has_name, has_price, has_exact_url])
        if required_passed == 4:
            status = "AI-READABLE"
        elif required_passed >= 2:
            status = "PARTIALLY READABLE"
        else:
            status = "INSUFFICIENT DATA"

        return {
            "status": status,
            "is_actionable": status == "AI-READABLE",
            "passed_checks": [k for k, v in checks.items() if v],
            "missing_checks": [k for k, v in checks.items() if not v]
        }

    def _product_to_catalog_item(self, p: Product) -> Dict[str, Any]:
        images = p.images or []
        specs = p.specifications or {}
        p_dict: Dict[str, Any] = {
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "currency": p.currency,
            "product_url": p.product_url,
            "is_individual_product": p.is_individual_product,
            "result_type": p.result_type,
        }
        if p.merchant_name or p.merchant:
            p_dict["merchant"] = p.merchant_name or p.merchant
        if p.brand:
            p_dict["brand"] = p.brand
        if p.category:
            p_dict["category"] = p.category
        if p.description:
            p_dict["description"] = p.description
        if p.availability is not None:
            p_dict["availability"] = p.availability
        if p.rating is not None:
            p_dict["rating"] = p.rating
        if p.review_count is not None:
            p_dict["review_count"] = p.review_count
        if images:
            p_dict["images"] = images
            p_dict["image_url"] = images[0]
        if specs.get("mrp") is not None:
            p_dict["mrp"] = specs.get("mrp")
        if specs.get("mrp_text"):
            p_dict["mrp_text"] = specs.get("mrp_text")
        if specs.get("discount"):
            p_dict["discount"] = specs.get("discount")
        if specs.get("price_text"):
            p_dict["price_text"] = specs.get("price_text")
        if specs.get("price_confidence"):
            p_dict["price_confidence"] = specs.get("price_confidence")
        extra_specs = {
            k: v for k, v in specs.items()
            if k not in {"source", "source_page_url"} and v not in (None, "", [])
        }
        if extra_specs:
            p_dict["specifications"] = extra_specs
        p_dict["ai_readability"] = self.calculate_ai_readability(p_dict)
        return p_dict

    def inspect_session_catalog(
        self,
        session_id: str,
        page_url: Optional[str] = None,
        source_name: Optional[str] = None,
        raw_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        products_list: List[Dict[str, Any]] = []
        detected_count = 0
        debug: Dict[str, Any] = {}

        if raw_items:
            detected_count = len(raw_items)
            for item in raw_items:
                name = (item.get("name") or item.get("title") or "").strip()
                url = item.get("product_url") or item.get("url") or page_url or ""
                if not name or not url or not str(url).startswith("http"):
                    continue
                try:
                    price_val = float(item.get("price") or 0)
                except (TypeError, ValueError):
                    price_val = 0
                p_dict: Dict[str, Any] = {
                    "id": item.get("id"),
                    "name": name,
                    "price": price_val or None,
                    "currency": item.get("currency") or "INR",
                    "product_url": url,
                    "is_individual_product": True,
                }
                if item.get("merchant") or source_name:
                    p_dict["merchant"] = item.get("merchant") or source_name
                if item.get("brand"):
                    p_dict["brand"] = item.get("brand")
                if item.get("category"):
                    p_dict["category"] = item.get("category")
                if item.get("image") or item.get("image_url"):
                    p_dict["image_url"] = item.get("image") or item.get("image_url")
                if item.get("rating") is not None:
                    p_dict["rating"] = item.get("rating")
                if item.get("availability") is not None:
                    p_dict["availability"] = item.get("availability")
                p_dict["ai_readability"] = self.calculate_ai_readability(p_dict)
                products_list.append(p_dict)
        else:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_page_product_ids, current_page_url, current_page_source, catalogue_debug FROM session_states WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            ids: List[str] = []
            debug: Dict[str, Any] = {}
            if row:
                page_url = page_url or row["current_page_url"]
                source_name = source_name or row["current_page_source"]
                if row["current_page_product_ids"]:
                    try:
                        ids = json.loads(row["current_page_product_ids"])
                    except Exception:
                        ids = []
                if row["catalogue_debug"]:
                    try:
                        debug = json.loads(row["catalogue_debug"])
                    except Exception:
                        debug = {}
            detected_count = debug.get("detected_count", len(ids))
            if ids:
                placeholders = ",".join("?" for _ in ids)
                cursor.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", ids)
                rows = cursor.fetchall()
                prod_map = {r["id"]: Product.from_row(r) for r in rows}
                for pid in ids:
                    if pid in prod_map:
                        p = prod_map[pid]
                        if p.name and p.product_url:
                            products_list.append(self._product_to_catalog_item(p))
            conn.close()

        source: Dict[str, Any] = {}
        if source_name:
            source["merchant_name"] = source_name
        if page_url:
            source["page_url"] = page_url
        source["timestamp"] = datetime.datetime.now().isoformat()
        source["page_type"] = "product_listing" if len(products_list) > 1 else "individual_product"

        payload = {
            "status": "success",
            "source": source,
            "summary": {
                "total_detected": detected_count,
                "total_valid": len(products_list),
                "exact_urls_verified": sum(1 for p in products_list if p.get("product_url")),
                "prices_verified": sum(1 for p in products_list if p.get("price")),
                "ai_readable_count": sum(1 for p in products_list if p.get("ai_readability", {}).get("is_actionable")),
            },
            "products": products_list,
        }
        if debug:
            payload["extraction_debug"] = debug
        if not products_list:
            payload["message"] = (
                "I couldn't extract the products from this page yet."
                if not debug
                else "I couldn't extract the products from this page yet. Catalogue debug is attached for Agent Console."
            )
        return payload

    def inspect_catalog_context(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        raw_items: Optional[List[Dict[str, Any]]] = None,
        page_url: Optional[str] = None,
        source_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if session_id or raw_items:
            return self.inspect_session_catalog(
                session_id=session_id or "nova_authoritative_cart",
                page_url=page_url,
                source_name=source_name,
                raw_items=raw_items,
            )
        return {
            "status": "success",
            "source": {"timestamp": datetime.datetime.now().isoformat()},
            "summary": {
                "total_detected": 0,
                "total_valid": 0,
                "exact_urls_verified": 0,
                "prices_verified": 0,
                "ai_readable_count": 0,
            },
            "products": [],
            "message": "No current-page catalogue is available. Open a supported ecommerce page with the NOVA extension, or pass session_id / raw_items.",
        }


catalog_service = CatalogService()
