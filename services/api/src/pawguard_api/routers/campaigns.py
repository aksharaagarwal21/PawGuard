from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import text

from pawguard_api.contracts import (
    CampaignAreaIn,
    CampaignIn,
    CampaignOut,
    PlanDecisionIn,
    PlanIn,
    PlanOut,
    SurveyIn,
    SurveyOut,
    TeamIn,
    TeamOut,
)
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import campaigns

router = APIRouter(prefix="/api/v1", tags=["campaigns"])


@router.post("/surveys", status_code=201, response_model=SurveyOut, summary="Record a street count")
def record_survey(body: SurveyIn, ctx: CurrentOrg) -> SurveyOut:
    """Permission: ``survey.write``. Counts are observations, not a census; they become the default estimate
    for planning that area."""
    with ctx.tx() as db:
        sid = campaigns.record_survey(db, ctx, body)
        r = db.execute(text("select * from app.survey_counts where id = :id"), {"id": sid}).one()
        return SurveyOut(id=r.id, area_id=r.area_id, observed_on=r.observed_on, dogs_counted=r.dogs_counted,
                         marked_count=r.marked_count, puppies_count=r.puppies_count, method=r.method)


@router.get("/teams", response_model=list[TeamOut], summary="Field teams")
def list_teams(ctx: CurrentOrg) -> list[TeamOut]:
    """Permission: ``campaign.manage`` or ``task.manage``."""
    with ctx.tx() as db:
        return campaigns.list_teams(db, ctx)


@router.post("/teams", status_code=201, response_model=list[TeamOut], summary="Add a team")
def create_team(body: TeamIn, ctx: CurrentOrg) -> list[TeamOut]:
    """Permission: ``campaign.manage``."""
    with ctx.tx() as db:
        campaigns.create_team(db, ctx, body)
        return campaigns.list_teams(db, ctx)


@router.get("/campaigns", response_model=list[CampaignOut], summary="Campaigns")
def list_campaigns(ctx: CurrentOrg) -> list[CampaignOut]:
    """Permission: ``campaign.manage`` or ``task.manage``."""
    with ctx.tx() as db:
        return campaigns.list_campaigns(db, ctx)


@router.post("/campaigns", status_code=201, response_model=CampaignOut, summary="Create a campaign")
def create_campaign(body: CampaignIn, ctx: CurrentOrg) -> CampaignOut:
    """Permission: ``campaign.manage``."""
    with ctx.tx() as db:
        cid = campaigns.create_campaign(db, ctx, body)
        return campaigns.get_campaign(db, ctx, cid)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Campaign with area inputs")
def get_campaign(campaign_id: UUID, ctx: CurrentOrg) -> CampaignOut:
    """Permission: ``campaign.manage`` or ``task.manage``. Each area shows the manual estimate if set, otherwise
    a suggestion with its source (latest street count, else registry records)."""
    with ctx.tx() as db:
        return campaigns.get_campaign(db, ctx, campaign_id)


@router.put("/campaigns/{campaign_id}/areas/{area_id}", response_model=CampaignOut, summary="Set area inputs")
def update_area(campaign_id: UUID, area_id: UUID, body: CampaignAreaIn, ctx: CurrentOrg) -> CampaignOut:
    """Permission: ``campaign.manage``. Requires the area's current ``row_version``."""
    with ctx.tx() as db:
        campaigns.update_campaign_area(db, ctx, campaign_id, area_id, body)
        db.flush()
        return campaigns.get_campaign(db, ctx, campaign_id)


@router.get("/campaigns/{campaign_id}/plans", response_model=list[PlanOut], summary="Plan versions")
def list_plans(campaign_id: UUID, ctx: CurrentOrg) -> list[PlanOut]:
    """Permission: ``campaign.manage`` or ``task.manage``. Newest first."""
    with ctx.tx() as db:
        return campaigns.list_plans(db, ctx, campaign_id)


@router.post("/campaigns/{campaign_id}/plans", status_code=201, response_model=PlanOut, summary="Plan a day")
def create_plan(campaign_id: UUID, body: PlanIn, ctx: CurrentOrg) -> PlanOut:
    """Permission: ``campaign.manage``. Snapshots the inputs and queues the solver; poll until ``ready``."""
    with ctx.tx() as db:
        pid = campaigns.create_plan(db, ctx, campaign_id, body)
        return campaigns.get_plan(db, ctx, pid)


@router.get("/plans/{plan_id}", response_model=PlanOut, summary="Plan detail")
def get_plan(plan_id: UUID, ctx: CurrentOrg) -> PlanOut:
    """Permission: ``campaign.manage`` or ``task.manage``."""
    with ctx.tx() as db:
        return campaigns.get_plan(db, ctx, plan_id)


@router.post("/plans/{plan_id}/approve", response_model=PlanOut, summary="Approve a plan")
def approve(plan_id: UUID, body: PlanDecisionIn, ctx: CurrentOrg) -> PlanOut:
    """Permission: ``campaign.manage``. Approval does not dispatch anything."""
    with ctx.tx() as db:
        campaigns.approve_plan(db, ctx, plan_id, body.row_version, body.note)
        db.flush()
        return campaigns.get_plan(db, ctx, plan_id)


@router.post("/plans/{plan_id}/publish", response_model=PlanOut, summary="Publish an approved plan as tasks")
def publish(plan_id: UUID, body: PlanDecisionIn, ctx: CurrentOrg) -> PlanOut:
    """Permission: ``campaign.manage`` + ``task.manage``. Creates one assigned field task per planned stop."""
    with ctx.tx() as db:
        campaigns.publish_plan(db, ctx, plan_id, body.row_version)
        db.flush()
        return campaigns.get_plan(db, ctx, plan_id)
