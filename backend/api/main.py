import os
import sys
import json
import hashlib
import datetime
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

# Add parent directory to path to enable backend imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.config import RAZORPAY_KEY_ID, DEBUG
from backend.database.db import init_db, get_connection
from backend.agent.agent import run_agent, clear_session
from backend.tools.cart_tools import get_cart, add_to_cart, clear_cart
from backend.commerce.models import Product
from backend.payment.razorpay import create_razorpay_order, verify_payment_signature
from backend.integrations.calendar_adapter import calendar_adapter
from backend.integrations.email_adapter import email_adapter
from backend.personalization.history_analyzer import history_analyzer
from backend.personalization.recommendation_engine import recommendation_engine
from backend.discovery.engine import discovery_engine

from backend.providers.audit_provider import audit_service
from backend.providers.revenue_provider import revenue_analytics_service
from backend.providers.catalog_provider import catalog_service
from backend.providers.bounds_provider import bounds_service
from backend.providers.email_provider import email_service

app = FastAPI(title="NOVA: Personal AI Commerce Agent", version="1.0.0")

# Allow frontend dev server to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── No-cache middleware for static files (dev convenience) ────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheStaticMiddleware)

from backend.commerce.location import MarketResolver

# ── Request / Response Models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    market: Optional[Dict[str, Any]] = None

class ClearRequest(BaseModel):
    session_id: str

class CreatePaymentOrderRequest(BaseModel):
    internal_order_id: str   # Our order ID (ord_xxx)

class VerifyPaymentRequest(BaseModel):
    internal_order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class InspectCatalogRequest(BaseModel):
    query: Optional[str] = None
    category: Optional[str] = None
    raw_items: Optional[list] = None
    page_url: Optional[str] = None
    source_name: Optional[str] = None
    session_id: Optional[str] = None

class ExternalPageContextRequest(BaseModel):
    session_id: str
    products: List[Dict[str, Any]] = []
    page_url: Optional[str] = None
    source_name: Optional[str] = None
    extraction_debug: Optional[Dict[str, Any]] = None

class ExternalAddToCartRequest(BaseModel):
    session_id: str
    product: Dict[str, Any]
    quantity: Optional[int] = 1
    page_url: Optional[str] = None
    source_name: Optional[str] = None

class TestEmailRequest(BaseModel):
    recipient: Optional[str] = None
    subject: Optional[str] = None
    category: Optional[str] = "all"

# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup_event():
    init_db()
    print("✅ NOVA backend started. Database initialized.")
    print(f"   Razorpay Key ID: {RAZORPAY_KEY_ID[:15]}...")

# ── Market Detection Endpoint ─────────────────────────────────────────────────

@app.get("/api/health")
@app.get("/health")
async def health_endpoint():
    return JSONResponse(content={"status": "ok", "service": "NOVA AI Commerce Agent", "online": True})

@app.get("/api/market/detect")
async def detect_market_endpoint(country: Optional[str] = None, currency: Optional[str] = None, timezone: Optional[str] = None):
    m = MarketResolver.resolve_market(country_code=country, currency_code=currency, timezone=timezone)
    return JSONResponse(content=m.to_dict())

# ── Chat API ──────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.session_id or not req.message:
        raise HTTPException(status_code=400, detail="session_id and message are required")
    try:
        result = run_agent(req.session_id, req.message, market_override=req.market)

        # Surface proceed_to_payment results so the frontend can immediately open the
        # Razorpay Checkout panel. Without this, the conversational agent would say
        # "complete the panel" but the frontend would have no order id / amount to
        # render the payment UI with, so the flow stalls.
        payment_handoff = None
        tools = result.get("executed_tools") or []
        for t in tools:
            if t.get("name") == "proceed_to_payment":
                r = t.get("result") or {}
                if r.get("success") and r.get("razorpay_order_id"):
                    payment_handoff = {
                        "internal_order_id": r.get("internal_order_id"),
                        "razorpay_order_id": r.get("razorpay_order_id"),
                        "amount": r.get("amount"),
                        "amount_paise": r.get("amount_paise"),
                        "currency": r.get("currency"),
                        "demo_mode": r.get("demo_mode", False),
                        "stage": r.get("stage", "razorpay_order_ready"),
                        "next_action_user": r.get("next_action_user"),
                    }
                    break
        if payment_handoff:
            payment_handoff["success"] = True
            result["payment_handoff"] = payment_handoff

        return JSONResponse(content=result)
    except Exception as e:
        print(f"Chat endpoint error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "response": "Sorry, I encountered an internal error. Please try again."}
        )


# ── Discover & Integrations APIs ───────────────────────────────────────────────

from backend.agent.agent import update_active_products, update_current_page_products

class IntegrationsSettingsRequest(BaseModel):
    calendar_connected: Optional[bool] = None
    email_enabled: Optional[bool] = None
    user_email: Optional[str] = None
    email_frequency: Optional[str] = "daily"
    spending_limit: Optional[float] = None
    clear_spending_limit: Optional[bool] = None

def _host_from_url(url: str) -> str:
    try:
        return urlparse(url or "").hostname or ""
    except Exception:
        return ""

def _is_listing_or_search_url(url: str) -> bool:
    parsed = urlparse(url or "")
    path = (parsed.path or "").lower()
    qs = parse_qs(parsed.query or "")
    if not parsed.scheme.startswith("http"):
        return True
    listing_path_markers = ("/s", "/search", "/collections", "/category", "/categories", "/browse", "/shop", "/pr")
    product_path_markers = ("/dp/", "/gp/product/", "/p/", "/product/", "/itm", "/item/", "/ip/")
    if any(marker in path for marker in product_path_markers):
        return False
    path_parts = [part for part in path.split("/") if part]
    if "pr" in path_parts:
        return True
    if any(marker == path or path.startswith(marker + "/") for marker in listing_path_markers):
        return True
    if any(k.lower() in {"q", "k", "keyword", "keywords", "search"} for k in qs.keys()):
        return True
    return False

def _currency_from_text(value: str, fallback: str = "INR") -> str:
    text = str(value or "")
    if "₹" in text or "rs" in text.lower() or "inr" in text.lower():
        return "INR"
    if "$" in text or "usd" in text.lower():
        return "USD"
    if "£" in text or "gbp" in text.lower():
        return "GBP"
    if "€" in text or "eur" in text.lower():
        return "EUR"
    return fallback

def _money_from_text(value: str) -> Optional[float]:
    import re
    text = str(value or "").replace(",", "")
    pattern = re.compile(
        r"(?:₹|rs\.?|inr|\$|usd|£|gbp|€|eur)\s*([0-9]+(?:\.[0-9]{1,2})?)|"
        r"([0-9]+(?:\.[0-9]{1,2})?)\s*(?:rupees?|dollars?|pounds?|euros?)",
        re.IGNORECASE
    )
    for match in pattern.finditer(text):
        context = text[max(0, match.start() - 24):match.end() + 24]
        is_current_price = re.search(r"\b(current|selling|deal|special|now|price)\b", context, re.IGNORECASE)
        is_non_selling_value = re.search(r"\b(emi|month|monthly|bank|cashback|coupon|discount|off|save|exchange|delivery|shipping|fee|charges|mrp|list price|original price)\b", context, re.IGNORECASE)
        if is_non_selling_value and not is_current_price:
            continue
        amount = match.group(1) or match.group(2)
        if amount:
            return float(amount)
    return None

def _is_valid_catalogue_product(product: Product) -> bool:
    """Catalogue ingest: keep real page items even when cart-confidence checks would reject them."""
    name = (product.name or "").strip()
    if not product.id or len(name) < 4:
        return False
    url = product.product_url or ""
    if not url.startswith("http"):
        return False
    if _is_listing_or_search_url(url):
        return False
    return True


def _normalize_external_product(raw: Dict[str, Any], page_url: Optional[str], source_name: Optional[str]) -> Product:
    product_url = raw.get("product_url") or raw.get("url") or ""
    if not product_url and page_url and not _is_listing_or_search_url(page_url):
        product_url = page_url
    name = (raw.get("name") or raw.get("title") or "").strip()
    merchant = raw.get("merchant") or raw.get("merchant_name") or source_name or _host_from_url(product_url) or "Detected Web Store"
    price_text_amount = _money_from_text(raw.get("priceText", ""))
    price = price_text_amount if price_text_amount is not None else raw.get("price")
    price = float(price or 0)
    currency = raw.get("currency") or _currency_from_text(raw.get("priceText", ""), "INR")
    canonical_basis = "|".join([merchant.lower(), product_url.strip().lower(), name.lower(), str(int(price * 100))])
    product_id = raw.get("id") or "ext_" + hashlib.sha256(canonical_basis.encode("utf-8")).hexdigest()[:20]
    images = raw.get("images") or []
    image = raw.get("image") or raw.get("image_url")
    if image and image not in images:
        images = [image] + images

    return Product(
        id=product_id,
        name=name,
        brand=raw.get("brand") or "",
        category=raw.get("category") or "External Shopping Page",
        description=raw.get("description") or raw.get("visibleText") or "Detected from the current shopping page.",
        price=price,
        currency=currency,
        rating=raw.get("rating"),
        review_count=raw.get("reviews") or raw.get("review_count"),
        availability=False if raw.get("availability") in {False, "false", "out of stock", "OutOfStock"} else True,
        merchant=merchant,
        merchant_name=merchant,
        source_name=source_name or merchant,
        product_url=product_url,
        specifications=raw.get("attributes") or {
            "source_page_url": page_url,
            "source": "browser_extension",
            "rating_text": raw.get("ratingText"),
            "price_text": raw.get("priceText"),
            "price_confidence": raw.get("priceConfidence"),
            "mrp": raw.get("mrp"),
            "mrp_text": raw.get("mrpText"),
            "discount": raw.get("discount") or raw.get("discountText"),
            "sku": raw.get("sku") or raw.get("pid"),
            "availability_text": raw.get("availabilityText"),
        },
        images=images,
        retrieved_at=datetime.datetime.utcnow().isoformat() + "Z",
        is_verified=True,
        is_demo=False,
        is_individual_product=not _is_listing_or_search_url(product_url),
        result_type="individual_product" if not _is_listing_or_search_url(product_url) else "browse_list"
    )

def _validate_external_product(product: Product) -> Optional[str]:
    if not product.id or not product.name:
        return "Cannot add this page item because NOVA could not read a stable product name and identity."
    if not product.product_url or _is_listing_or_search_url(product.product_url):
        return "Cannot add a search/listing page to the NOVA cart. Open an exact product or choose a visible product card first."
    if product.price <= 0:
        return "Cannot add this item because NOVA could not verify a valid product price greater than zero."
    if product.specifications.get("source") == "browser_extension" and product.specifications.get("price_confidence") in {"none", "low"}:
        return "Cannot add this item because NOVA could not confidently identify the current selling price on the page."
    if not product.merchant_name or product.merchant_name == "Unknown":
        return "Cannot add this item because NOVA could not identify the merchant/source."
    if not product.availability:
        return "Cannot add this item because it appears unavailable."
    return None

def _cache_external_products(products: List[Product]) -> List[str]:
    if not products:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    product_ids = []
    for p in products:
        cursor.execute(
            """INSERT INTO products (
                id, name, brand, category, description, price, currency,
                rating, review_count, availability, merchant, delivery_information,
                specifications, images, product_url, merchant_name, source_name,
                retrieved_at, is_verified, is_demo, is_individual_product, result_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                price=excluded.price,
                currency=excluded.currency,
                rating=excluded.rating,
                review_count=excluded.review_count,
                availability=excluded.availability,
                merchant=excluded.merchant,
                merchant_name=excluded.merchant_name,
                source_name=excluded.source_name,
                product_url=excluded.product_url,
                specifications=excluded.specifications,
                images=excluded.images,
                retrieved_at=excluded.retrieved_at,
                is_verified=excluded.is_verified,
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
        product_ids.append(p.id)
    conn.commit()
    conn.close()
    return product_ids

@app.get("/api/discover")
async def get_discover_endpoint(category: Optional[str] = "all", query: Optional[str] = None, country: Optional[str] = None, session_id: Optional[str] = "default_session"):
    market_override = {"country_code": country} if country else None
    res = discovery_engine.get_discovery_feed(category=category, query=query, market_override=market_override)
    if session_id and res.get("feed"):
        pids = [p["id"] for p in res["feed"] if isinstance(p, dict) and "id" in p]
        if pids:
            update_active_products(session_id, pids)
    return JSONResponse(content=res)

@app.get("/api/recommendations")
async def get_recommendations_endpoint(
    session_id: str,
    product_id: Optional[str] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    country: Optional[str] = None
):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    res = recommendation_engine.get_recommendations(
        session_id=session_id,
        current_product_id=product_id,
        category=category,
        query=query,
        country_code=country
    )
    if res.get("recommendations"):
        pids = [p["id"] for p in res["recommendations"] if isinstance(p, dict) and "id" in p]
        if pids:
            update_active_products(session_id, pids)
    return JSONResponse(content=res)

@app.get("/api/history/summary")
async def get_history_summary_endpoint(session_id: str):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    summary = history_analyzer.analyze_frequent_purchases(session_id=session_id)
    return JSONResponse(content=summary)


@app.get("/api/settings/integrations")
async def get_integrations_settings():
    from backend.providers.bounds_provider import get_configured_spending_limit
    return JSONResponse(content={
        "calendar": {
            "is_connected": calendar_adapter.is_connected
        },
        "email": {
            "is_configured": email_adapter.is_configured,
            "user_email": email_adapter.user_email,
            "frequency": email_adapter.frequency
        },
        "spending_limit": get_configured_spending_limit()
    })

@app.post("/api/settings/integrations")
async def update_integrations_settings(req: IntegrationsSettingsRequest):
    from backend.providers.bounds_provider import set_configured_spending_limit, get_configured_spending_limit
    if req.calendar_connected is not None:
        calendar_adapter.set_connection_status(req.calendar_connected)
    if req.user_email is not None or req.email_enabled is not None:
        email_adapter.configure(
            email=req.user_email if req.user_email is not None else (email_adapter.user_email or ""),
            enabled=req.email_enabled if req.email_enabled is not None else True,
            frequency=req.email_frequency or "daily"
        )
    if req.clear_spending_limit:
        set_configured_spending_limit(None)
    elif req.spending_limit is not None:
        set_configured_spending_limit(float(req.spending_limit))
    return JSONResponse(content={
        "success": True,
        "message": "Integration settings updated.",
        "calendar_connected": calendar_adapter.is_connected,
        "email_configured": email_adapter.is_configured,
        "spending_limit": get_configured_spending_limit()
    })

# ── Catalog Mode ──────────────────────────────────────────────────────────────
@app.get("/api/catalog/inspect")
async def get_catalog_inspect(
    query: Optional[str] = None,
    category: Optional[str] = None,
    session_id: Optional[str] = None,
    page_url: Optional[str] = None,
    source_name: Optional[str] = None,
):
    res = catalog_service.inspect_catalog_context(
        query=query,
        category=category,
        session_id=session_id,
        page_url=page_url,
        source_name=source_name,
    )
    return JSONResponse(content=res)

@app.post("/api/catalog/inspect")
async def post_catalog_inspect(req: InspectCatalogRequest):
    res = catalog_service.inspect_catalog_context(
        query=req.query,
        category=req.category,
        raw_items=req.raw_items,
        page_url=req.page_url,
        source_name=req.source_name,
        session_id=req.session_id,
    )
    return JSONResponse(content=res)

# ── Revenue Impact Analytics (Phase 9) ─────────────────────────────────────────
@app.get("/api/analytics/revenue")
async def get_revenue_analytics():
    metrics = revenue_analytics_service.get_merchant_metrics()
    return JSONResponse(content=metrics)

# ── Transaction Audit Logs (Phase 7) ────────────────────────────────────────────
@app.get("/api/audit/logs")
async def get_audit_logs(session_id: str, limit: int = 50):
    logs = audit_service.get_session_audit_trail(session_id=session_id, limit=limit)
    return JSONResponse(content={"session_id": session_id, "total_events": len(logs), "events": logs})


@app.get("/api/extension/pending-commands")
async def extension_pending_commands(session_id: str):
    """One-shot browser commands for the extension (tab navigation). Consumed on read."""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    from backend.agent.shop_planner import pop_pending_navigation
    urls = pop_pending_navigation(session_id)
    commands = [{"type": "navigate_tab", "url": url} for url in urls]
    return JSONResponse(content={"session_id": session_id, "commands": commands})

# ── Email Service Test & Verification (Phase 11) ─────────────────────────────
@app.post("/api/email/test")
async def test_email_dispatch(req: TestEmailRequest):
    res = email_adapter.handle_email_action(action="send_digest", subject=req.subject, recipient_email=req.recipient, category=req.category)
    return JSONResponse(content=res)

# ── Cart API ──────────────────────────────────────────────────────────────────

@app.get("/api/cart")
async def cart_endpoint(session_id: str):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        cart = get_cart(session_id)
        return JSONResponse(content=cart)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/external/page-products")
async def external_page_products_endpoint(req: ExternalPageContextRequest):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    normalized = [
        _normalize_external_product(item, req.page_url, req.source_name)
        for item in (req.products or [])
    ]
    named = [p for p in normalized if (p.name or "").strip()]
    valid = [p for p in named if _is_valid_catalogue_product(p)]
    product_ids = _cache_external_products(named)
    valid_ids = [p.id for p in valid]
    debug = dict(req.extraction_debug or {})
    debug.update({
        "detected_count": len(named),
        "valid_count": len(valid),
        "page_url": req.page_url,
        "source_name": req.source_name,
        "rejected_listing_or_incomplete": [
            {"name": p.name, "url": p.product_url, "price": p.price}
            for p in named if p.id not in set(valid_ids)
        ][:12],
    })
    # Page navigation replaces stale product context. Conversational ordinals
    # ("the second one") must refer to this page's valid catalogue, not an older page.
    update_current_page_products(
        req.session_id,
        valid_ids,
        page_url=req.page_url,
        source_name=req.source_name,
        catalogue_debug=debug,
    )
    if valid_ids:
        update_active_products(req.session_id, valid_ids)
    else:
        update_active_products(req.session_id, [])
    audit_service.record_event(
        session_id=req.session_id,
        event_type="EXTERNAL_PAGE_CATALOG_INGESTED",
        data={
            "page_url": req.page_url,
            "source_name": req.source_name,
            "detected_count": len(named),
            "valid_product_ids": valid_ids
        }
    )
    return JSONResponse(content={
        "success": True,
        "detected_count": len(named),
        "valid_count": len(valid),
        "product_ids": product_ids,
        "valid_product_ids": valid_ids,
        "extraction_debug": debug,
        "products": [p.to_dict() for p in named]
    })

@app.post("/api/external/add-to-cart")
async def external_add_to_cart_endpoint(req: ExternalAddToCartRequest):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    product = _normalize_external_product(req.product or {}, req.page_url, req.source_name)
    validation_error = _validate_external_product(product)
    if validation_error:
        audit_service.record_event(
            session_id=req.session_id,
            event_type="EXTERNAL_ADD_TO_CART_REJECTED",
            data={
                "reason": validation_error,
                "page_url": req.page_url,
                "candidate": product.to_dict()
            }
        )
        return JSONResponse(content={"success": False, "error": validation_error, "product": product.to_dict()})

    _cache_external_products([product])
    update_active_products(req.session_id, [product.id])
    cart_result = add_to_cart(product.id, quantity=max(1, int(req.quantity or 1)), session_id=req.session_id)

    if cart_result.get("error"):
        audit_service.record_event(
            session_id=req.session_id,
            event_type="EXTERNAL_ADD_TO_CART_FAILED",
            data={"product_id": product.id, "error": cart_result["error"]}
        )
        return JSONResponse(content={"success": False, "error": cart_result["error"], "product": product.to_dict()})

    audit_service.record_event(
        session_id=req.session_id,
        event_type="CART_UPDATED",
        data={
            "source": "browser_extension",
            "product_id": product.id,
            "name": product.name,
            "price": product.price,
            "currency": product.currency,
            "merchant": product.merchant_name,
            "product_url": product.product_url,
            "cart_total": cart_result.get("cart", {}).get("total_amount")
        }
    )
    return JSONResponse(content={
        "success": True,
        "message": cart_result.get("message"),
        "product": product.to_dict(),
        "cart": cart_result.get("cart")
    })

@app.post("/api/clear")
async def clear_endpoint(req: ClearRequest):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        clear_session(req.session_id)
        return JSONResponse(content={"success": True, "message": "Session and cart cleared."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ── Payment API ───────────────────────────────────────────────────────────────

@app.get("/api/payment/config")
async def payment_config():
    """Return the Razorpay publishable key to the frontend (safe to expose)."""
    return JSONResponse(content={"key_id": RAZORPAY_KEY_ID})


@app.post("/api/payment/create-order")
async def payment_create_order(req: CreatePaymentOrderRequest):
    """
    Step 1 of the payment flow:
    - Look up our internal order total
    - Create a Razorpay order
    - Store the razorpay_order_id back on our order record
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (req.internal_order_id,))
    order = cursor.fetchone()
    conn.close()

    if not order:
        raise HTTPException(status_code=404, detail=f"Order {req.internal_order_id} not found.")

    order = dict(order)

    if order["status"] == "paid":
        raise HTTPException(status_code=400, detail="This order has already been paid.")

    # Check if we are using placeholder credentials (demo mode)
    # Placeholder credentials cannot open a real Razorpay TEST window.
    is_demo = RAZORPAY_KEY_ID == "rzp_test_placeholder"

    if is_demo:
        audit_service.record_event(
            session_id=order["session_id"],
            event_type="RAZORPAY_ORDER_CREATE_FAILED",
            data={
                "internal_order_id": req.internal_order_id,
                "error": "Razorpay TEST key is not configured"
            }
        )
        raise HTTPException(
            status_code=400,
            detail="Razorpay TEST credentials are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET. The cart is unchanged."
        )

    try:
        rzp_order = create_razorpay_order(
            amount_inr=order["total_amount"],
            internal_order_id=req.internal_order_id,
            currency=order["currency"]
        )

        # Persist the Razorpay order ID on our order record
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET razorpay_order_id = ? WHERE id = ?",
            (rzp_order["id"], req.internal_order_id)
        )
        conn.commit()
        conn.close()

        audit_service.record_event(
            session_id=order["session_id"],
            event_type="RAZORPAY_ORDER_CREATED",
            data={
                "internal_order_id": req.internal_order_id,
                "razorpay_order_id": rzp_order["id"],
                "amount": order["total_amount"],
                "currency": order["currency"],
                "demo_mode": False
            }
        )

        return JSONResponse(content={
            "razorpay_order_id": rzp_order["id"],
            "amount": rzp_order["amount"],
            "currency": rzp_order["currency"],
            "demo_mode": False
        })
    except Exception as e:
        print(f"Razorpay create order error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/payment/verify")
async def payment_verify(req: VerifyPaymentRequest):
    """
    Step 2 of the payment flow:
    - Verify the HMAC-SHA256 signature from Razorpay
    - Mark our internal order as 'paid'
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (req.internal_order_id,))
    order = cursor.fetchone()
    conn.close()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    order = dict(order)

    # Demo mode — accept any payment without real verification
    is_demo = req.razorpay_order_id.startswith("order_DEMO_")

    if not is_demo:
        valid = verify_payment_signature(
            req.razorpay_order_id,
            req.razorpay_payment_id,
            req.razorpay_signature
        )
        if not valid:
            audit_service.record_event(
                session_id=order["session_id"],
                event_type="PAYMENT_FAILED",
                data={
                    "internal_order_id": req.internal_order_id,
                    "razorpay_order_id": req.razorpay_order_id,
                    "razorpay_payment_id": req.razorpay_payment_id,
                    "reason": "signature_verification_failed"
                }
            )
            raise HTTPException(status_code=400, detail="Payment signature verification failed. Payment may be fraudulent.")

    # Mark order as paid
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE orders SET status = 'paid', razorpay_payment_id = ?, razorpay_order_id = ?
           WHERE id = ?""",
        (req.razorpay_payment_id, req.razorpay_order_id, req.internal_order_id)
    )
    # Fetch the actual order items so the confirmation email contains REAL purchased items,
    # prices, and quantities — not a fake placeholder "Verified Package Purchase" row.
    cursor.execute(
        """SELECT p.name, oi.quantity, oi.price, p.merchant_name, p.merchant, p.product_url
             FROM order_items oi JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?""",
        (req.internal_order_id,),
    )
    paid_items_rows = cursor.fetchall()
    paid_items = [
        {
            "name": r["name"],
            "quantity": int(r["quantity"]),
            "price": float(r["price"]),
            "merchant": r["merchant_name"] or r["merchant"],
            "product_url": r["product_url"],
        }
        for r in paid_items_rows
    ]
    conn.commit()
    conn.close()

    # Record Revenue Analytics, Audit Event, and Order Confirmation Email
    order_amount = order.get("total_amount", 0.0)
    order_session = order.get("session_id", "default_session")

    revenue_analytics_service.record_transaction(
        order_id=req.internal_order_id,
        session_id=order_session,
        total_amount=order_amount,
        has_recommendation=True,
        incremental_amount=order_amount * 0.25
    )

    audit_service.record_event(
        session_id=order_session,
        event_type="PAYMENT_SUCCESS",
        data={
            "internal_order_id": req.internal_order_id,
            "razorpay_order_id": req.razorpay_order_id,
            "razorpay_payment_id": req.razorpay_payment_id,
            "demo_mode": is_demo,
            "total_amount": order_amount,
            "items": paid_items,
        }
    )

    # Do not invent placeholder line items if the join returned nothing.
    actual_items = paid_items

    from backend.config import SMTP_USER
    configured_recipient = (
        email_adapter.user_email
        or SMTP_USER
        or os.getenv("USER_EMAIL", "")
    ).strip()
    email_result = {"status": "SKIPPED", "message": "No purchased items were recorded on the order."}
    if actual_items:
        email_result = email_service.send_order_confirmation(
            recipient=configured_recipient,
            order_id=req.internal_order_id,
            total_amount=order_amount,
            items=actual_items,
            payment_id=req.razorpay_payment_id,
            session_id=order_session
        )
    email_ok = str(email_result.get("status") or "").upper() in {"SENT", "SUCCESS"}
    audit_service.record_event(
        session_id=order_session,
        event_type="ORDER_CONFIRMATION_EMAIL_SENT" if email_ok else "ORDER_CONFIRMATION_EMAIL_FAILED",
        data={
            "internal_order_id": req.internal_order_id,
            "recipient": configured_recipient,
            "email_status": email_result.get("status"),
            "email_message_id": email_result.get("message_id"),
            "smtp_provider": email_result.get("delivery_mode") or email_result.get("provider_error") or email_result.get("message"),
            "items_count": len(actual_items)
        }
    )

    from backend.agent.commerce_router import set_pending_order_id
    set_pending_order_id(order_session, None)
    clear_cart(order_session)

    audit_service.record_event(
        session_id=order_session,
        event_type="CART_CLEARED_AFTER_VERIFIED_PAYMENT",
        data={"internal_order_id": req.internal_order_id},
    )

    return JSONResponse(content={
        "success": True,
        "message": "Payment verified and order marked as paid!",
        "order_id": req.internal_order_id,
        "payment_id": req.razorpay_payment_id,
        "demo_mode": is_demo,
        "items": actual_items,
        "email_status": email_result.get("status"),
        "email_sent": email_ok,
    })

# ── Static Files / Frontend ───────────────────────────────────────────────────

frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend"
)

if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def read_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse(content={"status": "NOVA Backend running. Frontend folder is missing."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
