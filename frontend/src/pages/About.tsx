import { Link } from 'react-router-dom'

export default function About() {
  return (
    <>
      <section className="page-head">
        <div className="container">
          <p className="eyebrow">About us</p>
          <h1>Bulldog pride, straight from New Haven</h1>
          <p className="lead">
            Campus Customs is a local shop that sells officially licensed Yale apparel for the whole
            Yale community.
          </p>
        </div>
      </section>

      <section className="section container about">
        <div className="about__story">
          <h2>Who we are</h2>
          <p>
            We think the best college gear tells a story, like the residential college you called
            home, the team you cheered for on a cold November afternoon, or the graduate program
            that shaped your career. So we carry far more than a single logo sweatshirt. Our
            racks cover residential colleges, varsity sports, graduate and professional schools,
            and classic throwback designs.
          </p>
          <p>
            We also know that Yale spirit doesn’t stop at the students. Parents, grandparents,
            siblings, aunts, and uncles all have something to celebrate, and we stock pieces made
            just for them.
          </p>
          <h2>What we stand for</h2>
          <ul className="checklist">
            <li>
              <strong>Authentic merchandise.</strong> Everything we sell is officially licensed.
            </li>
            <li>
              <strong>Something for everyone.</strong> Every style runs from XS through XXL, so the
              whole family can match on game day.
            </li>
            <li>
              <strong>Honest information.</strong> Product pages show real prices and live stock by
              size, so you know what’s available before you visit.
            </li>
          </ul>
        </div>

        <aside className="about__card">
          <h3>Visit the shop</h3>
          <p className="about__address">
            57 Broadway
            <br />
            New Haven, CT 06511
          </p>
          <p className="muted">Just steps from campus.</p>
          <Link to="/products" className="btn btn--primary">
            Browse products
          </Link>
          <p className="about__note">
            Questions about a size or style? Tap the chat bubble in the corner.
          </p>
        </aside>
      </section>
    </>
  )
}
