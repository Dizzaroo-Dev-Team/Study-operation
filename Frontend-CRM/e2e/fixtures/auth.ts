import { test as base, expect, Page, APIRequestContext } from '@playwright/test'

/**
 * Authenticated-session fixtures.
 *
 * The CRM's local auth mode (VITE_IAM_AUTH_MODE=local) works like this:
 *   1. POST /api/auth/login (form-encoded username+password) -> { access_token, user }
 *   2. FE stores `auth_token` + `auth_user` in localStorage
 *   3. AuthContext revalidates the token via GET /api/auth/me on boot
 *
 * These fixtures reproduce step 1 against the API directly, then inject the
 * token+user into localStorage via addInitScript so the app boots already
 * authenticated — no clicking through the login form (faster + less brittle).
 *
 * MEMBERSHIP: study access is governed by IAM `resource_access` (Mongo
 * local_app_user_attributes), enforced when comms_enforce_membership=true. The
 * E2E_USER_* account MUST already be a member of E2E_STUDY_ID. The
 * E2E_NONMEMBER_* account must NOT be — it backs the negative-access test.
 *
 * Required env (see e2e/README.md): E2E_API_URL, E2E_USER_EMAIL,
 * E2E_USER_PASSWORD, E2E_STUDY_ID. Optional: E2E_NONMEMBER_EMAIL/PASSWORD.
 */

const API_URL = process.env.E2E_API_URL || 'http://127.0.0.1:8000'

export interface Session {
  token: string
  user: Record<string, unknown>
}

/** Log in against the backend and return the bearer token + user dict. */
export async function apiLogin(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<Session> {
  const res = await request.post(`${API_URL}/api/auth/login`, {
    form: { username: email, password },
  })
  if (!res.ok()) {
    throw new Error(
      `Login failed for ${email}: HTTP ${res.status()} ${await res.text()}\n` +
        `Check E2E_USER_EMAIL/E2E_USER_PASSWORD and that the backend at ${API_URL} ` +
        `is reachable and pointed at a DB where this account exists.`,
    )
  }
  const body = await res.json()
  return { token: body.access_token, user: body.user }
}

/** Boot a page already authenticated as the given session. */
export async function applySession(page: Page, session: Session): Promise<void> {
  await page.addInitScript((s) => {
    localStorage.setItem('auth_token', s.token)
    localStorage.setItem('auth_user', JSON.stringify(s.user))
  }, session)
}

/**
 * Pre-select the study + site in localStorage so the member lands in a ready
 * state (the Conversations area shows "Select a site first" until a site is
 * chosen, and sites do not auto-select). Storage keys match StudySiteContext.
 */
export async function applyStudySiteSelection(page: Page): Promise<void> {
  const studyId = process.env.E2E_STUDY_ID
  const siteId = process.env.E2E_SITE_ID
  if (!studyId || !siteId) return
  await page.addInitScript(
    (sel) => {
      localStorage.setItem('dizzaroo_selected_study', sel.studyId)
      localStorage.setItem('dizzaroo_selected_site', sel.siteId)
    },
    { studyId, siteId },
  )
}

function requireEnv(name: string): string {
  const v = process.env[name]
  if (!v) {
    throw new Error(
      `Missing required env var ${name}. E2E auth needs a real member account — ` +
        `see e2e/README.md. (This is the documented S2 blocker: a logged-in ` +
        `member session must be provisioned before these specs can run.)`,
    )
  }
  return v
}

type Fixtures = {
  /** A page authenticated as a study MEMBER (E2E_USER_*). */
  memberPage: Page
  /** A page authenticated as a NON-member (E2E_NONMEMBER_*). */
  nonMemberPage: Page
  /** The study id the member belongs to. */
  studyId: string
}

export const test = base.extend<Fixtures>({
  studyId: async ({}, use) => {
    await use(requireEnv('E2E_STUDY_ID'))
  },

  memberPage: async ({ browser, request }, use) => {
    const session = await apiLogin(
      request,
      requireEnv('E2E_USER_EMAIL'),
      requireEnv('E2E_USER_PASSWORD'),
    )
    const context = await browser.newContext()
    const page = await context.newPage()
    // Sending a message triggers an AI pre-send check that can pop a
    // window.confirm("AI noticed some issues… send anyway?"). Playwright
    // auto-DISMISSES unhandled dialogs (= Cancel), which silently aborts the
    // send. Accept so the flow proceeds as a normal user clicking "OK".
    page.on('dialog', (d) => d.accept().catch(() => {}))
    await applySession(page, session)
    await applyStudySiteSelection(page)
    await use(page)
    await context.close()
  },

  nonMemberPage: async ({ browser, request }, use) => {
    const session = await apiLogin(
      request,
      requireEnv('E2E_NONMEMBER_EMAIL'),
      requireEnv('E2E_NONMEMBER_PASSWORD'),
    )
    const context = await browser.newContext()
    const page = await context.newPage()
    await applySession(page, session)
    await use(page)
    await context.close()
  },
})

export { expect }
