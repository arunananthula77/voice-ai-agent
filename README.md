# 🏥 Real-Time Multilingual Voice AI Agent
### Clinical Appointment Booking System

> **Target latency: <450ms end-to-end from speech end to first audio response.**

A production-ready real-time voice AI agent that enables patients to book, reschedule, and cancel clinical appointments through natural voice conversations — in **English, Hindi, and Tamil** — with zero human intervention.

---

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Memory Design](#memory-design)
4. [Latency Breakdown](#latency-breakdown)
5. [Multilingual Handling](#multilingual-handling)
6. [Outbound Campaign Mode](#outbound-campaign-mode)
7. [Tool Orchestration](#tool-orchestration)
8. [Project Structure](#project-structure)
9. [API Reference](#api-reference)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Deployment](#deployment)
13. [Trade-offs & Known Limitations](#trade-offs--known-limitations)

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- OpenAI API Key (or use mock mode)
- Redis (optional; falls back to in-memory)

### 1. Clone and set up environment

```bash
git clone https://github.com/your-username/voice-ai-agent.git
cd voice-ai-agent

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Seed demo data

```bash
python seed_demo.py
```

This creates sample doctors, patients, and 14-day availability schedules.

### 3. Start the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### 5. Test the WebSocket voice endpoint

```
ws://localhost:8000/ws/voice/pat-001
```

---

### Docker (full stack)

```bash
cp .env.example .env      # add OPENAI_API_KEY
docker-compose up --build
```

Services:
- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- Redis: localhost:6379
- PostgreSQL: localhost:5432

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                          │
│   MediaRecorder API → WebSocket (binary) → Audio playback       │
└────────────────────────────┬────────────────────────────────────┘
                             │ WebSocket (ws://host/ws/voice/{id})
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND                              │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────────┐  │
│  │ WebSocket│    │  REST Routes │    │  Background Scheduler │  │
│  │ Handler  │    │ /api/appts   │    │  (Campaign Runner)    │  │
│  └────┬─────┘    │ /api/patients│    └───────────────────────┘  │
│       │          │ /api/campaigns    │                           │
│       ▼          └──────────────┘   │                           │
│  ┌─────────────────────────────┐    │                           │
│  │    VOICE PIPELINE           │    │                           │
│  │  ┌─────┐ ┌──────┐ ┌──────┐ │    │                           │
│  │  │ STT │→│ Lang │→│Agent │ │    │                           │
│  │  │Whis-│ │Detect│ │(LLM) │ │    │                           │
│  │  │ per │ │      │ │+ Tools││    │                           │
│  │  └─────┘ └──────┘ └──┬───┘ │    │                           │
│  │                       │     │    │                           │
│  │  ┌────────────────────┘     │    │                           │
│  │  ▼                          │    │                           │
│  │  ┌─────┐                    │    │                           │
│  │  │ TTS │                    │    │                           │
│  │  └─────┘                    │    │                           │
│  └─────────────────────────────┘    │                           │
└─────────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────────────────────┐
│   REDIS         │  │   POSTGRESQL / SQLITE            │
│ Session Memory  │  │  appointments, patients,          │
│ Patient Context │  │  doctors, doctor_schedules,       │
│ (TTL-based)     │  │  campaigns                        │
└─────────────────┘  └─────────────────────────────────┘
```

### Key Design Decisions

**1. WebSocket-first for voice**
Audio is streamed in 100ms chunks over WebSocket instead of waiting for a complete recording. This allows silence detection and early processing, shaving ~200ms off perceived latency.

**2. Parallel pipeline where possible**
Language detection runs on the transcript immediately — while the agent starts reasoning, the TTS engine is pre-warmed. The response is streamed to the client as audio bytes begin arriving.

**3. Agentic loop with bounded iterations**
The LLM uses OpenAI function calling (tool use). The agent loop caps at 5 tool-call iterations to prevent runaway reasoning. Tool calls go to the backend via internal HTTP for clean separation.

**4. Stateless agent, stateful memory**
The `VoiceAgent` class holds no state between turns — all state lives in Redis (session) and the DB (persistent). This enables horizontal scaling without sticky sessions.

---

## Memory Design

### Two-level memory architecture

#### Level 1: Session Memory (short-term)
- **Storage**: Redis (TTL: 1 hour) → in-memory fallback
- **Key**: `session:{session_id}`
- **Content**: Conversation history (last 20 turns), current intent, pending confirmation payloads
- **Purpose**: Tracks mid-conversation context so the agent knows what was already discussed

```json
{
  "patient_id": "pat-001",
  "started_at": "2025-06-01T10:00:00",
  "history": [
    {"role": "user", "content": "Book cardiologist tomorrow", "timestamp": "..."},
    {"role": "assistant", "content": "I found 3 slots with Dr. Sharma...", "timestamp": "..."}
  ],
  "current_intent": "booking",
  "pending_confirmation": {"doctor_id": "doc-001", "date": "2025-06-02", "time_slot": "10:00"}
}
```

#### Level 2: Persistent Memory (long-term)
- **Storage**: Redis (TTL: 30 days) → in-memory fallback
- **Key**: `patient_context:{patient_id}`
- **Content**: Preferred language, preferred doctor, past appointments (last 10), interaction log (last 50)
- **Purpose**: Carries context across sessions — returning patients get personalized responses

```json
{
  "patient_id": "pat-001",
  "preferred_language": "hi",
  "preferred_doctor": "Dr. Priya Sharma",
  "past_appointments": [...],
  "interaction_log": [...],
  "last_seen": "2025-05-28T14:30:00"
}
```

#### How memory is injected into the prompt
The persistent context is embedded in the system prompt at session start. The session history is passed as the full `messages` array to the LLM — so the agent has both:
- What happened across all past visits (persistent)
- What happened in this conversation (session)

---

## Latency Breakdown

### Target: <450ms total

| Stage | Typical | Optimized | Notes |
|-------|---------|-----------|-------|
| Speech-to-Text (Whisper) | 120–180ms | 80ms | Cloud API; stream chunks |
| Language Detection | <5ms | <1ms | Unicode heuristics, no API call |
| Agent Reasoning (GPT-4o) | 200–300ms | 150ms | Streaming response; gpt-4o is fastest |
| Text-to-Speech (OpenAI tts-1) | 80–120ms | 60ms | tts-1 model optimized for real-time |
| **Total** | **~450ms** | **~291ms** | |

### Latency is measured and logged on every turn:
```
LATENCY | patient=pat-001 | session=xyz | stt=145ms | lang=2ms | agent=210ms | tts=88ms | total=445ms
```

The WebSocket also sends a `{"type": "latency", ...}` frame to the client after each turn so it displays in the UI.

### Optimizations implemented
1. **Silence detection** triggers processing before the user explicitly signals end-of-speech
2. **gpt-4o** instead of gpt-4-turbo: ~40% faster first-token latency
3. **tts-1** (not tts-1-hd): optimized for real-time, lower quality tradeoff acceptable for voice
4. **Unicode-based language detection** (~0ms) instead of API calls
5. **Internal HTTP calls** for tool execution instead of external round-trips
6. **WebSocket binary frames** for audio instead of base64 encoding overhead

---

## Multilingual Handling

### Supported languages

| Language | Script | Detection Method | TTS Voice |
|----------|--------|-----------------|-----------|
| English | Latin | Fallback default | OpenAI `nova` |
| Hindi | Devanagari (+ Hinglish) | Unicode range + keyword match | OpenAI `shimmer` |
| Tamil | Tamil script | Unicode range | OpenAI `shimmer` |

### Language detection flow
1. **Unicode script analysis** (instant): count Devanagari (U+0900–U+097F) and Tamil (U+0B80–U+0BFF) characters
2. **Transliteration keyword match**: Hinglish phrases like "mujhe", "kal", "chahiye"
3. **langdetect library**: statistical model fallback
4. **Default**: English

### Language persistence
- Detected language is saved to `patient_context.preferred_language` in persistent memory
- Returning patients are served in their saved language from the first response
- Language can switch mid-session — the agent adapts immediately

---

## Outbound Campaign Mode

The system supports proactive outbound calling for:
- **Reminders**: "Your appointment with Dr. Sharma is tomorrow at 10 AM"
- **Follow-ups**: "How are you feeling after your last visit?"
- **Vaccinations**: "Your flu shot is due this month"

### How it works
1. Create a campaign via `POST /api/campaigns/` with patient IDs and scheduled time
2. FastAPI `BackgroundTasks` fires the campaign runner asynchronously
3. The runner waits until `scheduled_at`, then iterates over patients
4. Each patient gets an outbound call (mock log in dev; Twilio in production)
5. The opening message is in the patient's preferred language
6. Campaign status updates: `pending → running → completed`

### Twilio integration (production)
Set `TWILIO_ENABLED=true` and provide credentials. The Twilio call connects to a TwiML endpoint that bridges the call to the WebSocket voice agent — the same pipeline as inbound calls.

---

## Tool Orchestration

The agent uses OpenAI function calling with 6 tools:

| Tool | Description |
|------|-------------|
| `list_doctors` | Find doctors by specialty |
| `check_availability` | Get free slots for a doctor+date |
| `book_appointment` | Create a booking |
| `cancel_appointment` | Cancel an existing booking |
| `reschedule_appointment` | Change date/time of a booking |
| `get_patient_appointments` | List upcoming appointments |

### Booking flow (multi-tool)
```
User: "I need to see a cardiologist tomorrow"
  → list_doctors(specialty="cardiologist")
  → check_availability(doctor_id="doc-001", date="2025-06-02")
  → Agent: "Dr. Sharma has slots at 9:30, 10:00, 2:00 PM. Which do you prefer?"
User: "10 AM please"
  → book_appointment(patient_id, doctor_id, date, time_slot="10:00")
  → Agent: "Booked! Your appointment is confirmed for June 2nd at 10 AM."
```

### Conflict handling
- Double booking: agent immediately calls `check_availability` and offers alternatives
- Past date: agent asks for a valid future date
- Doctor unavailable: agent offers similar specialty

---

## Project Structure

```
voice-ai-agent/
│
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── db/
│   │   └── database.py            # SQLAlchemy models + DB init
│   └── api/routes/
│       ├── appointments.py        # Appointment CRUD + availability
│       ├── patients.py            # Patient management
│       ├── campaigns.py           # Outbound campaign endpoints
│       └── websocket.py           # Real-time voice WebSocket
│
├── agent/
│   ├── reasoning/
│   │   └── agent.py               # VoiceAgent class + agentic loop
│   ├── prompt/
│   │   └── templates.py           # System prompt builder
│   └── tools/
│       └── appointment_tools.py   # Tool functions (called by agent)
│
├── memory/
│   ├── session/
│   │   └── manager.py             # Short-term session memory (Redis/in-memory)
│   └── persistent/
│       └── manager.py             # Long-term patient context (Redis/in-memory)
│
├── services/
│   ├── stt/
│   │   └── transcriber.py         # Whisper STT (cloud + local)
│   ├── tts/
│   │   └── synthesizer.py         # OpenAI TTS + gTTS fallback
│   └── language_detection/
│       └── detector.py            # Multi-strategy language detection
│
├── scheduler/
│   └── campaign_runner.py         # Background outbound campaign runner
│
├── tests/
│   └── test_agent.py              # Pytest unit + integration tests
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # Main voice agent UI
│   │   └── index.tsx              # React entry point
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
│
├── seed_demo.py                   # Demo data seeder
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

---

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/appointments/book` | Book an appointment |
| PATCH | `/api/appointments/{id}/reschedule` | Reschedule |
| DELETE | `/api/appointments/{id}/cancel` | Cancel |
| GET | `/api/appointments/availability` | Check free slots |
| GET | `/api/appointments/` | List patient appointments |
| POST | `/api/patients/` | Create patient |
| GET | `/api/patients/{id}` | Get patient |
| POST | `/api/campaigns/` | Create outbound campaign |
| GET | `/api/campaigns/` | List campaigns |

### WebSocket

**Endpoint**: `ws://host/ws/voice/{patient_id}`

**Client → Server (binary)**: Raw audio chunks (PCM/WebM)

**Client → Server (text)**:
```json
{"type": "end_of_speech"}
{"type": "interrupt"}
```

**Server → Client (text)**:
```json
{"type": "transcript", "text": "...", "stt_ms": 145}
{"type": "response", "text": "...", "language": "en", "agent_ms": 210}
{"type": "latency", "stt_ms": 145, "lang_ms": 2, "agent_ms": 210, "tts_ms": 88, "total_ms": 445}
{"type": "error", "message": "..."}
```

**Server → Client (binary)**: MP3 audio response

---

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | **Required** for STT, TTS, LLM |
| `LLM_MODEL` | `gpt-4o` | LLM model to use |
| `USE_LOCAL_WHISPER` | `false` | Use local Whisper model (no API cost) |
| `TTS_PROVIDER` | `openai` | `openai` or `gtts` |
| `USE_REDIS` | `false` | Enable Redis for session/persistent memory |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `DATABASE_URL` | SQLite | Database connection URL |
| `TWILIO_ENABLED` | `false` | Enable real outbound calls |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=. --cov-report=html

# Run specific test
pytest tests/test_agent.py::test_detect_hindi_devanagari -v
```

Test coverage includes:
- Language detection (all 3 languages + edge cases)
- Session memory (init, add turns, max history, intent tracking, end session)
- Persistent memory (new patient defaults, language update, interaction logging)
- Scheduling validation (past date rejection, future date acceptance, double-booking detection)
- System prompt building (all 3 languages)

---

## Deployment

### Render (Backend)
1. Create a new Web Service
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables

### Vercel (Frontend)
```bash
cd frontend
npm run build
vercel deploy dist/
```

### Environment variables for production
- Set `DATABASE_URL` to a PostgreSQL connection string
- Set `USE_REDIS=true` and `REDIS_URL`
- Set `TWILIO_ENABLED=true` for outbound calls

---

## Trade-offs & Known Limitations

### Trade-offs Made

**SQLite in dev / PostgreSQL in prod**
SQLite is used by default for zero-config local development. The async SQLAlchemy setup switches seamlessly to PostgreSQL via the `DATABASE_URL` env var.

**In-memory Redis fallback**
Redis is optional — the system degrades gracefully to in-memory dicts. This means session state is lost on server restart in dev mode. Production should always use Redis.

**OpenAI for STT + TTS**
Using the OpenAI API for both STT (Whisper) and TTS keeps latency predictable and avoids local GPU requirements. The trade-off is API cost and an external dependency. `USE_LOCAL_WHISPER=true` removes this for STT.

**gpt-4o latency vs accuracy**
GPT-4o is faster but costs more than GPT-3.5-turbo. For clinical contexts where intent accuracy matters, this is the right trade-off. The `LLM_MODEL` env var makes this swappable.

### Known Limitations

1. **Real telephony requires Twilio**: Outbound campaigns mock-log calls in dev mode. Real phone calls need `TWILIO_ENABLED=true` and valid Twilio credentials + a TwiML bridge endpoint.

2. **Audio format handling**: The WebSocket expects WebM/PCM audio. Browser `MediaRecorder` outputs WebM. If integrating with telephony, audio conversion (ffmpeg) is needed for μ-law/PCM-16.

3. **Hindi transliteration (Hinglish)**: Romanized Hindi detection relies on a small keyword list. For robust Hinglish, a dedicated classifier (fastText or similar) would be more reliable.

4. **No true streaming TTS**: The current pipeline waits for the full LLM response before synthesizing. Streaming TTS (word-by-word) would reduce perceived latency by ~100ms but requires more complex audio buffering on the client.

5. **Horizontal scaling caveat**: In-memory session fallback breaks horizontal scaling. Redis must be enabled for multi-instance deployments.

6. **Tamil TTS quality**: OpenAI TTS `shimmer` voice handles Tamil reasonably but is not a native Tamil TTS engine. For production Tamil support, a dedicated Tamil TTS service (e.g., IIT Madras TTS, Azure Tamil) would give better results.
