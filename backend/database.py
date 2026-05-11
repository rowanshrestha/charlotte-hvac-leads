import sqlite3
import json
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "leads.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name  TEXT NOT NULL,
                last_name   TEXT NOT NULL,
                phone       TEXT NOT NULL,
                email       TEXT NOT NULL,
                service     TEXT NOT NULL,
                zip         TEXT NOT NULL,
                city        TEXT DEFAULT 'Charlotte',
                state       TEXT DEFAULT 'NC',
                source      TEXT DEFAULT 'landing_page',
                status      TEXT DEFAULT 'new',
                sold_to     TEXT,
                sold_price  REAL,
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contractors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                email       TEXT NOT NULL,
                phone       TEXT,
                city        TEXT,
                services    TEXT,
                notified_count INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_notifications (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id       INTEGER,
                contractor_id INTEGER,
                sent_at       TEXT NOT NULL,
                opened        INTEGER DEFAULT 0,
                responded     INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def save_lead(data: dict) -> int:
    data["created_at"] = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("""
            INSERT INTO leads
                (first_name, last_name, phone, email, service, zip, city, state, source, created_at)
            VALUES
                (:first_name, :last_name, :phone, :email, :service, :zip, :city, :state, :source, :created_at)
        """, data)
        conn.commit()
        return cur.lastrowid


def get_all_leads() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_leads_today() -> list[dict]:
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM leads WHERE created_at LIKE ? ORDER BY created_at DESC",
            (f"{today}%",)
        ).fetchall()
        return [dict(r) for r in rows]


def get_lead_by_id(lead_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None


def update_lead_status(lead_id: int, status: str, sold_to: str = None, sold_price: float = None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE leads SET status=?, sold_to=?, sold_price=? WHERE id=?",
            (status, sold_to, sold_price, lead_id)
        )
        conn.commit()


def save_contractor(data: dict) -> int:
    data["created_at"] = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("""
            INSERT OR IGNORE INTO contractors (name, email, phone, city, services, created_at)
            VALUES (:name, :email, :phone, :city, :services, :created_at)
        """, data)
        conn.commit()
        return cur.lastrowid


def get_contractors() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM contractors").fetchall()
        return [dict(r) for r in rows]


def log_notification(lead_id: int, contractor_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO lead_notifications (lead_id, contractor_id, sent_at) VALUES (?, ?, ?)",
            (lead_id, contractor_id, datetime.now().isoformat())
        )
        conn.execute(
            "UPDATE contractors SET notified_count = notified_count + 1 WHERE id = ?",
            (contractor_id,)
        )
        conn.commit()
