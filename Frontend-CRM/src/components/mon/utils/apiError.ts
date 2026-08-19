/** Extract a user-readable message from axios/FastAPI error responses. */
export function extractApiErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object') {
    const ax = err as { response?: { data?: { detail?: unknown } }; message?: string }
    const detail = ax.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail.trim()
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0]
      if (typeof first === 'object' && first !== null && 'msg' in first) {
        return String((first as { msg?: string }).msg || fallback)
      }
    }
    if (typeof ax.message === 'string' && ax.message.trim()) {
      return ax.message.trim()
    }
  }
  if (err instanceof Error && err.message.trim()) {
    return err.message.trim()
  }
  return fallback
}

export function logMonitoringError(context: string, err: unknown): void {
  console.error(`[Monitoring] ${context}`, err)
}
