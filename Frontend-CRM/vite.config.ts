import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// -----------------------------------------------------------------------------
// Manual chunk strategy
// -----------------------------------------------------------------------------
// Why: without explicit chunking, Vite lumped every transitively-imported
// node_module into the main entry. The May 2026 audit measured a 3.6MB main
// chunk dominated by Radix UI, recharts, @react-pdf-viewer, pdfjs-dist,
// @tiptap, and @azure/storage-blob — every page paid for every dep.
//
// The function-based form is preferred over the object form because it lets
// us match by prefix without enumerating every sub-package. Anything not
// matched falls into the default "vendor" chunk, and our own source code
// stays under whatever lazy boundary brought it in (see App.tsx for the
// route-level React.lazy splits).
//
// Caching wins: a code-only release now invalidates ONE chunk; bumping
// recharts only invalidates `vendor-charts`. Cold-load wins: features that
// never touch a heavy dep no longer download it.
// -----------------------------------------------------------------------------
function manualChunks(id: string): string | undefined {
  if (!id.includes('node_modules')) return undefined

  // -----------------------------------------------------------------------
  // Carve-out rule: ONLY split libs that do NOT import React.
  //
  // History — the original Hunt 1 config split React into its own chunk and
  // split React-using libs (Radix, recharts, react-router, react-hot-toast,
  // tiptap, dnd-kit, react-hook-form, react-markdown) into separate chunks
  // too. In production this produced
  //     "Cannot read properties of undefined (reading 'createContext')"
  // on first paint because a chunk's CJS-interop wrapper evaluated
  // `React.createContext(...)` before the chunk that held React had been
  // assigned to the module-namespace object. Rollup's chunking heuristics
  // can hoist references in ways the import-graph doesn't always honor for
  // legacy CJS modules.
  //
  // Safe rule going forward: ONLY split libs with zero React surface area
  // (pure data utilities, PDF/DOCX engines, the Azure SDK). Everything that
  // touches React stays in the catch-all `vendor` chunk together with React
  // itself, so React is guaranteed to initialize before any consumer reads
  // `React.createContext`.
  //
  // The lazy-loaded route chunks (defined in App.tsx / UnifiedInbox.tsx via
  // React.lazy) already give us most of the bundle-split win without
  // requiring vendor sub-splits.
  // -----------------------------------------------------------------------

  // PDF rendering core — pdfjs-dist has no React surface.
  if (id.includes('pdfjs-dist')) {
    return 'vendor-pdf-core'
  }
  // DOCX rendering / generation — docx + docx-preview are React-free.
  if (id.includes('docx-preview') || id.includes('/docx/')) {
    return 'vendor-docx'
  }
  // PDF generation (html → pdf) — html2pdf.js + html2canvas + jspdf.
  if (id.includes('html2pdf.js') || id.includes('jspdf') || id.includes('html2canvas')) {
    return 'vendor-pdfgen'
  }
  // Azure SDK — heavy, React-free.
  if (id.includes('@azure/')) {
    return 'vendor-azure'
  }
  // jszip / papaparse / json2csv — bulk data utils, React-free.
  if (id.includes('/jszip/') || id.includes('/papaparse/') || id.includes('/json2csv/')) {
    return 'vendor-data'
  }
  // Mermaid (+ its mermaid-only deps: dagre, cytoscape, elk, khroma, roughjs). It is
  // React-free and reached ONLY via a dynamic import() on the AI-authoring confirm
  // screen, so its own chunk stays ASYNC — loaded on demand, never in the initial
  // bundle. (Shared d3-* used by recharts intentionally stays in `vendor`.)
  if (
    id.includes('/mermaid/') || id.includes('/@mermaid-js/') ||
    id.includes('/dagre-d3-es/') || id.includes('/dagre/') ||
    id.includes('/cytoscape') || id.includes('/khroma/') ||
    id.includes('/elkjs/') || id.includes('/roughjs/') || id.includes('/ts-dedent/')
  ) {
    return 'vendor-mermaid'
  }

  // Everything else — including React itself, react-dom, react-router,
  // @radix-ui/*, recharts, @tanstack/*, @tiptap/*, @dnd-kit/*,
  // react-hot-toast, react-hook-form, react-markdown, etc. — lands in the
  // catch-all `vendor` chunk together. This guarantees React initializes
  // first within the chunk so every dependent's `createContext` call sees
  // a defined React.
  return 'vendor'
}

export default defineConfig({
  plugins: [react()],

  // Drop dev-only call sites from the production build. ~1-3% size reduction
  // plus a small runtime win on hot paths littered with debug logging.
  esbuild: {
    drop: ['console', 'debugger'],
  },

  build: {
    // The bundle-size gate (scripts/check-bundle-size.mjs) enforces these
    // budgets in CI; this just suppresses the noisy build warning so the
    // signal in CI logs is the gate's output, not Vite's default 500KB nag.
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },

  resolve: {
    alias: [
      // ── ISF-specific sub-path aliases ────────────────────────────────────
      // These MUST come BEFORE the generic `@` → `src` alias so Vite matches
      // them first.  All of these paths exist inside src/modules/isf/ but ISF
      // source files reference them with bare `@/…` paths.

      // ISF component sub-folders (files NOT under src/components/)
      {
        find: '@/components/dialogs',
        replacement: path.resolve(process.cwd(), 'src/modules/isf/components/dialogs'),
      },
      {
        find: '@/components/documents',
        replacement: path.resolve(process.cwd(), 'src/modules/isf/components/documents'),
      },
      {
        find: '@/components/ai',
        replacement: path.resolve(process.cwd(), 'src/modules/isf/components/ai'),
      },

      // ISF config / data / services / utils (all live under src/modules/isf/)
      {
        find: '@/config',
        replacement: path.resolve(process.cwd(), 'src/modules/isf/config'),
      },
      {
        find: '@/data',
        replacement: path.resolve(process.cwd(), 'src/modules/isf/data'),
      },
      {
        find: '@/services',
        replacement: path.resolve(process.cwd(), 'src/modules/isf/services'),
      },
      {
        find: '@/utils',
        replacement: path.resolve(process.cwd(), 'src/modules/isf/utils'),
      },

      // ── Generic CRM alias (must come last) ───────────────────────────────
      // Covers:
      //   @/components/ui/*  → src/components/ui/*  (shadcn/ui copied here)
      //   @/lib/utils        → src/lib/utils.js      (cn helper – created)
      //   @/*                → src/*                 (everything else)
      {
        find: '@',
        replacement: path.resolve(process.cwd(), 'src'),
      },
    ],
  },

  server: {
    host: '0.0.0.0',
    // Leading-dot entries match the host AND any subdomain. This survives
    // ngrok URL rotation on the free plan, so devs don't have to edit this
    // file every time the tunnel hostname changes.
    allowedHosts: [
      '.ngrok-free.dev',
      '.ngrok-free.app',
      '.ngrok.io',
    ],
    port: 3000,
  },
})
