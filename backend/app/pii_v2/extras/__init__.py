"""Extras recogniser plugin: lat/long pairs + map URLs.

Implemented as a separate jurisdiction-style plugin (code ``EXTRAS``) so
its recognisers get appended to the existing regex pipeline. EXTRAS is
always loaded by ``collect_recognizers`` regardless of the configured
jurisdictions, similar to USER_CUSTOM.
"""

from __future__ import annotations

import re
from typing import List

from app.pii_v2.jurisdictions.base import JurisdictionPlugin, RecognizerSpec


def _valid_lat_long(value: str) -> bool:
    """Range-validate a 'lat,long' string before accepting it."""
    try:
        lat_s, lon_s = [p.strip() for p in value.split(",", 1)]
        lat = float(lat_s)
        lon = float(lon_s)
    except (ValueError, IndexError):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


class ExtrasPlugin(JurisdictionPlugin):
    code = "EXTRAS"
    display_name = "Extras (location / map identifiers)"

    def get_recognizers(self) -> List[RecognizerSpec]:
        return [
            RecognizerSpec(
                entity_type="LAT_LONG_PAIR",
                pattern=r"[-+]?\d{1,3}\.\d{3,}\s*,\s*[-+]?\d{1,3}\.\d{3,}",
                score=0.7,
                jurisdiction="EXTRAS",
                context_terms=["lat", "long", "lng", "coord"],
                context_boost=0.2,
                validator=_valid_lat_long,
                flags=re.IGNORECASE,
            ),
            RecognizerSpec(
                entity_type="MAP_URL_GOOGLE",
                pattern=r"https?://(?:www\.)?google\.[a-z.]+/maps[^\s<>\"']*",
                score=0.95,
                jurisdiction="EXTRAS",
                flags=re.IGNORECASE,
            ),
            RecognizerSpec(
                entity_type="MAP_URL_APPLE",
                pattern=r"https?://maps\.apple\.com/[^\s<>\"']*",
                score=0.95,
                jurisdiction="EXTRAS",
                flags=re.IGNORECASE,
            ),
            RecognizerSpec(
                entity_type="MAP_URL_OSM",
                pattern=r"https?://(?:www\.)?openstreetmap\.org/[^\s<>\"']*",
                score=0.95,
                jurisdiction="EXTRAS",
                flags=re.IGNORECASE,
            ),
        ]
