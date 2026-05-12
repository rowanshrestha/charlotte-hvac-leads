import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from database import init_db, save_lead, get_all_leads, get_leads_today
from agents.notifier import notify_new_lead
from agents.outreach import find_and_notify_contractors
from agents.prospector import run_prospector, init_prospector_db


class LeadSubmission(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: EmailStr
    service: str
    zip: str
    source: str = "landing_page"
    city: str = "Charlotte"
    state: str = "NC"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_prospector_db()
    # Run prospector once on startup to find + pitch contractors immediately
    asyncio.create_task(run_prospector(max_emails=10))
    yield


app = FastAPI(title="Charlotte HVAC Lead System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def run_notifications(lead_id: int, lead_data: dict):
    try:
        await notify_new_lead(lead_id, lead_data)
    except Exception as e:
        print(f"[Notifier error] {e}")
    try:
        await find_and_notify_contractors(lead_id, lead_data)
    except Exception as e:
        print(f"[Outreach error] {e}")


@app.post("/api/leads")
async def submit_lead(lead: LeadSubmission, background_tasks: BackgroundTasks):
    lead_id = save_lead(lead.model_dump())
    background_tasks.add_task(run_notifications, lead_id, lead.model_dump())
    return {"status": "success", "lead_id": lead_id}


@app.post("/api/prospect")
async def trigger_prospector(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_prospector, 10)
    return {"status": "Prospector running — will find and email contractors in background"}

@app.get("/api/debug")
async def debug_env():
    return {
        "telegram_token_set": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "telegram_chat_id_set": bool(os.getenv("TELEGRAM_CHAT_ID")),
        "smtp_user_set": bool(os.getenv("SMTP_USER")),
        "smtp_pass_set": bool(os.getenv("SMTP_PASS")),
    }

@app.post("/api/test-telegram")
async def test_telegram():
    import httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return {"error": "Telegram not configured", "token_set": bool(token), "chat_set": bool(chat_id)}
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "✅ Test from Railway — notifications are working!"},
            timeout=10
        )
    return res.json()

@app.get("/api/leads")
async def list_leads():
    return {"leads": get_all_leads()}


@app.get("/api/stats")
async def get_stats():
    all_leads = get_all_leads()
    today = get_leads_today()
    return {
        "total_leads": len(all_leads),
        "leads_today": len(today),
        "leads_this_week": len([
            l for l in all_leads
            if (datetime.now() - datetime.fromisoformat(l["created_at"])).days < 7
        ]),
    }


# Serve frontend
frontend_path = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_path, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
