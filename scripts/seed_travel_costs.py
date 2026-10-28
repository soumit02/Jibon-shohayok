"""
Loads data/travel_costs.csv into the travel_costs table (the Trip Planner reads prices only from here, never from the AI's memory).

1. Open data/travel_costs.csv in Excel/VS Code and replace every 0 with a price you checked yourself.
   Add more rows if you like. Rows with cost 0 are skipped.
2. Run:  python scripts/seed_travel_costs.py
   (For the live site: put the Neon DATABASE_URL in .env, run it once, then put the local value back.)
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete

from app.db.models import TravelCost
from app.db.session import SessionLocal, init_db

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "travel_costs.csv"

init_db()
with SessionLocal() as db, open(CSV_PATH, newline="", encoding="utf-8") as fh:
    rows = [r for r in csv.DictReader(fh) if r["cost_bdt"].strip().isdigit() and int(r["cost_bdt"]) > 0]
    db.execute(delete(TravelCost))
    for r in rows:
        db.add(TravelCost(route=r["route"].strip(), mode=r["mode"].strip(), cost_bdt=int(r["cost_bdt"]), notes=r["notes"].strip()))
    db.commit()
    print(f"Saved {len(rows)} cost rows." if rows else "No rows saved: replace the 0 values in data/travel_costs.csv first.")
