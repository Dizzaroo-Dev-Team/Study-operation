# pgBouncer deployment plan

> Status: **not deployed yet**. Use this doc when scaling past 2 uvicorn
> workers, OR when total Postgres connections start brushing the cluster
> limit (Neon free tier is 100, paid varies).

## Why pgBouncer

Each uvicorn worker holds its own SQLAlchemy connection pool. After Hunt 3
the defaults are `pool_size=20, max_overflow=40` per worker, so:

| Workers | Peak PG connections |
|---|---|
| 1 | up to 60 |
| 2 | up to 120 |
| 4 | up to 240 |
| 8 | up to 480 |

Beyond ~50 actual connections, Postgres performance degrades and Neon free
tier blocks new connections. pgBouncer in **transaction-pooling** mode lets
1000+ app-side connections share ~25 actual Postgres connections by
checking out a backend connection only for the duration of a transaction.

## Constraints with transaction-mode pooling

Transaction-mode pooling **forbids session-level features**:

- ❌ Server-side cursors (`SELECT ... FOR HOLD`)
- ❌ Prepared statements (libpq-managed)
- ❌ `LISTEN`/`NOTIFY`
- ❌ Advisory locks
- ❌ `SET LOCAL` / session variables

asyncpg by default uses prepared statements internally. **Disable them in
the SQLAlchemy URL** by adding `?prepared_statement_cache_size=0`. Set this
in the App Service `DATABASE_URL` env, not in code, so dev (which doesn't
go through pgBouncer) keeps the default.

The app **does not currently use** LISTEN/NOTIFY or advisory locks (grep
checked: zero hits in `app/`). Server-side cursors aren't used either. So
transaction-mode is safe.

## docker-compose change

Add this service to `Backend-CRM/docker-compose.yml` next to `postgres`:

```yaml
  pgbouncer:
    image: edoburu/pgbouncer:1.22.1
    environment:
      DB_USER: ${POSTGRES_USER:-crm_user}
      DB_PASSWORD: ${POSTGRES_PASSWORD:-crm_pass}
      DB_HOST: postgres
      DB_NAME: ${POSTGRES_DB:-crm_db}
      POOL_MODE: transaction
      MAX_CLIENT_CONN: 1000
      DEFAULT_POOL_SIZE: 25
      RESERVE_POOL_SIZE: 5
      RESERVE_POOL_TIMEOUT: 3
      SERVER_RESET_QUERY: DISCARD ALL
      # Required for asyncpg compatibility — keep TLS off between
      # pgbouncer and postgres on the docker network; clients talk to
      # pgbouncer over plain TCP and TLS is terminated by App Service in prod.
      AUTH_TYPE: md5
    ports:
      - "6432:5432"   # expose on host port 6432 for local debugging
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h localhost -p 5432 -U ${POSTGRES_USER:-crm_user}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

## App env change

In the `backend` and `worker` services, change `DATABASE_URL`:

```diff
- DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-crm_user}:${POSTGRES_PASSWORD:-crm_pass}@postgres:5432/${POSTGRES_DB:-crm_db}
+ DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-crm_user}:${POSTGRES_PASSWORD:-crm_pass}@pgbouncer:5432/${POSTGRES_DB:-crm_db}?prepared_statement_cache_size=0
```

And add a dependency:

```yaml
    depends_on:
      pgbouncer:
        condition: service_healthy
      redis:
        condition: service_healthy
```

(Replaces the direct `postgres` dependency.)

## Pool sizing alongside pgBouncer

When pgBouncer is in front, the app pool can be **larger** (since pgBouncer
is the real funnel to Postgres). Bump:

```
DB_POOL_SIZE=50
DB_MAX_OVERFLOW=100
```

per worker. With pgBouncer's `DEFAULT_POOL_SIZE=25` actually hitting
Postgres, you can have any number of app-side connections without
swamping the database.

## Prod (Azure App Service)

Two options:

1. **Sidecar in the same App Service plan** — add a second container in
   the compose file deployed to Azure Web App for Containers. Lowest
   latency, simplest networking. Needs the App Service plan to support
   multi-container (Linux + compose).
2. **Separate Container Instance** — runs pgBouncer in its own ACI,
   reachable over a private VNet. More complex but isolates pgBouncer
   failure from the app.

For most setups, option 1. For Neon (which already has its own pgBouncer
in front of every project), you may not need this at all — just point
`DATABASE_URL` at Neon's pooler endpoint (`-pooler` host suffix).

## Verification after deploy

```sql
-- inside the postgres container, check active connections from pgBouncer
SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE 'pgbouncer%';
```

Should stay near `DEFAULT_POOL_SIZE` (25) regardless of app traffic.

```bash
# pgBouncer admin console
psql -h localhost -p 6432 -U pgbouncer pgbouncer
SHOW POOLS;
SHOW STATS;
```

## Rollback

If something breaks, point `DATABASE_URL` back at `postgres:5432` (skip
pgbouncer) and `docker compose up -d backend worker`. Single env-var change.
