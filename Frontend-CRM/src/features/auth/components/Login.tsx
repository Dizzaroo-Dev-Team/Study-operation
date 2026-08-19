import React, { useState, FormEvent } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import BrandButton from '@/components/ui/BrandButton'

interface LoginProps {
  onSwitchToSignup: () => void
}

const Login: React.FC<LoginProps> = ({ onSwitchToSignup }) => {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      await login(email, password)
    } catch (err: any) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4" style={{
      background: 'linear-gradient(135deg, #E6F2FF 0%, #F0F9F4 100%)',
    }}>
      <div className="bg-white rounded-xl dizzaroo-shadow-lg p-8 w-full max-w-md border border-gray-100">
        <div className="text-center mb-8">
          <div className="mb-6 flex justify-center items-center gap-2">
            <img
              src="/dizzaroo_logo.png"
              alt="Dizzaroo"
              className="h-10 w-auto object-contain"
              style={{ maxHeight: '40px' }}
              onError={(e) => {
                const target = e.target as HTMLImageElement
                target.style.display = 'none'
              }}
            />
            <span className="text-dizzaroo-deep-blue font-bold text-xl">
              CRM
            </span>
          </div>
          <h1 className="text-dizzaroo-deep-blue mb-2 text-2xl font-bold">Welcome Back</h1>
          <p className="text-gray-600 text-sm">Sign in to your account</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border-2 border-red-200 text-red-700 rounded-xl text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue text-sm transition-all"
              placeholder="your.email@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-4 py-3 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue text-sm transition-all"
              placeholder="Enter your password"
            />
          </div>

          <BrandButton
            type="submit"
            disabled={loading}
            variant="primary"
            size="lg"
            className="w-full"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </BrandButton>
        </form>

        <div className="mt-6 text-center">
          <p className="text-gray-600 text-sm">
            Don't have an account?{' '}
            <button
              onClick={onSwitchToSignup}
              className="text-dizzaroo-deep-blue font-semibold hover:text-dizzaroo-deep-blue-dark transition-colors"
            >
              Sign up
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}

export default Login

