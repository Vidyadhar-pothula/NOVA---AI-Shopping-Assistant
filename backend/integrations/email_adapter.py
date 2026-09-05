from typing import Dict, Any, Optional
import datetime
from backend.discovery.engine import discovery_engine
from backend.providers.email_provider import email_service
from backend.tools.registry import registry

from backend.config import SMTP_USER

class EmailAdapter:
    def __init__(self):
        self.is_configured = True
        self.user_email = SMTP_USER or "pothulavidyadhar@gmail.com"
        self.frequency = "daily"  # 'daily', 'weekly', 'important_only'
        self.categories = ["sales", "festivals", "sports", "movies"]

    def configure(self, email: str, enabled: bool = True, frequency: str = "daily"):
        self.user_email = (email or "").strip()
        self.is_configured = enabled
        self.frequency = frequency

    def handle_email_action(
        self,
        action: str,
        subject: Optional[str] = None,
        recipient_email: Optional[str] = None,
        category: Optional[str] = None,
        session_id: str = "default_session"
    ) -> Dict[str, Any]:
        # 1. Determine target email recipient from user's saved preference or request
        target_email = (recipient_email or self.user_email or "").strip()

        # Step 11: Check if Email preference toggle is enabled
        if not self.is_configured and not recipient_email:
            return {
                "status": "permission_required",
                "is_configured": False,
                "message": "Email notifications are disabled or not configured in Settings. Please set your email address and enable notifications in Settings before requesting deal emails."
            }

        if not target_email or not email_service.is_valid_email(target_email):
            return {
                "status": "INVALID_RECIPIENT",
                "is_configured": self.is_configured,
                "recipient": target_email,
                "message": "Please enter a valid notification email address in Settings before requesting deal digests."
            }

        # 2. Gather live deal discovery items
        feed_res = discovery_engine.get_discovery_feed(category=category or "all")
        feed_items = feed_res.get("feed", [])[:5]

        today_str = datetime.date.today().strftime("%B %d, %Y")
        email_subject = subject or f"NOVA Discover — What's New Today ({today_str})"

        # 3. Format dynamic markdown content with verified product/deal links
        lines = [
            f"# {email_subject}",
            f"Here are the latest curated deals and event highlights for you:\n"
        ]

        for idx, item in enumerate(feed_items, 1):
            title = item.get("title", "Featured Item")
            merchant = item.get("merchant") or item.get("source") or "Verified Source"
            url = item.get("url", "#")
            desc = item.get("description", "")
            lines.append(f"### {idx}. {title}")
            lines.append(f"- **Source**: {merchant}")
            lines.append(f"- **Details**: {desc}")
            lines.append(f"- **Link**: [{merchant} Deal Link]({url})\n")

        email_content = "\n".join(lines)

        # 4. Delegate to email_service for real SMTP delivery
        result = email_service.send_email(
            recipient=target_email,
            subject=email_subject,
            body_markdown=email_content,
            email_type="deal_digest",
            session_id=session_id
        )

        result["preview_items_count"] = len(feed_items)
        result["is_configured"] = self.is_configured
        return result

email_adapter = EmailAdapter()

def email_action(
    action: str = "send_digest",
    subject: Optional[str] = None,
    recipient_email: Optional[str] = None,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """Execute permissioned Email notification actions ('Email me today's best deals')."""
    return email_adapter.handle_email_action(
        action=action,
        subject=subject,
        recipient_email=recipient_email,
        category=category
    )

email_action_schema = {
    "type": "function",
    "function": {
        "name": "email_action",
        "description": "Send or draft personalized deal notifications, sports merchandise updates, or festival gift digests to user's configured email address.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action type: 'send_digest', 'send_recommendations'."
                },
                "subject": {
                    "type": "string",
                    "description": "Optional email subject line."
                },
                "recipient_email": {
                    "type": "string",
                    "description": "Recipient email address if specified."
                },
                "category": {
                    "type": "string",
                    "description": "Filter category: 'all', 'deals', 'festivals', 'sports', 'movies'."
                }
            }
        }
    }
}

registry.register(email_action_schema, email_action)
