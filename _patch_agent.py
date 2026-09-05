"""Patch backend/agent/agent.py in-place to replace the fallback function block."""
import re

path = "/Users/vidyadhar/razorpay hackathon/backend/agent/agent.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# ─── NEW REPLACEMENT BLOCK ────────────────────────────────────────────────────
NEW_BLOCK = '''

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
                (r.get("currency") or "\\u20b9" for r in result if isinstance(r, dict) and r.get("currency")),
                "\\u20b9",
            )
            parts.append(f"I found {count} option(s) matching your request. Here are the top matches:")
            for r in result[:6]:
                if not isinstance(r, dict) or not r.get("name"):
                    continue
                price = r.get("price")
                merchant = r.get("merchant_name") or r.get("merchant") or ""
                rating = r.get("rating")
                line = f"- {r[\'name\']}"
                if price:
                    line += f"  \\u2014  {currency} {price}"
                if merchant:
                    line += f"  ({merchant})"
                if rating:
                    line += f"  \\u2605 {rating}"
                parts.append(line)
            # Proactive complementary suggestions after product results
            if not looks_like_accessory_request(user_message):
                parts.append("")
                parts.append(accessory_blurb(raw_intent, None))
        elif isinstance(result, str) and "error" in result.lower():
            parts.append("I ran into a problem retrieving products. Try specifying a different source or narrowing the budget.")
    if parts:
        return "\\n".join(parts)
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
    Never returns a generic \'tell me what you want\' when the user provided enough info.
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
        return "I\'m ready to help you find, compare, or buy products. What are you looking for?"

    has_product = bool(_PRODUCTISH.search(raw))
    max_price = parse_max_price(raw)
    merchants = merchants_from_text(raw)

    if has_product and max_price:
        product_part = _re.split(r\'\\b(?:under|below|less than|upto|up to|within|max)\\b\', raw, flags=_re.I)[0].strip()
        budget_str = f"\\u20b9{int(max_price):,}"
        merchant_str = f" on {merchants[0].replace(\'www.\', \'\')}" if merchants else ""
        return (
            f"Sure \\u2014 I\'ll look for {product_part}{merchant_str} under {budget_str} "
            f"and find the best available options for you."
        )
    if has_product:
        return f"On it \\u2014 I\'ll search for {raw} and compare the best available options."
    if looks_like_shop_search(user_message):
        return "I\'ll search for that now. Give me a moment to check what\'s available."
    return "I can help you find products, compare prices, or manage your cart. What would you like to do?"

'''

# ─── LOCATE OLD BLOCK ─────────────────────────────────────────────────────────
start_marker = "\ndef _shop_fallback_payload"
end_marker = "\ndef clear_session"

start_idx = content.find(start_marker)
end_idx   = content.find(end_marker)

assert start_idx != -1, "Could not find start marker"
assert end_idx   != -1, "Could not find end marker"
assert end_idx > start_idx

# Replace the old block with the new one
content = content[:start_idx] + NEW_BLOCK + content[end_idx:]

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied successfully.")
print(f"File size: {len(content)} bytes")
