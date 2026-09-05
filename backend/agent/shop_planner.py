"""Shopping intent helpers for NOVA chat, navigation, and accessory copy.

Does not invent product names, prices, or URLs. Search URLs are templates
for supported storefronts based on the user's query text.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from backend.agent.commerce_router import extract_user_intent, get_session_flag, set_session_flag

_LAST_SHOP_COL = "last_shop_query"
_PENDING_NAV_COL = "pending_navigation"

_PRODUCTISH = re.compile(
    r"\b(laptop|laptops|notebook|macbook|phone|phones|mobile|mobiles|headphone|headphones|"
    r"earbud|earbuds|earphone|earphones|tv|television|camera|watch|watches|tablet|ipad|"
    r"monitor|keyboard|mouse|charger|bottle|shoes|sneaker|bag|backpack|printer|"
    r"refrigerator|washing machine|ac|air conditioner|speaker|console|gpu|ssd)\b",
    re.IGNORECASE,
)
_BUDGET = re.compile(
    r"(?:under|below|less than|upto|up to|within|max(?:imum)?)\s*(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*)",
    re.IGNORECASE,
)
_BUDGET_BARE = re.compile(r"(?:₹|rs\.?)\s*([0-9][0-9,]*)", re.IGNORECASE)
_MULTI_SOURCE = re.compile(r"\bmultiple (?:sources|stores|sites|merchants)|from (?:several|different) (?:sites|stores)\b", re.IGNORECASE)
_ACCESSORY = re.compile(
    r"\b(along with|together with|accessor(?:y|ies)|pair(?:ing)?|goes with|use with|buy with this|"
    r"what can i buy along|complementary|add-?ons?)\b",
    re.IGNORECASE,
)
_REFINE_SHORT = re.compile(
    r"^(?:with\s+)?(?:[0-9]+\s*gb(?:\s*ram)?|i[3579]|ryzen|intel|amd|dell|hp|lenovo|asus|acer|"
    r"apple|samsung|sony|boat|noise|the best(?: one)?|cheapest|cheaper|best one)$",
    re.IGNORECASE,
)

SUPPORTED_SEARCH_HOSTS = (
    "www.flipkart.com",
    "www.amazon.in",
    "www.amazon.com",
    "www.myntra.com",
)


def _norm_host(value: str) -> str:
    h = (value or "").lower().strip()
    h = h.replace("https://", "").replace("http://", "").split("/")[0]
    if h.startswith("www."):
        return h
    if h in {"flipkart.com", "amazon.in", "amazon.com", "myntra.com"}:
        return "www." + h
    return h


def merchants_from_text(text: str) -> List[str]:
    t = (text or "").lower()
    found: List[str] = []
    mapping = (
        ("flipkart", "www.flipkart.com"),
        ("amazon.in", "www.amazon.in"),
        ("amazon", "www.amazon.in"),
        ("myntra", "www.myntra.com"),
    )
    for needle, host in mapping:
        if needle in t and host not in found:
            found.append(host)
    return found


def parse_max_price(text: str) -> Optional[float]:
    match = _BUDGET.search(text or "")
    if match:
        return float(match.group(1).replace(",", ""))
    match = _BUDGET_BARE.search(text or "")
    if match and re.search(r"\b(under|below|less|upto|up to|within|budget|max)\b", text or "", re.I):
        return float(match.group(1).replace(",", ""))
    return None


def looks_like_shop_search(message: str) -> bool:
    raw = extract_user_intent(message)
    t = raw.strip()
    if not t:
        return False
    if _ACCESSORY.search(t):
        return False
    if _PRODUCTISH.search(t) and re.search(r"\b(need|want|find|search|show|looking|buy|get|under|below)\b", t, re.I):
        return True
    if _PRODUCTISH.search(t) and parse_max_price(t) is not None:
        return True
    if _REFINE_SHORT.match(t.strip()):
        return True
    return bool(re.search(r"\b(find|search|show me|i need|i want)\b", t, re.I) and len(t.split()) >= 3)


def looks_like_accessory_request(message: str) -> bool:
    return bool(_ACCESSORY.search(extract_user_intent(message)))


def wants_multi_source(message: str) -> bool:
    return bool(_MULTI_SOURCE.search(extract_user_intent(message)))


def load_last_shop(session_id: str) -> Dict[str, Any]:
    raw = get_session_flag(session_id, _LAST_SHOP_COL)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_last_shop(session_id: str, payload: Dict[str, Any]) -> None:
    set_session_flag(session_id, _LAST_SHOP_COL, json.dumps(payload))


def merge_shop_query(session_id: str, user_message: str) -> Dict[str, Any]:
    raw = extract_user_intent(user_message)
    prev = load_last_shop(session_id)
    max_price = parse_max_price(raw)
    merchants = merchants_from_text(raw)
    extras = list(prev.get("extras") or [])
    query_core = raw
    if _REFINE_SHORT.match(raw.strip()) and prev.get("query"):
        extra = raw.strip()
        if extra.lower() not in {e.lower() for e in extras}:
            extras.append(extra)
        query_core = " ".join([prev.get("query") or "", extra]).strip()
        if max_price is None:
            max_price = prev.get("max_price")
        if not merchants:
            merchants = list(prev.get("merchants") or [])
    elif prev.get("query") and not _PRODUCTISH.search(raw) and len(raw.split()) <= 6:
        extras.append(raw.strip())
        query_core = " ".join([prev.get("query") or "", raw]).strip()
        if max_price is None:
            max_price = prev.get("max_price")
        if not merchants:
            merchants = list(prev.get("merchants") or [])
    if max_price is None:
        max_price = prev.get("max_price")
    if not merchants:
        merchants = list(prev.get("merchants") or [])
    merged = {
        "query": query_core,
        "max_price": max_price,
        "merchants": merchants,
        "extras": extras,
        "multi_source": wants_multi_source(raw) or bool(prev.get("multi_source")),
    }
    save_last_shop(session_id, merged)
    return merged


def build_search_url(host: str, query: str) -> Optional[str]:
    host = _norm_host(host)
    q = quote_plus((query or "").strip())
    if not q:
        return None
    if host.endswith("flipkart.com"):
        return f"https://www.flipkart.com/search?q={q}"
    if host.endswith("amazon.in"):
        return f"https://www.amazon.in/s?k={q}"
    if host.endswith("amazon.com"):
        return f"https://www.amazon.com/s?k={q}"
    if host.endswith("myntra.com"):
        slug = quote_plus((query or "").strip().replace(" ", "-"))
        return f"https://www.myntra.com/{slug}"
    return None


def target_search_urls(session_id: str, shop: Dict[str, Any], page_source: Optional[str] = None) -> List[str]:
    query = shop.get("query") or ""
    hosts: List[str] = list(shop.get("merchants") or [])
    if shop.get("multi_source"):
        for h in ("www.flipkart.com", "www.amazon.in"):
            if h not in hosts:
                hosts.append(h)
    if not hosts and page_source:
        host = _norm_host(page_source)
        if any(host.endswith(s.split("www.")[-1]) for s in SUPPORTED_SEARCH_HOSTS) or host in SUPPORTED_SEARCH_HOSTS:
            hosts = [host if host.startswith("www.") or host.count(".") >= 1 else host]
            built = build_search_url(host, query)
            return [built] if built else []
    if not hosts:
        src = get_session_flag(session_id, "current_page_source")
        if src:
            built = build_search_url(src, query)
            if built:
                return [built]
        hosts = ["www.flipkart.com"]
    urls: List[str] = []
    for host in hosts:
        url = build_search_url(host, query)
        if url and url not in urls:
            urls.append(url)
    return urls


def queue_navigation(session_id: str, urls: List[str]) -> Optional[str]:
    urls = [u for u in urls if u]
    if not urls:
        return None
    set_session_flag(session_id, _PENDING_NAV_COL, json.dumps({"urls": urls}))
    return urls[0]


def pop_pending_navigation(session_id: str) -> List[str]:
    raw = get_session_flag(session_id, _PENDING_NAV_COL)
    set_session_flag(session_id, _PENDING_NAV_COL, None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("urls"), list):
            return [u for u in data["urls"] if isinstance(u, str)]
        if isinstance(data, dict) and data.get("url"):
            return [data["url"]]
    except Exception:
        if isinstance(raw, str) and raw.startswith("http"):
            return [raw]
    return []


def accessory_categories_for_text(text: str) -> List[str]:
    q = (text or "").lower()
    if re.search(r"\b(laptop|notebook|macbook)\b", q):
        return [
            "a laptop sleeve or bag",
            "a wireless mouse",
            "an external keyboard",
            "a cooling pad",
            "a USB-C hub",
            "headphones or a headset",
        ]
    if re.search(r"\b(phone|mobile|smartphone)\b", q):
        return ["a protective case", "a screen protector", "a charger or power bank", "earphones"]
    if re.search(r"\b(headphone|earbud|earphone)\b", q):
        return ["a carrying case", "an extra charging cable", "ear tips"]
    if re.search(r"\b(camera)\b", q):
        return ["a memory card", "a camera bag", "a tripod"]
    return ["a compatible accessory or spare"]


def accessory_blurb(query_text: str, real_products: Optional[List[Dict[str, Any]]] = None) -> str:
    cats = accessory_categories_for_text(query_text)
    lines = [
        "Since you are shopping for this, you may also want to consider:",
        *[f"- {c}" for c in cats],
    ]
    real = [
        p for p in (real_products or [])
        if p.get("name") and p.get("product_url") and p.get("price")
    ]
    if real:
        lines.append("From the current page I can already see these related items (not invented):")
        for p in real[:3]:
            price = p.get("price")
            curr = p.get("currency") or "₹"
            lines.append(f"- {p.get('name')} ({curr} {price}) from {p.get('merchant') or p.get('merchant_name') or 'the current page'}")
        return "\n".join(lines)
    lines.append(
        "Those are accessory categories, not products I invented. "
        "If you want, I can search the current shopping source for them."
    )
    return "\n".join(lines)


def related_from_catalogue(products: List[Dict[str, Any]], query_text: str) -> List[Dict[str, Any]]:
    q = (query_text or "").lower()
    needles = []
    if re.search(r"\b(laptop|notebook|macbook)\b", q):
        needles = ["mouse", "sleeve", "bag", "keyboard", "hub", "headset", "headphone", "cooling"]
    elif re.search(r"\b(phone|mobile)\b", q):
        needles = ["case", "cover", "charger", "tempered", "earphone", "power bank"]
    if not needles:
        return []
    out = []
    for p in products or []:
        name = (p.get("name") or "").lower()
        if any(n in name for n in needles):
            out.append(p)
    return out


def format_inr(value: Optional[float]) -> str:
    if value is None:
        return ""
    try:
        n = int(float(value))
        return f"₹{n:,}"
    except (TypeError, ValueError):
        return str(value)


def natural_search_ack(shop: Dict[str, Any], from_page: bool, will_navigate: bool) -> str:
    q = shop.get("query") or "those products"
    budget = format_inr(shop.get("max_price"))
    budget_bit = f" under {budget}" if budget else ""
    if from_page:
        return (
            f"I found matching options{budget_bit} on the current shopping page. "
            f"Here are the best ones I could read from that page based on your request for {q}."
        )
    if will_navigate:
        return (
            f"Absolutely. I’ll look for {q}{budget_bit} and open the relevant shopping results "
            "so I can inspect the products that are actually listed."
        )
    return f"I’ll look for {q}{budget_bit} and compare the options I can actually retrieve."


def looks_like_internal_payload(text: Optional[str]) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            return True
        if isinstance(obj, dict) and any(k in obj for k in ("query", "max_price", "function_name", "parameters", "arguments", "name", "tool")):
            return True
    lowered = stripped.lower()
    markers = (
        "unexpected keyword argument",
        "function_name",
        "calling model",
        "timed out",
        "tool execution failed",
        "error executing tool",
    )
    return any(m in lowered for m in markers)


def strip_internal_json(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    cleaned = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", text, flags=re.I)
    cleaned = re.sub(
        r"\{[^{}]*\"(?:query|max_price|min_price|category|result_count|function_name|parameters|arguments)\"[^{}]*\}",
        "",
        cleaned,
    )
    cleaned = cleaned.strip()
    if looks_like_internal_payload(cleaned):
        return None
    return cleaned or None


def extract_search_args_from_content(content: Optional[str]) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    blobs = re.findall(r"\{[^{}]+\}", content)
    for raw in blobs:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        query = obj.get("query")
        if isinstance(query, str) and query.strip():
            args: Dict[str, Any] = {"query": query.strip()}
            for key in ("max_price", "min_price", "category", "result_count"):
                if obj.get(key) not in (None, "", "null"):
                    args[key] = obj[key]
            return args
    return None


def try_shop_turn(session_id: str, user_message: str) -> Optional[Dict[str, Any]]:
    """Deterministic shopping path: search page catalogue, navigate, never dump JSON."""
    raw = extract_user_intent(user_message)
    accessory = looks_like_accessory_request(raw)
    shopping = looks_like_shop_search(raw)
    if not accessory and not shopping:
        return None

    from backend.providers.catalog_provider import catalog_service
    from backend.tools.product_tools import search_products
    from backend.tools.action_tools import navigate_browser

    cat = catalog_service.inspect_session_catalog(session_id)
    page_products = cat.get("products") or []

    if accessory:
        shop = load_last_shop(session_id)
        query_text = shop.get("query") or raw
        related = related_from_catalogue(page_products, query_text)
        blurb = accessory_blurb(query_text, related)
        tools = []
        if related:
            tools.append({"name": "search_products", "arguments": {"query": query_text}, "result": related})
        return {
            "response": blurb,
            "executed_tools": tools,
        }

    shop = merge_shop_query(session_id, user_message)
    query = shop.get("query") or raw
    max_price = shop.get("max_price")
    from_page: List[Dict[str, Any]] = []
    qwords = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    for p in page_products:
        name = (p.get("name") or "").lower()
        price = p.get("price")
        if max_price is not None and price and float(price) > float(max_price):
            continue
        if qwords and not any(w in name for w in qwords):
            continue
        from_page.append(p)

    executed: List[Dict[str, Any]] = []
    nav_url = None
    if len(from_page) < 1:
        urls = target_search_urls(session_id, shop, cat.get("source", {}).get("merchant_name"))
        nav_url = queue_navigation(session_id, urls)
        if nav_url:
            nav_result = navigate_browser(action="open_url", url=nav_url, session_id=session_id)
            executed.append({"name": "navigate_browser", "arguments": {"action": "open_url", "url": nav_url}, "result": nav_result})

    search_args: Dict[str, Any] = {"query": query, "session_id": session_id}
    if max_price is not None:
        search_args["max_price"] = max_price
    results = search_products(**{k: v for k, v in search_args.items()})
    executed.append({
        "name": "search_products",
        "arguments": {k: v for k, v in search_args.items() if k != "session_id"},
        "result": results,
    })

    used_page = bool(from_page) and isinstance(results, list) and any(
        (r.get("product_url") or r.get("id")) in {
            (p.get("product_url") or p.get("id")) for p in from_page
        }
        for r in results
        if isinstance(r, dict)
    )
    ack = natural_search_ack(shop, from_page=bool(from_page), will_navigate=bool(nav_url))
    if isinstance(results, list) and results:
        names = [r.get("name") for r in results if isinstance(r, dict) and r.get("name")]
        if names:
            ack += "\n\nTop matches I can actually show:\n" + "\n".join(
                f"- {n}" for n in names[:5]
            )
    elif nav_url:
        ack += " I couldn't extract matching products from the current page yet, so I'm opening the search results now."
    else:
        ack += " I couldn't extract matching products from this page yet."

    related = related_from_catalogue(page_products, query)
    ack += "\n\n" + accessory_blurb(query, related)
    return {"response": ack, "executed_tools": executed}
