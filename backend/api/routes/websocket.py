import time, json, logging, asyncio
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from services.stt.transcriber import transcribe_audio
from services.language_detection.detector import detect_language
from services.tts.synthesizer import synthesize_speech
from agent.reasoning.agent import VoiceAgent
from memory.session.manager import SessionMemoryManager
from memory.persistent.manager import PersistentMemoryManager

logger = logging.getLogger(__name__)
router = APIRouter()
session_manager = SessionMemoryManager()
persistent_manager = PersistentMemoryManager()

@router.websocket("/voice/{patient_id}")
async def voice_conversation(websocket: WebSocket, patient_id: str, session_id: Optional[str] = Query(default=None)):
    await websocket.accept()
    if not session_id:
        session_id = f"session_{patient_id}_{int(time.time())}"
    patient_context = await persistent_manager.get_patient_context(patient_id)
    await session_manager.init_session(session_id, patient_id)
    agent = VoiceAgent(patient_id=patient_id, session_id=session_id, patient_context=patient_context, session_manager=session_manager, persistent_manager=persistent_manager)
    audio_buffer = bytearray()
    last_audio_time = time.time()
    processing = False
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                if audio_buffer and not processing and (time.time() - last_audio_time) * 1000 > 700:
                    chunk = bytes(audio_buffer)
                    audio_buffer.clear()
                    processing = True
                    await _process_audio_turn(websocket, chunk, agent, patient_id, session_id)
                    processing = False
                continue
            if "bytes" in data:
                audio_buffer.extend(data["bytes"])
                last_audio_time = time.time()
            elif "text" in data:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "text_input" and not processing:
                        processing = True
                        await _process_text_turn(websocket, msg["text"], agent, patient_id, session_id)
                        processing = False
                    elif msg.get("type") == "end_of_speech" and audio_buffer and not processing:
                        chunk = bytes(audio_buffer)
                        audio_buffer.clear()
                        processing = True
                        await _process_audio_turn(websocket, chunk, agent, patient_id, session_id)
                        processing = False
                    elif msg.get("type") == "interrupt":
                        audio_buffer.clear()
                        processing = False
                        await websocket.send_text(json.dumps({"type": "interrupted"}))
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        await session_manager.end_session(session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except:
            pass

async def _process_text_turn(websocket, text, agent, patient_id, session_id):
    pipeline_start = time.perf_counter()
    await websocket.send_text(json.dumps({"type": "text_echo", "text": text}))
    t1 = time.perf_counter()
    language = await detect_language(text)
    lang_ms = round((time.perf_counter() - t1) * 1000, 2)
    t2 = time.perf_counter()
    response = await agent.process(text, language)
    agent_ms = round((time.perf_counter() - t2) * 1000, 2)
    await websocket.send_text(json.dumps({"type": "response", "text": response, "language": language, "agent_ms": agent_ms}))
    t3 = time.perf_counter()
    audio = await synthesize_speech(response, language)
    tts_ms = round((time.perf_counter() - t3) * 1000, 2)
    total_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
    await websocket.send_text(json.dumps({"type": "latency", "stt_ms": 0, "lang_ms": lang_ms, "agent_ms": agent_ms, "tts_ms": tts_ms, "total_ms": total_ms, "within_budget": total_ms < 2000}))
    if audio:
        await websocket.send_bytes(audio)

async def _process_audio_turn(websocket, audio_bytes, agent, patient_id, session_id):
    pipeline_start = time.perf_counter()
    t0 = time.perf_counter()
    transcript = await transcribe_audio(audio_bytes)
    stt_ms = round((time.perf_counter() - t0) * 1000, 2)
    if not transcript or not transcript.strip():
        await websocket.send_text(json.dumps({"type": "error", "message": "Could not transcribe. Please type instead."}))
        return
    await websocket.send_text(json.dumps({"type": "transcript", "text": transcript, "stt_ms": stt_ms}))
    t1 = time.perf_counter()
    language = await detect_language(transcript)
    lang_ms = round((time.perf_counter() - t1) * 1000, 2)
    t2 = time.perf_counter()
    response = await agent.process(transcript, language)
    agent_ms = round((time.perf_counter() - t2) * 1000, 2)
    await websocket.send_text(json.dumps({"type": "response", "text": response, "language": language, "agent_ms": agent_ms}))
    t3 = time.perf_counter()
    audio = await synthesize_speech(response, language)
    tts_ms = round((time.perf_counter() - t3) * 1000, 2)
    total_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
    logger.info(f"LATENCY | patient={patient_id} | stt={stt_ms}ms | lang={lang_ms}ms | agent={agent_ms}ms | tts={tts_ms}ms | total={total_ms}ms")
    await websocket.send_text(json.dumps({"type": "latency", "stt_ms": stt_ms, "lang_ms": lang_ms, "agent_ms": agent_ms, "tts_ms": tts_ms, "total_ms": total_ms, "within_budget": total_ms < 2000}))
    if audio:
        await websocket.send_bytes(audio)
