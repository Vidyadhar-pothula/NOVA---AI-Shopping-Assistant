import sys
sys.path.insert(0, "/Users/vidyadhar/razorpay hackathon")
from backend.providers.email_provider import email_service
import smtplib

email_service.reload_config()
print(f"has_real_provider: {email_service.has_real_provider}")
print(f"host: {email_service.smtp_host}")
print(f"port: {email_service.smtp_port}")
print(f"user: {email_service.smtp_user}")

try:
    with smtplib.SMTP(email_service.smtp_host, email_service.smtp_port, timeout=10) as s:
        code, msg = s.ehlo()
        print(f"EHLO: {code}")
        if email_service.smtp_port == 587:
            code2, msg2 = s.starttls()
            print(f"STARTTLS: {code2}")
            code3, msg3 = s.ehlo()
            print(f"EHLO2: {code3}")
        try:
            s.login(email_service.smtp_user, email_service.smtp_password)
            print("SMTP LOGIN: SUCCESS")
        except Exception as login_err:
            print(f"SMTP LOGIN FAILED: {type(login_err).__name__}: {login_err}")
except Exception as ce:
    print(f"SMTP CONNECT FAILED: {type(ce).__name__}: {ce}")

print()
print("=== Sending test email ===")
res = email_service.send_order_confirmation(
    recipient=email_service.smtp_user,
    order_id="ord_TEST_SMTP_001",
    total_amount=1299.0,
    items=[{"name": "SMTP Test Product", "quantity": 1, "price": 1299.0}],
    payment_id="pay_TEST_001",
    session_id="smtp_test_session"
)
print(f"Result: {res}")
