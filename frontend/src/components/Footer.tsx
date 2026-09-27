import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container footer__inner">
        <div>
          <p className="footer__brand">Campus Customs</p>
          <p className="footer__muted">Officially licensed Yale apparel.</p>
          <p className="footer__muted">57 Broadway, New Haven, CT 06511</p>
        </div>
        <nav className="footer__links" aria-label="Footer">
          <Link to="/products">Shop</Link>
          <Link to="/about">About Us</Link>
          <Link to="/login">Log In</Link>
          <Link to="/create-account">Create Account</Link>
        </nav>
      </div>
      <div className="container footer__legal">
        © {new Date().getFullYear()} Campus Customs · Class project demo storefront
      </div>
    </footer>
  )
}
