"""Writes a small made-up resident workbook (every value is synthetic) for recording the demo video.

Run from backend/:  PYTHONPATH=. uv run python ../demo-video/sample_workbook.py /tmp/sample.xlsx
"""
import sys, openpyxl
from app.context import RESIDENT_COLUMNS, INTERACTION_COLUMNS
def row(cols, **kw): return [kw.get(c, "") for c in cols]
wb = openpyxl.Workbook(); wb.active.title = "README"
wb.active.append(["EVERY VALUE IS SYNTHETIC. Made-up sample data for a demo video."])
rs = wb.create_sheet("Residents"); rs.append(RESIDENT_COLUMNS)
rs.append(row(RESIDENT_COLUMNS, resident_id="R001", first_name="Marisol", last_name="Quenby", email="marisol.quenby@example.com",
  phone="555-0101", preferred_contact="text", preferred_language="English", community="Heron Lake Apartments", unit_type="2BR",
  move_in_date="2024-03-15", monthly_rent=1585, renewal_status="renewed", current_balance=0,
  preferred_entry_window="mornings (8-11 AM)", open_work_orders=1, notes_for_staff="Has a dog; text before entry."))
rs.append(row(RESIDENT_COLUMNS, resident_id="R002", first_name="Theo", last_name="Brandt", email="theo@example.com", phone="555-0102",
  preferred_contact="portal", preferred_language="English", community="Birchwood Commons", unit_type="1BR", move_in_date="2025-01-10",
  monthly_rent=1290, renewal_status="not due"))
rs.append(row(RESIDENT_COLUMNS, resident_id="R003", first_name="Jordan", last_name="Pellingham", email="jordan@example.com",
  phone="555-0103", preferred_contact="text", preferred_language="English", community="Sandpiper Pointe", unit_type="1BR",
  move_in_date="2024-12-01", monthly_rent=1349, renewal_status="offer sent"))
it = wb.create_sheet("Interactions"); it.append(INTERACTION_COLUMNS)
for iid, rid, ts, cat, subj, st, res, fu in [
  ("I002","R001","2026-06-08 14:31","maintenance","AC not cooling","closed","2026-06-09","N"),
  ("I003","R001","2026-08-19 08:47","maintenance","AC out again","closed","2026-08-20","N"),
  ("I008","R001","2026-10-27 08:12","maintenance","AC rattling","open",None,"Y"),
  ("I016","R003","2026-10-01 10:30","renewal","Renewal offer and 9-month question","closed","2026-10-01","Y")]:
  it.append(row(INTERACTION_COLUMNS, interaction_id=iid, resident_id=rid, timestamp=ts, channel="chat", category=cat, subject=subj,
    full_text="Resident: "+subj, status=st, resolved_date=res, follow_up_needed=fu))
wb.save(sys.argv[1])
