"""
Seed the milestone_library_item table with standard clinical trial
pass-through / non-personnel direct costs.

Source: GrantPlan CRO Site Budget System standard template (screenshot).

Run:
    python -m app.modules.site_budgeting.seed_milestone_library
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.modules.site_budgeting.db_models import MilestoneLibraryItem

_NS = uuid.UUID("019a2c3d-beef-7e1a-b001-c0ffee000001")


def _id(code: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"milestone_library:{code}")


# (code, name, category, default_amount, payment_trigger, sort_order)
_ITEMS: list[tuple[str, str, str, Decimal | None, str | None, int]] = [
    # ── IRB / IEC ────────────────────────────────────────────────────────────
    ("IRB-01", "Initial IRB/IEC review fee",              "IRB / IEC",    Decimal("2500"),  "On submission",      10),
    ("IRB-02", "Annual continuing IRB review fee",         "IRB / IEC",    Decimal("1200"),  "Annual",             20),
    ("IRB-03", "Protocol amendment review fee",            "IRB / IEC",    Decimal("500"),   "Per amendment",      30),
    ("IRB-04", "SAE / expedited safety review fee",        "IRB / IEC",    Decimal("300"),   "Per event",          40),
    ("IRB-05", "Study closure / termination fee",          "IRB / IEC",    Decimal("800"),   "On study closure",   50),

    # ── Start-Up ─────────────────────────────────────────────────────────────
    ("STA-01", "Site Feasibility Assessment (SFA)",        "Start-Up",     Decimal("1500"),  "On completion",      10),
    ("STA-02", "Protocol & ICF translation",               "Start-Up",     Decimal("1200"),  "Per document",       20),
    ("STA-03", "Site Initiation Visit (SIV) support",      "Start-Up",     Decimal("2000"),  "On SIV completion",  30),

    # ── Laboratory ───────────────────────────────────────────────────────────
    ("LAB-90", "Central laboratory kit / shipping",        "Laboratory",   Decimal("45"),    "Per sample",         10),

    # ── Imaging ──────────────────────────────────────────────────────────────
    ("IMG-90", "Independent radiological review",          "Imaging",      Decimal("380"),   "Per patient",        10),

    # ── Pharmacy ─────────────────────────────────────────────────────────────
    ("PHA-90", "IP accountability (monthly pharmacy fee)", "Pharmacy",     Decimal("800"),   "Monthly",            10),
    ("PHA-91", "IP destruction / return logistics",        "Pharmacy",     Decimal("600"),   "On study close",     20),

    # ── Monitoring ───────────────────────────────────────────────────────────
    ("MON-01", "Monitoring visit support",                 "Monitoring",   Decimal("800"),   "Per visit",          10),
    ("MON-02", "Close-out monitoring visit support",       "Monitoring",   Decimal("1000"),  "On close-out",       20),

    # ── Archival ─────────────────────────────────────────────────────────────
    ("ARC-01", "Document archival (annual)",               "Archival",     Decimal("600"),   "Annual",             10),
    ("ARC-02", "Electronic TMF / ISF digitisation",        "Archival",     Decimal("1500"),  "On completion",      20),

    # ── Patient Costs ─────────────────────────────────────────────────────────
    ("PAT-01", "Patient travel reimbursement",             "Patient Costs", Decimal("60"),   "Per visit",          10),
    ("PAT-02", "Patient stipend / time compensation",      "Patient Costs", Decimal("50"),   "Per visit",          20),

    # ── Insurance ────────────────────────────────────────────────────────────
    ("INS-01", "Trial subject insurance / indemnity",      "Insurance",    Decimal("2000"),  "Annual",             10),

    # ── Contingency ──────────────────────────────────────────────────────────
    ("CON-01", "Contingency (~10% direct costs)",          "Contingency",  Decimal("5000"),  "Lump sum estimate",  10),
]


async def run() -> None:
    print("=== seed_milestone_library ===\n")
    inserted = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        for code, name, category, amount, trigger, sort_order in _ITEMS:
            item_id = _id(code)
            exists = (
                await session.execute(
                    select(MilestoneLibraryItem.id).where(MilestoneLibraryItem.id == item_id)
                )
            ).scalar_one_or_none()

            if exists:
                skipped += 1
                print(f"[skip]   {code} — {name}")
                continue

            session.add(MilestoneLibraryItem(
                id=item_id,
                name=name,
                default_amount=amount,
                payment_trigger=trigger,
                category=category,
                sort_order=sort_order,
                is_active=True,
            ))
            inserted += 1
            amt_str = f"${amount:,.2f}" if amount is not None else "no default"
            print(f"[insert] {code} — {name} ({category}, {amt_str})")

        await session.commit()

    print(f"\nDone. inserted={inserted}, skipped={skipped}.")


if __name__ == "__main__":
    asyncio.run(run())
