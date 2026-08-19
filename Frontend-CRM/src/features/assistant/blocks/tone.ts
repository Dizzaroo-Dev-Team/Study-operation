import type { Tone } from './types'

// Status/tone → Tailwind classes, matching the CRM's existing pill convention
// (e.g. TasksTab STATUS_PILL: bg-*-50 text-*-700 border-*-200).
export const toneChipClass: Record<Tone, string> = {
  success: 'bg-green-50 text-green-700 border-green-200',
  warning: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  info: 'bg-sky-50 text-sky-700 border-sky-200',
  error: 'bg-red-50 text-red-700 border-red-200',
  neutral: 'bg-gray-100 text-gray-600 border-gray-200',
}

export const toneTextClass: Record<Tone, string> = {
  success: 'text-green-700',
  warning: 'text-yellow-700',
  info: 'text-sky-700',
  error: 'text-red-600',
  neutral: 'text-gray-500',
}

export function chipClass(tone: Tone = 'neutral'): string {
  return toneChipClass[tone] ?? toneChipClass.neutral
}

export function textClass(tone: Tone = 'neutral'): string {
  return toneTextClass[tone] ?? toneTextClass.neutral
}
