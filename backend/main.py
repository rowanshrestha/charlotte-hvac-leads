import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from database import init_db, save_lead, get_all_leads, get_leads_today
from agents.notifier import notify_new_lead
from agents.outreach import find_and_notify_contractors


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
    yield


app = FastAPI(title="Charlotte HVAC Lead System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/leads")
async def submit_lead(lead: LeadSubmission):
    lead_id = save_lead(lead.model_dump())

    # Fire notifications concurrently — don't block the response
    asyncio.create_task(notify_new_lead(lead_id, lead.model_dump()))
    asyncio.create_task(find_and_notify_contractors(lead_id, lead.model_dump()))

    return {"status": "success", "lead_id": lead_id}


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
