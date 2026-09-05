import re
from typing import Dict, Any, Optional
from backend.database.db import get_connection
from backend.commerce.models import Product, CartItem, Cart
from backend.tools.registry import registry

def get_cart(session_id: str = "default_session", **kwargs) -> Dict[str, Any]:
    """Retrieve all items and pricing details for the current active cart."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Ensure cart exists
    cursor.execute("INSERT OR IGNORE INTO carts (id) VALUES (?)", (session_id,))
    conn.commit()
    
    # Query cart items and product details
    cursor.execute("""
        SELECT ci.quantity, p.* 
        FROM cart_items ci 
        JOIN products p ON ci.product_id = p.id 
        WHERE ci.cart_id = ?
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    for row in rows:
        prod = Product.from_row(row)
        items.append(CartItem(product=prod, quantity=row["quantity"]))
        
    cart = Cart(cart_id=session_id, items=items)
    return cart.to_dict()

def add_to_cart(product_id: str, quantity: int = 1, session_id: str = "default_session", **kwargs) -> Dict[str, Any]:
    """Add a product to the cart. Specifying a product_id and optional quantity."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if product exists by exact canonical ID
    cursor.execute("SELECT availability, name, price, is_individual_product, id FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    
    # Fallback: if product_id is a name string, pronoun, or ordinal reference, perform context & DB lookup
    if not row:
        target_ref = str(product_id or "").strip().lower()
        active_products = []
        
        # 1. Fetch current-page products first (authoritative for "this"), then conversation products
        cursor.execute(
            "SELECT last_product_ids, current_page_product_ids FROM session_states WHERE session_id = ?",
            (session_id,),
        )
        s_row = cursor.fetchone()
        if s_row:
            import json
            page_ids = []
            conv_ids = []
            try:
                if s_row["current_page_product_ids"]:
                    page_ids = json.loads(s_row["current_page_product_ids"])
            except Exception:
                page_ids = []
            try:
                if s_row["last_product_ids"]:
                    conv_ids = json.loads(s_row["last_product_ids"])
            except Exception:
                conv_ids = []
            pids = page_ids or conv_ids
            if pids:
                    placeholders = ",".join("?" for _ in pids)
                    cursor.execute(f"SELECT availability, name, price, is_individual_product, id, brand, merchant_name FROM products WHERE id IN ({placeholders}) AND is_individual_product = 1 AND price > 0", pids)
                    rows = cursor.fetchall()
                    # Preserve exact active display order
                    prod_map = {r["id"]: r for r in rows}
                    active_products = [prod_map[pid] for pid in pids if pid in prod_map]

        # 2. Check ordinal / pronoun references against active products
        if active_products:
            if target_ref in ["that", "it", "this", "recommended", "the product"]:
                row = active_products[0]
                product_id = row["id"]
            elif target_ref in ["first", "1st", "1", "one"]:
                row = active_products[0]
                product_id = row["id"]
            elif target_ref in ["second", "2nd", "2", "two"] and len(active_products) > 1:
                row = active_products[1]
                product_id = row["id"]
            elif target_ref in ["third", "3rd", "3", "three"] and len(active_products) > 2:
                row = active_products[2]
                product_id = row["id"]
            elif target_ref in ["last", "final"] and active_products:
                row = active_products[-1]
                product_id = row["id"]

        # 3. If still not matched, check keyword/name matching against active products
        if not row and active_products and target_ref:
            ref_words = set(re.findall(r'[a-z0-9]+', target_ref))
            matching_rows = []
            for p_row in active_products:
                name_words = set(re.findall(r'[a-z0-9]+', p_row["name"].lower()))
                brand_words = set(re.findall(r'[a-z0-9]+', (p_row["brand"] or "").lower()))
                if ref_words.issubset(name_words) or ref_words.issubset(brand_words) or target_ref in p_row["name"].lower():
                    matching_rows.append(p_row)
            
            if len(matching_rows) == 1:
                row = matching_rows[0]
                product_id = row["id"]
            elif len(matching_rows) > 1:
                conn.close()
                options_str = "; ".join(f"({i+1}) {r['name']} (₹{r['price']})" for i, r in enumerate(matching_rows[:3]))
                return {
                    "status": "clarification_required",
                    "error": f"Multiple matching products found for '{product_id}': {options_str}. Please specify which one you'd like to add."
                }

        # 4. Fallback search in products DB table by name
        if not row and target_ref:
            cursor.execute("SELECT availability, name, price, is_individual_product, id FROM products WHERE LOWER(name) LIKE ? AND is_individual_product = 1 AND price > 0", (f"%{target_ref}%",))
            db_matches = cursor.fetchall()
            if len(db_matches) == 1:
                row = db_matches[0]
                product_id = row["id"]
            elif len(db_matches) > 1:
                conn.close()
                options_str = "; ".join(f"({i+1}) {r['name']} (₹{r['price']})" for i, r in enumerate(db_matches[:3]))
                return {
                    "status": "clarification_required",
                    "error": f"Multiple products match '{product_id}': {options_str}. Please specify which option you want."
                }

    if not row:
        conn.close()
        return {"error": f"Product with ID '{product_id}' does not exist."}

    # Strict commerce identity validation: browse/category pages and ₹0 items cannot enter cart
    if (row["is_individual_product"] is not None and not row["is_individual_product"]) or (row["price"] is not None and row["price"] <= 0):
        conn.close()
        return {"error": "Cannot add generic search/browse results to cart. Only verified individual products can be added."}
        
    if not row["availability"]:
        conn.close()
        return {"error": f"Sorry, '{row['name']}' is currently out of stock."}
        
    # Ensure cart exists
    cursor.execute("INSERT OR IGNORE INTO carts (id) VALUES (?)", (session_id,))
    
    # Check if item is already in cart
    cursor.execute("SELECT quantity FROM cart_items WHERE cart_id = ? AND product_id = ?", (session_id, product_id))
    item_row = cursor.fetchone()
    
    if item_row:
        new_qty = item_row["quantity"] + quantity
        cursor.execute("UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND product_id = ?", (new_qty, session_id, product_id))
    else:
        cursor.execute("INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (?, ?, ?)", (session_id, product_id, quantity))
        
    conn.commit()
    conn.close()
    
    # Return updated cart
    return {
        "success": True,
        "message": f"Added {quantity}x '{row['name']}' (₹{row['price']} each) to your cart.",
        "cart": get_cart(session_id)
    }

def remove_from_cart(product_id: str, quantity: int = 1, session_id: str = "default_session", **kwargs) -> Dict[str, Any]:
    """Remove a product (or decrement its quantity) from the cart."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if item is in cart
    cursor.execute("SELECT quantity, name FROM cart_items ci JOIN products p ON ci.product_id = p.id WHERE ci.cart_id = ? AND ci.product_id = ?", (session_id, product_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Product is not in your cart."}
        
    current_qty = row["quantity"]
    prod_name = row["name"]
    
    if current_qty <= quantity:
        cursor.execute("DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?", (session_id, product_id))
        msg = f"Removed '{prod_name}' completely from your cart."
    else:
        new_qty = current_qty - quantity
        cursor.execute("UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND product_id = ?", (new_qty, session_id, product_id))
        msg = f"Reduced quantity of '{prod_name}' by {quantity}."
        
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": msg,
        "cart": get_cart(session_id)
    }

def clear_cart(session_id: str = "default_session", **kwargs) -> Dict[str, Any]:
    """Clear all items in the current active cart."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (session_id,))
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": "Your cart has been cleared.",
        "cart": get_cart(session_id)
    }

# Register tools with schemas (excluding session_id parameter)

get_cart_schema = {
    "type": "function",
    "function": {
        "name": "get_cart",
        "description": "View current products inside the cart, their quantities, subtotals, and total price.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

add_to_cart_schema = {
    "type": "function",
    "function": {
        "name": "add_to_cart",
        "description": "Add a specific product to the shopping cart by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The ID of the product to add."
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of items to add. Defaults to 1."
                }
            },
            "required": ["product_id"]
        }
    }
}

remove_from_cart_schema = {
    "type": "function",
    "function": {
        "name": "remove_from_cart",
        "description": "Remove a specific product from the shopping cart by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The ID of the product to remove."
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of items to remove. Defaults to 1."
                }
            },
            "required": ["product_id"]
        }
    }
}

clear_cart_schema = {
    "type": "function",
    "function": {
        "name": "clear_cart",
        "description": "Clear all products in the active shopping cart.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

registry.register(get_cart_schema, get_cart)
registry.register(add_to_cart_schema, add_to_cart)
registry.register(remove_from_cart_schema, remove_from_cart)
registry.register(clear_cart_schema, clear_cart)
