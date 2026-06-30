"""Generate a synthetic UK-banking PII benchmark dataset (.prompt/009 §13).

Outputs JSONL records with the schema expected by the dataset benchmark
runner. Each record is annotated with character-accurate gold spans so the
evaluator can compute exact/partial precision/recall.

Composition mix per §13.2:

    uk_structured_pii:        30%
    banking_identifiers:      25%
    names_and_addresses:      20%
    customer_service_notes:   10%
    noisy_ocr_text:            5%
    sensitive_indicators:      5%
    negative_no_pii_examples:  5%

Usage:

    uv run python -m scripts.generate_pii_dataset --count 500 --out data/pii_v2/synthetic_500.jsonl

The annotations cover the structured / banking categories with high
fidelity. PERSON / UK_ADDRESS are emitted as multi-token spans without
sub-token annotation (the recogniser is the judge of those).
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Tuple


FIRST_NAMES = ["John", "Jane", "Aisha", "Daniel", "Rajesh", "Olivia", "Hiroshi", "Wendy", "Chidi", "Priya"]
LAST_NAMES = ["Smith", "Patel", "Khan", "O'Connor", "Singh", "Brown", "Watanabe", "Adeyemi", "Sharma", "Davies"]
STREETS = ["High Street", "King's Road", "Downing Street", "Baker Street", "Oxford Street", "Whitehall", "Pall Mall"]
CITIES = ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Bristol", "Edinburgh"]
POSTCODES = ["SW1A 1AA", "EC1A 1BB", "M1 1AE", "B33 8TH", "LS1 4AP", "G2 1AB", "EH1 1YZ"]


@dataclass
class Span:
    entity_type: str
    start: int
    end: int
    text: str


@dataclass
class Record:
    id: str
    text: str = ""
    entities: List[Span] = field(default_factory=list)

    def append(self, fragment: str) -> None:
        self.text += fragment

    def append_entity(self, entity_type: str, value: str) -> None:
        start = len(self.text)
        self.text += value
        self.entities.append(Span(entity_type, start, start + len(value), value))

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "text": self.text,
            "entities": [
                {"entity_type": e.entity_type, "start": e.start, "end": e.end, "text": e.text}
                for e in self.entities
            ],
        }


def gen_sort_code() -> str:
    return f"{random.randint(10, 99)}-{random.randint(10, 99)}-{random.randint(10, 99)}"


def gen_account_number() -> str:
    return f"{random.randint(10_000_000, 99_999_999)}"


def gen_phone() -> str:
    return random.choice([
        f"+44 7{random.randint(100, 999)} {random.randint(100000, 999999)}",
        f"07{random.randint(100, 999)} {random.randint(100000, 999999)}",
        f"020 {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
    ])


def gen_nino() -> str:
    """Spec-compliant random NINO (avoiding bad prefixes)."""
    bad = {"BG", "GB", "KN", "NK", "NT", "TN", "ZZ"}
    while True:
        first = random.choice("ABCEGHJ-PR-TW-Z".replace("-", ""))
        second = random.choice("ABCEGHJ-NPR-TW-Z".replace("-", ""))
        prefix = first + second
        if prefix not in bad:
            break
    digits = f"{random.randint(0, 99):02d} {random.randint(0, 99):02d} {random.randint(0, 99):02d}"
    suffix = random.choice("ABCD")
    return f"{prefix} {digits} {suffix}"


def gen_email() -> str:
    name = random.choice(FIRST_NAMES).lower()
    domain = random.choice(["example.com", "mail.uk", "bank.co.uk", "yahoo.co.uk"])
    return f"{name}.{random.choice(LAST_NAMES).lower()}@{domain}"


def gen_card_number() -> str:
    # Luhn-valid 16-digit Visa (4xxx) — for benchmark realism. The first
    # 15 digits are random, last digit closes the Luhn checksum.
    base = "4" + "".join(str(random.randint(0, 9)) for _ in range(14))
    total = 0
    for i, d in enumerate(reversed(base)):
        n = int(d)
        if i % 2 == 0:  # positions that will become odd in the final string when checksum is appended
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - total % 10) % 10
    return base + str(check)


def gen_iban() -> str:
    # GB-formatted IBAN; checksum is computed for MOD-97.
    bank = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=4))
    account = "".join(str(random.randint(0, 9)) for _ in range(14))
    body = bank + account + "GB00"
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in body)
    remainder = int(numeric) % 97
    check = 98 - remainder
    return f"GB{check:02d}{bank}{account}"


def gen_full_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def gen_address() -> Tuple[str, str]:
    """Returns (full_address, postcode)."""
    number = random.randint(1, 250)
    street = random.choice(STREETS)
    city = random.choice(CITIES)
    postcode = random.choice(POSTCODES)
    full = f"{number} {street}, {city} {postcode}"
    return full, postcode


# ---------- generators per category ----------


def gen_uk_structured(rec: Record) -> None:
    rec.append("Please verify the postcode ")
    _, pc = gen_address()
    rec.append_entity("UK_POSTCODE", pc)
    rec.append(" before posting the documents. Contact number: ")
    rec.append_entity("UK_PHONE_NUMBER", gen_phone())
    rec.append(". National Insurance: ")
    rec.append_entity("UK_NATIONAL_INSURANCE_NUMBER", gen_nino())
    rec.append(".")


def gen_banking(rec: Record) -> None:
    rec.append("Set up the standing order from sort code ")
    rec.append_entity("UK_SORT_CODE", gen_sort_code())
    rec.append(" account ")
    rec.append_entity("UK_BANK_ACCOUNT_NUMBER", gen_account_number())
    rec.append(". Card ending ")
    rec.append_entity("CREDIT_CARD_NUMBER", gen_card_number())
    rec.append(" expires 12/29. IBAN ")
    rec.append_entity("UK_IBAN", gen_iban())
    rec.append(".")


def gen_names_and_addresses(rec: Record) -> None:
    rec.append("Customer ")
    rec.append_entity("PERSON", gen_full_name())
    rec.append(" lives at ")
    full, postcode = gen_address()
    # Compute the inner postcode span first, then push the outer UK_ADDRESS span.
    addr_start = len(rec.text)
    rec.text += full
    addr_end = len(rec.text)
    pc_idx = full.rfind(postcode)
    if pc_idx >= 0:
        pc_start = addr_start + pc_idx
        rec.entities.append(Span("UK_POSTCODE", pc_start, pc_start + len(postcode), postcode))
    rec.entities.append(Span("UK_ADDRESS", addr_start, addr_end, full))
    rec.append(". Email: ")
    rec.append_entity("EMAIL_ADDRESS", gen_email())
    rec.append(".")


def gen_customer_service_notes(rec: Record) -> None:
    rec.append("Customer ")
    rec.append_entity("PERSON", gen_full_name())
    rec.append(" called regarding their account. They confirmed contact at ")
    rec.append_entity("UK_PHONE_NUMBER", gen_phone())
    rec.append(" and requested a statement to be sent to ")
    rec.append_entity("EMAIL_ADDRESS", gen_email())
    rec.append(". Reference logged.")


def gen_noisy_ocr_text(rec: Record) -> None:
    rec.append("Inv0ice# 12O4-5 6 sort code  ")
    rec.append_entity("UK_SORT_CODE", gen_sort_code())
    rec.append(" a/c ")
    rec.append_entity("UK_BANK_ACCOUNT_NUMBER", gen_account_number())
    rec.append(". Receipt sent to ")
    rec.append_entity("EMAIL_ADDRESS", gen_email())
    rec.append(" — please re-print if illegble.")


def gen_sensitive_indicator(rec: Record) -> None:
    rec.append("Customer ")
    rec.append_entity("PERSON", gen_full_name())
    rec.append(" says they are ")
    rec.append_entity("VULNERABLE_CUSTOMER_INDICATOR", "vulnerable due to recent bereavement")
    rec.append(" and need support with arrears.")


def gen_negative(rec: Record) -> None:
    # No PII at all.
    fragments = [
        "Our office hours are 9am to 5pm Monday to Friday.",
        "The interest rate on standard savings is published monthly.",
        "Please retain this leaflet for your records.",
        "Updated terms and conditions take effect next quarter.",
    ]
    rec.append(random.choice(fragments))


CATEGORIES: List[Tuple[str, float, Callable[[Record], None]]] = [
    ("uk_structured", 0.30, gen_uk_structured),
    ("banking", 0.25, gen_banking),
    ("names_addresses", 0.20, gen_names_and_addresses),
    ("customer_service", 0.10, gen_customer_service_notes),
    ("noisy_ocr", 0.05, gen_noisy_ocr_text),
    ("sensitive", 0.05, gen_sensitive_indicator),
    ("negative", 0.05, gen_negative),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic UK PII JSONL")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("w") as f:
        for i in range(args.count):
            rec = Record(id=f"uk_case_{i + 1:04d}")
            cat = _pick_category()
            cat(rec)
            f.write(json.dumps(rec.to_dict()) + "\n")

    print(f"wrote {args.count} records to {args.out}")


def _pick_category() -> Callable[[Record], None]:
    r = random.random()
    cum = 0.0
    for _, weight, fn in CATEGORIES:
        cum += weight
        if r <= cum:
            return fn
    return CATEGORIES[-1][2]


if __name__ == "__main__":
    main()
