"""
Appointments REST API routes.
"""

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.db.database import get_db, Appointment, DoctorSchedule, Doctor

router = APIRouter()


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class BookAppointmentRequest(BaseModel):
    patient_id: str
    doctor_id: str
    date: str        # YYYY-MM-DD
    time_slot: str   # HH:MM
    language: str = "en"
    notes: str = ""


class RescheduleRequest(BaseModel):
    new_date: str
    new_time_slot: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/")
async def list_appointments(
    patient_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Appointment)
    if patient_id:
        query = query.where(Appointment.patient_id == patient_id)
    result = await db.execute(query)
    appointments = result.scalars().all()
    return [_serialize(a) for a in appointments]


@router.post("/book")
async def book_appointment(req: BookAppointmentRequest, db: AsyncSession = Depends(get_db)):
    """Book an appointment after validating slot availability."""
    # Check double booking
    conflict = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.doctor_id == req.doctor_id,
                Appointment.date == req.date,
                Appointment.time_slot == req.time_slot,
                Appointment.status == "confirmed"
            )
        )
    )
    if conflict.scalars().first():
        raise HTTPException(status_code=409, detail="Slot already booked. Please choose another time.")

    # Validate past-time booking
    slot_dt_str = f"{req.date} {req.time_slot}"
    try:
        slot_dt = datetime.strptime(slot_dt_str, "%Y-%m-%d %H:%M")
        if slot_dt < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Cannot book an appointment in the past.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time format.")

    # Validate doctor exists
    doc = await db.execute(select(Doctor).where(Doctor.id == req.doctor_id))
    doctor = doc.scalars().first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    if not doctor.available:
        raise HTTPException(status_code=400, detail="Doctor is not currently available.")

    appt = Appointment(
        id=str(uuid.uuid4()),
        patient_id=req.patient_id,
        doctor_id=req.doctor_id,
        date=req.date,
        time_slot=req.time_slot,
        language=req.language,
        notes=req.notes,
        status="confirmed"
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt)
    return {"success": True, "appointment": _serialize(appt)}


@router.patch("/{appointment_id}/reschedule")
async def reschedule_appointment(
    appointment_id: str,
    req: RescheduleRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalars().first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    if appt.status != "confirmed":
        raise HTTPException(status_code=400, detail="Only confirmed appointments can be rescheduled.")

    # Check new slot conflict
    conflict = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.doctor_id == appt.doctor_id,
                Appointment.date == req.new_date,
                Appointment.time_slot == req.new_time_slot,
                Appointment.status == "confirmed",
                Appointment.id != appointment_id
            )
        )
    )
    if conflict.scalars().first():
        raise HTTPException(status_code=409, detail="New slot is already booked.")

    appt.date = req.new_date
    appt.time_slot = req.new_time_slot
    await db.commit()
    await db.refresh(appt)
    return {"success": True, "appointment": _serialize(appt)}


@router.delete("/{appointment_id}/cancel")
async def cancel_appointment(appointment_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalars().first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    appt.status = "cancelled"
    await db.commit()
    return {"success": True, "message": "Appointment cancelled."}


@router.get("/availability")
async def check_availability(doctor_id: str, date: str, db: AsyncSession = Depends(get_db)):
    """Return available slots for a doctor on a given date."""
    sched = await db.execute(
        select(DoctorSchedule).where(
            and_(DoctorSchedule.doctor_id == doctor_id, DoctorSchedule.date == date)
        )
    )
    schedule = sched.scalars().first()
    if not schedule:
        return {"available_slots": []}

    booked = await db.execute(
        select(Appointment.time_slot).where(
            and_(
                Appointment.doctor_id == doctor_id,
                Appointment.date == date,
                Appointment.status == "confirmed"
            )
        )
    )
    booked_slots = {row[0] for row in booked.fetchall()}
    free_slots = [s for s in schedule.available_slots if s not in booked_slots]
    return {"available_slots": free_slots, "booked_slots": list(booked_slots)}


def _serialize(a: Appointment) -> dict:
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "doctor_id": a.doctor_id,
        "date": a.date,
        "time_slot": a.time_slot,
        "status": a.status,
        "language": a.language,
        "notes": a.notes,
        "created_at": str(a.created_at)
    }
