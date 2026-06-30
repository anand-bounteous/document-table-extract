"""Same-length mock generators per PII entity type.

Every generator takes ``(original: str, rng: random.Random)`` and returns
a string whose length **exactly matches** ``original``. This is the load-
bearing invariant: it lets the image redactor white-fill the original
bbox and re-draw the mock at the same coordinates without overflow.

Generators are pure functions of ``original`` + ``rng`` state, so the
caller controls determinism by reusing the same rng for repeated calls
with the same inputs.

Faker is used opportunistically for free-form types (PERSON, addresses,
organisations) when ``[pii-v2-redaction]`` is installed. A small built-in
dictionary in :mod:`._fallback_names` covers the no-Faker case. UK-
structured types (postcode / NINO / sort code / IBAN / phone) are
hand-coded — they can't use Faker anyway because length + format must be
preserved bit-for-bit.
"""

from __future__ import annotations

import logging
import random
import string
from typing import Callable, Dict, Optional

from app.pii_v2.redaction import _fallback_names as _fb

logger = logging.getLogger(__name__)

_faker_instance: Optional[object] = None
_faker_checked = False


def _get_faker() -> Optional[object]:
    """Lazy Faker import. Returns ``None`` when the dep isn't installed."""
    global _faker_instance, _faker_checked
    if _faker_checked:
        return _faker_instance
    _faker_checked = True
    try:
        from faker import Faker  # type: ignore
        _faker_instance = Faker(locale="en_GB")
        logger.debug("faker available — using locale en_GB for redaction mocks")
    except ImportError:
        logger.info("faker not installed; using built-in name dictionary for redaction")
        _faker_instance = None
    return _faker_instance


# --------------------------------------------------------------------------
# Free-form generators
# --------------------------------------------------------------------------


def _pick_by_length(pool: list[str], target: int, rng: random.Random) -> Optional[str]:
    """Pick a string from ``pool`` whose length matches ``target``.

    Returns ``None`` when no exact match exists so the caller can fall back
    to a padding strategy.
    """
    candidates = [s for s in pool if len(s) == target]
    if not candidates:
        return None
    return rng.choice(candidates)


def _pad_to_length(seed: str, target: int, rng: random.Random) -> str:
    """Trim or pad ``seed`` to exactly ``target`` chars.

    Padding uses lowercase letters so the result still looks like a name
    rather than a placeholder. Trimming preserves the leading characters
    (so initial/title information stays visible).
    """
    if len(seed) == target:
        return seed
    if len(seed) > target:
        return seed[:target]
    pad_chars = "".join(rng.choices(string.ascii_lowercase, k=target - len(seed)))
    return seed + pad_chars


def mock_person(original: str, rng: random.Random) -> str:
    target = len(original)
    fake = _get_faker()
    # First try Faker — seeded from our rng so determinism within a pii_run
    # is preserved. Try a handful of candidates for a same-length match.
    if fake is not None:
        try:
            fake.seed_instance(rng.randint(0, 2**31 - 1))  # type: ignore[attr-defined]
            for _ in range(12):
                candidate = fake.name()  # type: ignore[attr-defined]
                if len(candidate) == target:
                    return candidate
        except Exception:  # noqa: BLE001
            pass
    # Try the built-in pool for an exact length match.
    pool_full = [f"{f} {l}" for f in _fb.FIRST_NAMES for l in _fb.LAST_NAMES]
    pick = _pick_by_length(pool_full, target, rng)
    if pick is not None:
        return pick
    # Fall back: concat a first + last name and pad / trim.
    seed = f"{rng.choice(_fb.FIRST_NAMES)} {rng.choice(_fb.LAST_NAMES)}"
    return _pad_to_length(seed, target, rng)


def mock_organisation(original: str, rng: random.Random) -> str:
    target = len(original)
    pick = _pick_by_length(_fb.ORGANISATIONS, target, rng)
    if pick is not None:
        return pick
    seed = rng.choice(_fb.ORGANISATIONS)
    return _pad_to_length(seed, target, rng)


def mock_address(original: str, rng: random.Random) -> str:
    target = len(original)
    fake = _get_faker()
    if fake is not None:
        try:
            fake.seed_instance(rng.randint(0, 2**31 - 1))  # type: ignore[attr-defined]
            for _ in range(15):
                candidate = fake.street_address().replace("\n", " ")  # type: ignore[attr-defined]
                if len(candidate) == target:
                    return candidate
        except Exception:  # noqa: BLE001
            pass
    number = rng.randint(1, 250)
    street = rng.choice(_fb.STREETS)
    city = rng.choice(_fb.CITIES)
    seed = f"{number} {street}, {city}"
    return _pad_to_length(seed, target, rng)


def mock_location(original: str, rng: random.Random) -> str:
    target = len(original)
    pick = _pick_by_length(_fb.CITIES, target, rng)
    if pick is not None:
        return pick
    return _pad_to_length(rng.choice(_fb.CITIES), target, rng)


def mock_email(original: str, rng: random.Random) -> str:
    target = len(original)
    if "@" not in original:
        # Not actually an email; degrade to letters.
        return "".join(rng.choices(string.ascii_lowercase, k=target))
    at_pos = original.find("@")
    local_len = at_pos
    domain_len = target - at_pos - 1
    if local_len <= 0 or domain_len <= 0:
        return "".join(rng.choices(string.ascii_lowercase, k=target))
    # Build local part from FIRST/LAST names; trim/pad to fit.
    seed_local = rng.choice(_fb.EMAIL_LOCAL_PARTS)
    if len(seed_local) > local_len:
        local = seed_local[:local_len]
    else:
        local = seed_local + "".join(rng.choices(string.ascii_lowercase, k=local_len - len(seed_local)))
    # Build domain — try the per-length pool, fall back to padded "mail.co.uk".
    domain_pool = _fb.EMAIL_DOMAINS_BY_LEN.get(domain_len)
    if domain_pool:
        domain = rng.choice(domain_pool)
    else:
        domain = _pad_to_length("mail.co.uk", domain_len, rng)
    return f"{local}@{domain}"


def mock_url(original: str, rng: random.Random) -> str:
    """Same-length URL: preserve scheme + structure, randomise the host+path body."""
    target = len(original)
    # If the original starts with http(s), keep that prefix.
    for prefix in ("https://", "http://"):
        if original.startswith(prefix):
            body_len = target - len(prefix)
            body = _structured_body(original[len(prefix):], rng)
            return prefix + body
    return _structured_body(original, rng)


def _structured_body(seed: str, rng: random.Random) -> str:
    """Position-preserving replacement: letters→letters, digits→digits, else identical."""
    out = []
    for ch in seed:
        if ch.isalpha():
            out.append(rng.choice(string.ascii_lowercase if ch.islower() else string.ascii_uppercase))
        elif ch.isdigit():
            out.append(rng.choice(string.digits))
        else:
            out.append(ch)
    return "".join(out)


# --------------------------------------------------------------------------
# UK-structured generators (length + format preserved exactly)
# --------------------------------------------------------------------------


def mock_uk_postcode(original: str, rng: random.Random) -> str:
    """Preserve the original mask. ``A`` = letter, ``9`` = digit, anything
    else (space, dash) is kept verbatim."""
    out = []
    for ch in original:
        if ch.isalpha():
            out.append(rng.choice(string.ascii_uppercase))
        elif ch.isdigit():
            out.append(rng.choice(string.digits))
        else:
            out.append(ch)
    return "".join(out)


def mock_uk_nino(original: str, rng: random.Random) -> str:
    """NINO format: two letters + 6 digits + 1 letter, with optional spaces.

    Avoids the disallowed prefixes (BG, GB, KN, NK, NT, TN, ZZ).
    """
    bad = {"BG", "GB", "KN", "NK", "NT", "TN", "ZZ"}
    out_chars: list[str] = []
    letter_positions: list[int] = []
    for i, ch in enumerate(original):
        if ch.isalpha():
            out_chars.append("?")
            letter_positions.append(i)
        elif ch.isdigit():
            out_chars.append(rng.choice(string.digits))
        else:
            out_chars.append(ch)
    if letter_positions:
        prefix_set = {ch for ch in string.ascii_uppercase if ch not in "DFIQUV"}
        suffix_set = set("ABCD")
        # Generate prefix avoiding bad pairs.
        while True:
            first = rng.choice(sorted(prefix_set))
            second = rng.choice(sorted(prefix_set - {"O"}))
            if first + second not in bad:
                break
        out_chars[letter_positions[0]] = first
        if len(letter_positions) >= 2:
            out_chars[letter_positions[1]] = second
        for pos in letter_positions[2:]:
            out_chars[pos] = rng.choice(sorted(suffix_set))
    return "".join(out_chars)


def mock_uk_sort_code(original: str, rng: random.Random) -> str:
    """Six digits with original separators preserved."""
    return "".join(rng.choice(string.digits) if ch.isdigit() else ch for ch in original)


def mock_uk_bank_account(original: str, rng: random.Random) -> str:
    return "".join(rng.choice(string.digits) if ch.isdigit() else ch for ch in original)


def mock_uk_iban(original: str, rng: random.Random) -> str:
    """Keep ``GB`` country prefix; randomise the rest preserving char classes."""
    if not original.upper().startswith("GB"):
        return _structured_body(original, rng)
    body = _structured_body(original[2:], rng)
    return "GB" + body


def mock_phone(original: str, rng: random.Random) -> str:
    return "".join(rng.choice(string.digits) if ch.isdigit() else ch for ch in original)


def mock_credit_card(original: str, rng: random.Random) -> str:
    return "".join(rng.choice(string.digits) if ch.isdigit() else ch for ch in original)


def mock_lat_long(original: str, rng: random.Random) -> str:
    """Random lat,long that fits the original mask. Keeps decimal precision."""
    return _structured_body(original, rng)


def mock_date(original: str, rng: random.Random) -> str:
    return _structured_body(original, rng)


def mock_ip_address(original: str, rng: random.Random) -> str:
    return _structured_body(original, rng)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

_GENERATORS: Dict[str, Callable[[str, random.Random], str]] = {
    "PERSON": mock_person,
    "ORGANISATION": mock_organisation,
    "UK_ADDRESS": mock_address,
    "ADDRESS": mock_address,
    "LOCATION": mock_location,
    "EMAIL_ADDRESS": mock_email,
    "URL": mock_url,
    "MAP_URL_GOOGLE": mock_url,
    "MAP_URL_APPLE": mock_url,
    "MAP_URL_OSM": mock_url,
    "LAT_LONG_PAIR": mock_lat_long,
    "UK_POSTCODE": mock_uk_postcode,
    "UK_NATIONAL_INSURANCE_NUMBER": mock_uk_nino,
    "UK_SORT_CODE": mock_uk_sort_code,
    "UK_BANK_ACCOUNT_NUMBER": mock_uk_bank_account,
    "UK_IBAN": mock_uk_iban,
    "IBAN": mock_uk_iban,
    "UK_PHONE_NUMBER": mock_phone,
    "PHONE_NUMBER": mock_phone,
    "CREDIT_CARD_NUMBER": mock_credit_card,
    "DATE": mock_date,
    "DATE_OF_BIRTH": mock_date,
    "IP_ADDRESS": mock_ip_address,
}


def mock_for(entity_type: str, original: str, rng: random.Random) -> str:
    """Public entry point. Returns a same-length mock for ``original``."""
    if not original:
        return original
    gen = _GENERATORS.get(entity_type, _structured_body)
    mock = gen(original, rng)
    # Defensive — every generator should already guarantee this, but a bug
    # in any one of them would corrupt downstream bbox alignment, so we
    # repair the length here as a last-resort safety net.
    if len(mock) != len(original):
        logger.warning(
            "mock generator for %s returned wrong length (%d != %d); padding",
            entity_type, len(mock), len(original),
        )
        mock = _pad_to_length(mock, len(original), rng)
    return mock
