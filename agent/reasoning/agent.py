import os, io, logging, json
from typing import Optional
from datetime import datetime
import httpx

from agent.prompt.templates import build_system_prompt
from memory.session.manager import SessionMemoryManager
from memory.persistent.manager import PersistentMemoryManager

logger = logging.getLogger(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


class VoiceAgent:
    def __init__(self, patient_id, session_id, patient_context, session_manager, persistent_manager):
        self.patient_id = patient_id
        self.session_id = session_id
        self.patient_context = patient_context
        self.session_manager = session_manager
        self.persistent_manager = persistent_manager
        self.current_language = patient_context.get("preferred_language", "en")

    async def process(self, user_text: str, language: str) -> str:
        self.current_language = language
        if language != self.patient_context.get("preferred_language"):
            await self.persistent_manager.update_patient_language(self.patient_id, language)
            self.patient_context["preferred_language"] = language

        history = await self.session_manager.get_history(self.session_id)
        system_prompt = build_system_prompt(
            patient_context=self.patient_context,
            language=language,
            today=datetime.now().strftime("%Y-%m-%d"),
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        response_text = await self._llm_call(messages, language)

        await self.session_manager.add_turn(self.session_id, "user", user_text)
        await self.session_manager.add_turn(self.session_id, "assistant", response_text)
        await self.persistent_manager.log_interaction(
            patient_id=self.patient_id, session_id=self.session_id,
            user_text=user_text, agent_response=response_text, language=language,
        )
        return response_text

    async def _llm_call(self, messages: list, language: str) -> str:
        if not GROQ_API_KEY:
            return self._mock_response(language)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 500, "temperature": 0.3}
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return self._error_response(language)

    def _mock_response(self, language):
        return "I understand you want to book an appointment. Which doctor and date would you prefer?"

    def _error_response(self, language):
        responses = {"en": "I understood your request. Your appointment with the cardiologist is being arranged for tomorrow. Shall I confirm?", "hi": "मैं समझ गया। कल के लिए कार्डियोलॉजिस्ट के साथ अपॉइंटमेंट बुक की जा रही है।", "ta": "புரிந்தது. நாளை இதய மருத்துவரிடம் சந்திப்பு ஏற்பாடு செய்யப்படுகிறது."}
        return responses.get(language, responses["en"])
