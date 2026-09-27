import { useState } from 'react'
import type { SyntheticEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, signup } from '../api/client'
import SignedInCard from '../components/SignedInCard'
import { useAuth } from '../lib/auth'

const MIN_PASSWORD_LENGTH = 8 // matches MIN_PASSWORD_CHARS in backend/auth.py

const EMPTY_FORM = { firstName: '', lastName: '', email: '', password: '', confirm: '' }

export default function CreateAccount() {
  const { user, signIn } = useAuth()
  // Fields mirror the users table: first_name, last_name, email, password (stored only as a hash).
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function set(field: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  // Quick checks before calling the backend; the backend re-validates everything.
  function clientError(): string | null {
    if (!form.firstName.trim() || !form.lastName.trim()) return 'Please enter your first and last name.'
    if (!form.email.trim()) return 'Please enter your email.'
    if (form.password.length < MIN_PASSWORD_LENGTH) {
      return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`
    }
    if (form.password !== form.confirm) return 'Passwords do not match.'
    return null
  }

  async function handleSubmit(e: SyntheticEvent) {
    e.preventDefault()
    const problem = clientError()
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const res = await signup({
        first_name: form.firstName,
        last_name: form.lastName,
        email: form.email,
        password: form.password,
        confirm_password: form.confirm,
      })
      signIn(res)
      setSuccess(`${res.message} You’re now logged in.`)
      setForm(EMPTY_FORM)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const mismatch = form.confirm.length > 0 && form.password !== form.confirm

  return (
    <section className="auth">
      <div className="auth__card">
        <p className="eyebrow eyebrow--dark">Join the community</p>
        <h1>Create account</h1>

        {user ? (
          <SignedInCard message={success} />
        ) : (
          <>
            <p className="muted">Save your chats with our assistant and get a personal welcome every visit.</p>
            <form className="form" onSubmit={handleSubmit} noValidate>
              <div className="form__row">
                <label className="field">
                  <span>First name</span>
                  <input
                    className="input"
                    autoComplete="given-name"
                    required
                    maxLength={50}
                    value={form.firstName}
                    onChange={(e) => set('firstName', e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Last name</span>
                  <input
                    className="input"
                    autoComplete="family-name"
                    required
                    maxLength={50}
                    value={form.lastName}
                    onChange={(e) => set('lastName', e.target.value)}
                  />
                </label>
              </div>
              <label className="field">
                <span>Email</span>
                <input
                  className="input"
                  type="email"
                  autoComplete="email"
                  required
                  value={form.email}
                  onChange={(e) => set('email', e.target.value)}
                />
              </label>
              <label className="field">
                <span>Password</span>
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  maxLength={128}
                  value={form.password}
                  onChange={(e) => set('password', e.target.value)}
                />
                <small className="field__hint">At least {MIN_PASSWORD_LENGTH} characters.</small>
              </label>
              <label className="field">
                <span>Confirm password</span>
                <input
                  className={`input ${mismatch ? 'input--invalid' : ''}`}
                  type="password"
                  autoComplete="new-password"
                  required
                  maxLength={128}
                  value={form.confirm}
                  onChange={(e) => set('confirm', e.target.value)}
                  aria-invalid={mismatch}
                />
                {mismatch && <small className="field__hint field__hint--error">Passwords don’t match yet.</small>}
              </label>
              {error && (
                <p className="notice notice--error" role="alert">
                  {error}
                </p>
              )}
              <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
                {submitting ? 'Creating account…' : 'Create account'}
              </button>
            </form>
            <p className="auth__switch">
              Already have an account? <Link to="/login">Log in</Link>
            </p>
          </>
        )}
      </div>
    </section>
  )
}
