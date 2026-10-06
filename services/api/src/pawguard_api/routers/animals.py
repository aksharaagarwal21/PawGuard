from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from pawguard_api.contracts import (
    AnimalCreate,
    AnimalOut,
    AnimalPage,
    AnimalUpdate,
    ObservationCreate,
    ObservationOut,
    ProfileTransition,
)
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import animals, idempotency

router = APIRouter(prefix="/api/v1", tags=["animals"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def _created(payload: dict, status: int = 201) -> JSONResponse:  # type: ignore[type-arg]
    return JSONResponse(payload, status_code=status)


@router.get("/animals", response_model=AnimalPage, summary="Search the animal registry")
def list_animals(
    ctx: CurrentOrg,
    q: Annotated[str | None, Query(max_length=80, description="Reference, nickname or descriptor")] = None,
    area_id: UUID | None = None,
    profile_state: Annotated[list[Literal["provisional", "reviewed", "active", "disputed", "merged_alias",
                                          "archived"]] | None, Query()] = None,
    vaccination_status: Literal["verified_record", "submitted_only", "no_verified_record"] | None = None,
    seen_within_days: Annotated[int | None, Query(ge=1, le=3650)] = None,
    has_open_task: bool | None = None,
    include_merged: bool = False,
    cursor: Annotated[str | None, Query(max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AnimalPage:
    """Permission: ``animal.read``. Results are limited to the selected organisation. Caregiver contacts and exact
    locations are never part of registry results."""
    with ctx.tx() as db:
        items, nxt, total = animals.search_animals(
            db, ctx, q=q, area_id=area_id, profile_states=profile_state, vaccination_status=vaccination_status,
            seen_within_days=seen_within_days, has_open_task=has_open_task, include_merged=include_merged,
            cursor=cursor, limit=limit)
    return AnimalPage(items=items, next_cursor=nxt, total_matching=total)


@router.post("/animals", status_code=201, response_model=AnimalOut, summary="Register an animal (provisional)")
def create_animal(body: AnimalCreate, ctx: CurrentOrg, idempotency_key: IdemKey = None) -> JSONResponse:
    """Permission: ``animal.write`` (plus ``observation.write`` when a first observation is included). New
    profiles are always ``provisional``. Supports ``Idempotency-Key`` and ``client_operation_id``."""
    route = "POST /animals"
    with ctx.tx() as db:
        replay = idempotency.claim(db, ctx, route, idempotency_key, body.model_dump(mode="json"))
        if replay:
            return _created(replay.body, replay.status_code)
        animal_id = animals.create_animal(db, ctx, body)
        db.flush()
        payload = animals.get_animal(db, ctx, animal_id).model_dump(mode="json")
        idempotency.store(db, ctx, route, idempotency_key, 201, payload, "animal", animal_id)
    return _created(payload)


@router.get("/animals/{animal_id}", response_model=AnimalOut, summary="Animal profile")
def get_animal(animal_id: UUID, ctx: CurrentOrg) -> AnimalOut:
    """Permission: ``animal.read``. Merged aliases are returned with ``merged_into_reference``."""
    with ctx.tx() as db:
        return animals.get_animal(db, ctx, animal_id)


@router.patch("/animals/{animal_id}", response_model=AnimalOut, summary="Update descriptive details")
def update_animal(animal_id: UUID, body: AnimalUpdate, ctx: CurrentOrg) -> AnimalOut:
    """Permission: ``animal.write``. Requires the current ``row_version``; a stale version returns 409."""
    with ctx.tx() as db:
        animals.update_animal(db, ctx, animal_id, body)
        db.flush()
        return animals.get_animal(db, ctx, animal_id)


@router.post("/animals/{animal_id}/profile-transitions", response_model=AnimalOut,
             summary="Review, dispute or archive a profile")
def transition_profile(animal_id: UUID, body: ProfileTransition, ctx: CurrentOrg) -> AnimalOut:
    """Permission: ``animal.write`` to flag a dispute; ``animal.merge`` to review, activate, resolve or archive.
    Disputes, archiving and resolving a dispute require a reason."""
    with ctx.tx() as db:
        animals.transition_profile(db, ctx, animal_id, body)
        db.flush()
        return animals.get_animal(db, ctx, animal_id)


@router.get("/animals/{animal_id}/observations", response_model=list[ObservationOut], summary="Sightings")
def list_observations(animal_id: UUID, ctx: CurrentOrg,
                      limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[ObservationOut]:
    """Permission: ``animal.read``. Coordinates are exact only with ``animal.location.exact``; otherwise they are
    snapped to a ~500 m grid and marked approximate."""
    with ctx.tx() as db:
        animals.load_animal(db, animal_id)
        return animals.list_observations(db, ctx, animal_id, limit)


@router.post("/observations", status_code=201, summary="Record a sighting")
def create_observation(body: ObservationCreate, ctx: CurrentOrg, idempotency_key: IdemKey = None) -> JSONResponse:
    """Permission: ``observation.write``. ``animal_id`` may be omitted while identity is unresolved. Notes must
    be non-diagnostic. Supports ``Idempotency-Key`` and ``client_operation_id``."""
    route = "POST /observations"
    with ctx.tx() as db:
        replay = idempotency.claim(db, ctx, route, idempotency_key, body.model_dump(mode="json"))
        if replay:
            return _created(replay.body, replay.status_code)
        obs_id = animals.create_observation(db, ctx, body)
        payload = {"id": str(obs_id)}
        idempotency.store(db, ctx, route, idempotency_key, 201, payload, "observation", obs_id)
    return _created(payload)
