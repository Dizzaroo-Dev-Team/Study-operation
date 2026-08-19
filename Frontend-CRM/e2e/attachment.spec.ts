import { test, expect } from './fixtures/auth'
import { apiLogin } from './fixtures/auth'

/**
 * Flow 3 — upload an attachment and download it back (round-trip).
 *
 * Exercises the attachment upload + download paths with real member auth —
 * including download_attachment, which carried one of the dict-vs-object bugs.
 * Driven through the API (multipart upload + binary download) so the byte
 * round-trip is asserted exactly; the conversation attachment store is the
 * local filesystem (settings.upload_dir), so nothing external is touched.
 */
const API = process.env.E2E_API_URL || 'http://127.0.0.1:8000'
const STUDY = process.env.E2E_STUDY_ID!
const SITE = process.env.E2E_SITE_ID || 'E2E-SITE-001'

test.describe('attachments: upload + download round-trip', () => {
  test('an uploaded file downloads back byte-for-byte', async ({ request }) => {
    const { token } = await apiLogin(request, process.env.E2E_USER_EMAIL!, process.env.E2E_USER_PASSWORD!)
    const auth = { Authorization: `Bearer ${token}` }

    // A conversation to attach to.
    const convRes = await request.post(`${API}/api/conversations`, {
      headers: auth,
      data: { subject: `E2E Attach ${Date.now()}`, study_id: STUDY, site_id: SITE },
    })
    expect(convRes.ok(), `create conv -> ${convRes.status()}`).toBeTruthy()
    const convId = (await convRes.json()).id

    // Upload a file (multipart).
    const payload = `e2e attachment payload ${Date.now()}`
    const fileName = `e2e-attach-${Date.now()}.txt`
    const upRes = await request.post(`${API}/api/conversations/${convId}/attachments`, {
      headers: auth,
      multipart: {
        file: { name: fileName, mimeType: 'text/plain', buffer: Buffer.from(payload) },
      },
    })
    expect(upRes.ok(), `upload -> HTTP ${upRes.status()}: ${await upRes.text()}`).toBeTruthy()
    const attachmentId = (await upRes.json()).id
    expect(attachmentId).toBeTruthy()

    // Download it back and assert the bytes match (download_attachment is one of
    // the dict-vs-object fixes — a regression here would 500 or corrupt).
    const dlRes = await request.get(`${API}/api/attachments/${attachmentId}/download`, { headers: auth })
    expect(dlRes.status(), `download -> HTTP ${dlRes.status()}: ${await dlRes.text()}`).toBe(200)
    expect(await dlRes.text()).toBe(payload)
  })
})
