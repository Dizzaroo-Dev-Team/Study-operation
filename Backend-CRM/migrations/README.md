## Migrations Folder

This directory contains one-off migration scripts used to evolve the PostgreSQL schema and data over time.

### Layout

- `schema/` – core schema and feature migrations that create or alter database tables and columns (e.g. agreements, templates, StudySite, feasibility, chat, access control, IRB admin).
- `seed/` – idempotent master-data seeders. Safe to run on any environment after schema is in place.
- `archive/` – historical or experimental migration scripts that have been **superseded** by `scripts/setup_local_db_full.sql` or by later migrations. Kept for audit purposes only. **Do not run in new environments.**

### New developers — start here

You almost never need to run the files in `schema/` one by one. The consolidated bootstrap covers them:

```bash
cd Backend-CRM
psql -d crm_local -v ON_ERROR_STOP=1 -f scripts/setup_local_db_full.sql
```

That produces a database with the same shape as Neon (the source of truth). For richer site-budgeting seeds, then run:

```bash
python migrations/seed/seed_budgeting_master_data.py
python migrations/seed/seed_categories_and_bundles.py
```

See `docs/SYNC_DATABASE_README.md` for the full workflow.

### When to use the individual scripts in `schema/`

- Applying a single hot-fix to an existing environment that has not yet picked up that change.
- Reviewing the historical evolution of a particular table.

### Rules

- These scripts are **not** imported by the FastAPI app — they're run manually (or via ops tooling).
- Do **not** delete or rewrite files in `schema/` without confirming with the migration history and production rollout plan. Move superseded files into `archive/` instead.
