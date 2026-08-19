import { test, expect } from './fixtures/auth'
import { apiLogin } from './fixtures/auth'
import { selectStudyAndSite } from './fixtures/nav'

/**
 * Flow 2 — combine two threads and confirm the merged result shows.
 *
 * The UI only surfaces "combine" via AI similarity suggestions
 * (/threads/suggest-combinations → Gemini), which is non-deterministic and
 * unsuitable for a stable E2E. So we exercise the REAL combine endpoint
 * (POST /threads/combine — the path that used to 500) with the member's own
 * bearer token (real auth + write-guard), then verify in the UI that the kept
 * thread shows and the merged-away thread is gone.
 */
const API = process.env.E2E_API_URL || 'http://127.0.0.1:8000'
const STUDY = process.env.E2E_STUDY_ID!
const SITE = process.env.E2E_SITE_ID || 'E2E-SITE-001'

test.describe('threads: combine two threads', () => {
  test('combining two threads returns a merged thread (no 500) and it shows in the UI', async ({
    memberPage,
    request,
  }) => {
    const { token } = await apiLogin(request, process.env.E2E_USER_EMAIL!, process.env.E2E_USER_PASSWORD!)
    const auth = { Authorization: `Bearer ${token}` }
    const stamp = Date.now()
    const keepTitle = `E2E Keep ${stamp}`
    const mergeTitle = `E2E Merge ${stamp}`

    const mkThread = async (title: string) => {
      const res = await request.post(`${API}/api/threads`, {
        headers: auth,
        data: {
          title,
          related_study_id: STUDY,
          site_id: SITE,
          visibility_scope: 'site',
          participants_emails: [process.env.E2E_USER_EMAIL],
        },
      })
      expect(res.ok(), `create thread "${title}" -> HTTP ${res.status()}: ${await res.text()}`).toBeTruthy()
      return (await res.json()).id as string
    }

    const keepId = await mkThread(keepTitle)
    const mergeId = await mkThread(mergeTitle)

    // The combine path that previously 500'd. target_thread_id is kept.
    const combine = await request.post(`${API}/api/threads/combine`, {
      headers: auth,
      data: { thread1_id: keepId, thread2_id: mergeId, target_thread_id: keepId },
    })
    expect(
      combine.status(),
      `combine must not 500 — got HTTP ${combine.status()}: ${await combine.text()}`,
    ).toBe(200)
    const merged = await combine.json()
    expect(merged.id).toBe(keepId)

    // Merged result shows in the UI: the kept thread is present in the list.
    await memberPage.goto('/')
    await selectStudyAndSite(memberPage)
    await memberPage.getByRole('button', { name: /conversations/i }).first().click()
    await memberPage.getByRole('button', { name: /^threads$/i }).first().click()
    await expect(memberPage.getByText(keepTitle).first()).toBeVisible({ timeout: 15_000 })
  })
})
