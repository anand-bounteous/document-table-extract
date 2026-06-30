"""Jurisdiction plugin loader.

Each plugin contributes ``RecognizerSpec`` definitions (regex + validator +
context boost + score). The plugin loader assembles a flat list of
recognizers across the requested jurisdictions.
"""

from app.pii_v2.extras import ExtrasPlugin
from app.pii_v2.jurisdictions.base import (
    JurisdictionPlugin,
    RecognizerSpec,
    ValidatorFn,
)
from app.pii_v2.jurisdictions.global_common import GlobalCommonPlugin
from app.pii_v2.jurisdictions.uk import UKPlugin
from app.pii_v2.jurisdictions.user_custom import UserCustomPlugin

PLUGINS: dict[str, JurisdictionPlugin] = {
    "GLOBAL_COMMON": GlobalCommonPlugin(),
    "UK": UKPlugin(),
    "USER_CUSTOM": UserCustomPlugin(),
    "EXTRAS": ExtrasPlugin(),
}


def get_plugin(code: str) -> JurisdictionPlugin:
    if code not in PLUGINS:
        raise KeyError(f"Unknown jurisdiction: {code} (have: {sorted(PLUGINS)})")
    return PLUGINS[code]


def collect_recognizers(codes: list[str]) -> list[RecognizerSpec]:
    """Build the active recogniser list.

    USER_CUSTOM (manual-annotation feedback loop) and EXTRAS (lat/long +
    map URLs) are always appended so they're available without explicit
    configuration. USER_CUSTOM emits no specs until the user has saved
    at least one annotation.
    """
    out: list[RecognizerSpec] = []
    for code in codes:
        out.extend(get_plugin(code).get_recognizers())
    for implicit in ("USER_CUSTOM", "EXTRAS"):
        if implicit not in codes:
            out.extend(PLUGINS[implicit].get_recognizers())
    return out


__all__ = [
    "JurisdictionPlugin",
    "RecognizerSpec",
    "ValidatorFn",
    "PLUGINS",
    "get_plugin",
    "collect_recognizers",
]
