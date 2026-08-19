#!/usr/bin/env node
/**
 * Typecheck gate with a baseline snapshot.
 *
 * `tsc --noEmit` currently reports ~118 pre-existing errors in Frontend-CRM
 * (unused vars, implicit-any params, a handful of real type mismatches). We do
 * NOT mass-fix those here — that's a separate cleanup project. Instead this
 * script captures the current set as a baseline so the gate fails only on NEW
 * type errors a change introduces. Same idea as check-api-imports.mjs.
 *
 * Error signature = `relativePath|TScode|message`. Line/column are deliberately
 * dropped from the signature so that editing unrelated code above an existing
 * error (which shifts its line number) does not register as a "new" error.
 *
 * Usage:
 *   node scripts/typecheck-baseline.mjs            # report, exit 1 on NEW errors
 *   node scripts/typecheck-baseline.mjs --baseline # snapshot current errors
 */
import { spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const REPO_ROOT = join(__dirname, '..')
const BASELINE_PATH = join(__dirname, 'typecheck.baseline')

// tsc emits lines like:  src/foo/Bar.tsx(24,5): error TS6133: 'x' is declared...
const ERROR_RE = /^(.+?)\((\d+),(\d+)\): error (TS\d+): (.+)$/

function runTsc() {
  const res = spawnSync(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['tsc', '--noEmit'],
    { cwd: REPO_ROOT, encoding: 'utf8', shell: process.platform === 'win32' },
  )
  // tsc prints diagnostics to stdout; combine both streams to be safe.
  return `${res.stdout || ''}${res.stderr || ''}`
}

function parse(output) {
  const sigs = []
  for (const raw of output.split(/\r?\n/)) {
    const m = ERROR_RE.exec(raw.trim())
    if (!m) continue
    const [, file, , , code, msg] = m
    const relFile = relative(REPO_ROOT, join(REPO_ROOT, file)).split('\\').join('/')
    sigs.push(`${relFile}|${code}|${msg}`)
  }
  return sigs
}

const writeBaseline = process.argv.slice(2).includes('--baseline')

const errors = parse(runTsc())

if (writeBaseline) {
  // Preserve duplicate signatures (same file|code|msg can legitimately occur
  // N times) so the multiset diff below sees the true count.
  writeFileSync(BASELINE_PATH, errors.slice().sort().join('\n') + '\n')
  console.log(`Wrote baseline: ${errors.length} pre-existing type errors -> ${relative(REPO_ROOT, BASELINE_PATH)}`)
  process.exit(0)
}

// Read as an array (NOT a Set) so duplicate signatures keep their multiplicity.
const baselineLines = existsSync(BASELINE_PATH)
  ? readFileSync(BASELINE_PATH, 'utf8').split('\n').map((s) => s.trim()).filter(Boolean)
  : []

// Count duplicates correctly: a signature in the baseline once but now appearing
// twice means one genuinely new occurrence. Use a multiset diff.
const baseCounts = new Map()
for (const s of baselineLines) baseCounts.set(s, (baseCounts.get(s) || 0) + 1)
const newErrors = []
const seen = new Map()
for (const s of errors) {
  const used = seen.get(s) || 0
  if (used < (baseCounts.get(s) || 0)) {
    seen.set(s, used + 1) // covered by baseline
  } else {
    newErrors.push(s)
  }
}

console.log(`Total type errors: ${errors.length}`)
if (baselineLines.length > 0) {
  console.log(`Baseline pre-existing: ${baselineLines.length}`)
  console.log(`New type errors since baseline: ${newErrors.length}`)
}

if (newErrors.length > 0) {
  console.log('\nNEW type errors (introduced since baseline):')
  for (const s of newErrors) {
    const [file, code, msg] = s.split('|')
    console.log(`  ${file}: ${code}: ${msg}`)
  }
  console.log(
    '\nFix the error, or — if it is an acceptable pre-existing condition —\n' +
    '     re-run with --baseline to update the snapshot.',
  )
  process.exit(1)
}

if (!baselineLines.length && errors.length > 0) {
  console.log(
    `\nNo baseline file exists yet and ${errors.length} type errors are present.\n` +
    `Run: node scripts/typecheck-baseline.mjs --baseline\n` +
    `to capture the current state, so the gate fails only on NEW errors going forward.`,
  )
  process.exit(0)
}

console.log('OK — no new type errors')
