import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@/components/dialogs', replacement: path.resolve(process.cwd(), 'src/modules/isf/components/dialogs') },
      { find: '@/components/documents', replacement: path.resolve(process.cwd(), 'src/modules/isf/components/documents') },
      { find: '@/components/ai', replacement: path.resolve(process.cwd(), 'src/modules/isf/components/ai') },
      { find: '@/config', replacement: path.resolve(process.cwd(), 'src/modules/isf/config') },
      { find: '@/data', replacement: path.resolve(process.cwd(), 'src/modules/isf/data') },
      { find: '@/services', replacement: path.resolve(process.cwd(), 'src/modules/isf/services') },
      { find: '@/utils', replacement: path.resolve(process.cwd(), 'src/modules/isf/utils') },
      { find: '@', replacement: path.resolve(process.cwd(), 'src') },
    ],
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      reporter: ['text', 'html'],
    },
  },
})
