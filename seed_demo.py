"""
Demo seed script — populates the database with sample doctors, schedules, and patients.
Run once after first startup: python seed_demo.py
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from backend.db.database import init_db, AsyncSessionLocal, Doctor, DoctorSchedule, Patient


DOCTORS = [
    {"id": "doc-001", "name": "Dr. Priya Sharma",   "specialty": "cardiologist"},
    {"id": "doc-002", "name": "Dr. Ravi Kumar",     "specialty": "dermatologist"},
    {"id": "doc-003", "name": "Dr. Anjali Menon",   "specialty": "neurologist"},
    {"id": "doc-004", "name": "Dr. Suresh Iyer",    "specialty": "general physician"},
    {"id": "doc-005", "name": "Dr. Meena Pillai",   "specialty": "pediatrician"},
]

PATIENTS = [
    {"id": "pat-001", "name": "Rahul Verma",    "phone": "+919876543210", "preferred_language": "hi"},
    {"id": "pat-002", "name": "Kavitha Nair",   "phone": "+919876543211", "preferred_language": "ta"},
    {"id": "pat-003", "name": "Arun Sharma",    "phone": "+919876543212", "preferred_language": "en"},
]

BASE_SLOTS = ["09:00", "09:30", "10:00", "10:30", "11:00",
              "14:00", "14:30", "15:00", "15:30", "16:00"]


async def seed():
    await init_db()

    async with AsyncSessionLocal() as db:
        # Add doctors
        for doc_data in DOCTORS:
            existing = await db.get(Doctor, doc_data["id"])
            if not existing:
                db.add(Doctor(**doc_data))

        # Add patients
        for pat_data in PATIENTS:
            existing = await db.get(Patient, pat_data["id"])
            if not existing:
                db.add(Patient(created_at=datetime.utcnow(), **pat_data))

        # Add doctor schedules for next 14 days
        today = datetime.today()
        for doc in DOCTORS:
            for day_offset in range(1, 15):
                date_str = (today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                # Skip weekends
                if (today + timedelta(days=day_offset)).weekday() >= 5:
                    continue
                from sqlalchemy import select, and_
                existing_sched = await db.execute(
                    select(DoctorSchedule).where(
                        and_(
                            DoctorSchedule.doctor_id == doc["id"],
                            DoctorSchedule.date == date_str
                        )
                    )
                )
                if not existing_sched.scalars().first():
                    db.add(DoctorSchedule(
                        doctor_id=doc["id"],
                        date=date_str,
                        available_slots=BASE_SLOTS
                    ))

        await db.commit()

    print("✅ Demo data seeded successfully.")
    print("Doctors:", [d["name"] for d in DOCTORS])
    print("Patients:", [p["name"] for p in PATIENTS])


if __name__ == "__main__":
    asyncio.run(seed())
