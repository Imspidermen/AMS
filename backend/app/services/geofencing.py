from dataclasses import dataclass
from datetime import datetime
import math

from app.core.timezone import as_utc, utc_now
from app.models.entities import Location

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class GeoResult:
    accepted: bool
    reason: str | None
    distance_m: float
    accuracy_m: float


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    values = (lat1, lon1, lat2, lon2)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Coordinates must be finite numbers")
    if not -90 <= lat1 <= 90 or not -90 <= lat2 <= 90:
        raise ValueError("Latitude must be between -90 and 90")
    if not -180 <= lon1 <= 180 or not -180 <= lon2 <= 180:
        raise ValueError("Longitude must be between -180 and 180")
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def validate_location_reading(
    location: Location,
    latitude: float,
    longitude: float,
    accuracy_m: float,
    measured_at: datetime,
    now: datetime | None = None,
    max_age_seconds: int = 120,
) -> GeoResult:
    if not location.active:
        return GeoResult(False, "location_inactive", 0.0, accuracy_m)
    if not math.isfinite(accuracy_m) or accuracy_m <= 0:
        return GeoResult(False, "invalid_accuracy", 0.0, accuracy_m)
    try:
        distance = haversine_distance_m(latitude, longitude, location.latitude, location.longitude)
    except ValueError:
        return GeoResult(False, "invalid_coordinates", 0.0, accuracy_m)
    clock = as_utc(now or utc_now())
    sample_time = as_utc(measured_at)
    age = (clock - sample_time).total_seconds()
    if age < -30 or age > max_age_seconds:
        return GeoResult(False, "stale_location", distance, accuracy_m)
    if accuracy_m > location.max_accuracy_m:
        return GeoResult(False, "inaccurate_location", distance, accuracy_m)
    if distance > location.radius_m:
        return GeoResult(False, "outside_geofence", distance, accuracy_m)
    return GeoResult(True, None, distance, accuracy_m)
