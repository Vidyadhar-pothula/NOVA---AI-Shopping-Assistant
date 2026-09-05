import os
import re
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List
from backend.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
from backend.providers.audit_provider import audit_service

_EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$')

class EmailService:
    """
    Real Email Delivery Pipeline Service (Phase 11 & Email Fix).
    Integrates directly with SMTP servers (Gmail, SendGrid, Mailgun, Amazon SES, or custom SMTP).

    Statuses returned:
    - SENT: Successfully accepted by the external SMTP server.
    - NOT_CONFIGURED: Missing SMTP_HOST / SMTP_USER / SMTP_PASSWORD in environment.
    - INVALID_RECIPIENT: Recipient email address is missing or invalid.
    - FAILED: SMTP connection, authentication, or provider delivery error.
    """

    def __init__(self):
        self.reload_config()

    def reload_config(self):
        self.smtp_host = os.getenv("SMTP_HOST", SMTP_HOST)
        self.smtp_port = int(os.getenv("SMTP_PORT", str(SMTP_PORT or 587)))
        self.smtp_user = os.getenv("SMTP_USER", SMTP_USER)
        self.smtp_password = os.getenv("SMTP_PASSWORD", SMTP_PASSWORD)
        self.smtp_from = os.getenv("SMTP_FROM", SMTP_FROM or self.smtp_user or "nova-agent@local.dev")
        self.has_real_provider = bool(self.smtp_host and self.smtp_user and self.smtp_password)

    def is_valid_email(self, email: Optional[str]) -> bool:
        if not email or not isinstance(email, str):
            return False
        clean = email.strip()
        if clean in ["user@example.com", "<user_email>", "<user's configured email>", ""]:
            return False
        return bool(_EMAIL_REGEX.match(clean))

    def send_email(
        self,
        recipient: str,
        subject: str,
        body_markdown: str,
        email_type: str = "deal_digest",
        session_id: str = "default_session"
    ) -> Dict[str, Any]:
        self.reload_config()
        target = (recipient or "").strip()
        timestamp = datetime.datetime.now().isoformat()

        # Step 1: Validate Recipient Email
        if not self.is_valid_email(target):
            audit_service.record_event(
                session_id=session_id,
                event_type="EMAIL_INVALID_RECIPIENT",
                data={"recipient": target, "subject": subject, "type": email_type}
            )
            return {
                "status": "INVALID_RECIPIENT",
                "recipient": target,
                "subject": subject,
                "timestamp": timestamp,
                "message": f"The recipient email address '{target}' is invalid or missing. Please update your notification email in Settings."
            }

        # Step 2: Check SMTP Provider Configuration
        if not self.has_real_provider:
            audit_service.record_event(
                session_id=session_id,
                event_type="EMAIL_NOT_CONFIGURED",
                data={"recipient": target, "subject": subject, "type": email_type}
            )
            return {
                "status": "NOT_CONFIGURED",
                "recipient": target,
                "subject": subject,
                "timestamp": timestamp,
                "missing_variables": [
                    var for var, val in [
                        ("SMTP_HOST", self.smtp_host),
                        ("SMTP_USER", self.smtp_user),
                        ("SMTP_PASSWORD", self.smtp_password)
                    ] if not val
                ],
                "message": f"Real email delivery is not configured on the server. Please supply SMTP_HOST, SMTP_USER, and SMTP_PASSWORD environment variables to deliver emails to {target}."
            }

        # Step 3: Attempt Real SMTP Delivery
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_from
            msg["To"] = target

            # Plain text part
            text_part = MIMEText(body_markdown, "plain")
            msg.attach(text_part)

            # HTML part for rich email clients
            body_for_html = (
                body_markdown
                .replace("# ", "<h1>")
                .replace("### ", "<h3>")
                .replace("\n", "<br>")
            )
            html_body = (
                "<html><body><div style='font-family:sans-serif;line-height:1.6;'>"
                + body_for_html
                + "</div></body></html>"
            )
            html_part = MIMEText(html_body, "html")
            msg.attach(html_part)

            # Connect and send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=12) as server:
                server.ehlo()
                if self.smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                send_errors = server.sendmail(self.smtp_from, [target], msg.as_string())

            if send_errors and target in send_errors:
                err_code, err_msg = send_errors[target]
                err_str = f"SMTP rejected recipient: {err_code} {err_msg}"
                audit_service.record_event(
                    session_id=session_id,
                    event_type="EMAIL_FAILED",
                    data={"recipient": target, "subject": subject, "error": err_str}
                )
                return {
                    "status": "FAILED",
                    "recipient": target,
                    "subject": subject,
                    "timestamp": timestamp,
                    "provider_error": err_str,
                    "message": f"The email server rejected delivery to {target}: {err_str}"
                }

            # Generate synthetic provider message ID for audit log
            msg_id = f"msg_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{target.split('@')[0]}"

            audit_service.record_event(
                session_id=session_id,
                event_type="EMAIL_SENT_SMTP",
                data={"recipient": target, "subject": subject, "type": email_type, "message_id": msg_id, "provider": self.smtp_host}
            )

            return {
                "status": "SENT",
                "delivery_mode": "smtp_live",
                "recipient": target,
                "sender": self.smtp_from,
                "subject": subject,
                "message_id": msg_id,
                "timestamp": timestamp,
                "message": f"Email '{subject}' successfully handed to {self.smtp_host} for delivery to {target}."
            }

        except smtplib.SMTPAuthenticationError as auth_err:
            err_msg = f"SMTP Authentication failed for user '{self.smtp_user}': {auth_err}"
            audit_service.record_event(session_id=session_id, event_type="EMAIL_FAILED", data={"recipient": target, "error": err_msg})
            return {
                "status": "FAILED",
                "recipient": target,
                "timestamp": timestamp,
                "provider_error": err_msg,
                "message": "Email delivery failed due to SMTP authentication credentials error."
            }

        except smtplib.SMTPDataError as data_err:
            err_msg = f"SMTP Provider Rejected Message (e.g. Mailbox quota or spam filter): {data_err}"
            audit_service.record_event(session_id=session_id, event_type="EMAIL_FAILED", data={"recipient": target, "error": err_msg})
            return {
                "status": "FAILED",
                "recipient": target,
                "timestamp": timestamp,
                "provider_error": err_msg,
                "message": "Email provider rejected the email message (recipient mailbox storage over-quota or rejected by filter)."
            }

        except Exception as general_err:
            err_msg = f"SMTP Delivery Error ({type(general_err).__name__}): {general_err}"
            audit_service.record_event(session_id=session_id, event_type="EMAIL_FAILED", data={"recipient": target, "error": err_msg})
            return {
                "status": "FAILED",
                "recipient": target,
                "timestamp": timestamp,
                "provider_error": err_msg,
                "message": f"Could not send email to {target} due to provider error."
            }

    def send_order_confirmation(
        self,
        recipient: str,
        order_id: str,
        total_amount: float,
        items: List[Dict[str, Any]],
        payment_id: Optional[str] = None,
        session_id: str = "default_session"
    ) -> Dict[str, Any]:
        subject = f"Receipt & Order Confirmation #{order_id} — NOVA Commerce"
        lines = [
            f"# Order Confirmation #{order_id}",
            f"Thank you for your purchase via NOVA AI Commerce Agent!\n",
            f"- **Order ID**: `{order_id}`",
            f"- **Razorpay Payment ID**: `{payment_id}`" if payment_id else "- **Razorpay Payment ID**: not provided",
            f"- **Total Amount Paid**: {total_amount}\n",
            "### Purchased Items:"
        ]
        for it in items:
            name = it.get("name") or it.get("title") or "Product Item"
            qty = it.get("quantity", 1)
            price = it.get("price", 0.0)
            merchant = it.get("merchant")
            url = it.get("product_url")
            extra = ""
            if merchant:
                extra += f" — {merchant}"
            lines.append(f"- **{name}** (x{qty}) — {price}{extra}")
            if url:
                lines.append(f"  {url}")

        lines.append("\nYour order is confirmed and scheduled for processing.")
        return self.send_email(recipient=recipient, subject=subject, body_markdown="\n".join(lines), email_type="order_confirmation", session_id=session_id)

    def send_payment_failure_notice(
        self,
        recipient: str,
        order_id: str,
        reason: str = "Transaction declined or cancelled by user",
        session_id: str = "default_session"
    ) -> Dict[str, Any]:
        subject = f"Payment Attention Required for Order #{order_id}"
        lines = [
            f"# Payment Attempt Notice — Order #{order_id}",
            f"We noticed that your recent payment attempt for order `{order_id}` was not completed.\n",
            f"- **Reason**: {reason}",
            f"- **Status**: Payment Failed / Cancelled",
            f"- **Cart Status**: Saved safely in your session\n",
            "You can retry payment or modify items anytime by returning to NOVA."
        ]
        return self.send_email(recipient=recipient, subject=subject, body_markdown="\n".join(lines), email_type="payment_failure", session_id=session_id)

    def send_test_email(self, recipient_email: str) -> Dict[str, Any]:
        subject = f"NOVA Real Email Delivery Pipeline Test ({datetime.datetime.now().strftime('%H:%M:%S')})"
        body = f"# NOVA Email Delivery Test\n\nThis is an automated delivery test from your NOVA AI Commerce Agent.\n\n- **Recipient**: {recipient_email}\n- **Timestamp**: {datetime.datetime.now().isoformat()}\n\nIf you received this message in your inbox, real email delivery is functioning perfectly!"
        return self.send_email(recipient=recipient_email, subject=subject, body_markdown=body, email_type="test_delivery")

email_service = EmailService()
