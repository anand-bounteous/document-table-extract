"""Maps every entity type to a dashboard category.

The dashboard renders four top-level sections (PII / Network / Location /
Visual). Each cell summary carries per-category counts so the frontend can
filter without a second round-trip.
"""

from __future__ import annotations

CATEGORY_PII = "PII"
CATEGORY_NETWORK = "Network"
CATEGORY_LOCATION = "Location"
CATEGORY_VISUAL = "Visual"

NETWORK_TYPES = {"EMAIL_ADDRESS", "URL"}
LOCATION_TYPES = {
    "LAT_LONG_PAIR",
    "MAP_URL_GOOGLE",
    "MAP_URL_APPLE",
    "MAP_URL_OSM",
}
VISUAL_TYPES = {"QR_CODE", "BAR_CODE"}


def category_for(entity_type: str) -> str:
    if entity_type in VISUAL_TYPES:
        return CATEGORY_VISUAL
    if entity_type in LOCATION_TYPES:
        return CATEGORY_LOCATION
    if entity_type in NETWORK_TYPES:
        return CATEGORY_NETWORK
    return CATEGORY_PII


ALL_CATEGORIES = [CATEGORY_PII, CATEGORY_NETWORK, CATEGORY_LOCATION, CATEGORY_VISUAL]
