import { Link } from 'react-router-dom'
import ErrorState from '../components/ErrorState'
import ProductCard from '../components/ProductCard'
import ProductImage from '../components/ProductImage'
import { COLLECTIONS } from '../lib/collections'
import { categoryOf } from '../lib/format'
import { useProducts } from '../lib/useProducts'
import type { ProductSummary } from '../types'

// One in-stock product from each garment category, so the featured row shows range.
function pickFeatured(products: ProductSummary[], count: number): ProductSummary[] {
  const seen = new Set<string>()
  const picks: ProductSummary[] = []
  const byStock = [...products].sort((a, b) => b.total_stock - a.total_stock)
  for (const p of byStock) {
    const cat = categoryOf(p.garment_type)
    if (!seen.has(cat)) {
      seen.add(cat)
      picks.push(p)
    }
    if (picks.length === count) break
  }
  return picks
}

export default function Home() {
  const { products, loading, error, retry } = useProducts()
  const featured = pickFeatured(products, 4)
  const heroImages = featured.slice(0, 3)

  return (
    <>
      <section className="hero">
        <div className="container hero__inner">
          <div className="hero__copy">
            <p className="eyebrow">Made for the Bulldog faithful</p>
            <h1>
              Wear your <span className="accent">Yale blue</span> everywhere.
            </h1>
            <p className="lead">
              Officially licensed hoodies, crewnecks, tees, and quarter-zips for students, alumni,
              and every proud family member in between. Sold right here in New Haven, just steps
              from campus.
            </p>
            <div className="hero__actions">
              <Link to="/products" className="btn btn--light">
                Shop the collection
              </Link>
              <Link to="/about" className="btn btn--ghost">
                Our story
              </Link>
            </div>
            {!loading && !error && (
              <p className="hero__stat">
                <strong>{products.length}</strong> styles in the shop right now
              </p>
            )}
          </div>
          <div className="hero__collage" aria-hidden="true">
            {heroImages.map((p, i) => (
              <div key={p.product_id} className={`hero__tile hero__tile--${i}`}>
                <ProductImage src={p.image_url} alt="" />
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section container">
        <div className="section__head">
          <div>
            <p className="eyebrow eyebrow--dark">Shop by collection</p>
            <h2>Find your corner of campus</h2>
          </div>
        </div>
        <div className="collections">
          {COLLECTIONS.map((c) => (
            <Link key={c.key} to={`/products?collection=${c.key}`} className="collection-card">
              <h3>{c.title}</h3>
              <p>{c.blurb}</p>
              <span className="collection-card__cta">Browse →</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="section container">
        <div className="section__head">
          <div>
            <p className="eyebrow eyebrow--dark">Fan favorites</p>
            <h2>Ready for your next trip to the Bowl</h2>
          </div>
          <Link to="/products" className="link-arrow">
            View all products →
          </Link>
        </div>
        {loading ? (
          <>
            <p className="loading-note" role="status" aria-live="polite">
              <span className="spinner" aria-hidden="true" /> Loading fan favorites…
            </p>
            <div className="grid" aria-hidden="true">
              {Array.from({ length: 4 }, (_, i) => (
                <div key={i} className="product-card product-card--skeleton" />
              ))}
            </div>
          </>
        ) : error ? (
          <ErrorState error={error} title="We couldn’t load products" onRetry={retry} />
        ) : (
          <div className="grid">
            {featured.map((p) => (
              <ProductCard key={p.product_id} product={p} />
            ))}
          </div>
        )}
      </section>

      <section className="section container">
        <div className="promise">
          <div>
            <h3>Officially licensed</h3>
            <p>Every piece carries authentic Yale marks, so you know what you are wearing is the real thing.</p>
          </div>
          <div>
            <h3>Sized for everyone</h3>
            <p>Every style comes in XS through XXL, with live stock counts on each product page.</p>
          </div>
          <div>
            <h3>Rooted in New Haven</h3>
            <p>Stop by our shop at 57 Broadway, just steps from campus.</p>
          </div>
        </div>
      </section>
    </>
  )
}
