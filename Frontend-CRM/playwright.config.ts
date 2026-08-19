import { defineConfig, devices } from '@playwright/test'
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// Load e2e/.env.e2e (LOCAL TEST ONLY) without adding a dotenv dependency.
// Existing process.env values win, so CI/shell overrides still work.
const HERE = dirname(fileURLToPath(import.meta.url))
const envFile = join(HERE, 'e2e', '.env.e2e')
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/)
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2]
  }
}

/**
 * Playwright E2E config for Frontend-CRM.
 *
 * Everything is env-driven so the same specs run against a local dev stack or
 * a CI test stack WITHOUT code edits:
 *   E2E_BASE_URL   frontend origin            (default http://127.0.0.1:5173)
 *   E2E_API_URL    backend origin (no /api)   (default http://127.0.0.1:8000)
 *   E2E_USER_EMAIL / E2E_USER_PASSWORD        member account (study member)
 *   E2E_STUDY_ID                              study the member belongs to
 *   E2E_NONMEMBER_EMAIL / E2E_NONMEMBER_PASSWORD  non-member account (optional)
 *
 * See e2e/README.md for the full contract and how to provision a member.
 */
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:3000'
const API_URL = process.env.E2E_API_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  testDir: './e2e',
  // The flows mutate shared server state (conversations/threads), so keep the
  // suite serial and single-worker until per-test data isolation exists.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  // Sends trigger a real AI pre-send check (Gemini) that can take 10-20s, so
  // flows need generous budgets.
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Auto-start Vite if it isn't already running. Points the FE at E2E_API_URL
  // and forces local (email+password / localStorage-JWT) auth mode so the
  // session fixture can inject a token.
  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      // All backend routers mount under /api (see Backend-CRM/app/main.py), so
      // the FE base must include it.
      VITE_API_BASE: `${API_URL}/api`,
      VITE_IAM_AUTH_MODE: 'local',
    },
  },
})
