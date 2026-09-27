import { Link } from 'react-router-dom'
import { cardStatus, formatPrice } from '../lib/format'
import ProductImage from './ProductImage'
import type { ProductSummary } from '../types'

interface Props {
  product: ProductSummary
}

export default function ProductCard({ product }: Props) {
  // Status comes only from the product's real inventory (total_stock and in_stock_sizes).
  const status = cardStatus(product.total_stock, product.in_stock_sizes ?? [])
  return (
    <Link
      to={`/products/${product.product_id}`}
      className={`product-card ${status.tone === 'out' ? 'product-card--out' : ''}`}
      aria-label={`${product.name}, ${formatPrice(product.price)}, ${status.label}`}
    >
      <div className="product-card__media">
        <ProductImage src={product.image_url} alt={product.name} loading="lazy" />
        {status.tone === 'out' && <span className="badge badge--out">Sold out</span>}
        <span className="product-card__cta" aria-hidden="true">
          View details →
        </span>
      </div>
      <div className="product-card__body">
        <p className="product-card__type">{product.garment_type}</p>
        <h3 className="product-card__name">{product.name}</h3>
        <p className="product-card__desc">{product.description}</p>
        <div className="product-card__footer">
          <p className="product-card__price">{formatPrice(product.price)}</p>
          <span className={`stock-pill stock-pill--${status.tone}`}>{status.label}</span>
        </div>
        <p className="product-card__sizes">{status.detail}</p>
      </div>
    </Link>
  )
}
