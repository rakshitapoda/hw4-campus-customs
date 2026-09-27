import { useMemo } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import ErrorState from '../components/ErrorState'
import ProductCard from '../components/ProductCard'
import { CHAT_VIEW_PARAM, CHAT_VIEW_VALUE, useChatSearch } from '../lib/chatSearch'
import { findCollection } from '../lib/collections'
import { CATEGORIES, categoryOf, formatPrice } from '../lib/format'
import {
  PRICE_BANDS,
  SIZES,
  SORT_OPTIONS,
  activeFilterCount,
  colorFamilies,
  countBy,
  matchesFilters,
  readFilters,
  sortProducts,
} from '../lib/productFilters'
import type { SortKey } from '../lib/productFilters'
import { useProducts } from '../lib/useProducts'

const FILTER_LABELS: Record<string, string> = {
  category: 'Category',
  color: 'Color',
  max_price: 'Max price',
  size_in_stock: 'Size in stock',
}

export default function Products() {
  const [params] = useSearchParams()
  const { results } = useChatSearch()
  // /products?view=chat shows the latest chat search; plain /products is the normal catalogue.
  if (params.get(CHAT_VIEW_PARAM) === CHAT_VIEW_VALUE && results) {
    return <ChatSearchResultsView />
  }
  return <CatalogueView />
}

function SkeletonGrid({ count, label }: { count: number; label: string }) {
  return (
    <>
      <p className="loading-note" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" /> {label}
      </p>
      <div className="grid" aria-hidden="true">
        {Array.from({ length: count }, (_, i) => (
          <div key={i} className="product-card product-card--skeleton" />
        ))}
      </div>
    </>
  )
}

/** Products found by the chat agent's catalogue search, rendered with the standard ProductCard. */
function ChatSearchResultsView() {
  const { results, clearResults } = useChatSearch()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const sort = (params.get('sort') ?? 'relevance') as SortKey
  const sorted = useMemo(() => sortProducts(results?.products ?? [], sort), [results, sort])
  if (!results) return null

  const filters = Object.entries(results.filters)
  const corrections = Object.entries(results.corrections ?? {})
  return (
    <>
      <section className="page-head page-head--shop">
        <div className="container">
          <p className="eyebrow">Chat search results</p>
          <h1>“{results.shopper_message}”</h1>
          <p className="lead">
            {results.total_matches === 0
              ? 'Our assistant searched the catalogue but found no matching products.'
              : `Our assistant found ${results.total_matches} matching product${results.total_matches === 1 ? '' : 's'} in the catalogue.`}
          </p>
        </div>
      </section>

      <section className="section container">
        <div className="chat-results__bar">
          <div className="chat-results__meta">
            <span className="chat-results__badge">From chat</span>
            {results.query && (
              <span className="tag">
                Search: <strong>{results.query}</strong>
              </span>
            )}
            {filters.map(([key, value]) => (
              <span key={key} className="tag">
                {FILTER_LABELS[key] ?? key}: <strong>{key === 'max_price' ? `$${value}` : String(value)}</strong>
              </span>
            ))}
            {results.match_mode === 'partial' && (
              <span className="tag tag--warn">Partial matches: not every word matched</span>
            )}
          </div>
          <div className="chat-results__actions">
            {results.products.length > 1 && (
              <select
                className="input select input--sm"
                value={sort}
                onChange={(e) => {
                  const next = new URLSearchParams(params)
                  if (e.target.value === 'relevance') next.delete('sort')
                  else next.set('sort', e.target.value)
                  setParams(next, { replace: true })
                }}
                aria-label="Sort chat results"
              >
                <option value="relevance">Best match</option>
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
            <Link to="/products" className="btn btn--primary btn--sm">
              Show all products
            </Link>
            <button
              type="button"
              className="btn btn--outline btn--sm"
              onClick={() => {
                clearResults()
                navigate('/products')
              }}
            >
              Clear chat results
            </button>
          </div>
        </div>

        {corrections.length > 0 && (
          <p className="filter-note" role="status">
            Showing results for{' '}
            {corrections.map(([typed, fixed], i) => (
              <span key={typed}>
                {i > 0 && ', '}
                <strong>{fixed}</strong> (you typed “{typed}”)
              </span>
            ))}
            .
          </p>
        )}

        {results.products.length === 0 ? (
          <p className="notice">No products match that search. Try asking the assistant for something broader.</p>
        ) : (
          <>
            <p className="result-count">
              {results.products.length} of {results.total_matches} products
            </p>
            <div className="grid">
              {sorted.map((p) => (
                <ProductCard key={p.product_id} product={p} />
              ))}
            </div>
          </>
        )}
      </section>
    </>
  )
}

function CatalogueView() {
  const { products, loading, error, retry } = useProducts()
  const [params, setParams] = useSearchParams()
  const { results: chatResults } = useChatSearch()

  // useSearchParams returns a stable object per URL, so these recompute only when the URL changes.
  const filters = useMemo(() => readFilters(params), [params])
  const sort = (params.get('sort') ?? 'name') as SortKey
  const collection = findCollection(params.get('collection'))

  function update(key: string, value: string, defaultValue = '') {
    const next = new URLSearchParams(params)
    if (value === defaultValue) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  function clearAll() {
    // Keep the sort order and any collection the shopper came from; drop every filter.
    const next = new URLSearchParams()
    for (const key of ['sort', 'collection']) {
      const value = params.get(key)
      if (value) next.set(key, value)
    }
    setParams(next, { replace: true })
  }

  const base = useMemo(
    () => (collection ? products.filter((p) => collection.matches(p)) : products),
    [products, collection],
  )
  const visible = useMemo(
    () => sortProducts(base.filter((p) => matchesFilters(p, filters)), sort),
    [base, filters, sort],
  )
  // Option counts reflect the *other* active filters, so shoppers never pick a dead end.
  const categoryCounts = useMemo(
    () => countBy(base, filters, 'category', (p) => [categoryOf(p.garment_type)]),
    [base, filters],
  )
  const colorCounts = useMemo(
    () => countBy(base, filters, 'color', (p) => colorFamilies(p.colors)),
    [base, filters],
  )
  const priceCounts = useMemo(
    () => countBy(base, filters, 'price', (p) => PRICE_BANDS.filter((b) => b.test(p.price)).map((b) => b.key)),
    [base, filters],
  )
  const sizeCounts = useMemo(
    () => countBy(base, filters, 'size', (p) => p.in_stock_sizes),
    [base, filters],
  )
  const colorOptions = Object.keys(colorCounts).sort()
  const active = activeFilterCount(filters)
  const categoryTotal = Object.values(categoryCounts).reduce((a, b) => a + b, 0)
  const ready = !loading && !error // only show counts / disable options once products have loaded

  const activePills = [
    filters.query.trim() && { key: 'q', label: `“${filters.query.trim()}”` },
    filters.category !== 'all' && {
      key: 'category',
      label: CATEGORIES.find((c) => c.key === filters.category)?.label ?? filters.category,
    },
    filters.price && { key: 'price', label: PRICE_BANDS.find((b) => b.key === filters.price)?.label ?? filters.price },
    filters.color && { key: 'color', label: filters.color },
    filters.size && { key: 'size', label: `Size ${filters.size} in stock` },
  ].filter(Boolean) as { key: string; label: string }[]

  return (
    <>
      <section className="page-head page-head--shop">
        <div className="container page-head__inner">
          <div>
            <p className="eyebrow">{collection ? 'Collection' : 'The Campus Customs shop'}</p>
            <h1>{collection ? collection.title : 'Shop Yale apparel'}</h1>
            <p className="lead">
              {collection
                ? collection.blurb
                : 'Hoodies, crewnecks, tees, and layers, all officially licensed and ready for campus.'}
            </p>
          </div>
          {ready && base.length > 0 && (
            // Facts computed from the loaded catalogue, not hardcoded.
            <ul className="shop-facts" aria-label="About this catalogue">
              <li>
                <strong>{base.length}</strong> styles
              </li>
              <li>
                From <strong>{formatPrice(Math.min(...base.map((p) => p.price)))}</strong>
              </li>
              <li>
                <span className="shop-facts__dot" aria-hidden="true" /> Live stock by size
              </li>
            </ul>
          )}
        </div>
      </section>

      <section className="section container">
        <div className="toolbar">
          <div className="chips" role="tablist" aria-label="Filter by product type">
            {CATEGORIES.map((c) => {
              const count = c.key === 'all' ? categoryTotal : (categoryCounts[c.key] ?? 0)
              return (
                <button
                  key={c.key}
                  type="button"
                  role="tab"
                  aria-selected={filters.category === c.key}
                  className={`chip ${filters.category === c.key ? 'is-active' : ''}`}
                  onClick={() => update('category', c.key, 'all')}
                  disabled={ready && count === 0 && filters.category !== c.key}
                >
                  {c.label}
                  {ready && <span className="chip__count">{count}</span>}
                </button>
              )
            })}
          </div>
          <input
            type="search"
            className="input toolbar__search"
            placeholder="Search colors, schools, sports…"
            value={filters.query}
            onChange={(e) => update('q', e.target.value)}
            aria-label="Search products"
          />
        </div>

        <div className="filters" aria-label="More filters">
          <label className="filter">
            <span>Price</span>
            <select className="input select" value={filters.price} onChange={(e) => update('price', e.target.value)}>
              <option value="">Any price</option>
              {PRICE_BANDS.map((b) => (
                <option key={b.key} value={b.key} disabled={!priceCounts[b.key] && filters.price !== b.key}>
                  {b.label} ({priceCounts[b.key] ?? 0})
                </option>
              ))}
            </select>
          </label>
          <label className="filter">
            <span>Color</span>
            <select className="input select" value={filters.color} onChange={(e) => update('color', e.target.value)}>
              <option value="">Any color</option>
              {colorOptions.map((c) => (
                <option key={c} value={c}>
                  {c} ({colorCounts[c]})
                </option>
              ))}
            </select>
          </label>
          <label className="filter">
            <span>Size in stock</span>
            <select className="input select" value={filters.size} onChange={(e) => update('size', e.target.value)}>
              <option value="">Any size</option>
              {SIZES.map((s) => (
                <option key={s} value={s} disabled={!sizeCounts[s] && filters.size !== s}>
                  {s} ({sizeCounts[s] ?? 0})
                </option>
              ))}
            </select>
          </label>
          <label className="filter">
            <span>Sort by</span>
            <select
              className="input select"
              value={sort}
              onChange={(e) => update('sort', e.target.value, 'name')}
              aria-label="Sort products"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {activePills.length > 0 && (
          <div className="active-filters" aria-label="Active filters">
            {activePills.map((f) => (
              <button
                key={f.key}
                type="button"
                className="active-filter"
                onClick={() => update(f.key, f.key === 'category' ? 'all' : '', f.key === 'category' ? 'all' : '')}
                aria-label={`Remove filter ${f.label}`}
              >
                {f.label} <span aria-hidden="true">×</span>
              </button>
            ))}
            {active > 1 && (
              <button type="button" className="link-button" onClick={clearAll}>
                Clear all filters
              </button>
            )}
          </div>
        )}

        {chatResults && (
          <p className="filter-note">
            You have results from a chat search ·{' '}
            <Link to={`/products?${CHAT_VIEW_PARAM}=${CHAT_VIEW_VALUE}`}>View chat results</Link>
          </p>
        )}

        {collection && (
          <p className="filter-note">
            Showing the <strong>{collection.title}</strong> collection ·{' '}
            <Link to="/products">Clear</Link>
          </p>
        )}

        {loading ? (
          <SkeletonGrid count={8} label="Loading the catalogue…" />
        ) : error ? (
          <ErrorState error={error} title="We couldn’t load products" onRetry={retry} />
        ) : (
          <>
            <p className="result-count" role="status" aria-live="polite">
              Showing {visible.length} of {base.length} products
            </p>
            {visible.length === 0 ? (
              <div className="empty-results">
                <p>No products match these filters.</p>
                <button type="button" className="btn btn--primary btn--sm" onClick={clearAll}>
                  Clear filters
                </button>
              </div>
            ) : (
              <div className="grid">
                {visible.map((p) => (
                  <ProductCard key={p.product_id} product={p} />
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </>
  )
}
