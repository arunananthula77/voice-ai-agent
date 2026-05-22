"""
Appointment tool functions — called by the AI agent via tool orchestration.
These are async functions that talk directly to the DB or internal API.
"""

import os
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Internal API base (self-calls when running as separate services)
# In monolith mode, we import DB functions directly for speed
BASE_URL = os.getenv("INTERNAL_API_URL", "http://localhost:8000")


async def check_availability(doctor_id: str, date: str) -> dict:
    """Check available slots for a doctor on a given date."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{BASE_URL}/api/appointments/availability",
                params={"doctor_id": doctor_id, "date": date}
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"check_availability error: {e}")
        return {"error": str(e), "available_slots": []}


async def book_appointment(
    patient_id: str,
    doctor_id: str,
    date: str,
    time_slot: str,
    language: str = "en",
    notes: str = ""
) -> dict:
    """Book an appointment."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{BASE_URL}/api/appointments/book",
                json={
                    "patient_id": patient_id,
                    "doctor_id": doctor_id,
                    "date": date,
                    "time_slot": time_slot,
                    "language": language,
                    "notes": notes
                }
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        error_detail = e.response.json().get("detail", str(e))
        logger.warning(f"book_appointment conflict: {error_detail}")
        return {"error": error_detail, "success": False}
    except Exception as e:
        logger.error(f"book_appointment error: {e}")
        return {"error": str(e), "success": False}


async def cancel_appointment(appointment_id: str) -> dict:
    """Cancel an appointment."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.delete(
                f"{BASE_URL}/api/appointments/{appointment_id}/cancel"
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"cancel_appointment error: {e}")
        return {"error": str(e), "success": False}


async def reschedule_appointment(
    appointment_id: str,
    new_date: str,
    new_time_slot: str
) -> dict:
    """Reschedule an existing appointment."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{BASE_URL}/api/appointments/{appointment_id}/reschedule",
                json={"new_date": new_date, "new_time_slot": new_time_slot}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        error_detail = e.response.json().get("detail", str(e))
        return {"error": error_detail, "success": False}
    except Exception as e:
        logger.error(f"reschedule_appointment error: {e}")
        return {"error": str(e), "success": False}


async def get_patient_appointments(patient_id: str) -> dict:
    """Get all appointments for a patient."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{BASE_URL}/api/appointments/",
                params={"patient_id": patient_id}
            )
            resp.raise_for_status()
            return {"appointments": resp.json()}
    except Exception as e:
        logger.error(f"get_patient_appointments error: {e}")
        return {"error": str(e), "appointments": []}


async def list_doctors(specialty: Optional[str] = None) -> dict:
    """List doctors, optionally by specialty."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            params = {}
            if specialty:
                params["specialty"] = specialty
            resp = await client.get(f"{BASE_URL}/api/appointments/doctors", params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"list_doctors error: {e}")
        # Return mock doctors for demo purposes
        return {
            "doctors": [
                {"id": "doc-001", "name": "Dr. Priya Sharma", "specialty": "cardiologist"},
                {"id": "doc-002", "name": "Dr. Ravi Kumar", "specialty": "dermatologist"},
                {"id": "doc-003", "name": "Dr. Anjali Menon", "specialty": "neurologist"},
                {"id": "doc-004", "name": "Dr. Suresh Iyer", "specialty": "general physician"},
            ]
        }
