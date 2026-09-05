import json
import re
from typing import List, Dict, Any, Tuple, Optional
from backend.llm.providers import OllamaProvider
from backend.tools import registry
from backend.database.db import get_connection
from backend.commerce.models import Product

# Configurable model name from environment or default
import os
MODEL_NAME = os.getenv("NOVA_LLM_MODEL", "llama3.1:8b")

# In-memory conversation histories: session_id -> list of messages
session_histories: Dict[str, List[Dict[str, Any]]] = {}

def get_llm_provider():
    return OllamaProvider(model_name=MODEL_NAME)

def _build_product_context_lines(product_ids: List[str]) -> Tuple[List[str], List[str]]:
    if not product_ids:
        return [], []
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in product_ids)
    cursor.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", product_ids)
    rows = cursor.fetchall()
    conn.close()
    prod_map = {r["id"]: Product.from_row(r) for r in rows}
    context_lines = []
    ordered_ids = []
    for idx, pid in enumerate(product_ids):
        if pid in prod_map:
            p = prod_map[pid]
            context_lines.append(f"[{idx + 1}] ID: '{p.id}' | Name: '{p.name}' | Brand: '{p.brand}' | Price: ₹{p.price} | Store: '{p.merchant}' | Rating: {p.rating or 'N/A'}")
            ordered_ids.append(p.id)
    return context_lines, ordered_ids


def get_active_products_context(session_id: str) -> Tuple[str, List[str]]:
    """Fetch recently referenced products for this session and format a text context for the LLM."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_product_ids, current_page_product_ids FROM session_states WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return "", []

    # ── Current browser page products (highest priority for "this product" references) ──
    current_ids: List[str] = []
    try:
        if row["current_page_product_ids"]:
            current_ids = json.loads(row["current_page_product_ids"])
    except Exception:
        current_ids = []

    # ── Conversational products (for "second one", "cheapest", etc.) ──
    conv_ids: List[str] = []
    try:
        if row["last_product_ids"]:
            conv_ids = json.loads(row["last_product_ids"])
    except Exception:
        conv_ids = []

    current_lines, _ = _build_product_context_lines(current_ids)
    conv_lines, conv_ordered_ids = _build_product_context_lines(conv_ids)

    sections: List[str] = []
    if current_lines:
        sections.append(
            "CURRENT BROWSER PAGE PRODUCTS (use these when user says 'this', 'this product', 'this page', 'buy this', 'add this to cart', or 'checkout this product'):\n"
            + "\n".join(current_lines)
            + "\nThese override the conversation products below for current-page references."
        )

    if conv_lines:
        sections.append(
            "Active/Recently Displayed Products (in order — conversational references like 'the first one', 'the second shoe', 'cheaper option', or 'compare the first two'):\n"
            + "\n".join(conv_lines)
            + "\nUse these indices to resolve ordinal/conversational references and map them to their ID in your tool arguments."
        )

    combined: List[str] = current_ids or conv_ids
    context_str = ("\n\n".join(sections)) if sections else ""
    return context_str, (conv_ordered_ids or combined)


def update_active_products(session_id: str, product_ids: List[str]):
    """Update the database session_states with the list of recently displayed conversational product IDs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO session_states (session_id, last_product_ids, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET 
            last_product_ids = excluded.last_product_ids,
            updated_at = CURRENT_TIMESTAMP
    """, (session_id, json.dumps(product_ids or [])))
    conn.commit()
    conn.close()


def update_current_page_products(
    session_id: str,
    product_ids: List[str],
    page_url: Optional[str] = None,
    source_name: Optional[str] = None,
    catalogue_debug: Optional[Dict[str, Any]] = None,
):
    """Update the authoritative current-browser-page product context (synced from extension)."""
    conn = get_connection()
    cursor = conn.cursor()
    payload = json.dumps(product_ids) if product_ids else None
    debug_payload = json.dumps(catalogue_debug) if catalogue_debug is not None else None
    cursor.execute("""
        INSERT INTO session_states (
            session_id, current_page_product_ids, current_page_url, current_page_source, catalogue_debug, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET
            current_page_product_ids = excluded.current_page_product_ids,
            current_page_url = COALESCE(excluded.current_page_url, session_states.current_page_url),
            current_page_source = COALESCE(excluded.current_page_source, session_states.current_page_source),
            catalogue_debug = COALESCE(excluded.catalogue_debug, session_states.catalogue_debug),
            updated_at = CURRENT_TIMESTAMP
    """, (session_id, payload, page_url, source_name, debug_payload))
    conn.commit()
    conn.close()

def parse_product_ids_from_result(tool_name: str, result: Any) -> List[str]:
    """Helper to extract product IDs from a tool's return value to populate conversational context."""
    product_ids = []
    if not result:
        return []
        
    def _extract_from_obj(obj: Any):
        if isinstance(obj, list):
            for item in obj:
                _extract_from_obj(item)
        elif isinstance(obj, dict):
            if "id" in obj and isinstance(obj["id"], str):
                product_ids.append(obj["id"])
            elif "product_id" in obj and isinstance(obj["product_id"], str):
                product_ids.append(obj["product_id"])
            elif "product" in obj and isinstance(obj["product"], dict):
                _extract_from_obj(obj["product"])
            else:
                for key in ["products", "recommendations", "feed", "results", "items", "comparison"]:
                    if key in obj and isinstance(obj[key], (list, dict)):
                        _extract_from_obj(obj[key])

    _extract_from_obj(result)
    
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for pid in product_ids:
        if pid not in seen:
            seen.add(pid)
            deduped.append(pid)
    return deduped

from backend.commerce.location import MarketResolver

_TOOL_JSON_PATTERN = re.compile(
    r'\{\s*["\']name["\']\s*:\s*["\'][^"\']+'  # {"name": "..."
    r'(?:[^{}]|\{[^{}]*\})*\}',               # ...rest of the JSON blob
    re.DOTALL
)

_FENCED_JSON_PATTERN = re.compile(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', re.IGNORECASE)
_PRICE_PATTERN = re.compile(
    r'(?:₹|rs\.?|inr|\$|usd|£|gbp|eur|€)\s*\d+|\d+\s*(?:rupees?|rs\.?|inr|dollars?|usd|pounds?|gbp|euros?|eur)',
    re.IGNORECASE
)
_BUDGET_PATTERN = re.compile(
    r'\b(?:under|below|less than|within|budget|maximum|max|up to|upto|around|near|'
    r'between|from)\b.{0,30}(?:₹|rs\.?|inr|\$|usd|£|gbp|eur|€)?\s*\d+|'
    r'(?:₹|rs\.?|inr|\$|usd|£|gbp|eur|€)\s*\d+.{0,30}\b(?:budget|max|maximum|limit)\b',
    re.IGNORECASE
)
_COUNT_PATTERN = re.compile(
    r'\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+'
    r'(?:options?|results?|products?|items?|recommendations?|suggestions?)\b',
    re.IGNORECASE
)
_SHOPPING_INTENT_PATTERN = re.compile(
    r'\b(?:buy|shop|shopping|find|search|show|recommend|compare|price|cost|deal|'
    r'option|product|item|cart|order|checkout|need|want|looking|under|below|'
    r'above|budget|better|cheaper|best|worth|review|rating|laptop|phone|headphone)\b',
    re.IGNORECASE
)
_PRODUCT_NOUN_PATTERN = re.compile(
    r'\b(?:laptop|laptops|notebook|phone|phones|mobile|headphone|headphones|earbud|earbuds|'
    r'tv|camera|watch|tablet|monitor|keyboard|mouse|shoes|bag)\b',
    re.IGNORECASE
)
_PURE_CHAT_PATTERN = re.compile(
    r'^\s*(?:hi|hii|hello|hey|yo|thanks|thank you|ok|okay|yes|yeah|yep|no|nope|'
    r'uh no|hmm|hmmm|cool|nice|great|fine|what do you think)\s*[.!?]*\s*$',
    re.IGNORECASE
)

def _sanitize_llm_content(content: Optional[str]) -> Optional[str]:
    """
    Strip raw JSON tool-call blobs that some Ollama model versions emit
    inside the `content` field alongside structured tool_calls.
    Those blobs must never reach the user-facing chat.
    """
    if not content:
        return content

    from backend.agent.shop_planner import (
        looks_like_internal_payload,
        strip_internal_json,
    )

    sanitized = _FENCED_JSON_PATTERN.sub('', content)
    sanitized = _TOOL_JSON_PATTERN.sub('', sanitized)
    # Remove trailing JSON blobs that start with any quote+key pattern
    sanitized = re.sub(r'\{\s*["\'](?:name|tool|function|query)["\'][\s\S]*?\}\s*$', '', sanitized).strip()
    # Also strip bare JSON objects that look like search/tool args (no trailing/leading text)
    sanitized = re.sub(
        r'^\s*\{\s*["\']?(?:query|max_price|min_price|category|result_count|function_name|parameters|arguments)["\']?\s*:[\s\S]*?\}\s*$',
        '',
        sanitized,
        flags=re.MULTILINE,
    ).strip()
    # Remove any remaining {...} blocks containing known internal keys
    sanitized = re.sub(
        r'\{[^{}]*["\'](?:query|max_price|min_price|category|result_count|function_name|parameters|arguments)["\'][^{}]*\}',
        '',
        sanitized,
    ).strip()

    stripped = strip_internal_json(sanitized)
    if stripped is None or looks_like_internal_payload(stripped):
        sanitized = ""
    else:
        sanitized = stripped

    internal_markers = (
        "ambiguous category noun",
        '"parameters"',
        '"arguments"',
        '"query":',
        '"max_price":',
        '"min_price":',
        '"result_count":',
        '"category":',
        "search_products",
        "add_to_cart",
        "create_order",
        "compare_products",
        "compare_prices",
        "function_name",
        "unexpected keyword argument",
        "error executing tool",
        "calling model",
        "timed out",
    )
    lines = []
    for line in sanitized.splitlines():
        line_lower = line.lower()
        if any(marker.lower() in line_lower for marker in internal_markers):
            continue
        lines.append(line)
    sanitized = "\n".join(lines).strip()
    return sanitized if sanitized else None

def _extract_tool_calls_from_content(content: Optional[str], allowed_tool_names: set) -> List[Dict[str, Any]]:
    """Recover tool calls when a local model prints tool JSON as chat text."""
    if not content:
        return []
    if _content_says_not_ready_to_search(content):
        return []

    candidates = [m.group(1) for m in _FENCED_JSON_PATTERN.finditer(content)]
    candidates.extend(m.group(0) for m in _TOOL_JSON_PATTERN.finditer(content))

    tool_calls = []
    for raw in candidates:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if not isinstance(parsed, dict):
            continue

        # Extract tool name from any of the common name keys
        name = (
            parsed.get("name")
            or parsed.get("tool")
            or parsed.get("function")
            or parsed.get("function_name")  # some llama3 variants use this
        )
        # Extract arguments — prefer a nested dict, otherwise treat remaining
        # non-meta keys as the argument dict itself (flat format)
        args = parsed.get("arguments") or parsed.get("parameters") or {}
        if not args and name:
            # Flat format: {"function_name": "X", "action": "...", "target_reference": "..."}
            meta_keys = {"name", "tool", "function", "function_name", "tool_name", "type"}
            args = {k: v for k, v in parsed.items() if k not in meta_keys}

        if name in allowed_tool_names and isinstance(args, dict):
            tool_calls.append({"name": name, "arguments": args})

    if not tool_calls:
        from backend.agent.shop_planner import extract_search_args_from_content
        search_args = extract_search_args_from_content(content)
        if search_args and "search_products" in allowed_tool_names:
            tool_calls.append({"name": "search_products", "arguments": search_args})

    return tool_calls

def _content_says_not_ready_to_search(content: str) -> bool:
    lowered = content.lower()
    return any(
        phrase in lowered
        for phrase in (
            "ambiguous category noun",
            "too vague",
            "not enough information",
            "without specifying",
            "needs clarification",
        )
    )

def _recent_user_context(history: List[Dict[str, Any]], user_message: str, turns: int = 6) -> str:
    recent_user_messages = [
        msg.get("content", "")
        for msg in history[-turns:]
        if msg.get("role") == "user" and isinstance(msg.get("content"), str)
    ]
    return "\n".join(recent_user_messages + [user_message])

def _word_set(text: str) -> set:
    words = set()
    for word in re.findall(r'[a-z0-9]+', text.lower()):
        words.add(word)
        if word.endswith("s") and len(word) > 3:
            words.add(word[:-1])
    return words

def _remove_invented_arguments(tool_name: str, args: Dict[str, Any], user_context: str) -> Dict[str, Any]:
    """Keep tool calls grounded in what the user actually said."""
    cleaned = dict(args or {})

    if tool_name in {"search_products", "compare_prices"}:
        grounding_context = "\n".join(
            line for line in (user_context or "").splitlines()
            if "visible page price" not in line.lower()
        )
        user_words = _word_set(grounding_context)
        category = cleaned.get("category")
        if isinstance(category, str) and category.strip():
            category_words = _word_set(category)
            if category_words and not category_words.issubset(user_words):
                cleaned.pop("category", None)
        if not _BUDGET_PATTERN.search(grounding_context):
            cleaned.pop("min_price", None)
            cleaned.pop("max_price", None)
        if not _COUNT_PATTERN.search(grounding_context):
            cleaned.pop("result_count", None)

    return cleaned

def _latest_user_intent_text(latest_user_message: str) -> str:
    match = re.search(r'^\s*User message:\s*(.+?)\s*$', latest_user_message or "", re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    return (latest_user_message or "").strip()

def _should_skip_tool_call(tool_name: str, args: Dict[str, Any], latest_user_message: str) -> bool:
    if tool_name != "search_products":
        return False

    latest = _latest_user_intent_text(latest_user_message)
    query = str((args or {}).get("query") or "").strip()

    if _PURE_CHAT_PATTERN.match(latest):
        return True
    if not query:
        return True
    if _SHOPPING_INTENT_PATTERN.search(latest) or _PRODUCT_NOUN_PATTERN.search(latest):
        return False
    if len(query.split()) <= 2 and not _SHOPPING_INTENT_PATTERN.search(latest):
        return True

    return False

def run_agent(session_id: str, user_message: str, market_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run the conversational agent loop:
    - Sends full conversation history to the LLM
    - The LLM handles ambiguity, clarification, and tool-calling decisions naturally
    - Sanitizes any raw tool-call JSON that leaks into LLM content before returning
    - Updates conversation memory after each turn
    """

    # 1. Fetch history
    if session_id not in session_histories:
        session_histories[session_id] = []
    history = session_histories[session_id]

    # Deterministic commerce path: cart / cart-checkout / confirmation / catalogue
    # must never be answered from recent-product context or LLM memory.
    from backend.agent.commerce_router import try_deterministic_commerce
    intercepted = try_deterministic_commerce(session_id, user_message)
    if intercepted:
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": intercepted.get("response") or ""})
        return intercepted

    # 2. Get active product context
    prod_context_str, _ = get_active_products_context(session_id)

    # 3. Resolve user shopping market
    country_code = market_override.get("country_code") if isinstance(market_override, dict) else None
    currency_code = market_override.get("currency_code") if isinstance(market_override, dict) else None
    market_obj = MarketResolver.resolve_market(country_code=country_code, currency_code=currency_code)
    
    # 4. Create core system prompt
    system_prompt = f"""You are NOVA, an intelligent Personal AI Commerce Agent. Help users find, compare, and purchase real products through natural, friendly conversation.

USER MARKET:
• Market: {market_obj.country_name} ({market_obj.country_code})
• Currency: {market_obj.currency_code} ({market_obj.currency_symbol})
• Respect any override the user states: "show in USD", "search US stores", etc.

═══════════════════════════════════════════════════════
CONVERSATION PRINCIPLES
═══════════════════════════════════════════════════════

1. MAINTAIN CONTEXT ACROSS TURNS
   Remember everything the user has said in this session.
   If the user said "steel" in a previous message, retain it.
   If the user said "under ₹1000", that budget carries forward until explicitly changed.
   Updates like "actually under ₹1500" or "make it glass" refine the existing context, not a new conversation.

2. BE A NORMAL CONVERSATIONAL SHOPPING ASSISTANT
   Respond naturally to small talk, opinions, corrections, and follow-up questions.
   Use the previous turns to understand what the user means.
   If the user is still deciding, help them think through tradeoffs before searching.
   If they ask "what do you think?", give useful general guidance from the conversation and ask for the single missing detail that would make search useful.

3. ACT ON CLEAR SHOPPING REQUESTS
   If the user already named a product type, brand, or budget (for example "laptops under 80000"),
   search immediately. Do not ask them to repeat what they just said.
   Short follow-ups such as "Dell" or "with 16GB RAM" refine the previous search — combine them.
   If they name a store (Flipkart, Amazon), call navigate_browser with a search URL or query+merchant
   so the active tab can open those results, then use extracted/current-page products.
   Never paste JSON, function arguments, or planner objects into the user-facing reply.

4. NEVER INVENT PARAMETERS OR HIDDEN TEST VALUES
   Only pass values to search tools that the user has explicitly stated.
   NEVER fabricate: price limits, categories, product types, brands, or result counts.
   If a parameter is unknown, omit it from the tool call — do not invent a value.

5. SEARCH PRECISELY WHEN READY
   When you have enough information to search effectively, call search_products with:
   • A specific, descriptive query based on the user's actual words and preferences
   • max_price only if the user stated a budget
   • category only if clearly determined
   Do NOT pass result_count unless the user explicitly asked for a specific number.

6. SELECT ONE BEST PRODUCT BY DEFAULT
   After receiving search results, recommend ONE best match.
   Show more only when the user asks ("show me options", "compare", "give me a few").
   Rank by: relevance → budget fit → URL quality (product page > search page) → merchant trust.
   Briefly explain your pick in 1–2 sentences using only facts from the tool results.

7. BUDGET IS A HARD CONSTRAINT
   Never recommend a product above the user's stated budget.
   If nothing is found within budget, say so and offer the nearest alternative with its price.

8. DATA INTEGRITY — NEVER FABRICATE
   All product data (name, price, image, URL, merchant, rating) must come from tool results.
   If a field is missing, say so — do not invent it.
   Do not mix fields from different products.

9. PRODUCT LINKS
   The "View Product" link must go to the exact product page.
   Category pages or search pages are NOT product links.
   If only a listing URL is available, label it clearly as a listing, not a specific product.

10. NEVER OUTPUT RAW TOOL JSON IN YOUR RESPONSE
    Your response to the user must be natural conversational text.
    NEVER include JSON objects, tool call structures, function names, or parameter blocks in your text reply.
    Internal tool usage happens silently — only the conversational outcome is shown.
    If you decide to call a tool, use the tool-calling interface only and keep the user-facing content empty or conversational.

11. CONVERSATIONAL REFERENCES & NAVIGATION
    References fall into TWO distinct categories — use the correct source:

    A. CURRENT-PAGE REFERENCES (use the CURRENT BROWSER PAGE PRODUCTS section):
       "this product", "this page", "this", "this item", "buy this", "add this to cart",
       "analyze this", "checkout this product", "checkout this".
       Use resolve_product_action with these phrases as target_reference. When the
       CURRENT BROWSER PAGE PRODUCTS list is non-empty, IT IS THE AUTHORITATIVE
       source for deictic references like "this".

    B. CONVERSATIONAL ORDINAL REFERENCES (use the Active Products section):
       "the first one", "open the second one", "add the third", "the cheaper one",
       "the last option", "option 2", "show me the Amazon one", "add the Sony".
       Use resolve_product_action with these phrases as target_reference.

    For both types, call resolve_product_action with the phrase as target_reference
    and the user's intent as action (add_to_cart, checkout, open).

12. CHECKOUT + PAYMENT ROUTING — CRITICAL SAFETY. READ THIS SECTION TWICE.

    THE FIVE-STEP CHECKOUT PIPELINE (YOU MUST FOLLOW IT EXACTLY):

    STEP 1 — Order preparation (create_order or resolve_product_action(action=checkout)):
      → This prepares an internal order record with status="prepared".
      → After STEP 1, YOU MUST ask the user to EXPLICITLY confirm the prepared items
        and total. Say something like:
        "I've prepared your order for review. It contains [items] totaling [amount].
         Shall I proceed to Razorpay payment? Please confirm with 'yes' or 'no'."
      → NEVER say "Your order has been successfully placed" after STEP 1.
      → NEVER say the cart is cleared after STEP 1. The cart is 100% unchanged.
      → NEVER say payment happened, an email was sent, or the product is "on the way".
      → STEP 1 does NOT trigger the Razorpay UI. Only STEP 2 does.

    STEP 2 — User explicitly confirms.
      → Accept only a clear confirmation such as "yes", "confirm", "proceed", "okay go",
        "yes proceed", "pay", "yes I want to pay".
      → If the user says "no", "wait", "cancel", "hold on", or anything that is not a
        clear positive confirmation, STOP. Do NOT call proceed_to_payment.

    STEP 3 — Call proceed_to_payment(order_id=<the prepared order id from STEP 1>).
      → This creates the REAL Razorpay test order (or its deterministic demo-mode
        equivalent) and returns a razorpay_order_id + amount + currency.
      → It does NOT take payment. It does NOT clear the cart.
      → proceed_to_payment output MAY include an "agent_must_not_claim_success": true
        flag. IF YOU SEE THAT FLAG, YOU MUST NOT CLAIM ORDER SUCCESS IN YOUR REPLY.
      → After STEP 3, tell the user:
        "Please complete the Razorpay Checkout panel that has just appeared.
         I will confirm your order once the payment is successfully verified."
      → After STEP 3, STILL NEVER say "Your order has been successfully placed."

    STEP 4 — User completes (or cancels) the Razorpay UI in the browser/frontend.
      → This is handled by the frontend calling /api/payment/verify on successful
        HMAC verification. The frontend controls this step; you don't trigger it.

    STEP 5 — Frontend calls /api/payment/verify.
      → ONLY HERE does the backend:
          a) verify the Razorpay HMAC signature (or accept demo-mode equivalent);
          b) mark the internal order as "paid";
          c) record revenue analytics;
          d) send the REAL confirmation email via SMTP;
          e) CLEAR the AUTHORITATIVE CART (only the items in that specific order);
          f) emit a PAYMENT_SUCCESS audit event.
      → As the conversational agent, you will NOT see the /api/payment/verify response
        directly. If the user later comes back and says "did my order go through?",
        call get_cart() and check get_order_status() when you have that tool, or simply
        tell them that NOVA marks orders as successful only after Razorpay verification
        and that they'll receive a real email when that happens.

    THERE ARE NO SHORTCUTS. A successful-appearing LLM reply is NOT a successful order.

    DISTINCT CHECKOUT INTENTS:

    A. CHECKOUT MY CART (use the AUTHORITATIVE CART, never recent products):
       "checkout", "checkout my cart", "checkout the cart", "buy what's in my cart",
       "pay for my cart", "proceed to checkout the items in my cart".
       → Call create_order() directly. Do NOT call resolve_product_action.
       → If create_order returns "bounds_exceeded", STOP and tell the user clearly that
         the configured spending limit has blocked the payment. No further steps.
       → Never claim the cart is empty because recent products resolved to nothing.
       → Only create_order() and the authoritative get_cart() know the real contents.

    B. CHECKOUT A SELECTED / SPECIFIC PRODUCT:
       "checkout the second one", "buy the cheaper one", "checkout this product",
       "buy this", "purchase the boAt Airdopes".
       → Call resolve_product_action with action='checkout' and the reference phrase.
       → This will stage the product into the cart and then route through create_order,
         which applies the expenditure/spending limit before any Razorpay order.

    C. STANDALONE "proceed to payment" / "pay" / "let's pay" / "confirm" FOLLOWING
       a successful create_order in the previous turn:
       → This is STEP 2 confirmation. If the previous tool result contained a prepared
         order record with an order id, extract that order id and call
         proceed_to_payment(order_id=<id>).
       → If there is NO prepared order in the conversation context, first run STEP 1.

    NEVER DO THESE THINGS (they are treated as critical safety bugs):
    • Never call resolve_product_action with action='checkout' and a generic target_ref
      like "my cart" or "the cart" — use create_order() instead.
    • Never create a Razorpay order before the expenditure/spending limit check passes.
    • Never skip STEP 2 confirmation after a STEP 1 prepare.
    • Never simulate, fabricate, or hallucinate payment success.
    • Never say "order placed" before STEP 5 actually runs on the backend.
    • Never suggest the cart is cleared before verified payment.
    • Never claim an email was sent before verified payment.

13. NOVA DISCOVER & "WHAT'S NEW?"
    When the user asks "What's new?", "Any new stuff?", "What are the latest offers?",
    "What's happening for the World Cup?", "Show me merchandise for upcoming movies",
    or "What's happening in India this month?":
    Call get_discovery_feed with the relevant category or query.

14. CALENDAR & EMAIL PERMISSIONED ACTIONS
    Call calendar_action for requests like "Add World Cup final to my calendar".
    Call email_action for requests like "Email me today's best deals".

15A. CART QUERIES — NEVER USE RECENT PRODUCTS
    When the user asks "what's in my cart", "show my cart", "show cart", or "view cart":
    Call get_cart() ONLY. Do NOT call resolve_product_action, search_products,
    check_inventory, or get_product_details. The cart is independent of recent products.

15. PERSONALIZED RECOMMENDATIONS & PURCHASE HISTORY
    When the user asks "What do you recommend?", "What do I usually buy with this?",
    "What do I buy frequently?", "Suggest complementary items", or "Show my top
    categories":
    Call get_recommendations or get_purchase_history_summary.

16. CONTEXTUAL PAIRING / UPSELL — ONLY IMMEDIATELY AFTER "ADD THIS TO CART"
    This applies specifically right after you have just successfully added a SINGLE
    product to the cart (for example, the user said "add this to cart" on an external
    browser product page, or "add the boAt Airdopes to cart").

    RIGHT AFTER a successful single-product add_to_cart call, call get_pairing_suggestions
    (do NOT pass current_product_id unless you have a specific one — it reads the current
    browser page context or last added cart item automatically).

    Then in your response, say something like:

      "I've added [product name] to your cart. Would you like to pair it with anything?
       Here are a few relevant options based on [the honest evidence_statement returned by
       get_pairing_suggestions]:
         (1) [Suggestion 1 name] — [price] — [recommendation_reason]
         (2) [Suggestion 2 name] — [price] — [recommendation_reason]
         (3) [Suggestion 3 name] — [price] — [recommendation_reason]
       Just tell me which one(s) you'd like me to add, or say 'no thanks' / 'just this one'
       and I'll keep only the original product."

    KEY RULES FOR PAIRING:
    • Call get_pairing_suggestions ONLY right after adding a SINGLE product. If the user
      added multiple products in one step, or searched / browsed, skip pairing entirely.
    • Use the evidence_statement from get_pairing_suggestions HONESTLY. If it says
      "no authorized purchase history is available yet", you must NOT say "Based on your
      previous purchases...". You can say "Based on product compatibility and current
      store availability..." instead.
    • Only show 2–3 suggestions, all of which must be canonically-valid individual
      products (get_pairing_suggestions already filters this for you).
    • If the user says "Add the first one", "Add the mouse and sleeve", "Add both option 1
      and 2", etc., resolve the reference(s) to their canonical IDs using the product
      names / IDs returned in the suggestions payload, then call add_to_cart for each.
    • If the user says "no", "no thanks", "nothing else", "just this product", "only the
      original item", or any other clear decline: STOP. Do NOT ask again. Do not add any
      suggestion. Keep the conversation focused on the next step the user wants.
    • Never add pairing suggestions to the cart without a clear affirmative user selection.
    • Pairing NEVER bypasses the checkout pipeline. After the final cart is confirmed,
      you still MUST follow the full STEP 1 → STEP 2 → STEP 3 → STEP 4 → STEP 5 Razorpay
      flow from section 12. Every safety gate (bounds / confirmation / payment /
      verification) still applies to items added via pairing.
    • Suggestions are NEVER hardcoded. If get_pairing_suggestions returns 0 items,
      simply omit the pairing prompt and continue normally. Do not fabricate suggestions.

17. MODE SWITCHING & VOICE NAVIGATION
    When the user asks "Switch to Discover", "Move to discover mode", "Open discover
    mode", "Go to discover", "Take me to discover", "Open my orders", "Go to
    settings", "Switch to chat", or "Go to cart":
    Call switch_mode with the target mode name ('discover', 'chat', 'settings',
    'orders', 'cart', 'catalogue').

═══════════════════════════════════════════════════════
ACTIVE SESSION CONTEXT
═══════════════════════════════════════════════════════

{prod_context_str or "No products retrieved yet in this session."}

PRECEDENCE RULES FOR RESOLVING REFERENCES:
  • "this product" / "this page" / "buy this" / "add this to cart" → use
    CURRENT BROWSER PAGE PRODUCTS (deictic "right here on this page" context).
  • "the second one" / "the cheaper one" / "first option" → use the numbered
    Active/Recently Displayed Products (conversational ordinal context).
  • "checkout my cart" / "buy what's in my cart" → use the AUTHORITATIVE CART
    via create_order(), not either product list above.

Use the numbered [N] index within the relevant section to resolve ordinal
references like "the first one", "option 2", "compare the first two".
"""

    
    # 4. Fast path for simple greetings to respond instantly
    clean_msg = user_message.strip().lower()
    if clean_msg in {"hi", "hello", "hey", "hey nova", "hii", "yo", "hello nova", "hi nova"}:
        greeting = "👋 Hi there! I'm NOVA, your AI Commerce Assistant. What are you looking to shop for, compare, or buy today?"
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": greeting})
        return {"response": greeting, "executed_tools": []}

    # Construct complete message chain for Ollama API
    messages = [{"role": "system", "content": system_prompt}]
    
    # Append past conversation (limit to last 6 messages for token efficiency and fast inference)
    messages.extend(history[-16:])
    
    # Append the new user message
    messages.append({"role": "user", "content": user_message})
    
    # Add to internal persistent history
    history.append({"role": "user", "content": user_message})
    
    # 4. Agent Tool execution loop
    provider = get_llm_provider()
    tools = registry.get_schemas()
    allowed_tool_names = {schema["function"]["name"] for schema in tools}
    user_context = _recent_user_context(history, user_message)
    
    loop_count = 0
    max_loops = 5
    executed_tools = []
    
    while loop_count < max_loops:
        loop_count += 1
        print(f"Calling model {MODEL_NAME} (loop {loop_count})...")
        
        try:
            content, tool_calls = provider.generate_response(messages, tools)
        except RuntimeError as llm_err:
            err_str = str(llm_err).lower()
            if "empty" in err_str or "ollama" in err_str or "connect" in err_str:
                # Ollama connectivity or empty-output error — return a graceful response
                print(f"⚠️ LLM provider error: {llm_err}")
                fallback = "I'm having a bit of trouble reaching my thinking engine right now. Could you try rephrasing your question, or give me a moment and try again?"
                history.append({"role": "assistant", "content": fallback})
                return {"response": fallback, "executed_tools": executed_tools}
            raise
        
        # Some local models print tool JSON as content instead of structured tool_calls.
        # Recover those as internal calls, then sanitize content before it reaches chat.
        if not tool_calls:
            tool_calls = _extract_tool_calls_from_content(content, allowed_tool_names)
        clean_content = _sanitize_llm_content(content)
        
        # If there are no tool calls, this is the final conversational response
        if not tool_calls:
            # For shopping requests: try the deterministic shop path first so we
            # never hit the generic "tell me what you want" fallback when the user
            # has already provided enough information (e.g. "laptops under 80000").
            from backend.agent.shop_planner import looks_like_shop_search, looks_like_accessory_request
            is_shopping_msg = looks_like_shop_search(user_message) or looks_like_accessory_request(user_message)
            if is_shopping_msg:
                shop_fallback = _shop_fallback_payload(session_id, user_message, executed_tools)
                if shop_fallback:
                    history.append({"role": "assistant", "content": shop_fallback["response"]})
                    return shop_fallback

            if clean_content:
                # Final safety gate: if clean_content still looks like JSON or an
                # internal payload, convert it to a natural-language response.
                final_response = _ensure_natural_response(clean_content, session_id, user_message, executed_tools)
                history.append({"role": "assistant", "content": final_response})
                return {
                    "response": final_response,
                    "executed_tools": executed_tools
                }
            shop_fallback = _shop_fallback_payload(session_id, user_message, executed_tools)
            if shop_fallback:
                history.append({"role": "assistant", "content": shop_fallback["response"]})
                return shop_fallback
            fallback = _contextual_help_prompt(user_message)
            history.append({"role": "assistant", "content": fallback})
            return {"response": fallback, "executed_tools": executed_tools}
                
        # Handle tool calls
        print(f"Model requested {len(tool_calls)} tool calls: {tool_calls}")
        normalized_tool_calls = []
        for tc in tool_calls:
            tname = tc["name"]
            targs = _remove_invented_arguments(tname, tc.get("arguments") or {}, user_context)
            if _should_skip_tool_call(tname, targs, user_message):
                continue
            normalized_tool_calls.append({"name": tname, "arguments": targs})

        from backend.agent.commerce_router import rewrite_tool_calls
        normalized_tool_calls = rewrite_tool_calls(normalized_tool_calls, user_message)

        if not normalized_tool_calls:
            shop_fallback = _shop_fallback_payload(session_id, user_message, executed_tools)
            if shop_fallback:
                history.append({"role": "assistant", "content": shop_fallback["response"]})
                return shop_fallback
            response = clean_content or _contextual_help_prompt(user_message)
            response = _ensure_natural_response(response, session_id, user_message, executed_tools)
            history.append({"role": "assistant", "content": response})
            return {"response": response, "executed_tools": executed_tools}
        
        # We append the assistant's message with tool calls to the list
        # Use clean_content (sanitized) so history never stores raw JSON blobs
        assistant_msg = {
            "role": "assistant",
            "content": clean_content or "",
            "tool_calls": [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                } for i, tc in enumerate(normalized_tool_calls)
            ]
        }
        messages.append(assistant_msg)
        history.append(assistant_msg)
        
        # Execute each tool call
        for idx, tc in enumerate(normalized_tool_calls):
            tname = tc["name"]
            targs = tc["arguments"] or {}
            
            # Inject session_id if required by tool
            if tname in ["add_to_cart", "remove_from_cart", "get_cart", "clear_cart",
                          "create_order", "proceed_to_payment", "get_pairing_suggestions",
                          "resolve_product_action", "search_products", "get_product_details",
                          "get_recommendations", "get_copurchase_recommendations",
                          "get_purchase_history_summary", "compare_products", "compare_prices",
                          "email_action", "navigate_browser"]:
                targs["session_id"] = session_id
            if tname == "proceed_to_payment" and not targs.get("order_id"):
                from backend.agent.commerce_router import get_pending_order_id
                pending = get_pending_order_id(session_id)
                if pending:
                    targs["order_id"] = pending
                
            print(f"Executing tool {tname} with args {targs}...")
            result = registry.call_tool(tname, targs)

            if tname in ("create_order", "resolve_product_action") and isinstance(result, dict) and result.get("success") and result.get("order"):
                from backend.agent.commerce_router import set_pending_order_id
                set_pending_order_id(session_id, result["order"].get("id"))

            executed_tools.append({
                "name": tname,
                "arguments": {k: v for k, v in targs.items() if k != "session_id"}, # Hide session ID in logs
                "result": result
            })
            
            # If the tool list products, update active product context
            new_ids = parse_product_ids_from_result(tname, result)
            if new_ids:
                update_active_products(session_id, new_ids)
                
            # Append tool result message
            tool_msg = {
                "role": "tool",
                "content": json.dumps(result),
                "tool_call_id": f"call_{idx}"
            }
            messages.append(tool_msg)
            history.append(tool_msg)
            
    # Fallback response if loop limits reached
    fallback = _compose_user_facing_from_tools(executed_tools, user_message) or (
        "I can keep helping with that search. Ask me to refine by brand, budget, or source."
    )
    history.append({"role": "assistant", "content": fallback})
    return {
        "response": fallback,
        "executed_tools": executed_tools
    }


def _shop_fallback_payload(session_id: str, user_message: str, executed_tools) -> object:
    from backend.agent.shop_planner import looks_like_accessory_request, looks_like_shop_search, try_shop_turn
    if executed_tools:
        text = _compose_user_facing_from_tools(executed_tools, user_message)
        if text:
            return {"response": text, "executed_tools": executed_tools}
    if looks_like_accessory_request(user_message) or looks_like_shop_search(user_message):
        return try_shop_turn(session_id, user_message)
    return None


def _compose_user_facing_from_tools(executed_tools, user_message: str) -> object:
    from backend.agent.shop_planner import accessory_blurb, extract_user_intent, looks_like_accessory_request
    search = next((t for t in executed_tools if t.get("name") == "search_products"), None)
    nav = next((t for t in executed_tools if t.get("name") == "navigate_browser"), None)
    parts = []
    if nav and isinstance(nav.get("result"), dict) and nav["result"].get("url"):
        parts.append("I'll open the relevant shopping results and inspect the products listed there.")
    if search:
        result = search.get("result")
        if isinstance(result, list) and result:
            raw_intent = extract_user_intent(user_message)
            count = len([r for r in result if isinstance(r, dict)])
            currency = next(
                (r.get("currency") or "\u20b9" for r in result if isinstance(r, dict) and r.get("currency")),
                "\u20b9",
            )
            parts.append(f"I found {count} option(s) matching your request. Here are the top matches:")
            for r in result[:6]:
                if not isinstance(r, dict) or not r.get("name"):
                    continue
                price = r.get("price")
                merchant = r.get("merchant_name") or r.get("merchant") or ""
                rating = r.get("rating")
                line = f"- {r['name']}"
                if price:
                    line += f"  \u2014  {currency} {price}"
                if merchant:
                    line += f"  ({merchant})"
                if rating:
                    line += f"  \u2605 {rating}"
                parts.append(line)
            # Proactive complementary suggestions after product results
            if not looks_like_accessory_request(user_message):
                parts.append("")
                parts.append(accessory_blurb(raw_intent, None))
        elif isinstance(result, str) and "error" in result.lower():
            parts.append("I ran into a problem retrieving products. Try specifying a different source or narrowing the budget.")
    if parts:
        return "\n".join(parts)
    return None


def _ensure_natural_response(text: str, session_id: str, user_message: str, executed_tools) -> str:
    """
    Final safety gate: if text still looks like raw JSON / an internal payload,
    convert it to a natural-language response. Never expose internal data to the user.
    """
    from backend.agent.shop_planner import looks_like_internal_payload
    if not text or looks_like_internal_payload(text):
        shop = _shop_fallback_payload(session_id, user_message, executed_tools)
        if shop:
            return shop["response"]
        return _contextual_help_prompt(user_message)
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            import json as _json
            obj = _json.loads(stripped)
            if isinstance(obj, dict):
                shop = _shop_fallback_payload(session_id, user_message, executed_tools)
                if shop:
                    return shop["response"]
                return _contextual_help_prompt(user_message)
        except Exception:
            pass
    return text


def _contextual_help_prompt(user_message: str) -> str:
    """
    Generate a context-aware help prompt based on what the user already said.
    Never returns a generic 'tell me what you want' when the user provided enough info.
    """
    import re as _re
    from backend.agent.shop_planner import (
        extract_user_intent,
        _PRODUCTISH,
        parse_max_price,
        merchants_from_text,
        looks_like_shop_search,
    )
    raw = extract_user_intent(user_message)
    if not raw.strip():
        return "I'm ready to help you find, compare, or buy products. What are you looking for?"

    has_product = bool(_PRODUCTISH.search(raw))
    max_price = parse_max_price(raw)
    merchants = merchants_from_text(raw)

    if has_product and max_price:
        product_part = _re.split(r'\b(?:under|below|less than|upto|up to|within|max)\b', raw, flags=_re.I)[0].strip()
        budget_str = f"\u20b9{int(max_price):,}"
        merchant_str = f" on {merchants[0].replace('www.', '')}" if merchants else ""
        return (
            f"Sure \u2014 I'll look for {product_part}{merchant_str} under {budget_str} "
            f"and find the best available options for you."
        )
    if has_product:
        return f"On it \u2014 I'll search for {raw} and compare the best available options."
    if looks_like_shop_search(user_message):
        return "I'll search for that now. Give me a moment to check what's available."
    return "I can help you find products, compare prices, or manage your cart. What would you like to do?"


def clear_session(session_id: str):
    """Clear chat history and active products for a session."""
    if session_id in session_histories:
        session_histories[session_id] = []
        
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM session_states WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (session_id,))
    conn.commit()
    conn.close()
