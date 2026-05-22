"""
Language Detection Service.

Detects English, Hindi, and Tamil from transcribed text.
Uses multiple strategies: character-set heuristics (fast, zero-latency),
then langdetect library fallback, then LLM as last resort.
"""

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

LanguageCode = Literal["en", "hi", "ta"]


async def detect_language(text: str) -> LanguageCode:
    """
    Detect language of text. Returns "en", "hi", or "ta".
    
    Strategy (in order, stops at first confident result):
    1. Unicode script range detection (instant, very reliable)
    2. langdetect library
    3. Default to "en"
    """
    if not text or not text.strip():
        return "en"

    # ── Strategy 1: Unicode Script Detection ─────────────────────────────
    # Devanagari script → Hindi (U+0900–U+097F)
    devanagari_chars = len(re.findall(r'[\u0900-\u097F]', text))
    # Tamil script → Tamil (U+0B80–U+0BFF)
    tamil_chars = len(re.findall(r'[\u0B80-\u0BFF]', text))
    # ASCII/Latin characters
    latin_chars = len(re.findall(r'[a-zA-Z]', text))

    total = max(1, len(text.strip()))
    if devanagari_chars / total > 0.15:
        return "hi"
    if tamil_chars / total > 0.15:
        return "ta"

    # Transliterated Hindi keywords check (Hinglish)
    hindi_keywords = ["mujhe", "doctor", "kal", "aaj", "chahiye",
                      "appointment", "batao", "kab", "kahan"]
    lower = text.lower()
    if sum(1 for kw in hindi_keywords if kw in lower) >= 2:
        return "hi"

    # Transliterated Tamil keywords
    tamil_keywords = ["naan", "naalai", "doctor", "appointment",
                      "vendumm", "paarkkanum", "eppodi"]
    if sum(1 for kw in tamil_keywords if kw in lower) >= 2:
        return "ta"

    # ── Strategy 2: langdetect ────────────────────────────────────────────
    try:
        from langdetect import detect
        lang = detect(text)
        if lang == "hi":
            return "hi"
        elif lang == "ta":
            return "ta"
        else:
            return "en"
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"langdetect failed: {e}")

    return "en"


def get_system_language_instruction(language: LanguageCode) -> str:
    """Return language instruction to embed in LLM system prompt."""
    instructions = {
        "en": "Always respond in English.",
        "hi": "Always respond in Hindi (Devanagari script). Use clear, simple Hindi.",
        "ta": "Always respond in Tamil script. Use clear, simple Tamil.",
    }
    return instructions.get(language, instructions["en"])
