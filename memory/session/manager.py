"""
Session Memory Manager.

Stores per-session conversation history and current intent state.
Primary: Redis (with TTL)
Fallback: In-memory dict (for development without Redis)
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))  # 1 hour
USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"


class SessionMemoryManager:
    """
    Manages short-term, in-session conversation memory.
    
    Storage schema (Redis key: session:{session_id}):
    {
        "patient_id": str,
        "started_at": ISO datetime,
        "history": [
            {"role": "user"|"assistant", "content": str, "timestamp": str},
            ...
        ],
        "current_intent": str | null,
        "pending_confirmation": dict | null
    }
    """

    def __init__(self):
        self._redis = None
        self._memory: Dict[str, dict] = {}  # in-memory fallback

    async def _get_redis(self):
        if not USE_REDIS:
            return None
        if self._redis is None:
            try:
                import aioredis
                self._redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
            except ImportError:
                logger.warning("aioredis not installed. Using in-memory session storage.")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using in-memory fallback.")
        return self._redis

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def init_session(self, session_id: str, patient_id: str):
        """Initialize a new session."""
        data = {
            "patient_id": patient_id,
            "started_at": datetime.utcnow().isoformat(),
            "history": [],
            "current_intent": None,
            "pending_confirmation": None,
        }
        await self._save(session_id, data)
        logger.info(f"Session initialized: {session_id} for patient {patient_id}")

    async def add_turn(self, session_id: str, role: str, content: str):
        """Append a conversation turn to session history."""
        data = await self._load(session_id)
        if not data:
            return
        data["history"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        # Keep last 20 turns to stay within context window
        data["history"] = data["history"][-20:]
        await self._save(session_id, data)

    async def get_history(self, session_id: str) -> List[Dict]:
        """Return conversation history in OpenAI messages format."""
        data = await self._load(session_id)
        if not data:
            return []
        return [
            {"role": turn["role"], "content": turn["content"]}
            for turn in data.get("history", [])
        ]

    async def set_intent(self, session_id: str, intent: Optional[str]):
        """Update the current detected intent."""
        data = await self._load(session_id)
        if data:
            data["current_intent"] = intent
            await self._save(session_id, data)

    async def get_intent(self, session_id: str) -> Optional[str]:
        data = await self._load(session_id)
        return data.get("current_intent") if data else None

    async def set_pending_confirmation(self, session_id: str, payload: Optional[dict]):
        """Store data awaiting user confirmation (e.g., booking details)."""
        data = await self._load(session_id)
        if data:
            data["pending_confirmation"] = payload
            await self._save(session_id, data)

    async def get_pending_confirmation(self, session_id: str) -> Optional[dict]:
        data = await self._load(session_id)
        return data.get("pending_confirmation") if data else None

    async def end_session(self, session_id: str):
        """Clean up session on disconnect."""
        redis = await self._get_redis()
        if redis:
            await redis.delete(self._key(session_id))
        else:
            self._memory.pop(session_id, None)
        logger.info(f"Session ended: {session_id}")

    async def _save(self, session_id: str, data: dict):
        redis = await self._get_redis()
        if redis:
            await redis.setex(self._key(session_id), SESSION_TTL_SECONDS, json.dumps(data))
        else:
            self._memory[session_id] = data

    async def _load(self, session_id: str) -> Optional[dict]:
        redis = await self._get_redis()
        if redis:
            raw = await redis.get(self._key(session_id))
            return json.loads(raw) if raw else None
        else:
            return self._memory.get(session_id)
