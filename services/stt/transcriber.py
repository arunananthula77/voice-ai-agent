import os, io, logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

async def transcribe_audio(audio_bytes: bytes, language: Optional[str] = None) -> str:
    if not audio_bytes or len(audio_bytes) < 500:
        return ""
    if GROQ_API_KEY:
        return await _transcribe_groq(audio_bytes)
    return ""

async def _transcribe_groq(audio_bytes: bytes) -> str:
    tried = [
        ("audio.webm", "audio/webm; codecs=opus"),
        ("audio.ogg", "audio/ogg"),
        ("audio.wav", "audio/wav"),
    ]
    async with httpx.AsyncClient(timeout=15.0) as client:
        for fname, mime in tried:
            try:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    files={"file": (fname, io.BytesIO(audio_bytes), mime)},
                    data={"model": "whisper-large-v3-turbo", "response_format": "json"}
                )
                if response.status_code == 200:
                    text = response.json().get("text", "").strip()
                    logger.info(f"STT success with {mime}: {text}")
                    return text
                else:
                    logger.warning(f"STT {mime} failed: {response.status_code} {response.text[:100]}")
            except Exception as e:
                logger.error(f"STT error {mime}: {e}")
    return ""
