import os
import re
import httpx
import smtplib
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

DB_PATH = Path(__file__).parent.parent / "leads.db"

YELP_SEARCHES = [
    "https://www.yelp.com/search?find_desc=HVAC&find_loc=Charlotte%2C+NC",
    "https://www.yelp.com/search?find_desc=Air+Conditioning+Repair&find_loc=Charlotte%2C+NC",
    "https://www.yelp.com/search?find_desc=Heating+Cooling&find_loc=Charlotte%2C+NC",
    "https://www.yelp.com/search?find_desc=Furnace+Repair&find_loc=Charlotte%2C+NC",
]

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
WEBSITE_REGEX = re.compile(r'href="(https?://(?!.*yelp\.com)[^"]+)"[^>]*>(?:Business Website|website|Visit Website)', re.IGNORECASE)
SKIP_DOMAINS = {"example.com", "sentry.io", "wix.com", "squarespace.com",
                "wordpress.com", "google.com", "yelp.com", "facebook.com",
                "instagram.com", "twitter.com", "linkedin.com", "bbb.org"}


def init_prospector_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prospected_contractors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT,
                email       TEXT UNIQUE,
                website     TEXT,
                phone       TEXT,
                source      TEXT,
                emailed     INTEGER DEFAULT 0,
                email_sent_at TEXT,
                responded   INTEGER DEFAULT 0,
                created_at  TEXT
            )
        """)
        conn.commit()


def save_prospect(name: str, email: str, website: str = "", phone: str = "", source: str = "") -> bool:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO prospected_contractors
                    (name, email, website, phone, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, email, website, phone, source, datetime.now().isoformat()))
            conn.commit()
            return True
    except Exception:
        return False


def get_uncontacted_prospects(limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM prospected_contractors WHERE emailed = 0 LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_emailed(email: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE prospected_contractors SET emailed=1, email_sent_at=? WHERE email=?",
            (datetime.now().isoformat(), email)
        )
        conn.commit()


async def find_contractors_yelp(url: str, client: httpx.AsyncClient) -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    contractors = []
    try:
        res = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
        html = res.text

        # Extract business links from Yelp search results
        biz_links = re.findall(r'href="(/biz/[a-z0-9\-]+)"', html)
        biz_links = list(dict.fromkeys(biz_links))[:10]  # dedupe, take first 10

        for biz_path in biz_links:
            try:
                biz_url = f"https://www.yelp.com{biz_path}"
                biz_res = await client.get(biz_url, headers=headers, timeout=10, follow_redirects=True)
                biz_html = biz_res.text

                # Extract business name
                name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', biz_html)
                name = name_match.group(1).strip() if name_match else ""

                # Extract website URL from Yelp page
                website_match = re.search(r'"website"[^>]*href="(https?://[^"]+)"', biz_html)
                if not website_match:
                    website_match = re.search(r'href="(https?://(?!.*yelp)[^"]+)"[^>]*>(?:Business Website|Visit Website)', biz_html, re.IGNORECASE)

                website = website_match.group(1) if website_match else ""

                if name:
                    contractors.append({
                        "name": name,
                        "website": website,
                        "phone": "",
                        "source": "yelp"
                    })
                    print(f"[Prospector] Found on Yelp: {name} — {website or 'no website'}")
            except Exception:
                continue

    except Exception as e:
        print(f"[Prospector] Yelp scrape error: {e}")

    return contractors


async def scrape_email_from_website(url: str, client: httpx.AsyncClient) -> str:
    if not url:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"}
        res = await client.get(url, headers=headers, timeout=8, follow_redirects=True)
        emails = EMAIL_REGEX.findall(res.text)
        for email in emails:
            domain = email.split("@")[1].lower()
            if domain not in SKIP_DOMAINS and not domain.endswith(".png") and not domain.endswith(".jpg"):
                return email.lower()

        # Also try /contact page
        base = url.rstrip("/")
        for path in ["/contact", "/contact-us", "/about"]:
            try:
                res2 = await client.get(base + path, headers=headers, timeout=6, follow_redirects=True)
                emails2 = EMAIL_REGEX.findall(res2.text)
                for email in emails2:
                    domain = email.split("@")[1].lower()
                    if domain not in SKIP_DOMAINS:
                        return email.lower()
            except Exception:
                continue
    except Exception as e:
        print(f"[Prospector] Scrape error for {url}: {e}")
    return ""


def build_pitch_email(contractor_name: str) -> tuple[str, str]:
    subject = "Charlotte homeowners are requesting HVAC quotes — interested?"
    name = contractor_name.split()[0] if contractor_name else "there"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:580px;margin:0 auto;padding:20px;color:#1a1a2e">
      <p>Hi {name},</p>

      <p>My name is Rowan — I run <strong>Charlotte HVAC Pros</strong>, a lead generation service
      connecting Charlotte homeowners with local HVAC contractors.</p>

      <p>Right now I have homeowners in the Charlotte area actively requesting quotes for:</p>
      <ul>
        <li>AC repair & installation</li>
        <li>Heating repair & replacement</li>
        <li>Emergency HVAC service</li>
      </ul>

      <p>I sell <strong>exclusive leads</strong> — meaning each lead goes to only one contractor.
      No competing with 5 other companies on the same customer.</p>

      <p><strong>How it works:</strong></p>
      <ol>
        <li>A homeowner requests a quote on my site</li>
        <li>I send you their name, phone, email, and what they need</li>
        <li>You call them and close the job</li>
      </ol>

      <p>Leads are <strong>$50–75 each</strong>. I'll send you the first one <strong>completely free</strong>
      so you can see the quality before committing to anything.</p>

      <p>Interested? Just reply to this email and I'll send over your first lead today.</p>

      <p>Best,<br/>
      <strong>Rowan</strong><br/>
      Charlotte HVAC Pros<br/>
      <a href="https://charlotte-hvac-leads-production.up.railway.app">charlottehvacpros.com</a></p>

      <p style="font-size:11px;color:#9ca3af;margin-top:20px">
        You're receiving this because you're a local HVAC contractor in the Charlotte area.
        Reply "unsubscribe" to be removed.
      </p>
    </div>
    """
    return subject, html


async def send_pitch_email(contractor: dict) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        print(f"[Prospector] SMTP not configured — would email {contractor['email']}")
        return False

    subject, html = build_pitch_email(contractor.get("name", ""))

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Rowan | Charlotte HVAC Pros <{SMTP_USER}>"
        msg["To"] = contractor["email"]
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, contractor["email"], msg.as_string())

        mark_emailed(contractor["email"])
        print(f"[Prospector] Pitched {contractor['name']} at {contractor['email']}")
        return True
    except Exception as e:
        print(f"[Prospector] Email error to {contractor['email']}: {e}")
        return False


async def run_prospector(max_emails: int = 10):
    init_prospector_db()
    print(f"[Prospector] Starting — will find and pitch up to {max_emails} contractors")

    async with httpx.AsyncClient() as client:
        # Step 1: Find contractors via Yelp
        all_contractors = []
        for url in YELP_SEARCHES:
            results = await find_contractors_yelp(url, client)
            all_contractors.extend(results)
            print(f"[Prospector] Found {len(results)} contractors from Yelp search")

        # Step 2: Scrape emails from their websites
        found = 0
        for c in all_contractors:
            if found >= max_emails * 2:
                break
            email = await scrape_email_from_website(c.get("website", ""), client)
            if email:
                saved = save_prospect(
                    name=c["name"],
                    email=email,
                    website=c.get("website", ""),
                    phone=c.get("phone", ""),
                    source=c.get("source", "")
                )
                if saved:
                    found += 1
                    print(f"[Prospector] Found email: {c['name']} → {email}")

        print(f"[Prospector] Scraped {found} contractor emails")

        # Step 3: Email uncontacted prospects
        prospects = get_uncontacted_prospects(limit=max_emails)
        sent = 0
        for prospect in prospects:
            success = await send_pitch_email(prospect)
            if success:
                sent += 1

        print(f"[Prospector] Done — pitched {sent} contractors")
        return {"found": found, "emailed": sent}


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_prospector())
