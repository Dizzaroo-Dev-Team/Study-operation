# Frontend-CRM E2E (Playwright)

End-to-end tests for the core Communications flows. These run against a **local,
isolated Mongo** (`crm_e2e_test`) with a seeded member + non-member — never the
shared Atlas cluster. Env vars live in `e2e/.env.e2e` (LOCAL TEST ONLY) and are
auto-loaded; no manual exports needed.

**Setup + run:** see the "E2E (Playwright) — repeatable local setup" section in
the repo-root [`TESTING.md`](../../TESTING.md). TL;DR: switch `Backend-CRM/.env`
to local Mongo + bypass off + kafka off, `docker compose --profile local-mongo
up -d mongo`, recreate backend/worker, `docker compose exec backend python -m
scripts.seed_e2e`, then `npm run test:e2e`. All 5 specs pass headless.

## What's here

| File | Covers | Needs a member session? |
|------|--------|--------------------------|
| `session.smoke.spec.ts` | Login + token revalidation boots into the app | member (1 of 2 cases) |
| `conversation-send.spec.ts` | Create conversation → send → live render → persist on reload | yes |
| `thread-merge.spec.ts` | Create thread → post → combine two threads → merged shows | yes |
| `attachment.spec.ts` | Upload an attachment → download it back | yes |
| `non-member-denied.spec.ts` | Non-member cannot list a study's conversations (LEAK-1 guard) | non-member token |
| `fixtures/auth.ts` | `memberPage` / `nonMemberPage` fixtures (API login → localStorage inject) | — |
| `fixtures/nav.ts` | Navigate to the Communications area by visible text | — |

## Run it

```bash
# from Frontend-CRM/
npm run test:e2e            # headless
npm run test:e2e:ui         # Playwright UI mode
npx playwright test session.smoke.spec.ts   # just the harness smoke
```

Vite is started automatically (`reuseExistingServer: true`, port 3000) and
pointed at the backend via `VITE_API_BASE=$E2E_API_URL/api`, auth mode `local`.

## Environment contract

| Var | Default | Meaning |
|-----|---------|---------|
| `E2E_BASE_URL` | `http://127.0.0.1:3000` | Frontend origin (Vite dev port) |
| `E2E_API_URL` | `http://127.0.0.1:8000` | Backend origin (no `/api` suffix) |
| `E2E_USER_EMAIL` | — (required) | Member account email |
| `E2E_USER_PASSWORD` | — (required) | Member account password |
| `E2E_STUDY_ID` | — (required) | Study the member belongs to |
| `E2E_NONMEMBER_EMAIL` | — (optional) | Account that is NOT a member of `E2E_STUDY_ID` |
| `E2E_NONMEMBER_PASSWORD` | — (optional) | |

PowerShell example:

```powershell
$env:E2E_USER_EMAIL = 'member@your-dev.test'
$env:E2E_USER_PASSWORD = '...'
$env:E2E_STUDY_ID = '<study-uuid>'
npm run test:e2e
```

## The one blocker (S2)

The flow specs need a **logged-in study-member session**. The harness obtains it
by calling `POST /api/auth/login` (Mongo `local_users`) and injecting the JWT —
so the account must:

1. **Exist in the auth DB** the backend-under-test points at, with a known
   password, and
2. **Be a member of `E2E_STUDY_ID`** via IAM `resource_access`
   (Mongo `local_app_user_attributes`: `attributeName: "resource_access"`,
   `value: [{ role, resource_id }]` where `resource_id == study_id`), enforced
   when `comms_enforce_membership=true`.

Two ways to satisfy this:

- **Point at a dev/test backend you own** (NOT shared/production) and set the
  `E2E_USER_*` / `E2E_STUDY_ID` to an existing member there. This is the
  fastest path if such an account already exists.
- **Provision a member on a local seedable stack**: stand the backend up against
  local Mongo (`127.0.0.1:27017`, a DB whose name contains `test`) and local
  Postgres, then seed (a) a `local_users` doc and (b) a `resource_access`
  attribute for the study. The `non-member-denied` spec additionally wants a
  second account WITHOUT that membership.

> The harness itself is verified: the anonymous half of `session.smoke` passes
> against the live login page today. Only the member-account provisioning is
> outstanding — supply the env vars above and the flow specs run as-is. Confirm
> the `fixtures/nav.ts` Communications nav label and the in-spec selectors on
> first green run; add `data-testid`s where a selector is ambiguous.
