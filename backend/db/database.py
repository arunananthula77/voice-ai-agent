"""
Database configuration using SQLAlchemy (async) + SQLite (dev) / PostgreSQL (prod).
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./voice_agent.db")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True)           # UUID
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    preferred_language = Column(String, default="en")  # en / hi / ta
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default={})


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    specialty = Column(String, nullable=False)
    available = Column(Boolean, default=True)


class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=False)
    date = Column(String, nullable=False)           # YYYY-MM-DD
    available_slots = Column(JSON, default=[])      # list of "HH:MM" strings


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(String, primary_key=True)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=False)
    date = Column(String, nullable=False)           # YYYY-MM-DD
    time_slot = Column(String, nullable=False)      # HH:MM
    status = Column(String, default="confirmed")    # confirmed / cancelled / completed
    language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, default="")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    campaign_type = Column(String, nullable=False)  # reminder / followup / vaccination
    patient_ids = Column(JSON, default=[])
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String, default="pending")      # pending / running / completed
    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
