#!/usr/bin/env node
/**
 * Bundle-size gate.
 *
 * Enforces an upper bound on the entry chunk and on any individual chunk so
 * that a careless `import OnlyOfficeEditor from ...` cannot silently
 * re-balloon the main bundle.
 *
 * Budgets (all gzip-uncompressed, raw file size — adjust as we shrink):
 *   - entry chunk (index-*.js):  <= 1_500_000 bytes
 *   - any other chunk:           <= 1_500_000 bytes
 *
 * The chunk budget was 1_000_000 originally, but after the May 2026
 * createContext-of-undefined production bug we keep React in the same
 * chunk as every React-using lib (Radix, recharts, react-pdf-viewer,
 * tiptap, dnd-kit, react-router, etc.). That `vendor` chunk now legitimately
 * lands around 1.3 MB — still a one-time browser-cached download per user,
 * still way better than the original 3.6 MB entry. 1_500_000 leaves room
 * for one or two more React-using deps before we need to revisit.
 *
 * Override via env:
 *   ENTRY_BUDGET_BYTES, CHUNK_BUDGET_BYTES
 *
 * Usage (run after `vite build`):
 *   npm run build && npm run check:bundle-size
 *
 * Exits non-zero on violation so any CI runner (GitHub Actions, Azure
 * Pipelines, plain Makefile) can gate on it without extra plumbing.
 */
import { readdirSync, statSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const REPO_ROOT = join(__dirname, '..')
const DIST_ASSETS = join(REPO_ROOT, 'dist', 'assets')

const ENTRY_BUDGET = Number(process.env.ENTRY_BUDGET_BYTES ?? 1_500_000)
const CHUNK_BUDGET = Number(process.env.CHUNK_BUDGET_BYTES ?? 1_500_000)

function fmt(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

if (!existsSync(DIST_ASSETS)) {
  console.error(
    `[bundle-size] dist/assets not found at ${DIST_ASSETS}. Run \`npm run build\` first.`,
  )
  process.exit(2)
}

const files = readdirSync(DIST_ASSETS)
  .filter((f) => f.endsWith('.js'))
  .map((f) => {
    const full = join(DIST_ASSETS, f)
    return { name: f, full, size: statSync(full).size }
  })
  .sort((a, b) => b.size - a.size)

if (files.length === 0) {
  console.error('[bundle-size] no .js files under dist/assets — build output missing?')
  process.exit(2)
}

const violations = []

for (const f of files) {
  // Vite emits the entry as `index-<hash>.js`. Any other chunk gets the
  // CHUNK_BUDGET cap.
  const isEntry = /^index-[A-Za-z0-9_-]+\.js$/.test(f.name)
  const budget = isEntry ? ENTRY_BUDGET : CHUNK_BUDGET
  if (f.size > budget) {
    violations.push({ ...f, budget, isEntry })
  }
}

console.log('Top 10 chunks by size:')
for (const f of files.slice(0, 10)) {
  console.log(`  ${fmt(f.size).padStart(10)}  ${f.name}`)
}
console.log('')
console.log(`Budgets: entry <= ${fmt(ENTRY_BUDGET)}, other chunks <= ${fmt(CHUNK_BUDGET)}`)
console.log('')

if (violations.length === 0) {
  console.log('[bundle-size] OK — all chunks within budget.')
  process.exit(0)
}

console.error(`[bundle-size] ${violations.length} violation(s):`)
for (const v of violations) {
  console.error(
    `  ${v.isEntry ? 'ENTRY ' : 'CHUNK '}` +
      `${v.name} = ${fmt(v.size)} (budget ${fmt(v.budget)}, ` +
      `over by ${fmt(v.size - v.budget)})`,
  )
}
process.exit(1)
