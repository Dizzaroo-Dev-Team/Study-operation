"""
Test the refactor-budget pipeline end-to-end with the real US Budget Policy text.
Doesn't write to DB — just calls the extractor and reports what gets excluded.

  docker exec -w /app backend-crm-backend-1 python -m scripts.audit_refactor_us
"""
import asyncio
from sqlalchemy import select, text

from app.db import AsyncSessionLocal
import app.models  # noqa: F401  ensure SA metadata
from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetTemplate,
    CostElement,
)
from app.modules.site_budgeting.services import budget_service
from app.modules.site_budgeting.services.ai_budget_service import (
    extract_budget_rules_from_policy,
)


# Plain-text version of the user's US Budget Policy Guide PDF.
US_POLICY_TEXT = """\
United States (US) — Budget Policy Guide

BUDGET POLICY GUIDE
United States (US)
Oncology Clinical Trials
Inclusions | Exclusions | Rules | Practical Guidance

1. Overview
The United States clinical trial budget framework operates within a complex healthcare
landscape where routine care is typically billed to insurance. Sponsors must carefully distinguish
between research-specific costs (budgetable) and standard-of-care procedures (excluded).
Medicare Coverage Analysis (MCA) is a mandatory inclusion to ensure compliance with CMS
guidelines for clinical trials involving Medicare-eligible patients. Overhead is strictly capped to
maintain cost discipline.

2. Universal Oncology Baseline
The following cost categories form the universal baseline for all oncology clinical trial budgets
and apply to this country:
Start-up/Close-out fees, Per-Patient Grant (PPG), Imaging, Biopsies, Pharmacy, Pass-throughs

3. Budget Exclusions
The following items must NOT be included in the clinical trial budget for this country:

Excluded Item | Rationale / Detail
Routine Lab Costs | Standard laboratory tests that would occur regardless of study
participation are billed to the patient's insurance carrier. These
include CBC, CMP, urinalysis, and other routine panels.

Standard of Care (SoC) Procedures | Any procedure, test, or treatment that the patient would
receive outside of the clinical trial context must be excluded
from the study budget and billed through normal insurance
channels.

4. Budget Inclusions
The following items MUST be included in the clinical trial budget for this country:

Included Item | Detail / Requirement
Medicare Coverage Analysis (MCA) Fee | A mandatory fee covering the cost of performing a Medicare
Coverage Analysis. This analysis determines which trial costs
are billable to Medicare vs. the sponsor, ensuring CMS
compliance for trials enrolling Medicare beneficiaries.

5. Budgeting Rules
The following specific rules govern budget construction for this country:

Rule | Implementation Detail
Overhead Cap: 25-30% | Institutional overhead charged by sites is capped at 25-30%
and is applied only to direct study costs. This prevents inflated
budgets and ensures sponsor funds are directed toward
research activities.

6. Practical Budgeting Tips
- Conduct MCA early in site selection to identify cost allocation.
- Negotiate overhead rates during site contracting - many sites will accept 25%.
- Ensure clear line-item separation between research and SoC procedures.
- Verify insurance billing codes (CPT/ICD-10) align with budget exclusions.

7. Quick Reference Summary
Category | Summary
Exclusions | Routine Lab Costs; Standard of Care (SoC) Procedures
Inclusions | Medicare Coverage Analysis (MCA) Fee
Rules | Overhead Cap: 25-30%
"""


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # 1. Pick a trial + ensure it has a TRIAL template + an SOA-imported set of line items.
        trial_id = (await db.execute(text("SELECT id FROM studies LIMIT 1"))).scalar_one()
        # Wipe + create TRIAL template + import D0816C00010
        for w in [
            "DELETE FROM budget_visit_matrix WHERE budget_line_item_id IN (SELECT id FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :t))",
            "DELETE FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :t)",
            "DELETE FROM visit_schedule WHERE trial_id = :t",
            "DELETE FROM trial_factor_configuration WHERE trial_id = :t",
            "DELETE FROM budget_template WHERE trial_id = :t",
        ]:
            await db.execute(text(w), {"t": trial_id})
        await db.commit()

        trial_tpl = BudgetTemplate(
            trial_id=trial_id, name="audit-refactor-us",
            template_level="TRIAL", target_currency_code="USD",
        )
        db.add(trial_tpl); await db.flush(); await db.commit()

        await budget_service.generate_visit_matrix_from_soa(
            db, template_id=trial_tpl.id, study_id="D0816C00010",
            treatment_duration=24, followup_duration=24, unscheduled_visits=2,
        )
        await db.commit()

        # 2. Get the available element names for this trial (the only valid targets for refactor).
        line_items = (await db.execute(
            select(BudgetLineItem).where(BudgetLineItem.budget_template_id == trial_tpl.id)
        )).scalars().all()
        available_names = []
        for li in line_items:
            ce = await db.get(CostElement, li.cost_element_id)
            if ce:
                available_names.append(ce.name)

        print(f"Trial has {len(available_names)} line items (catalog elements):")
        for n in sorted(available_names):
            print(f"  - {n}")
        print()

        # 3. Run the LLM extraction with the real US policy text.
        documents = [(US_POLICY_TEXT.encode("utf-8"), "us_budget_policy.txt")]
        rules = await extract_budget_rules_from_policy(
            documents=documents,
            country_code="USA",
            available_element_names=available_names,
        )

        print(f"=== LLM result: {len(rules)} exclusion rule(s) ===")
        for r in rules:
            print(f"  EXCLUDE  {r['element_name']:50}  reason: {r.get('reason')}")
        print()

        # 4. Show what's left active
        excluded_names = {r["element_name"] for r in rules}
        active = [n for n in available_names if n not in excluded_names]
        print(f"=== Active (not excluded) — {len(active)} item(s) ===")
        for n in sorted(active):
            print(f"  - {n}")


if __name__ == "__main__":
    asyncio.run(main())
