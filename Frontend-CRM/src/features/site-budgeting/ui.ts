// Shared UI primitives for the site-budgeting module.
// Every button, input, and table across Study / Country / Site should pull from here
// so visual weight stays consistent as the layout evolves.

export const btn = {
  primary:
    'inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 active:bg-indigo-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
  primarySm:
    'inline-flex items-center justify-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md bg-indigo-600 text-white hover:bg-indigo-700 active:bg-indigo-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
  secondary:
    'inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 active:bg-slate-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
  secondarySm:
    'inline-flex items-center justify-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 active:bg-slate-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
  success:
    'inline-flex items-center justify-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md bg-emerald-500 text-white hover:bg-emerald-600 transition-colors disabled:opacity-40',
  icon:
    'h-8 w-8 inline-flex items-center justify-center rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors disabled:opacity-40',
  iconDanger:
    'h-8 w-8 inline-flex items-center justify-center rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-40',
  iconSuccess:
    'h-8 w-8 inline-flex items-center justify-center rounded-md text-emerald-500 hover:text-emerald-700 hover:bg-emerald-50 transition-colors disabled:opacity-40',
}

export const input = {
  base:
    'w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 transition-colors disabled:bg-slate-50 disabled:text-slate-400',
  sm:
    'w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-md bg-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 transition-colors disabled:bg-slate-50 disabled:text-slate-400',
  cell:
    'w-16 px-1.5 py-1 text-center text-xs font-mono border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 transition-colors disabled:bg-slate-50',
  cellFilled:
    'w-16 px-1.5 py-1 text-center text-xs font-mono border border-indigo-400 rounded-md bg-indigo-50 text-indigo-700 font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-200 transition-colors',
}

export const table = {
  wrap: 'overflow-auto rounded-lg border border-slate-200 bg-white',
  base: 'min-w-full text-sm',
  thead: 'bg-slate-50 border-b border-slate-200',
  th: 'px-3 py-2.5 text-left font-semibold text-slate-600 text-[11px] uppercase tracking-wide whitespace-nowrap',
  thRight: 'px-3 py-2.5 text-right font-semibold text-slate-600 text-[11px] uppercase tracking-wide whitespace-nowrap',
  thCenter: 'px-3 py-2.5 text-center font-semibold text-slate-600 text-[11px] uppercase tracking-wide whitespace-nowrap',
  row: 'border-t border-slate-100 hover:bg-slate-50 transition-colors',
  td: 'px-3 py-2.5 text-sm text-slate-700',
  tdRight: 'px-3 py-2.5 text-sm text-slate-700 text-right font-mono',
  tdCenter: 'px-3 py-2.5 text-sm text-slate-700 text-center',
}

export const card = 'rounded-lg border border-slate-200 bg-white'
export const cardPad = 'rounded-lg border border-slate-200 bg-white p-4'

export const label = 'text-[11px] font-semibold text-slate-500 uppercase tracking-wide'

export const badge = {
  neutral: 'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-600',
  success: 'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-50 text-emerald-700',
  warn: 'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-amber-50 text-amber-700',
  danger: 'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-red-50 text-red-700',
  info: 'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-blue-50 text-blue-700',
}

export const emptyState =
  'flex flex-col items-center justify-center py-12 text-sm text-slate-400 gap-2'
