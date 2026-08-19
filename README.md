# Study Operation

Monorepo containing the Study Operation CRM.

| Folder | Stack |
|---|---|
| [`Backend-CRM/`](Backend-CRM/) | Python · FastAPI · Postgres (SQLAlchemy + Alembic) · MongoDB · Celery |
| [`Frontend-CRM/`](Frontend-CRM/) | React · Vite · TypeScript · Tailwind CSS |

Each folder keeps its own `.gitignore`, dependency manifest, and build config, and is
developed independently.

## Configuration

No secrets are committed. Both apps read configuration from environment variables —
see `Backend-CRM/.env.example` for the backend, and `VITE_`-prefixed variables for the
frontend. Create the corresponding `.env` files locally; they are gitignored.
