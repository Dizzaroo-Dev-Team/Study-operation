import { test, expect } from './fixtures/auth'

/**
 * Harness smoke test — validates the auth fixture itself.
 *
 * This is the test to run FIRST. If it passes, the member-session machinery
 * (the documented S2 blocker) is working and the flow specs below can run. If
 * it fails, the flow specs would fail for the same reason — fix this first.
 */

test.describe('auth harness', () => {
  test('anonymous visitor is gated at the login screen', async ({ browser }) => {
    const ctx = await browser.newContext() // no session injected
    const page = await ctx.newPage()
    await page.goto('/')
    // Local mode shows an email+password form; the password field is the
    // most stable anonymous-state signal.
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await ctx.close()
  })

  test('member session boots straight into the authenticated app', async ({ memberPage }) => {
    await memberPage.goto('/')
    // Token revalidation (GET /api/auth/me) must succeed and keep us logged in.
    // If the token were rejected, AuthContext logs out and the password field
    // reappears — so its ABSENCE is our "authenticated" signal.
    await expect(memberPage.locator('input[type="password"]')).toHaveCount(0)
    const token = await memberPage.evaluate(() => localStorage.getItem('auth_token'))
    expect(token, 'auth_token should survive revalidation').toBeTruthy()
  })
})
