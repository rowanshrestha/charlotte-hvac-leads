import os
import httpx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from database import get_all_leads, get_leads_today

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "")

LEAD_SELL_PRICE = 75  # avg price per lead sold


async def send_daily_report():
    all_leads = get_all_leads()
    today_leads = get_leads_today()

    total = len(all_leads)
    today = len(today_leads)
    this_week = len([
        l for l in all_leads
        if (datetime.now() - datetime.fromisoformat(l["created_at"])).days < 7
    ])

    sold = [l for l in all_leads if l.get("status") == "sold"]
    revenue = sum(l.get("sold_price", LEAD_SELL_PRICE) for l in sold)
    unsold = total - len(sold)

    service_breakdown = {}
    for lead in all_leads:
        svc = lead.get("service", "unknown")
        service_breakdown[svc] = service_breakdown.get(svc, 0) + 1

    top_service = max(service_breakdown, key=service_breakdown.get) if service_breakdown else "N/A"

    report = {
        "total": total,
        "today": today,
        "this_week": this_week,
        "sold": len(sold),
        "unsold": unsold,
        "revenue": revenue,
        "top_service": top_service,
        "projected_monthly": this_week * 4 * LEAD_SELL_PRICE,
    }

    await _send_telegram_report(report)
    await _send_email_report(report, today_leads)
    print(f"[Reporter] Daily report sent — {today} leads today, ${revenue:.0f} total revenue")


async def _send_telegram_report(r: dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Reporter] Telegram not configured")
        return

    date_str = datetime.now().strftime("%b %d, %Y")
    message = (
        f"📊 *Daily Report — {date_str}*\n\n"
        f"📥 *Leads Today:* {r['today']}\n"
        f"📅 *Leads This Week:* {r['this_week']}\n"
        f"📦 *Total All Time:* {r['total']}\n\n"
        f"💰 *Sold:* {r['sold']} leads\n"
        f"🟡 *Unsold:* {r['unsold']} leads\n"
        f"💵 *Revenue Collected:* ${r['revenue']:.0f}\n"
        f"📈 *Projected Monthly:* ${r['projected_monthly']:.0f}\n\n"
        f"🔧 *Top Service:* {r['top_service'].replace('_', ' ').title()}"
    )

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
                timeout=10
            )
    except Exception as e:
        print(f"[Reporter] Telegram error: {e}")


async def _send_email_report(r: dict, today_leads: list):
    if not SMTP_USER or not OWNER_EMAIL:
        print("[Reporter] Email not configured")
        return

    date_str = datetime.now().strftime("%B %d, %Y")
    subject = f"📊 Daily HVAC Lead Report — {date_str} ({r['today']} leads today)"

    leads_html = ""
    for lead in today_leads[:10]:
        svc = lead.get("service", "").replace("_", " ").title()
        leads_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0">{lead['first_name']} {lead['last_name']}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0">{lead['phone']}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0">{svc}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0">{lead['zip']}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;color:{'#10b981' if lead.get('status')=='sold' else '#f59e0b'}">{lead.get('status','new').title()}</td>
        </tr>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px">
      <div style="background:#1a1a2e;padding:20px 24px;border-radius:8px 8px 0 0;display:flex;justify-content:space-between;align-items:center">
        <h2 style="color:#fff;margin:0">Charlotte<span style="color:#f97316">HVAC</span>Pros</h2>
        <span style="color:#a0aec0;font-size:14px">{date_str}</span>
      </div>

      <div style="background:#fff;border:1px solid #e2e8f0;padding:24px;border-radius:0 0 8px 8px">
        <h3 style="color:#1a1a2e;margin-top:0">Daily Performance Report</h3>

        <!-- Stats Grid -->
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px">
          <div style="background:#fef3e2;border-radius:8px;padding:16px;text-align:center">
            <div style="font-size:28px;font-weight:800;color:#f97316">{r['today']}</div>
            <div style="font-size:13px;color:#92400e">Leads Today</div>
          </div>
          <div style="background:#f0fdf4;border-radius:8px;padding:16px;text-align:center">
            <div style="font-size:28px;font-weight:800;color:#10b981">${r['revenue']:.0f}</div>
            <div style="font-size:13px;color:#166534">Revenue Earned</div>
          </div>
          <div style="background:#eff6ff;border-radius:8px;padding:16px;text-align:center">
            <div style="font-size:28px;font-weight:800;color:#3b82f6">${r['projected_monthly']:.0f}</div>
            <div style="font-size:13px;color:#1e40af">Projected Monthly</div>
          </div>
        </div>

        <!-- Today's Leads Table -->
        <h4 style="color:#1a1a2e">Today's Leads</h4>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <thead>
            <tr style="background:#f9fafb">
              <th style="padding:8px;text-align:left;color:#6b7280">Name</th>
              <th style="padding:8px;text-align:left;color:#6b7280">Phone</th>
              <th style="padding:8px;text-align:left;color:#6b7280">Service</th>
              <th style="padding:8px;text-align:left;color:#6b7280">Zip</th>
              <th style="padding:8px;text-align:left;color:#6b7280">Status</th>
            </tr>
          </thead>
          <tbody>{leads_html if leads_html else '<tr><td colspan="5" style="padding:16px;text-align:center;color:#9ca3af">No leads today yet</td></tr>'}</tbody>
        </table>

        <div style="margin-top:20px;padding:16px;background:#fef3e2;border-radius:8px;border-left:4px solid #f97316">
          <p style="margin:0;color:#92400e;font-size:14px">
            💡 <strong>Tip:</strong> You have <strong>{r['unsold']} unsold leads</strong>.
            Reach out to more contractors to convert them into revenue.
          </p>
        </div>
      </div>
    </div>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = OWNER_EMAIL
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, OWNER_EMAIL, msg.as_string())
        print("[Reporter] Daily email report sent")
    except Exception as e:
        print(f"[Reporter] Email error: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(send_daily_report())
