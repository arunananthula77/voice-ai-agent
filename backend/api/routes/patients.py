"""
Patients REST API routes.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.database import get_db, Patient

router = APIRouter()


class PatientCreate(BaseModel):
    name: str
    phone: str
    preferred_language: str = "en"


@router.post("/")
async def create_patient(req: PatientCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Patient).where(Patient.phone == req.phone))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Patient with this phone already exists.")
    patient = Patient(
        id=str(uuid.uuid4()),
        name=req.name,
        phone=req.phone,
        preferred_language=req.preferred_language
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return {"id": patient.id, "name": patient.name, "phone": patient.phone,
            "preferred_language": patient.preferred_language}


@router.get("/{patient_id}")
async def get_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return {"id": patient.id, "name": patient.name, "phone": patient.phone,
            "preferred_language": patient.preferred_language}


@router.patch("/{patient_id}/language")
async def update_language(patient_id: str, language: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    patient.preferred_language = language
    await db.commit()
    return {"success": True, "preferred_language": language}
