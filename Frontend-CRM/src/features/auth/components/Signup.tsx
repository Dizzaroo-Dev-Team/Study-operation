import React, { useState, FormEvent } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import BrandButton from '@/components/ui/BrandButton'

interface SignupProps {
  onSwitchToLogin: () => void
}

const Signup: React.FC<SignupProps> = ({ onSwitchToLogin }) => {
  const { signup } = useAuth()
  const [user_id, setUserId] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }

    setLoading(true)

    try {
      await signup(user_id, name, email, password)
    } catch (err: any) {
      setError(err.message || 'Signup failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 overflow-y-auto" style={{
      background: 'linear-gradient(135deg, #E6F2FF 0%, #F0F9F4 100%)',
    }}>
      <div className="bg-white rounded-xl dizzaroo-shadow-lg p-6 w-full max-w-md border border-gray-100 my-auto">
        <div className="text-center mb-5">
          <div className="mb-3 flex justify-center items-center gap-2">
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
          <h1 className="text-dizzaroo-deep-blue mb-1.5 text-2xl font-bold">Create Account</h1>
          <p className="text-gray-600 text-sm">Sign up for your account</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border-2 border-red-200 text-red-700 rounded-xl text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="user_id" className="block text-sm font-medium text-gray-700 mb-1.5">
              User ID <span className="text-red-500">*</span>
            </label>
            <input
              id="user_id"
              type="text"
              value={user_id}
              onChange={(e) => setUserId(e.target.value)}
              required
              className="w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue text-sm transition-all"
              placeholder="unique_user_id"
            />
          </div>

          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1.5">
              Full Name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue text-sm transition-all"
              placeholder="John Doe"
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
              Email <span className="text-red-500">*</span>
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue text-sm transition-all"
              placeholder="your.email@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
              Password <span className="text-red-500">*</span>
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              className="w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue text-sm transition-all"
              placeholder="At least 6 characters"
            />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1.5">
              Confirm Password <span className="text-red-500">*</span>
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue text-sm transition-all"
              placeholder="Confirm your password"
            />
          </div>

          <BrandButton
            type="submit"
            disabled={loading}
            variant="primary"
            size="lg"
            className="w-full mt-4"
          >
            {loading ? 'Creating account...' : 'Sign Up'}
          </BrandButton>
        </form>

        <div className="mt-6 mb-2 text-center">
          <p className="text-gray-600 text-sm">
            Already have an account?{' '}
            <button
              onClick={onSwitchToLogin}
              className="text-dizzaroo-deep-blue font-semibold hover:text-dizzaroo-deep-blue-dark transition-colors"
            >
              Sign in
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}

export default Signup

