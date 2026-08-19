# Migrations audit (Phase 6.1)

Snapshot of the `migrations/` tree taken during the refactor. **Read-only inventory** — no files are moved by this commit. Use the recommendations as a checklist for the next migration sweep.

## File tally

| Bucket | `.py` | `.sql` | Notes |
|---|---:|---:|---|
| `migrations/` (root, loose) | 0 | **26** | Hot-fix scripts accumulated outside the bootstrap. Action needed. |
| `migrations/schema/` | 56 | 2 | Historical per-feature scripts. Already documented as not run by new devs. |
| `migrations/seed/` | 2 | 0 | Idempotent master-data seeders. Keep. |
| `migrations/archive/` | 15 | 4 | Superseded scripts. Keep, do not run. |
| `migrations/README.md` | — | — | Existing dev-onboarding doc. |

**Canonical source of truth:** `scripts/setup_local_db_full.sql` (1,025 lines). New environments start here. Individual scripts in `schema/` are for replaying one specific change against an existing environment.

**No Alembic.** `alembic.ini` and `migrations/versions/` do not exist. The team chose a consolidated-bootstrap strategy instead. The original refactor plan's "Alembic-only going forward" recommendation does not match the team's actual practice — replaced with the recommendation below.

## The 26 loose `.sql` files at `migrations/` root

These are the files that need triage. Each should be classified into ONE of three buckets:

- **CONSOLIDATE** — fold into `scripts/setup_local_db_full.sql` so new environments get it automatically; keep the script file for reference under `archive/`.
- **ARCHIVE** — already-applied data fix, no schema change to preserve. Move to `archive/`.
- **KEEP** — pending in some environment, not yet applied everywhere. Leave at root until applied.

### Recommended classifications (based on filename heuristics — verify against prod before moving)

**Schema additions → CONSOLIDATE into bootstrap then archive the script:**
- `add_agreement_document_comments.sql`
- `add_agreement_edit_lock_fields.sql`
- `add_agreement_review_documents_table.sql`
- `add_agreement_review_tables.sql`
- `add_document_file_url.sql`
- `add_document_workflow_fields.sql`
- `add_facility_and_pi_id_to_sites.sql`
- `add_irb_performance_indexes.sql`
- `add_monitoring_visit_reports.sql`
- `add_pi_designation_and_department.sql`
- `add_site_coordinator_phone_to_site_profiles.sql`
- `add_study_site_id_to_workflow_steps.sql`
- `add_template_file_url.sql`
- `add_uppercase_userrole_enum_values.sql`
- `add_visit_reschedule_requests.sql`
- `add_widget_schedule_and_milestone_library.sql`

**Data fixes / renames → ARCHIVE (no need to keep in bootstrap):**
- `rename_chcams_iec_name.sql`
- `rename_heidelberg_iec_name.sql`
- `rename_md_anderson_irb_name.sql`
- `rename_oxford_iec.sql`
- `rename_oxford_site_name_to_cancer_hematology_centre_uk.sql`
- `reset_md_anderson_irb_required_documents.sql`
- `reset_tmc_iec_required_documents.sql`
- `update_oxford_rec_document_requirements.sql`
- `delete_placeholder_monitoring_visits.sql`

**Structural drop → CONSOLIDATE then archive:**
- `drop_study_id_site_irb_mapping.sql`

## Recommended process for triage

1. **For each ADD/DROP file** — confirm the change is present in production. If yes: verify `setup_local_db_full.sql` already covers it (search for the table/column name). If not, append the change to the bootstrap, then move the script to `archive/`.
2. **For each RENAME/RESET/UPDATE/DELETE file** — these are one-time data fixes. Confirm applied in all environments, then move directly to `archive/`. Do **not** include in the bootstrap (data fixes don't belong in schema setup).
3. **After the sweep** — the root of `migrations/` should contain only `README.md`, this `AUDIT.md`, and any genuinely pending scripts. Going forward: new hot-fixes land at root with a one-line entry in this doc; they get archived once applied in all environments.

## Why not Alembic?

The team's existing strategy (one consolidated bootstrap + per-environment hot-fix scripts that get folded back into the bootstrap) is a deliberate, valid alternative to Alembic. It trades:

- **Pro:** New environments bootstrap from one file, no version chain to apply sequentially.
- **Pro:** Schema reviewable as a single artifact during code review.
- **Pro:** No risk of migration ordering bugs (you've already had one — see `delete_placeholder_monitoring_visits.sql`).
- **Con:** No automatic backward-migration / rollback story.
- **Con:** Drift between bootstrap and prod is undetectable without manual diffing.

If the team ever wants to switch to Alembic, the first step would be to capture the current bootstrap as the **initial revision** and stamp every existing environment to that revision. That is a multi-day project requiring production-database access; do not attempt during a feature PR.

## What this audit does NOT do

- Does not move any file (read-only commit).
- Does not verify the recommended classifications against prod state — that requires running queries against the live database.
- Does not check the `schema/` scripts against the bootstrap for drift (~58 files — separate audit).
