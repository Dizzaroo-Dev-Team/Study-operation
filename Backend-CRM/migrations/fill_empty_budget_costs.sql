-- Fill EVERY empty/zero cost in the budget (cost elements + milestones) with a
-- market-standard price by concept. Idempotent: only touches rows with no positive
-- cost, so re-running is a no-op. Prices are grounded in the seeded FMV-2026 catalog.
-- Safe to run on any environment (local / staging / prod).
BEGIN;

-- ── 1. Cost elements ────────────────────────────────────────────────────────
-- Insert an FMV-2026 cost version for every active element that has no positive cost.
INSERT INTO element_cost_version
  (id, element_id, version_label, base_unit_cost, reference_currency, effective_from, source, is_bundle_override)
SELECT gen_random_uuid(), ce.id, 'FMV-2026',
  CASE
    WHEN lower(ce.name) LIKE '%physical exam%' THEN 65
    WHEN lower(ce.name) LIKE '%vital sign%' THEN 35
    WHEN lower(ce.name) LIKE '%ecog%' THEN 25
    WHEN lower(ce.name) LIKE '%ecg%' OR lower(ce.name) LIKE '%12-lead%' OR lower(ce.name) LIKE '%electrocardiogram%' THEN 125
    WHEN lower(ce.name) LIKE '%adverse%' AND lower(ce.name) LIKE '%concomitant%' THEN 75
    WHEN lower(ce.name) LIKE '%sae%' THEN 320
    WHEN lower(ce.name) LIKE '%adverse event%' THEN 65
    WHEN lower(ce.name) LIKE '%concomitant%' THEN 30
    WHEN (lower(ce.name) LIKE '%fresh%' AND lower(ce.name) LIKE '%biops%') OR lower(ce.name) LIKE '%core biops%' THEN 1200
    WHEN lower(ce.name) LIKE '%archival%' OR lower(ce.name) LIKE '%tissue collection%' OR lower(ce.name) LIKE '%tissue retrieval%' THEN 180
    WHEN lower(ce.name) LIKE '%biops%' THEN 1200
    WHEN lower(ce.name) LIKE '%tumor%' AND (lower(ce.name) LIKE '%mri%' OR lower(ce.name) LIKE '%ct/%' OR lower(ce.name) LIKE '%ct %' OR lower(ce.name) LIKE '%imag%' OR lower(ce.name) LIKE '%evaluation%' OR lower(ce.name) LIKE '%assessment%' OR lower(ce.name) LIKE '%scan%') THEN 1850
    WHEN (lower(ce.name) LIKE '%hematology%' AND lower(ce.name) LIKE '%chemistry%') OR lower(ce.name) LIKE '%heme, chem%' THEN 85
    WHEN lower(ce.name) LIKE '%coagulation%' THEN 40
    WHEN lower(ce.name) LIKE '%hematology%' THEN 40
    WHEN lower(ce.name) LIKE '%chemistry%' THEN 45
    WHEN lower(ce.name) LIKE '%urinalysis%' THEN 20
    WHEN lower(ce.name) LIKE '%thyroid%' THEN 55
    WHEN lower(ce.name) LIKE '%pregnancy%' THEN 25
    WHEN lower(ce.name) LIKE '%ca19%' OR lower(ce.name) LIKE '%cea%' THEN 65
    WHEN lower(ce.name) LIKE '%immunogenicity%' OR lower(ce.name) LIKE '%(ada)%' OR lower(ce.name) LIKE '%anti-drug antib%' THEN 280
    WHEN lower(ce.name) LIKE '%retrospective%' OR lower(ce.name) LIKE '%translational%' OR lower(ce.name) LIKE '%biomarker%' THEN 50
    WHEN lower(ce.name) ~ '\ypk\y' OR lower(ce.name) LIKE '%pharmacokinet%' THEN 85
    WHEN lower(ce.name) LIKE '%ophthalmolog%' OR lower(ce.name) LIKE '%eye exam%' THEN 150
    WHEN lower(ce.name) LIKE '%tsh%' OR lower(ce.name) LIKE '%thyroid%' THEN 55
    WHEN lower(ce.name) LIKE '%survival%' OR lower(ce.name) LIKE '%follow-up contact%' THEN 280
    WHEN lower(ce.name) LIKE '%unscheduled%' OR lower(ce.name) LIKE '%toxicity%' THEN 480
    WHEN lower(ce.name) LIKE '%inclusion%' OR lower(ce.name) LIKE '%exclusion%' OR lower(ce.name) LIKE '%eligibility criteria%' THEN 120
    WHEN lower(ce.name) LIKE '%medical%' AND lower(ce.name) LIKE '%history%' THEN 150
    WHEN lower(ce.name) LIKE '%demographic%' THEN 50
    WHEN lower(ce.name) LIKE '%informed consent%' THEN 180
    WHEN lower(ce.name) LIKE '%dpd%' THEN 150
    WHEN lower(ce.name) LIKE '%pre-medication%' OR lower(ce.name) LIKE '%premedication%' THEN 35
    WHEN lower(ce.name) LIKE '%dose modification%' THEN 45
    WHEN lower(ce.name) LIKE '%genetic%' OR lower(ce.name) LIKE '%pharmacogenom%' THEN 850
    WHEN lower(ce.name) LIKE '%administration%' OR lower(ce.name) LIKE '%tislelizumab%' OR lower(ce.name) LIKE '%infusion%' OR lower(ce.name) LIKE '%study drug%' THEN 185
    ELSE 100   -- generic per-visit assessment: never leave a $0/empty cost
  END,
  'USD', CURRENT_DATE, 'market-standard-fill', false
FROM cost_element ce
WHERE ce.is_active = true
  AND NOT EXISTS (
    SELECT 1 FROM element_cost_version v
    WHERE v.element_id = ce.id AND v.base_unit_cost > 0
  );

-- ── 2. Budget milestones (per-template instances) ───────────────────────────
UPDATE budget_milestone SET unit_cost = (
  CASE
    WHEN lower(name) LIKE '%initial%' AND lower(name) LIKE '%irb%' THEN 2500
    WHEN lower(name) LIKE '%irb%' AND (lower(name) LIKE '%close%' OR lower(name) LIKE '%termination%') THEN 800
    WHEN lower(name) LIKE '%irb%' AND lower(name) LIKE '%amendment%' THEN 500
    WHEN lower(name) LIKE '%irb%' AND (lower(name) LIKE '%continu%' OR lower(name) LIKE '%annual%') THEN 1200
    WHEN lower(name) LIKE '%irb%' THEN 2500
    WHEN lower(name) LIKE '%archiv%' OR lower(name) LIKE '%retention%' OR lower(name) LIKE '%storage%' THEN 600
    WHEN lower(name) LIKE '%destruction%' THEN 600
    WHEN lower(name) LIKE '%pharmacy%' AND lower(name) LIKE '%lab%' THEN 2400
    WHEN lower(name) LIKE '%pharmacy%' THEN 1200
    WHEN lower(name) LIKE '%lab%' AND lower(name) LIKE '%setup%' THEN 1200
    WHEN lower(name) LIKE '%ctms%' THEN 800
    WHEN lower(name) LIKE '%cta%' OR lower(name) LIKE '%legal%' THEN 1500
    WHEN lower(name) LIKE '%medicare%' OR lower(name) LIKE '%coverage analysis%' OR lower(name) LIKE '%mca%' THEN 2000
    WHEN lower(name) LIKE '%screen fail%' THEN 450
    WHEN lower(name) LIKE '%feasibility%' THEN 1500
    WHEN lower(name) LIKE '%siv%' OR lower(name) LIKE '%initiation%' THEN 2000
    WHEN lower(name) LIKE '%translation%' THEN 1200
    WHEN lower(name) LIKE '%insurance%' OR lower(name) LIKE '%indemnity%' THEN 2000
    WHEN lower(name) LIKE '%contingency%' THEN 5000
    WHEN lower(name) LIKE '%monitoring%' THEN 800
    ELSE 500   -- generic milestone fallback
  END
)
WHERE unit_cost IS NULL OR unit_cost = 0;

-- ── 3. Milestone library (master catalog), if any are blank there ────────────
UPDATE milestone_library_item SET default_amount = (
  CASE
    WHEN lower(name) LIKE '%initial%' AND lower(name) LIKE '%irb%' THEN 2500
    WHEN lower(name) LIKE '%irb%' AND (lower(name) LIKE '%close%' OR lower(name) LIKE '%termination%') THEN 800
    WHEN lower(name) LIKE '%irb%' AND lower(name) LIKE '%amendment%' THEN 500
    WHEN lower(name) LIKE '%irb%' THEN 1200
    WHEN lower(name) LIKE '%archiv%' OR lower(name) LIKE '%retention%' OR lower(name) LIKE '%storage%' THEN 600
    WHEN lower(name) LIKE '%destruction%' THEN 600
    WHEN lower(name) LIKE '%pharmacy%' THEN 1200
    WHEN lower(name) LIKE '%lab%' THEN 1200
    WHEN lower(name) LIKE '%contingency%' THEN 5000
    WHEN lower(name) LIKE '%insurance%' OR lower(name) LIKE '%indemnity%' THEN 2000
    ELSE 500
  END
)
WHERE default_amount IS NULL OR default_amount = 0;

COMMIT;

-- Verify — all three should return 0 rows:
-- SELECT ce.code, ce.name FROM cost_element ce WHERE ce.is_active
--   AND NOT EXISTS (SELECT 1 FROM element_cost_version v WHERE v.element_id=ce.id AND v.base_unit_cost>0);
-- SELECT name FROM budget_milestone WHERE unit_cost IS NULL OR unit_cost=0;
-- SELECT name FROM milestone_library_item WHERE default_amount IS NULL OR default_amount=0;
