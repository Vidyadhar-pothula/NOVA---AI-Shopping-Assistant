import datetime
from typing import List, Optional
from backend.commerce.connectors.base import CommerceConnector
from backend.commerce.models import Product
from backend.database.db import get_connection

class DemoCommerceConnector(CommerceConnector):
    def __init__(self, merchant_name: str = "DemoStore"):
        self.merchant_name = merchant_name

    def get_source_name(self) -> str:
        return f"{self.merchant_name} (Demo)"

    def is_available(self) -> bool:
        return True

    def search_products(
        self, 
        query: str, 
        category: Optional[str] = None, 
        min_price: Optional[float] = None, 
        max_price: Optional[float] = None
    ) -> List[Product]:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = "SELECT * FROM products WHERE merchant = ?"
        params = [self.merchant_name]
        
        if query:
            keywords = query.split()
            for kw in keywords:
                sql += " AND (name LIKE ? OR description LIKE ? OR brand LIKE ?)"
                params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
                
        if category:
            sql += " AND LOWER(category) = LOWER(?)"
            params.append(category)
            
        if min_price is not None:
            sql += " AND price >= ?"
            params.append(min_price)
            
        if max_price is not None:
            sql += " AND price <= ?"
            params.append(max_price)
            
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        
        products = []
        for row in rows:
            p = Product.from_row(row)
            p.is_demo = True
            p.is_verified = False
            p.source_name = f"{self.merchant_name} (Demo Fallback)"
            if not p.product_url:
                p.product_url = f"https://example.com/demo-product/{p.id}"
            products.append(p)

        return products

    def get_product_details(self, product_id_or_url: str) -> Optional[Product]:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM products WHERE id = ? AND merchant = ?", (product_id_or_url, self.merchant_name))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            p = Product.from_row(row)
            p.is_demo = True
            p.is_verified = False
            p.source_name = f"{self.merchant_name} (Demo Fallback)"
            if not p.product_url:
                p.product_url = f"https://example.com/demo-product/{p.id}"
            return p
        return None
