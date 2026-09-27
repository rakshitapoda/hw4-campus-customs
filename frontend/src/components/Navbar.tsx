import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../lib/auth'

const LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/products', label: 'Products', end: false },
  { to: '/about', label: 'About Us', end: true },
]

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const { user, signOut } = useAuth()

  return (
    <header className="navbar">
      <div className="announcement">Officially licensed Yale apparel · 57 Broadway, New Haven</div>
      <nav className="navbar__inner container" aria-label="Main">
        <Link to="/" className="brand">
          <span className="brand__mark">CC</span>
          <span className="brand__text">
            Campus Customs
            <small>Yale Apparel</small>
          </span>
        </Link>

        <button
          type="button"
          className="navbar__toggle"
          aria-expanded={open}
          aria-controls="nav-links"
          onClick={() => setOpen((o) => !o)}
        >
          <span className="sr-only">Toggle menu</span>
          <span aria-hidden="true">{open ? '✕' : '☰'}</span>
        </button>

        {/* Clicking any link closes the mobile menu */}
        <div id="nav-links" className={`navbar__links ${open ? 'is-open' : ''}`} onClick={() => setOpen(false)}>
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className="navlink">
              {l.label}
            </NavLink>
          ))}
          <span className="navbar__divider" aria-hidden="true" />
          {user ? (
            <>
              <span className="navbar__user" title={user.email}>
                <span className="navbar__avatar" aria-hidden="true">
                  {(user.first_name ?? user.name).charAt(0).toUpperCase()}
                </span>
                Hi, {user.first_name ?? user.name}
              </span>
              <button type="button" className="btn btn--outline btn--sm" onClick={signOut}>
                Log Out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login" className="navlink">
                Log In
              </NavLink>
              <NavLink to="/create-account" className="btn btn--primary btn--sm">
                Create Account
              </NavLink>
            </>
          )}
        </div>
      </nav>
    </header>
  )
}
