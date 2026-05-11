import os
import smtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

SERVICE_LABELS = {
    "ac_repair": "AC Repair",
    "ac_installation": "AC Installation / Replacement",
    "heating_repair": "Heating Repair",
    "heating_installation": "Heating Installation / Replacement",
    "maintenance": "Annual Maintenance / Tune-Up",
    "duct_cleaning": "Duct Cleaning",
    "emergency": "Emergency Service",
    "other": "Other / Not Sure",
}

# Load from environment — set these in .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "")


async def notify_new_lead(lead_id: int, lead: dict):
    service = SERVICE_LABELS.get(lead.get("service", ""), lead.get("service", "Unknown"))
    timestamp = datetime.now().strftime("%b %d, %Y at %I:%M %p")

    await _send_telegram(lead_id, lead, service, timestamp)
    await _send_owner_email(lead_id, lead, service, timestamp)
    await _send_confirmation_email(lead)


async def _send_telegram(lead_id: int, lead: dict, service: str, timestamp: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Notifier] Telegram not configured — skipping")
        return

    message = (
        f"🔥 *New HVAC Lead #{lead_id}*\n\n"
        f"👤 *Name:* {lead['first_name']} {lead['last_name']}\n"
        f"📞 *Phone:* {lead['phone']}\n"
        f"📧 *Email:* {lead['email']}\n"
        f"🔧 *Service:* {service}\n"
        f"📍 *Zip:* {lead['zip']} — Charlotte, NC\n"
        f"🕐 *Time:* {timestamp}\n\n"
        f"Reply to sell this lead to a contractor!"
    )

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
        print(f"[Notifier] Telegram sent for lead #{lead_id}")
    except Exception as e:
        print(f"[Notifier] Telegram error: {e}")


async def _send_owner_email(lead_id: int, lead: dict, service: str, timestamp: str):
    if not SMTP_USER or not OWNER_EMAIL:
        print("[Notifier] Email not configured — skipping owner email")
        return

    subject = f"🔥 New HVAC Lead #{lead_id} — {lead['first_name']} {lead['last_name']} ({service})"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
      <div style="background:#f97316;padding:16px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:#fff;margin:0">🔥 New Lead Captured!</h2>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;padding:24px;border-radius:0 0 8px 8px">
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:8px 0;color:#718096;font-size:14px">Lead ID</td><td style="padding:8px 0;font-weight:700">#{lead_id}</td></tr>
          <tr><td style="padding:8px 0;color:#718096;font-size:14px">Name</td><td style="padding:8px 0;font-weight:700">{lead['first_name']} {lead['last_name']}</td></tr>
          <tr><td style="padding:8px 0;color:#718096;font-size:14px">Phone</td><td style="padding:8px 0;font-weight:700">{lead['phone']}</td></tr>
          <tr><td style="padding:8px 0;color:#718096;font-size:14px">Email</td><td style="padding:8px 0;font-weight:700">{lead['email']}</td></tr>
          <tr><td style="padding:8px 0;color:#718096;font-size:14px">Service Needed</td><td style="padding:8px 0;font-weight:700">{service}</td></tr>
          <tr><td style="padding:8px 0;color:#718096;font-size:14px">Zip Code</td><td style="padding:8px 0;font-weight:700">{lead['zip']}</td></tr>
          <tr><td style="padding:8px 0;color:#718096;font-size:14px">Submitted</td><td style="padding:8px 0;font-weight:700">{timestamp}</td></tr>
        </table>
        <div style="margin-top:20px;padding:16px;background:#fef3e2;border-radius:8px;border-left:4px solid #f97316">
          <p style="margin:0;color:#92400e;font-size:14px">
            <strong>Action required:</strong> Contact a Charlotte contractor and sell this lead for $50–$100.
          </p>
        </div>
      </div>
    </div>
    """

    await _send_email(OWNER_EMAIL, subject, html)


async def _send_confirmation_email(lead: dict):
    if not SMTP_USER:
        return

    subject = "Your Free HVAC Quote Request — Charlotte HVAC Pros"
    service = SERVICE_LABELS.get(lead.get("service", ""), "HVAC Service")

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
      <div style="background:#1a1a2e;padding:16px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:#fff;margin:0">Charlotte<span style="color:#f97316">HVAC</span>Pros</h2>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;padding:24px;border-radius:0 0 8px 8px">
        <h3 style="color:#1a1a2e">Hi {lead['first_name']}, we got your request!</h3>
        <p style="color:#4a5568;line-height:1.6">
          A licensed Charlotte HVAC contractor will be calling you at <strong>{lead['phone']}</strong>
          within the next <strong>15 minutes</strong> to discuss your <strong>{service}</strong> needs
          and provide a free, no-obligation quote.
        </p>
        <div style="background:#f0fdf4;border-radius:8px;padding:16px;margin:20px 0">
          <p style="margin:0;color:#166534;font-size:14px">
            ✅ <strong>What to expect:</strong> The contractor will ask a few questions about your system,
            give you a price estimate, and schedule a time that works for you.
          </p>
        </div>
        <p style="color:#718096;font-size:13px">
          Questions? Reply to this email anytime. We're here to help.
        </p>
      </div>
    </div>
    """

    await _send_email(lead["email"], subject, html)


async def _send_email(to: str, subject: str, html: str):
    if not SMTP_USER or not SMTP_PASS:
        print(f"[Notifier] SMTP not configured — skipping email to {to}")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to, msg.as_string())
        print(f"[Notifier] Email sent to {to}")
    except Exception as e:
        print(f"[Notifier] Email error to {to}: {e}")
