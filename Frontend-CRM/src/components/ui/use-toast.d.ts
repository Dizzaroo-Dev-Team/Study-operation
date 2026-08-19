export interface ToastOptions {
  title?: string
  description?: string
  variant?: 'default' | 'destructive'
  duration?: number
  action?: React.ReactNode
}

export interface ToastApi {
  toast: (options: ToastOptions) => void
  toasts: ToastOptions[]
  dismiss: (id?: string) => void
}

export declare function useToast(): ToastApi
export declare function toast(options: ToastOptions): void
