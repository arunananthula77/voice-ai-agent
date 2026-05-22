"""
Campaign Runner — Background job for outbound call campaigns.

Simulates outbound calling by initiating agent conversations
for each patient in a campaign (reminder / follow-up / vaccination).

In production this integrates with Twilio Programmable Voice
or a similar telephony API to actually dial patients.
"""

import os
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

TWILIO_ENABLED = os.getenv("TWILIO_ENABLED", "false").lower() == "true"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
BACKEND_WEBSOCKET_URL = os.getenv("BACKEND_WEBSOCKET_URL", "wss://your-domain.com")


async def run_campaign(campaign_id: str):
    """
    Background task: execute an outbound campaign.
    
    For each patient in the campaign:
    1. Fetch patient phone number
    2. Initiate outbound call (via Twilio or mock)
    3. Log result
    """
    # Lazy import to avoid circular dependency
    from backend.db.database import AsyncSessionLocal, Campaign, Patient
    from sqlalchemy import select

    logger.info(f"Campaign runner started: {campaign_id}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalars().first()
        if not campaign:
            logger.error(f"Campaign not found: {campaign_id}")
            return

        # Wait until scheduled time
        now = datetime.utcnow()
        if campaign.scheduled_at > now:
            delay = (campaign.scheduled_at - now).total_seconds()
            logger.info(f"Campaign {campaign_id} waiting {delay:.0f}s until scheduled time")
            await asyncio.sleep(min(delay, 3600))  # max 1 hour wait per task

        campaign.status = "running"
        await db.commit()

        patient_ids = campaign.patient_ids
        logger.info(f"Campaign {campaign_id}: contacting {len(patient_ids)} patients")

        for patient_id in patient_ids:
            patient_result = await db.execute(
                select(Patient).where(Patient.id == patient_id)
            )
            patient = patient_result.scalars().first()
            if not patient:
                logger.warning(f"Patient {patient_id} not found, skipping")
                continue

            await _initiate_outbound_call(
                patient=patient,
                campaign=campaign,
            )
            await asyncio.sleep(2)  # Rate limit between calls

        campaign.status = "completed"
        await db.commit()
        logger.info(f"Campaign {campaign_id} completed.")


async def _initiate_outbound_call(patient, campaign) -> dict:
    """
    Initiate a single outbound call to a patient.
    
    In dev mode: logs the call details and simulates a response.
    In prod mode: uses Twilio to dial the patient and connect to WS agent.
    """
    language = patient.preferred_language or "en"

    opening_messages = {
        "reminder": {
            "en": f"Hello {patient.name}, this is a reminder about your upcoming appointment.",
            "hi": f"नमस्ते {patient.name}, आपकी आने वाली अपॉइंटमेंट की याद दिलाने के लिए कॉल किया है।",
            "ta": f"வணக்கம் {patient.name}, உங்கள் வரும் சந்திப்பை நினைவூட்ட அழைக்கிறோம்.",
        },
        "followup": {
            "en": f"Hello {patient.name}, this is a follow-up call to check on your recovery.",
            "hi": f"नमस्ते {patient.name}, आपके स्वास्थ्य की जानकारी लेने के लिए कॉल किया है।",
            "ta": f"வணக்கம் {patient.name}, உங்கள் உடல்நலம் பற்றி விசாரிக்க அழைக்கிறோம்.",
        },
        "vaccination": {
            "en": f"Hello {patient.name}, this is a reminder about your vaccination due date.",
            "hi": f"नमस्ते {patient.name}, आपके टीकाकरण की तारीख के बारे में याद दिलाने के लिए कॉल किया है।",
            "ta": f"வணக்கம் {patient.name}, உங்கள் தடுப்பூசி தேதியை நினைவூட்ட அழைக்கிறோம்.",
        }
    }

    message = opening_messages.get(
        campaign.campaign_type, opening_messages["reminder"]
    ).get(language, opening_messages["reminder"]["en"])

    if TWILIO_ENABLED:
        return await _twilio_call(patient.phone, patient.id, message)
    else:
        # Dev mode — log and mock
        logger.info(
            f"[MOCK OUTBOUND CALL] → {patient.phone} ({patient.name}) | "
            f"Campaign: {campaign.name} | Lang: {language}\n"
            f"Opening: {message}"
        )
        return {"status": "mock_initiated", "patient_id": patient.id}


async def _twilio_call(phone: str, patient_id: str, opening_message: str) -> dict:
    """Initiate a real Twilio call that connects to the voice WebSocket agent."""
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        # TwiML URL that bridges Twilio call to our WebSocket voice agent
        twiml_url = f"{BACKEND_WEBSOCKET_URL}/api/campaigns/twiml/{patient_id}"

        call = client.calls.create(
            to=phone,
            from_=TWILIO_FROM_NUMBER,
            url=twiml_url,
            method="POST"
        )
        logger.info(f"Twilio call initiated: {call.sid} → {phone}")
        return {"status": "initiated", "call_sid": call.sid}

    except ImportError:
        logger.error("twilio not installed. Run: pip install twilio")
        return {"status": "error", "reason": "twilio_not_installed"}
    except Exception as e:
        logger.error(f"Twilio call failed for {phone}: {e}")
        return {"status": "error", "reason": str(e)}
