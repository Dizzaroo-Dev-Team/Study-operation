import { Page, expect } from '@playwright/test'

/**
 * Navigation helpers for the flow specs.
 *
 * The CRM shell uses in-app tab navigation via sidebar BUTTONS (not routed
 * links). The Communications area additionally requires a site to be selected
 * via the navbar <select> dropdowns ("Select a site first" otherwise). The
 * localStorage hydration of the last site is racy, so we deterministically
 * drive the dropdowns instead.
 *
 * Study/site names default to the seeded E2E values; override via env if your
 * seed differs.
 */
const STUDY_NAME = process.env.E2E_STUDY_NAME || 'E2E Test Study'
const SITE_NAME = process.env.E2E_SITE_NAME || 'E2E Test Site'

/** Select the seeded study + site via the navbar dropdowns. */
export async function selectStudyAndSite(page: Page): Promise<void> {
  await expect(page.locator('input[type="password"]')).toHaveCount(0)

  const studySelect = page.locator(`select:has(option:text-is("${STUDY_NAME}"))`).first()
  if (await studySelect.count()) {
    await studySelect.selectOption({ label: STUDY_NAME }).catch(() => {})
  }

  // The site dropdown only populates after the study's sites load.
  const siteSelect = page.locator(`select:has(option:text-is("${SITE_NAME}"))`).first()
  await expect(siteSelect, 'site dropdown with the seeded site').toBeVisible({ timeout: 15_000 })
  await siteSelect.selectOption({ label: SITE_NAME })
}

export async function gotoCommunications(page: Page): Promise<void> {
  await page.goto('/')
  await selectStudyAndSite(page)
  await page.getByRole('button', { name: /conversations/i }).first().click()
}

/**
 * Type + send a message in the open conversation composer.
 *
 * Uses Enter, not the Send button: a fixed "Ask Me Anything" FAB sits over the
 * bottom-right Send button and intercepts pointer clicks. Enter (keyboard) is
 * the documented send shortcut and bypasses the overlay. The member fixture
 * auto-accepts the AI pre-send confirm dialog.
 */
export async function sendMessage(page: Page, text: string): Promise<void> {
  const input = page.getByPlaceholder(/Type a message/)
  await expect(input).toBeVisible({ timeout: 15_000 })
  await input.click()
  await input.pressSequentially(text, { delay: 15 })
  // A slow AI pre-send check runs before the actual POST, so wait for the
  // message POST to COMPLETE before returning — otherwise a quick reload races
  // ahead of persistence and the message is lost (optimistic render only).
  const posted = page.waitForResponse(
    (r) => /\/conversations\/[^/]+\/messages$/.test(r.url()) && r.request().method() === 'POST',
    { timeout: 25_000 },
  )
  await input.press('Enter')
  await posted
}
