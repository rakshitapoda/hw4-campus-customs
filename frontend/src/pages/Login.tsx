import { useState } from 'react'
import type { SyntheticEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, login } from '../api/client'
import SignedInCard from '../components/SignedInCard'
import { useAuth } from '../lib/auth'

export default function Login() {
  const { user, signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: SyntheticEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await login(email, password)
      signIn(res)
      setSuccess(`${res.message} You’re now logged in.`)
      setPassword('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth">
      <div className="auth__card">
        <p className="eyebrow eyebrow--dark">Welcome back</p>
        <h1>Log in</h1>

        {user ? (
          <SignedInCard message={success} />
        ) : (
          <>
            <p className="muted">Sign in to pick up your conversations with our shopping assistant.</p>
            <form className="form" onSubmit={handleSubmit} noValidate>
              <label className="field">
                <span>Email</span>
                <input
                  className="input"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Password</span>
                <input
                  className="input"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              {error && (
                <p className="notice notice--error" role="alert">
                  {error}
                </p>
              )}
              <button
                type="submit"
                className="btn btn--primary btn--block"
                disabled={submitting || !email.trim() || !password}
              >
                {submitting ? 'Logging in…' : 'Log in'}
              </button>
            </form>
            <p className="auth__switch">
              New to Campus Customs? <Link to="/create-account">Create an account</Link>
            </p>
          </>
        )}
      </div>
    </section>
  )
}
