"""
Real-Time Multilingual Voice AI Agent
Clinical Appointment Booking System
Main FastAPI application entry point
"""

import time
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import appointments, patients, campaigns, websocket
from backend.db.database import init_db
from memory.session.manager import SessionMemoryManager
from memory.persistent.manager import PersistentMemoryManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""
    logger.info("Starting Voice AI Agent...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("Shutting down Voice AI Agent...")


app = FastAPI(
    title="Real-Time Multilingual Voice AI Agent",
    description="Clinical Appointment Booking System with multilingual support",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST routers
app.include_router(appointments.router, prefix="/api/appointments", tags=["Appointments"])
app.include_router(patients.router, prefix="/api/patients", tags=["Patients"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket Voice"])


@app.get("/health")
async def health_check():
    return {"status": "running", "service": "Voice AI Agent", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
