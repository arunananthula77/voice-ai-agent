"""
Outbound Campaign REST API routes.
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.database import get_db, Campaign
from scheduler.campaign_runner import run_campaign

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    campaign_type: str          # reminder / followup / vaccination
    patient_ids: List[str]
    scheduled_at: str           # ISO datetime string


@router.post("/")
async def create_campaign(
    req: CampaignCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    campaign = Campaign(
        id=str(uuid.uuid4()),
        name=req.name,
        campaign_type=req.campaign_type,
        patient_ids=req.patient_ids,
        scheduled_at=datetime.fromisoformat(req.scheduled_at),
        status="pending"
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    # Fire-and-forget background runner
    background_tasks.add_task(run_campaign, campaign.id)
    return {"success": True, "campaign_id": campaign.id, "status": "pending"}


@router.get("/")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign))
    campaigns = result.scalars().all()
    return [{"id": c.id, "name": c.name, "type": c.campaign_type,
             "status": c.status, "scheduled_at": str(c.scheduled_at)} for c in campaigns]


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalars().first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return {"id": campaign.id, "name": campaign.name, "type": campaign.campaign_type,
            "patient_ids": campaign.patient_ids, "status": campaign.status,
            "scheduled_at": str(campaign.scheduled_at)}
