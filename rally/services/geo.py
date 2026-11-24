import math

EARTH_RADIUS_M = 6371008.8


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def reference_point(obj):
    """Organizer's scoring point: adjusted coordinates win over the original capture."""
    if obj["adj_lat"] is not None and obj["adj_lon"] is not None:
        return obj["adj_lat"], obj["adj_lon"]
    if obj["lat"] is not None and obj["lon"] is not None:
        return obj["lat"], obj["lon"]
    return None


def offset_m(lat0, lon0, lat, lon):
    """(east, north) meters from the first point to the second. Fine for distances of a few km."""
    k = math.radians(1) * EARTH_RADIUS_M
    return (lon - lon0) * k * math.cos(math.radians(lat0)), (lat - lat0) * k


def move(lat0, lon0, east_m, north_m):
    """The point east_m / north_m meters away from (lat0, lon0)."""
    k = math.radians(1) * EARTH_RADIUS_M
    return lat0 + north_m / k, lon0 + east_m / (k * math.cos(math.radians(lat0)))
