#!/usr/bin/env node
/**
 * Phase 4.5 boundary check.
 *
 * Rule: only files under src/services/, src/contexts/, src/features/<x>/services/,
 * src/modules/<x>/services/, or files matching *.api.ts/*.api.tsx may import
 * the shared axios instance from src/lib/api.
 *
 * Components must go through their feature's service module instead. This
 * keeps API surface drift out of the render tree and makes the surface
 * audited by code review.
 *
 * Usage:
 *   node scripts/check-api-imports.mjs           # report violations, exit 1 if any
 *   node scripts/check-api-imports.mjs --baseline # write current violations to .baseline
 *                                                 so CI fails only on NEW violations
 *
 * This is intentionally a tiny grep-based check rather than a full ESLint
 * setup. Frontend-CRM does not currently have ESLint wired up; introducing
 * it is a separate project. This script gives the team the guardrail now.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { readdir, stat } from 'node:fs/promises'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const REPO_ROOT = join(__dirname, '..')
const SRC = join(REPO_ROOT, 'src')
const BASELINE_PATH = join(__dirname, 'check-api-imports.baseline')

const API_IMPORT_RE = /from\s+['"](?:\.\.?\/)*lib\/api['"]|from\s+['"]@\/lib\/api['"]/

function isAllowedPath(relPath) {
  const norm = relPath.split(sep).join('/')
  if (norm.endsWith('.api.ts') || norm.endsWith('.api.tsx')) return true
  if (norm.includes('/services/')) return true
  if (norm.startsWith('contexts/')) return true
  // lib/api itself defines the axios client
  if (norm === 'lib/api.ts' || norm === 'lib/api.tsx') return true
  // generated codegen output
  if (norm.startsWith('api/generated/')) return true
  return false
}

async function* walk(dir) {
  for (const entry of await readdir(dir)) {
    if (entry === 'node_modules' || entry === '__tests__' || entry.startsWith('.')) continue
    const full = join(dir, entry)
    const st = await stat(full)
    if (st.isDirectory()) {
      yield* walk(full)
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry)) {
      yield full
    }
  }
}

const argv = process.argv.slice(2)
const writeBaseline = argv.includes('--baseline')

const violations = []
for await (const file of walk(SRC)) {
  const rel = relative(SRC, file)
  if (isAllowedPath(rel)) continue
  const body = readFileSync(file, 'utf8')
  if (API_IMPORT_RE.test(body)) {
    violations.push(rel.split(sep).join('/'))
  }
}

if (writeBaseline) {
  writeFileSync(BASELINE_PATH, violations.sort().join('\n') + '\n')
  console.log(`Wrote baseline: ${violations.length} pre-existing violations -> ${relative(REPO_ROOT, BASELINE_PATH)}`)
  process.exit(0)
}

const baseline = existsSync(BASELINE_PATH)
  ? new Set(readFileSync(BASELINE_PATH, 'utf8').split('\n').map((s) => s.trim()).filter(Boolean))
  : new Set()

const newViolations = violations.filter((v) => !baseline.has(v))
const fixedSinceBaseline = [...baseline].filter((v) => !violations.includes(v))

console.log(`Total violations: ${violations.length}`)
if (baseline.size > 0) {
  console.log(`Baseline pre-existing: ${baseline.size}`)
  console.log(`New violations since baseline: ${newViolations.length}`)
  if (fixedSinceBaseline.length > 0) {
    console.log(`Fixed since baseline (great!): ${fixedSinceBaseline.length}`)
  }
}

if (newViolations.length > 0) {
  console.log('\nNew api imports outside allowed paths:')
  for (const v of newViolations) console.log(`  ${v}`)
  console.log(
    '\nFix: move the API call into a services/ file or a <feature>.api.ts module,\n' +
    '     and have your component import that service instead.\n' +
    '     If this violation is intentional, re-run with --baseline to update the snapshot.',
  )
  process.exit(1)
}

if (!baseline.size && violations.length > 0) {
  console.log(
    `\nNo baseline file exists yet and ${violations.length} files currently import api directly.\n` +
    `Run: node scripts/check-api-imports.mjs --baseline\n` +
    `to capture the current state, so CI fails only on NEW violations going forward.`,
  )
  process.exit(0)
}

console.log('OK')
