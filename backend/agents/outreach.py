import os
import httpx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from anthropic import AsyncAnthropic

from database import get_contractors, save_contractor, log_notification

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

SERVICE_LABELS = {
    "ac_repair": "AC Repair",
    "ac_installation": "AC Installation / Replacement",
    "heating_repair": "Heating Repair",
    "heating_installation": "Heating Installation / Replacement",
    "maintenance": "Annual Maintenance / Tune-Up",
    "duct_cleaning": "Duct Cleaning",
    "emergency": "Emergency Service",
    "other": "HVAC Service",
}


async def find_and_notify_contractors(lead_id: int, lead: dict):
    contractors = get_contractors()

    if not contractors:
        print("[Outreach] No contractors in DB yet — searching Google Places...")
        contractors = await _find_contractors_via_google()

    if not contractors:
        print("[Outreach] No contractors found — skipping outreach")
        return

    # Notify up to 3 contractors per lead
    notified = 0
    for contractor in contractors[:3]:
        success = await _send_lead_to_contractor(lead_id, lead, contractor)
        if success:
            log_notification(lead_id, contractor["id"])
            notified += 1

    print(f"[Outreach] Notified {notified} contractors for lead #{lead_id}")


async def _find_contractors_via_google() -> list[dict]:
    if not GOOGLE_PLACES_API_KEY:
        print("[Outreach] No Google Places API key — using seed contractors")
        return _get_seed_contractors()

    contractors = []
    searches = ["HVAC contractor Charlotte NC", "air conditioning repair Charlotte NC", "heating contractor Charlotte NC"]

    async with httpx.AsyncClient() as client:
        for query in searches:
            try:
                res = await client.get(
                    "https://maps.googleapis.com/maps/api/place/textsearch/json",
                    params={"query": query, "key": GOOGLE_PLACES_API_KEY},
                    timeout=10
                )
                data = res.json()
                for place in data.get("results", [])[:5]:
                    # Get details for email/phone
                    detail_res = await client.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": place["place_id"],
                            "fields": "name,formatted_phone_number,website,email",
                            "key": GOOGLE_PLACES_API_KEY
                        },
                        timeout=10
                    )
                    detail = detail_res.json().get("result", {})
                    email = detail.get("email", "")
                    if email:
                        contractor_id = save_contractor({
                            "name": place["name"],
                            "email": email,
                            "phone": detail.get("formatted_phone_number", ""),
                            "city": "Charlotte",
                            "services": "HVAC"
                        })
                        contractors.append({"id": contractor_id, "name": place["name"], "email": email})
            except Exception as e:
                print(f"[Outreach] Google Places error: {e}")

    return contractors


def _get_seed_contractors() -> list[dict]:
    """Seed contractors to get started — replace with real ones you've manually found."""
    seeds = [
        # Add real Charlotte HVAC contractors here after manual research
        # {"name": "ABC Heating & Cooling", "email": "contact@abchvac.com", "phone": "704-555-0001", "city": "Charlotte", "services": "HVAC"},
    ]
    saved = []
    for s in seeds:
        cid = save_contractor(s)
        if cid:
            saved.append({**s, "id": cid})
    return saved


async def _send_lead_to_contractor(lead_id: int, lead: dict, contractor: dict) -> bool:
    service = SERVICE_LABELS.get(lead.get("service", ""), "HVAC Service")
    email_body = await _generate_lead_email(lead, service, contractor["name"])

    subject = f"🔥 New Customer Lead — {service} in {lead['zip']} Charlotte, NC"

    if not SMTP_USER or not SMTP_PASS:
        print(f"[Outreach] SMTP not configured — would send to {contractor['email']}")
        print(f"[Outreach] Subject: {subject}")
        return True  # Simulate success for testing

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = contractor["email"]
        msg.attach(MIMEText(email_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, contractor["email"], msg.as_string())

        print(f"[Outreach] Lead #{lead_id} sent to {contractor['name']} ({contractor['email']})")
        return True
    except Exception as e:
        print(f"[Outreach] Failed to send to {contractor['email']}: {e}")
        return False


async def _generate_lead_email(lead: dict, service: str, contractor_name: str) -> str:
    if not ANTHROPIC_API_KEY:
        return _fallback_email(lead, service, contractor_name)

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Write a short, professional HTML email to an HVAC contractor selling them a customer lead.

Contractor name: {contractor_name}
Customer: {lead['first_name']} {lead['last_name']}
Service needed: {service}
Location: Charlotte, NC {lead['zip']}
Phone: {lead['phone']}
Email: {lead['email']}

The email should:
- Be friendly and direct
- Present the lead as exclusive and time-sensitive
- Include all customer contact details in a clear table
- Ask them to reply or call the customer immediately
- Mention the lead price is $75 (negotiable)
- Be under 200 words
- Return only the HTML body content, no <html> or <body> tags"""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        print(f"[Outreach] Claude email generation error: {e}")
        return _fallback_email(lead, service, contractor_name)


def _fallback_email(lead: dict, service: str, contractor_name: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
      <h2 style="color:#f97316">🔥 New Customer Lead Available</h2>
      <p>Hi {contractor_name},</p>
      <p>A Charlotte homeowner just requested a <strong>{service}</strong> quote.
         This lead is <strong>exclusive and time-sensitive</strong> — first contractor to respond wins the job.</p>

      <table style="width:100%;border-collapse:collapse;margin:20px 0;background:#f9fafb;border-radius:8px;padding:16px">
        <tr><td style="padding:8px;color:#6b7280">Name</td><td style="padding:8px;font-weight:700">{lead['first_name']} {lead['last_name']}</td></tr>
        <tr><td style="padding:8px;color:#6b7280">Phone</td><td style="padding:8px;font-weight:700">{lead['phone']}</td></tr>
        <tr><td style="padding:8px;color:#6b7280">Email</td><td style="padding:8px;font-weight:700">{lead['email']}</td></tr>
        <tr><td style="padding:8px;color:#6b7280">Service</td><td style="padding:8px;font-weight:700">{service}</td></tr>
        <tr><td style="padding:8px;color:#6b7280">Zip Code</td><td style="padding:8px;font-weight:700">{lead['zip']} — Charlotte, NC</td></tr>
      </table>

      <p><strong>Lead price: $75</strong> — Reply to this email to claim it.</p>
      <p>Call the customer now at <strong>{lead['phone']}</strong> for best results.</p>
      <p style="color:#9ca3af;font-size:12px;margin-top:20px">
        Charlotte HVAC Pros · Reply to unsubscribe
      </p>
    </div>
    """
