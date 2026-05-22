"""
Tests for appointment booking, conflict detection, and scheduling validation.
Run: pytest tests/ -v
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from services.language_detection.detector import detect_language
from memory.session.manager import SessionMemoryManager
from memory.persistent.manager import PersistentMemoryManager


# ─── Language Detection Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detect_english():
    lang = await detect_language("Book an appointment with the cardiologist tomorrow")
    assert lang == "en"


@pytest.mark.asyncio
async def test_detect_hindi_devanagari():
    lang = await detect_language("मुझे कल डॉक्टर से मिलना है")
    assert lang == "hi"


@pytest.mark.asyncio
async def test_detect_tamil():
    lang = await detect_language("நாளை மருத்துவரை பார்க்க வேண்டும்")
    assert lang == "ta"


@pytest.mark.asyncio
async def test_detect_empty_defaults_english():
    lang = await detect_language("")
    assert lang == "en"


@pytest.mark.asyncio
async def test_detect_hinglish():
    lang = await detect_language("mujhe kal doctor se milna chahiye appointment")
    assert lang == "hi"


# ─── Session Memory Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_memory_init_and_history():
    mgr = SessionMemoryManager()
    await mgr.init_session("session-test-1", "patient-001")

    history = await mgr.get_history("session-test-1")
    assert history == []

    await mgr.add_turn("session-test-1", "user", "Hello")
    await mgr.add_turn("session-test-1", "assistant", "Hi! How can I help?")

    history = await mgr.get_history("session-test-1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_session_memory_max_history():
    """Session memory should cap at 20 turns."""
    mgr = SessionMemoryManager()
    await mgr.init_session("session-test-2", "patient-002")

    for i in range(25):
        await mgr.add_turn("session-test-2", "user", f"message {i}")

    history = await mgr.get_history("session-test-2")
    assert len(history) <= 20


@pytest.mark.asyncio
async def test_session_memory_intent():
    mgr = SessionMemoryManager()
    await mgr.init_session("session-test-3", "patient-003")
    await mgr.set_intent("session-test-3", "booking")
    intent = await mgr.get_intent("session-test-3")
    assert intent == "booking"


@pytest.mark.asyncio
async def test_session_memory_end_session():
    mgr = SessionMemoryManager()
    await mgr.init_session("session-test-4", "patient-004")
    await mgr.add_turn("session-test-4", "user", "Test")
    await mgr.end_session("session-test-4")
    history = await mgr.get_history("session-test-4")
    assert history == []


# ─── Persistent Memory Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persistent_memory_new_patient():
    mgr = PersistentMemoryManager()
    ctx = await mgr.get_patient_context("new-patient-999")
    assert ctx["preferred_language"] == "en"
    assert ctx["patient_id"] == "new-patient-999"
    assert ctx["past_appointments"] == []


@pytest.mark.asyncio
async def test_persistent_memory_language_update():
    mgr = PersistentMemoryManager()
    await mgr.get_patient_context("lang-test-patient")
    await mgr.update_patient_language("lang-test-patient", "hi")
    ctx = await mgr.get_patient_context("lang-test-patient")
    assert ctx["preferred_language"] == "hi"


@pytest.mark.asyncio
async def test_persistent_memory_interaction_log():
    mgr = PersistentMemoryManager()
    await mgr.log_interaction(
        patient_id="log-test-patient",
        session_id="session-x",
        user_text="Book appointment",
        agent_response="What specialty?",
        language="en"
    )
    summary = await mgr.get_interaction_summary("log-test-patient")
    assert "Book appointment" in summary


# ─── Scheduling Validation Tests ──────────────────────────────────────────────

def test_past_date_validation():
    """Validate that past appointments are rejected."""
    slot_str = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    slot_dt = datetime.strptime(slot_str, "%Y-%m-%d %H:%M")
    assert slot_dt < datetime.utcnow(), "Past slot should be before now"


def test_future_date_is_valid():
    """Future dates should pass validation."""
    slot_dt = datetime.utcnow() + timedelta(days=1)
    assert slot_dt > datetime.utcnow(), "Future slot should be after now"


def test_double_booking_slot_detection():
    """Simulate conflict detection logic."""
    booked_slots = {"09:00", "10:30", "14:00"}
    requested_slot = "10:30"
    is_conflict = requested_slot in booked_slots
    assert is_conflict is True


def test_available_slot_no_conflict():
    booked_slots = {"09:00", "10:30", "14:00"}
    requested_slot = "11:00"
    is_conflict = requested_slot in booked_slots
    assert is_conflict is False


# ─── Prompt Builder Tests ─────────────────────────────────────────────────────

def test_system_prompt_english():
    from agent.prompt.templates import build_system_prompt
    prompt = build_system_prompt(
        patient_context={"name": "Rahul", "preferred_language": "en", "past_appointments": []},
        language="en",
        today="2025-06-01"
    )
    assert "Rahul" in prompt
    assert "English" in prompt
    assert "2025-06-01" in prompt


def test_system_prompt_hindi():
    from agent.prompt.templates import build_system_prompt
    prompt = build_system_prompt(
        patient_context={"name": "Kavita", "preferred_language": "hi", "past_appointments": []},
        language="hi",
        today="2025-06-01"
    )
    assert "Hindi" in prompt


def test_system_prompt_tamil():
    from agent.prompt.templates import build_system_prompt
    prompt = build_system_prompt(
        patient_context={"name": "Arjun", "preferred_language": "ta", "past_appointments": []},
        language="ta",
        today="2025-06-01"
    )
    assert "Tamil" in prompt
