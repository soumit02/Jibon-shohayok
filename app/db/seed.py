"""Loads data/travel_costs.csv into the travel_costs table when the table is empty (runs at every startup)."""
import csv
import logging

from sqlalchemy import func, select

from app.core.config import BASE_DIR
from app.db.models import TravelCost
from app.db.session import SessionLocal

log = logging.getLogger("jibon.seed")
CSV_PATH = BASE_DIR / "data" / "travel_costs.csv"


def seed_travel_costs_if_empty() -> int:
    """Rows with cost 0 are ignored. Returns how many rows were added."""
    if not CSV_PATH.exists():
        return 0
    with SessionLocal() as db:
        if db.execute(select(func.count()).select_from(TravelCost)).scalar_one() > 0:
            return 0
        added = 0
        with open(CSV_PATH, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                cost = (row.get("cost_bdt") or "").strip()
                if cost.isdigit() and int(cost) > 0:
                    db.add(TravelCost(route=row["route"].strip(), mode=row["mode"].strip(), cost_bdt=int(cost), notes=(row.get("notes") or "").strip()))
                    added += 1
        db.commit()
    log.info("Seeded %s travel cost rows", added)
    return added
