import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'

interface Props {
  message?: string | null
}

// Shown on the auth pages after a successful login/sign-up, or when already signed in.
export default function SignedInCard({ message }: Props) {
  const { user, signOut } = useAuth()
  if (!user) return null

  return (
    <div className="signed-in">
      <div className="notice notice--success" role="status">
        {message ?? `You’re already logged in as ${user.name}.`}
      </div>
      <dl className="signed-in__details">
        <div>
          <dt>Name</dt>
          <dd>{user.name}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{user.email}</dd>
        </div>
      </dl>
      <div className="signed-in__actions">
        <Link to="/products" className="btn btn--primary">
          Start shopping
        </Link>
        <button type="button" className="btn btn--outline" onClick={signOut}>
          Log out
        </button>
      </div>
    </div>
  )
}
