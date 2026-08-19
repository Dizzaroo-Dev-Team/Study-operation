import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth'

/**
 * Flow 4 — a non-member must NOT be able to read a member's private conversation.
 *
 * Regression guard for LEAK-1 (cross-study read leak) + the membership gate
 * (comms_enforce_membership). Runs at the API layer with real bearer tokens —
 * robust and immune to UI selector drift.
 *
 * Note: system "notice_board" conversations are PUBLIC by design ("persistent
 * public board for everyone"), so the assertion targets a member-created
 * PRIVATE (thread-type) conversation — the thing that must never leak.
 */
const API = process.env.E2E_API_URL || 'http://127.0.0.1:8000'
const STUDY = process.env.E2E_STUDY_ID!
const SITE = process.env.E2E_SITE_ID || 'E2E-SITE-001'

test.describe('access control: non-member cannot read a member private conversation', () => {
  test('non-member is denied a member-created conversation (list + direct GET)', async ({ request }) => {
    const email = process.env.E2E_NONMEMBER_EMAIL
    const password = process.env.E2E_NONMEMBER_PASSWORD
    test.skip(!email || !password || !STUDY, 'requires E2E_NONMEMBER_* and E2E_STUDY_ID')

    // Member creates a private conversation.
    const { token: memberToken } = await apiLogin(
      request,
      process.env.E2E_USER_EMAIL!,
      process.env.E2E_USER_PASSWORD!,
    )
    const subject = `E2E Private ${Date.now()}`
    const created = await request.post(`${API}/api/conversations`, {
      headers: { Authorization: `Bearer ${memberToken}` },
      data: { subject, study_id: STUDY, site_id: SITE },
    })
    expect(created.ok(), `member create -> ${created.status()}`).toBeTruthy()
    const privateConvId = (await created.json()).id

    // Non-member logs in.
    const { token: nonToken } = await apiLogin(request, email!, password!)
    const nonAuth = { Authorization: `Bearer ${nonToken}` }

    // (a) The member's private conversation must NOT appear in the non-member's
    //     study listing. (Public notice_board entries may appear — exclude them.)
    const listRes = await request.get(`${API}/api/conversations`, {
      params: { study_id: STUDY },
      headers: nonAuth,
    })
    if (listRes.ok()) {
      const items = await listRes.json()
      const leaked = (items as Array<Record<string, unknown>>).filter(
        (c) => c.conversation_type !== 'notice_board' && c.id === privateConvId,
      )
      expect(leaked, "non-member must not see the member's private conversation").toHaveLength(0)
    } else {
      expect(listRes.status(), 'list should be 403 if not filtered').toBe(403)
    }

    // (b) Direct fetch of that conversation by id must be denied (not 200).
    const direct = await request.get(`${API}/api/conversations/${privateConvId}`, { headers: nonAuth })
    expect(
      direct.status(),
      `non-member direct GET should be denied (403/404), got ${direct.status()}`,
    ).not.toBe(200)
  })
})
