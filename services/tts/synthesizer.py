import io, logging, asyncio
from typing import Optional

logger = logging.getLogger(__name__)

async def synthesize_speech(text: str, language: str = "en") -> Optional[bytes]:
    if not text:
        return None
    return await _gtts(text, language)

async def _gtts(text: str, language: str) -> Optional[bytes]:
    lang_map = {"en": "en", "hi": "hi", "ta": "ta"}
    def _run():
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang=lang_map.get(language, "en"), slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            return buf.getvalue()
        except Exception as e:
            logger.error(f"gTTS error: {e}")
            return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run)
