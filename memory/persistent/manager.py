"""
Persistent Memory Manager.

Stores long-term patient context that survives across sessions.
Primary: Redis (with TTL)
Fallback: SQLite via the main DB
"""

import os
import json
import logging
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PERSISTENT_TTL_SECONDS = int(os.getenv("PERSISTENT_TTL_SECONDS", str(60 * 60 * 24 * 30)))  # 30 days
USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"
MAX_INTERACTION_LOG = 50  # Keep last 50 interactions per patient


class PersistentMemoryManager:
    """
    Manages long-term, cross-session patient context.
    
    Storage schema (Redis key: patient_context:{patient_id}):
    {
        "patient_id": str,
        "name": str,
        "preferred_language": str,
        "preferred_doctor": str | null,
        "past_appointments": [...],       # last N appointments
        "interaction_log": [...],         # last N interactions
        "last_seen": ISO datetime,
    }
    """

    def __init__(self):
        self._redis = None
        self._memory = {}  # in-memory fallback

    async def _get_redis(self):
        if not USE_REDIS:
            return None
        if self._redis is None:
            try:
                import aioredis
                self._redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
            except ImportError:
                logger.warning("aioredis not installed. Using in-memory persistent storage.")
            except Exception as e:
                logger.warning(f"Redis unavailable: {e}. Using in-memory fallback.")
        return self._redis

    def _key(self, patient_id: str) -> str:
        return f"patient_context:{patient_id}"

    async def get_patient_context(self, patient_id: str) -> dict:
        """
        Load patient context. Returns empty context if first time.
        """
        data = await self._load(patient_id)
        if not data:
            data = {
                "patient_id": patient_id,
                "name": "Patient",
                "preferred_language": "en",
                "preferred_doctor": None,
                "past_appointments": [],
                "interaction_log": [],
                "last_seen": None,
            }
        return data

    async def update_patient_language(self, patient_id: str, language: str):
        """Update the patient's preferred language."""
        data = await self.get_patient_context(patient_id)
        data["preferred_language"] = language
        await self._save(patient_id, data)
        logger.info(f"Updated language for patient {patient_id}: {language}")

    async def log_interaction(
        self,
        patient_id: str,
        session_id: str,
        user_text: str,
        agent_response: str,
        language: str,
    ):
        """Log a conversation turn to the patient's persistent history."""
        data = await self.get_patient_context(patient_id)
        data.setdefault("interaction_log", []).append({
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "user": user_text[:200],          # truncate for storage
            "agent": agent_response[:200],
            "language": language,
        })
        # Keep only last N interactions
        data["interaction_log"] = data["interaction_log"][-MAX_INTERACTION_LOG:]
        data["last_seen"] = datetime.utcnow().isoformat()
        await self._save(patient_id, data)

    async def record_appointment(self, patient_id: str, appointment: dict):
        """Record a completed appointment booking to patient history."""
        data = await self.get_patient_context(patient_id)
        data.setdefault("past_appointments", []).append({
            "appointment_id": appointment.get("id"),
            "doctor": appointment.get("doctor_name"),
            "specialty": appointment.get("specialty"),
            "date": appointment.get("date"),
            "status": appointment.get("status", "confirmed"),
        })
        # Track preferred doctor
        if appointment.get("doctor_name"):
            data["preferred_doctor"] = appointment["doctor_name"]
        await self._save(patient_id, data)

    async def get_interaction_summary(self, patient_id: str, last_n: int = 5) -> str:
        """Return a concise text summary of recent interactions for prompt injection."""
        data = await self.get_patient_context(patient_id)
        log = data.get("interaction_log", [])[-last_n:]
        if not log:
            return "No previous interactions."
        lines = [
            f"[{entry['timestamp'][:10]}] Patient: {entry['user']} | Agent: {entry['agent']}"
            for entry in log
        ]
        return "\n".join(lines)

    async def _save(self, patient_id: str, data: dict):
        redis = await self._get_redis()
        if redis:
            await redis.setex(self._key(patient_id), PERSISTENT_TTL_SECONDS, json.dumps(data))
        else:
            self._memory[patient_id] = data

    async def _load(self, patient_id: str) -> Optional[dict]:
        redis = await self._get_redis()
        if redis:
            raw = await redis.get(self._key(patient_id))
            return json.loads(raw) if raw else None
        else:
            return self._memory.get(patient_id)
