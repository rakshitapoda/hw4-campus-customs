import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, fetchProduct } from '../api/client'
import ErrorState from '../components/ErrorState'
import ProductImage from '../components/ProductImage'
import { formatPrice, stockLabel } from '../lib/format'
import type { ProductDetail as Product } from '../types'

type Status = 'loading' | 'ready' | 'not-found' | 'error'

// Keyed on productId so navigating between products remounts with fresh state.
export default function ProductDetailRoute() {
  const { productId = '' } = useParams()
  return <ProductDetail key={productId} productId={productId} />
}

function ProductDetail({ productId }: { productId: string }) {
  const [product, setProduct] = useState<Product | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState<unknown>(null)
  const [attempt, setAttempt] = useState(0)
  const [selectedSize, setSelectedSize] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchProduct(productId, controller.signal)
      .then((p) => {
        setProduct(p)
        setStatus('ready')
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(err)
        setStatus(err instanceof ApiError && (err.status === 404 || err.status === 400) ? 'not-found' : 'error')
      })
    return () => controller.abort()
  }, [productId, attempt])

  if (status === 'loading') {
    return (
      <section className="section container">
        <p className="loading-note" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" /> Loading product details…
        </p>
        <div className="detail detail--skeleton" aria-hidden="true">
          <div className="detail__media" />
          <div />
        </div>
      </section>
    )
  }

  if (status === 'not-found') {
    return (
      <section className="section container empty-state">
        <h1>Product not found</h1>
        <p>We couldn’t find that item in the catalogue. It may have been removed, or the link may be wrong.</p>
        <Link to="/products" className="btn btn--primary">
          Browse all products
        </Link>
      </section>
    )
  }

  if (status !== 'ready' || !product) {
    return (
      <section className="section container">
        <ErrorState
          error={error}
          title="We couldn’t load this product"
          onRetry={() => {
            setStatus('loading')
            setAttempt((a) => a + 1)
          }}
        />
        <p className="back-link">
          <Link to="/products">← Back to all products</Link>
        </p>
      </section>
    )
  }

  const selected = product.inventory.find((s) => s.size === selectedSize)
  const overall = stockLabel(product.total_stock)

  return (
    <section className="section container">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link> <span>/</span> <Link to="/products">Products</Link> <span>/</span>{' '}
        <span aria-current="page">{product.name}</span>
      </nav>

      <div className="detail">
        <div className="detail__media">
          <ProductImage src={product.image_url} alt={product.name} />
        </div>

        <div className="detail__info">
          <p className="product-card__type">{product.garment_type}</p>
          <h1 className="detail__name">{product.name}</h1>
          <p className="detail__price">{formatPrice(product.price)}</p>
          <p className="detail__desc">{product.description}</p>

          <dl className="detail__meta">
            <div>
              <dt>Colors</dt>
              <dd>
                {product.colors.length > 0 ? (
                  <span className="tags">
                    {product.colors.map((c) => (
                      <span key={c} className="tag">
                        {c}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="muted">Not listed</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Availability</dt>
              <dd>
                <span className={`stock stock--${overall.tone}`}>
                  {product.total_stock > 0 ? `${product.total_stock} units across all sizes` : 'Sold out'}
                </span>
              </dd>
            </div>
          </dl>

          {product.inventory.length > 0 ? (
            <div className="sizes">
              <div className="sizes__head">
                <h2>Sizes</h2>
                {selected && (
                  <span className={`stock stock--${stockLabel(selected.quantity).tone}`}>
                    Size {selected.size}: {stockLabel(selected.quantity).text}
                  </span>
                )}
              </div>
              <div className="sizes__grid">
                {product.inventory.map((s) => {
                  const label = stockLabel(s.quantity)
                  return (
                    <button
                      key={s.size}
                      type="button"
                      className={`size ${selectedSize === s.size ? 'is-active' : ''} size--${label.tone}`}
                      disabled={s.quantity <= 0}
                      aria-pressed={selectedSize === s.size}
                      onClick={() => setSelectedSize(s.size)}
                      title={label.text}
                    >
                      <span className="size__label">{s.size}</span>
                      <span className="size__qty">{s.quantity > 0 ? `${s.quantity} left` : 'Sold out'}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : (
            <p className="muted">Size and stock information isn’t available for this item.</p>
          )}

          {product.search_tags.length > 0 && (
            <div className="detail__tags">
              <h2>Tags</h2>
              <span className="tags">
                {product.search_tags.map((t) => (
                  <Link key={t} to={`/products?q=${encodeURIComponent(t)}`} className="tag tag--link">
                    {t}
                  </Link>
                ))}
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
