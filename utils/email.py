import requests
from config import BREVO_API_KEY, SENDER_EMAIL, SENDER_NAME


def send_otp_email(to_email, otp_code, purpose="verify_email"):
    subject_map = {
        "verify_email": "Verify your email",
        "reset_password": "Reset your password"
    }
    subject = subject_map.get(purpose, "Your verification code")

    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        },
        json={
            "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": f"<p>Your verification code is:</p><h2>{otp_code}</h2><p>This code expires in 10 minutes.</p>"
        }
    )

    if response.status_code >= 300:
        print(f"[EMAIL ERROR] Failed to send to {to_email}: {response.text}")

    return response.status_code < 300