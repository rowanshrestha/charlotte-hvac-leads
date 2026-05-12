"""
Runs as a separate process alongside main.py.
Sends the daily report every day at 8:00 PM.

Run with: python scheduler.py
"""
import asyncio
from datetime import datetime, time as dt_time

from agents.reporter import send_daily_report
from agents.prospector import run_prospector

REPORT_HOUR = 20    # 8 PM
REPORT_MINUTE = 0


async def run_scheduler():
    print("[Scheduler] Started — daily report fires at 8:00 PM")
    while True:
        now = datetime.now()
        next_run = now.replace(hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0)

        if now >= next_run:
            # Already past 8 PM today — schedule for tomorrow
            next_run = next_run.replace(day=now.day + 1)

        wait_seconds = (next_run - now).total_seconds()
        print(f"[Scheduler] Next report in {wait_seconds/3600:.1f} hours")
        await asyncio.sleep(wait_seconds)

        print("[Scheduler] Firing daily report + prospecting...")
        await send_daily_report()
        await run_prospector(max_emails=15)
        await asyncio.sleep(60)  # Prevent double-fire


if __name__ == "__main__":
    asyncio.run(run_scheduler())
