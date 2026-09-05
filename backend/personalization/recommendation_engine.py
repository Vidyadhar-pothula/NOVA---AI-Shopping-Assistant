from typing import List, Dict, Any, Optional
from backend.commerce.service import search_service
from backend.commerce.location import MarketResolver
from backend.personalization.history_analyzer import history_analyzer

class RecommendationEngine:
    """
    Shared Recommendation Engine for NOVA (used by both Standalone Web App and Extension).
    Combines General Product Relevance + Personal Customer Behavior (Frequency, Recency, Co-Purchase Pairs).
    """

    def get_recommendations(
        self,
        session_id: str,
        current_product_id: Optional[str] = None,
        category: Optional[str] = None,
        query: Optional[str] = None,
        country_code: Optional[str] = None,
        limit: int = 3
    ) -> Dict[str, Any]:
        market_obj = MarketResolver.resolve_market(country_code=country_code)

        # 1. Analyze user's order history
        freq_data = history_analyzer.analyze_frequent_purchases(session_id)
        has_history = freq_data.get("has_history", False)
        top_categories = freq_data.get("top_categories", {})
        top_brands = freq_data.get("top_brands", {})
        top_products = freq_data.get("top_products", [])

        # 2. Analyze co-purchase pairs if anchor category or product is specified
        anchor_category = category
        anchor_product = None
        if current_product_id:
            prod_details = search_service.get_product_details(current_product_id)
            if prod_details:
                anchor_product = prod_details
                if not anchor_category:
                    anchor_category = prod_details.category

        copurchase_data = history_analyzer.analyze_copurchase_pairs(
            session_id,
            anchor_product_id=current_product_id,
            anchor_category=anchor_category
        )
        copurchased_cats = copurchase_data.get("copurchased_categories", [])

        # 3. Determine target search queries based on current product + history
        search_queries = []
        explanation_reasons = []

        if anchor_product:
            # Cross-selling based on current product
            if copurchased_cats:
                best_copurchase_cat = copurchased_cats[0]["category"]
                search_queries.append(f"{best_copurchase_cat} for {anchor_product.name}")
                explanation_reasons.append(f"Frequently bought together with '{anchor_product.name}'")
            else:
                search_queries.append(f"{anchor_category or 'accessories'} for {anchor_product.name}")
                explanation_reasons.append(f"Complementary item for '{anchor_product.name}'")

        if has_history and top_categories:
            fav_cat = list(top_categories.keys())[0]
            fav_brand = list(top_brands.keys())[0] if top_brands else ""
            search_queries.append(f"{fav_brand} {fav_cat}".strip())
            count = top_categories[fav_cat]
            explanation_reasons.append(f"Based on your {count} previous purchase(s) in {fav_cat}")

        if query:
            search_queries.append(query)
            explanation_reasons.append(f"Matches your request for '{query}'")

        if not search_queries:
            fallback_cat = category or "Popular Deals"
            search_queries.append(fallback_cat)
            explanation_reasons.append("Top recommendation for your current market")

        # 4. Search live products for candidate recommendations
        recommendations = []
        seen_ids = set()
        if anchor_product:
            seen_ids.add(anchor_product.id)

        for idx, search_q in enumerate(search_queries):
            prods = search_service.search_products(search_q, market=market_obj)
            reason = explanation_reasons[idx] if idx < len(explanation_reasons) else "Recommended item"

            for p in prods:
                if p.id not in seen_ids and p.is_individual_product:
                    seen_ids.add(p.id)
                    rec_dict = p.to_dict()
                    rec_dict["recommendation_reason"] = reason
                    recommendations.append(rec_dict)
                    if len(recommendations) >= min(limit, 3):
                        break
            if len(recommendations) >= min(limit, 3):
                break

        if not recommendations:
            return {
                "status": "success",
                "has_personalized_history": has_history,
                "anchor_product": anchor_product.to_dict() if anchor_product else None,
                "total_recommendations": 0,
                "recommendations": [],
                "insights": {
                    "top_categories": top_categories,
                    "top_brands": top_brands,
                    "copurchased_categories": [c["category"] for c in copurchased_cats]
                },
                "message": "No authorized purchase history or related products are available to recommend yet."
            }

        return {
            "status": "success",
            "has_personalized_history": has_history,
            "anchor_product": anchor_product.to_dict() if anchor_product else None,
            "total_recommendations": len(recommendations),
            "recommendations": recommendations[:3],
            "insights": {
                "top_categories": top_categories,
                "top_brands": top_brands,
                "copurchased_categories": [c["category"] for c in copurchased_cats]
            }
        }

recommendation_engine = RecommendationEngine()
