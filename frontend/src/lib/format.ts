const priceFormatter = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatPrice(price: number): string {
  return priceFormatter.format(price)
}

// garment_type values in the database are inconsistent (22 variants), so group them by keyword.
export const CATEGORIES = [
  { key: 'all', label: 'All' },
  { key: 'hoodie', label: 'Hoodies' },
  { key: 'crewneck', label: 'Crewnecks' },
  { key: 'tee', label: 'T-Shirts' },
  { key: 'quarter-zip', label: 'Quarter-Zips' },
  { key: 'outerwear', label: 'Jackets & Fleece' },
] as const

export type CategoryKey = (typeof CATEGORIES)[number]['key']

export function categoryOf(garmentType: string): CategoryKey | 'other' {
  const g = garmentType.toLowerCase()
  if (g.includes('quarter-zip')) return 'quarter-zip'
  if (g.includes('jacket') || g.includes('fleece')) return 'outerwear'
  if (g.includes('hood')) return 'hoodie'
  // Check sweatshirts before tees: "sweatshirt" contains "shirt".
  if (g.includes('crewneck') || g.includes('sweatshirt') || g.includes('mockneck')) return 'crewneck'
  if (g.includes('shirt')) return 'tee'
  return 'other'
}

export function stockLabel(quantity: number): { text: string; tone: 'out' | 'low' | 'ok' } {
  if (quantity <= 0) return { text: 'Sold out', tone: 'out' }
  if (quantity <= 5) return { text: `Only ${quantity} left`, tone: 'low' }
  return { text: `${quantity} in stock`, tone: 'ok' }
}

// ---------- Card-level stock status (from real inventory: total_stock + in_stock_sizes) ----------

export const LOW_STOCK_TOTAL = 10 // 10 or fewer units left across all sizes
export const FEW_SIZES = 3 // 3 or fewer sizes still in stock (of XS–XXL)
const ALL_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']

export type CardStatus = { tone: 'out' | 'low' | 'few' | 'ok'; label: string; detail: string }

export function cardStatus(totalStock: number, inStockSizes: string[] = []): CardStatus {
  const sizes = ALL_SIZES.filter((s) => inStockSizes.includes(s))
  const sizeText =
    sizes.length === ALL_SIZES.length ? 'All sizes XS–XXL' : sizes.length ? `Sizes ${sizes.join(' · ')}` : 'No sizes available'
  if (totalStock <= 0) return { tone: 'out', label: 'Sold out', detail: 'Currently unavailable' }
  if (totalStock <= LOW_STOCK_TOTAL) return { tone: 'low', label: `Only ${totalStock} left`, detail: sizeText }
  if (sizes.length > 0 && sizes.length <= FEW_SIZES) return { tone: 'few', label: 'Few sizes left', detail: sizeText }
  return { tone: 'ok', label: 'In stock', detail: sizeText }
}
