import { test, expect } from './fixtures/auth'
import { gotoCommunications, selectStudyAndSite, sendMessage } from './fixtures/nav'

/**
 * Flow 1 — create a conversation, send a message, see it render live in the
 * open panel, then reload and confirm it persisted.
 *
 * Guards the live-render path (message appears in the open panel) and the
 * queued->sending dispatch path (the message is actually saved, so it survives
 * a reload — not just an optimistic render).
 */
test.describe('conversation: send + live render + persist', () => {
  test('a sent message renders live and survives reload', async ({ memberPage }) => {
    const page = memberPage
    await gotoCommunications(page)

    const subject = `E2E Conv ${Date.now()}`
    const marker = `e2e-msg-${Date.now()}`

    // Create the conversation (icon button: aria-label "New conversation").
    await page.getByRole('button', { name: /new conversation/i }).first().click()
    await page.getByPlaceholder('Conversation subject').fill(subject)
    await page.getByRole('button', { name: /^create$/i }).click()

    // The new conversation auto-opens; send a uniquely-identifiable message.
    await sendMessage(page, marker)

    // Live render in the open panel.
    await expect(page.getByText(marker).first()).toBeVisible({ timeout: 15_000 })

    // Persistence: reload, re-navigate, reopen the conversation, confirm the
    // message is still there (it was actually saved, not just optimistic).
    await page.reload()
    await selectStudyAndSite(page)
    await page.getByRole('button', { name: /conversations/i }).first().click()
    await page.getByText(subject).first().click()
    await expect(page.getByText(marker).first()).toBeVisible({ timeout: 15_000 })
  })
})
