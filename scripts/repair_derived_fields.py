"""Recompute derived fields (city/state from location_raw, role_category from title) after normalizer / classifier changes."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app.core.database import SessionLocal
from backend.app.models.job import Job
from ingestion.normalizer import JobNormalizer
db = SessionLocal(); changed = 0
for j in db.query(Job).all():
    loc = (j.location_raw or "").split(";")[0] if j.source == "greenhouse" else j.location_raw
    city, state = JobNormalizer.extract_city_state(loc)
    role = JobNormalizer.infer_role_category(j.title)
    if (city, state, role) != (j.city, j.state, j.role_category):
        j.city, j.state, j.role_category = city, state, role; changed += 1
db.commit(); print("rows updated:", changed)
