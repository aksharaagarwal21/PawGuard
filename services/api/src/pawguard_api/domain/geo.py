"""Location helpers. Inputs are named lat/lon; PostGIS points are (lon, lat) — conversion happens only here."""

from typing import Any

from sqlalchemy import func, literal
from sqlalchemy.sql.elements import ColumnElement

from pawguard_api.contracts import LocationIn, LocationOut

# ~0.005° ≈ 550 m north–south and ≈ 500 m east–west at Indian latitudes: "approximate (~500 m)".
APPROX_GRID_DEGREES = 0.005


def point(loc: LocationIn | None) -> ColumnElement[Any] | None:
    if loc is None:
        return None
    return func.ST_SetSRID(func.ST_MakePoint(literal(loc.lon), literal(loc.lat)), 4326).cast(_geog())


def approx_point(loc: LocationIn | None) -> ColumnElement[Any] | None:
    if loc is None:
        return None
    exact = func.ST_SetSRID(func.ST_MakePoint(literal(loc.lon), literal(loc.lat)), 4326)
    return func.ST_SnapToGrid(exact, APPROX_GRID_DEGREES).cast(_geog())


def _geog():  # type: ignore[no-untyped-def]
    from geoalchemy2 import Geography

    return Geography("POINT", srid=4326)


def location_out(lat: float | None, lon: float | None, accuracy: float | None, exact: bool) -> LocationOut | None:
    if lat is None or lon is None:
        return None
    return LocationOut(lat=round(lat, 6 if exact else 3), lon=round(lon, 6 if exact else 3),
                       accuracy_m=accuracy if exact else None, precision="exact" if exact else "approximate")
